# Copyright 2009-2020 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'BuilderInteractor',
    'extract_vitals_from_db',
    'shut_down_default_threadpool',
    ]

from collections import namedtuple
import logging
import os.path
import sys
import tempfile
import traceback

from requests import Session
from requests_toolbelt.downloadutils import stream
import six
from six.moves.urllib.parse import urlparse
import transaction
from twisted.internet import (
    defer,
    reactor as default_reactor,
    threads,
    )
from twisted.python.threadpool import ThreadPool
from twisted.web import xmlrpc
from zope.security.proxy import (
    isinstance as zope_isinstance,
    removeSecurityProxy,
    )

from lp.buildmaster.enums import (
    BuilderCleanStatus,
    BuilderResetProtocol,
    )
from lp.buildmaster.interfaces.builder import (
    BuildDaemonError,
    BuildDaemonIsolationError,
    CannotFetchFile,
    CannotResumeHost,
    )
from lp.buildmaster.interfaces.buildfarmjobbehaviour import (
    IBuildFarmJobBehaviour,
    )
from lp.services.config import config
from lp.services.twistedsupport import cancel_on_timeout
from lp.services.twistedsupport.processmonitor import ProcessWithTimeout
from lp.services.webapp import urlappend


class QuietQueryFactory(xmlrpc._QueryFactory):
    """XMLRPC client factory that doesn't splatter the log with junk."""
    noisy = False


_default_threadpool = None
_default_threadpool_shutdown = None


def default_threadpool(reactor=None):
    global _default_threadpool, _default_threadpool_shutdown
    if reactor is None:
        reactor = default_reactor
    if _default_threadpool is None:
        _default_threadpool = ThreadPool(
            maxthreads=config.builddmaster.download_connections,
            name=six.ensure_str('buildd-manager-requests'))
        _default_threadpool.start()
        shutdown_id = reactor.addSystemEventTrigger(
            'during', 'shutdown', _default_threadpool.stop)
        _default_threadpool_shutdown = (reactor, shutdown_id)
    return _default_threadpool


def shut_down_default_threadpool():
    """Shut down the default threadpool.  Used in test cleanup."""
    global _default_threadpool, _default_threadpool_shutdown
    if _default_threadpool is not None:
        _default_threadpool.stop()
        _default_threadpool = None
    if _default_threadpool_shutdown is not None:
        reactor, shutdown_id = _default_threadpool_shutdown
        reactor.removeSystemEventTrigger(shutdown_id)
        _default_threadpool_shutdown = None


class BuilderSlave(object):
    """Add in a few useful methods for the XMLRPC slave.

    :ivar url: The URL of the actual builder. The XML-RPC resource and
        the filecache live beneath this.
    """

    # WARNING: If you change the API for this, you should also change the APIs
    # of the mocks in soyuzbuilderhelpers to match. Otherwise, you will have
    # many false positives in your test run and will most likely break
    # production.

    def __init__(self, proxy, builder_url, vm_host, timeout, reactor,
                 threadpool):
        """Initialize a BuilderSlave.

        :param proxy: An XML-RPC proxy, implementing 'callRemote'. It must
            support passing and returning None objects.
        :param builder_url: The URL of the builder.
        :param vm_host: The VM host to use when resuming.
        """
        self.url = builder_url
        self._vm_host = vm_host
        self._file_cache_url = urlappend(builder_url, 'filecache')
        self._server = proxy
        self.timeout = timeout
        if reactor is None:
            reactor = default_reactor
        self.reactor = reactor
        if threadpool is None:
            threadpool = default_threadpool(reactor=reactor)
        self.threadpool = threadpool

    @classmethod
    def makeBuilderSlave(cls, builder_url, vm_host, timeout, reactor=None,
                         proxy=None, threadpool=None):
        """Create and return a `BuilderSlave`.

        :param builder_url: The URL of the slave buildd machine,
            e.g. http://localhost:8221
        :param vm_host: If the slave is virtual, specify its host machine
            here.
        :param reactor: Used by tests to override the Twisted reactor.
        :param proxy: Used By tests to override the xmlrpc.Proxy.
        :param threadpool: Used by tests to override the ThreadPool.
        """
        rpc_url = urlappend(builder_url.encode('utf-8'), 'rpc')
        if proxy is None:
            server_proxy = xmlrpc.Proxy(
                rpc_url, allowNone=True, connectTimeout=timeout)
            server_proxy.queryFactory = QuietQueryFactory
        else:
            server_proxy = proxy
        return cls(
            server_proxy, builder_url, vm_host, timeout, reactor, threadpool)

    def _with_timeout(self, d, timeout=None):
        return cancel_on_timeout(d, timeout or self.timeout, self.reactor)

    def abort(self):
        """Abort the current build."""
        return self._with_timeout(self._server.callRemote('abort'))

    def clean(self):
        """Clean up the waiting files and reset the slave's internal state."""
        return self._with_timeout(self._server.callRemote('clean'))

    def echo(self, *args):
        """Echo the arguments back."""
        return self._with_timeout(self._server.callRemote('echo', *args))

    def info(self):
        """Return the protocol version and the builder methods supported."""
        return self._with_timeout(self._server.callRemote('info'))

    def status(self):
        """Return the status of the build daemon."""
        return self._with_timeout(self._server.callRemote('status'))

    def ensurepresent(self, sha1sum, url, username, password):
        """Attempt to ensure the given file is present."""
        # XXX: Nothing external calls this. Make it private.
        # Use a larger timeout than other calls, as this synchronously
        # downloads large files.
        return self._with_timeout(
            self._server.callRemote(
                'ensurepresent', sha1sum, url, username, password),
            self.timeout * 5)

    def getURL(self, sha1):
        """Get the URL for a file on the builder with a given SHA-1."""
        return urlappend(self._file_cache_url, sha1).encode('utf8')

    @defer.inlineCallbacks
    def getFile(self, sha_sum, file_to_write, logger=None):
        """Fetch a file from the builder.

        :param sha_sum: The sha of the file (which is also its name on the
            builder)
        :param file_to_write: A file name or file-like object to write
            the file to
        :param logger: An optional logger.
        :return: A Deferred that calls back when the download is done, or
            errback with the error string.
        """
        file_url = self.getURL(sha_sum)

        def download():
            session = Session()
            session.trust_env = False
            response = session.get(file_url, timeout=self.timeout, stream=True)
            response.raise_for_status()
            if isinstance(file_to_write, six.string_types):
                f = tempfile.NamedTemporaryFile(
                    mode="wb", prefix=os.path.basename(file_to_write) + "_",
                    dir=os.path.dirname(file_to_write), delete=False)
            else:
                f = file_to_write
            try:
                stream.stream_response_to_file(response, path=f)
            except Exception:
                f.close()
                os.unlink(f.name)
                raise
            else:
                f.close()
                if isinstance(file_to_write, six.string_types):
                    os.rename(f.name, file_to_write)

        try:
            session = Session()
            session.trust_env = False
            yield threads.deferToThreadPool(
                self.reactor, self.threadpool, download)
            if logger is not None:
                logger.info("Grabbed %s" % file_url)
        except Exception as e:
            if logger is not None:
                logger.info("Failed to grab %s: %s\n%s" % (
                    file_url, str(e),
                    " ".join(traceback.format_exception(*sys.exc_info()))))
            raise

    def getFiles(self, files, logger=None):
        """Fetch many files from the builder.

        :param files: A sequence of pairs of the builder file name to
            retrieve and the file name or file object to write the file to.
        :param logger: An optional logger.

        :return: A DeferredList that calls back when the download is done.
        """
        dl = defer.gatherResults([
            self.getFile(builder_file, local_file, logger=logger)
            for builder_file, local_file in files])
        return dl

    def resume(self, clock=None):
        """Resume the builder in an asynchronous fashion.

        We use the builddmaster configuration 'socket_timeout' as
        the process timeout.

        :param clock: An optional twisted.internet.task.Clock to override
                      the default clock.  For use in tests.

        :return: a Deferred that returns a
            (stdout, stderr, subprocess exitcode) triple
        """
        url_components = urlparse(self.url)
        buildd_name = url_components.hostname.split('.')[0]
        resume_command = config.builddmaster.vm_resume_command % {
            'vm_host': self._vm_host,
            'buildd_name': buildd_name}
        # Twisted API requires string but the configuration provides unicode.
        resume_argv = [
            term.encode('utf-8') for term in resume_command.split()]
        d = defer.Deferred()
        p = ProcessWithTimeout(d, self.timeout, clock=clock)
        p.spawnProcess(resume_argv[0], tuple(resume_argv))
        return d

    @defer.inlineCallbacks
    def sendFileToSlave(self, sha1, url, username="", password="",
                        logger=None):
        """Helper to send the file at 'url' with 'sha1' to this builder."""
        if logger is not None:
            logger.info(
                "Asking %s to ensure it has %s (%s%s)" % (
                    self.url, sha1, url, ' with auth' if username else ''))
        present, info = yield self.ensurepresent(sha1, url, username, password)
        if not present:
            raise CannotFetchFile(url, info)

    def build(self, buildid, builder_type, chroot_sha1, filemap, args):
        """Build a thing on this build slave.

        :param buildid: A string identifying this build.
        :param builder_type: The type of builder needed.
        :param chroot_sha1: XXX
        :param filemap: A dictionary mapping from paths to SHA-1 hashes of
            the file contents.
        :param args: A dictionary of extra arguments. The contents depend on
            the build job type.
        """
        return self._with_timeout(self._server.callRemote(
            'build', buildid, builder_type, chroot_sha1, filemap, args))


BuilderVitals = namedtuple(
    'BuilderVitals',
    ('name', 'url', 'virtualized', 'vm_host', 'vm_reset_protocol',
     'builderok', 'manual', 'build_queue', 'version', 'clean_status'))

_BQ_UNSPECIFIED = object()


def extract_vitals_from_db(builder, build_queue=_BQ_UNSPECIFIED):
    if build_queue == _BQ_UNSPECIFIED:
        build_queue = builder.currentjob
    return BuilderVitals(
        builder.name, builder.url, builder.virtualized, builder.vm_host,
        builder.vm_reset_protocol, builder.builderok, builder.manual,
        build_queue, builder.version, builder.clean_status)


class BuilderInteractor(object):

    @staticmethod
    def makeSlaveFromVitals(vitals):
        if vitals.virtualized:
            timeout = config.builddmaster.virtualized_socket_timeout
        else:
            timeout = config.builddmaster.socket_timeout
        return BuilderSlave.makeBuilderSlave(
            vitals.url, vitals.vm_host, timeout)

    @staticmethod
    def getBuildBehaviour(queue_item, builder, slave):
        if queue_item is None:
            return None
        behaviour = IBuildFarmJobBehaviour(queue_item.specific_build)
        behaviour.setBuilder(builder, slave)
        return behaviour

    @classmethod
    def resumeSlaveHost(cls, vitals, slave):
        """Resume the slave host to a known good condition.

        Issues 'builddmaster.vm_resume_command' specified in the configuration
        to resume the slave.

        :raises: CannotResumeHost: if builder is not virtual or if the
            configuration command has failed.

        :return: A Deferred that fires when the resume operation finishes,
            whose value is a (stdout, stderr) tuple for success, or a Failure
            whose value is a CannotResumeHost exception.
        """
        if not vitals.virtualized:
            return defer.fail(CannotResumeHost('Builder is not virtualized.'))

        if not vitals.vm_host:
            return defer.fail(CannotResumeHost('Undefined vm_host.'))

        logger = cls._getSlaveScannerLogger()
        logger.info("Resuming %s (%s)" % (vitals.name, vitals.url))

        d = slave.resume()

        def got_resume_ok(args):
            stdout, stderr, returncode = args
            return stdout, stderr

        def got_resume_bad(failure):
            stdout, stderr, code = failure.value
            raise CannotResumeHost(
                "Resuming failed:\nOUT:\n%s\nERR:\n%s\n" % (stdout, stderr))

        return d.addCallback(got_resume_ok).addErrback(got_resume_bad)

    @classmethod
    @defer.inlineCallbacks
    def cleanSlave(cls, vitals, slave, builder_factory):
        """Prepare a slave for a new build.

        :return: A Deferred that fires when this stage of the resume
            operations finishes. If the value is True, the slave is now clean.
            If it's False, the clean is still in progress and this must be
            called again later.
        """
        if vitals.virtualized:
            if vitals.vm_reset_protocol == BuilderResetProtocol.PROTO_1_1:
                # In protocol 1.1 the reset trigger is synchronous, so
                # once resumeSlaveHost returns the slave should be
                # running.
                builder_factory[vitals.name].setCleanStatus(
                    BuilderCleanStatus.CLEANING)
                transaction.commit()
                yield cls.resumeSlaveHost(vitals, slave)
                # We ping the resumed slave before we try to do anything
                # useful with it. This is to ensure it's accepting
                # packets from the outside world, because testing has
                # shown that the first packet will randomly fail for no
                # apparent reason.  This could be a quirk of the Xen
                # guest, we're not sure. See bug 586359.
                yield slave.echo("ping")
                defer.returnValue(True)
            elif vitals.vm_reset_protocol == BuilderResetProtocol.PROTO_2_0:
                # In protocol 2.0 the reset trigger is asynchronous.
                # If the trigger succeeds we'll leave the slave in
                # CLEANING, and the non-LP slave management code will
                # set it back to CLEAN later using the webservice.
                if vitals.clean_status == BuilderCleanStatus.DIRTY:
                    yield cls.resumeSlaveHost(vitals, slave)
                    builder_factory[vitals.name].setCleanStatus(
                        BuilderCleanStatus.CLEANING)
                    transaction.commit()
                    logger = cls._getSlaveScannerLogger()
                    logger.info("%s is being cleaned.", vitals.name)
                defer.returnValue(False)
            raise CannotResumeHost(
                "Invalid vm_reset_protocol: %r" % vitals.vm_reset_protocol)
        else:
            slave_status = yield slave.status()
            status = slave_status.get('builder_status', None)
            if status == 'BuilderStatus.IDLE':
                # This is as clean as we can get it.
                defer.returnValue(True)
            elif status == 'BuilderStatus.BUILDING':
                # Asynchronously abort() the slave and wait until WAITING.
                yield slave.abort()
                defer.returnValue(False)
            elif status == 'BuilderStatus.ABORTING':
                # Wait it out until WAITING.
                defer.returnValue(False)
            elif status == 'BuilderStatus.WAITING':
                # Just a synchronous clean() call and we'll be idle.
                yield slave.clean()
                defer.returnValue(True)
            raise BuildDaemonError(
                "Invalid status during clean: %r" % status)

    @classmethod
    @defer.inlineCallbacks
    def _startBuild(cls, build_queue_item, vitals, builder, slave, behaviour,
                    logger):
        """Start a build on this builder.

        :param build_queue_item: A BuildQueueItem to build.
        :param logger: A logger to be used to log diagnostic information.

        :return: A Deferred that fires after the dispatch has completed whose
            value is None, or a Failure that contains an exception
            explaining what went wrong.
        """
        behaviour.verifyBuildRequest(logger)

        # Set the build behaviour depending on the provided build queue item.
        if not builder.builderok:
            raise BuildDaemonIsolationError(
                "Attempted to start a build on a known-bad builder.")

        if builder.clean_status != BuilderCleanStatus.CLEAN:
            raise BuildDaemonIsolationError(
                "Attempted to start build on a dirty slave.")

        builder.setCleanStatus(BuilderCleanStatus.DIRTY)
        transaction.commit()

        yield behaviour.dispatchBuildToSlave(logger)

    @classmethod
    @defer.inlineCallbacks
    def findAndStartJob(cls, vitals, builder, slave):
        """Find a job to run and send it to the buildd slave.

        :return: A Deferred whose value is the `IBuildQueue` instance
            found or None if no job was found.
        """
        logger = cls._getSlaveScannerLogger()
        # XXX This method should be removed in favour of two separately
        # called methods that find and dispatch the job.  It will
        # require a lot of test fixing.
        candidate = builder.acquireBuildCandidate()
        if candidate is None:
            logger.debug("No build candidates available for builder.")
            defer.returnValue(None)

        new_behaviour = cls.getBuildBehaviour(candidate, builder, slave)
        needed_bfjb = type(removeSecurityProxy(
            IBuildFarmJobBehaviour(candidate.specific_build)))
        if not zope_isinstance(new_behaviour, needed_bfjb):
            raise AssertionError(
                "Inappropriate IBuildFarmJobBehaviour: %r is not a %r" %
                (new_behaviour, needed_bfjb))
        yield cls._startBuild(
            candidate, vitals, builder, slave, new_behaviour, logger)
        defer.returnValue(candidate)

    @staticmethod
    def extractBuildStatus(slave_status):
        """Read build status name.

        :param slave_status: build status dict from BuilderSlave.status.
        :return: the unqualified status name, e.g. "OK".
        """
        status_string = slave_status['build_status']
        lead_string = 'BuildStatus.'
        assert status_string.startswith(lead_string), (
            "Malformed status string: '%s'" % status_string)
        return status_string[len(lead_string):]

    @classmethod
    @defer.inlineCallbacks
    def updateBuild(cls, vitals, slave, slave_status, builder_factory,
                    behaviour_factory):
        """Verify the current build job status.

        Perform the required actions for each state.

        :return: A Deferred that fires when the slave dialog is finished.
        """
        # IDLE is deliberately not handled here, because it should be
        # impossible to get past the cookie check unless the slave
        # matches the DB, and this method isn't called unless the DB
        # says there's a job.
        builder_status = slave_status['builder_status']
        if builder_status in (
                'BuilderStatus.BUILDING', 'BuilderStatus.ABORTING'):
            vitals.build_queue.collectStatus(slave_status)
            vitals.build_queue.specific_build.updateStatus(
                vitals.build_queue.specific_build.status,
                slave_status=slave_status)
            transaction.commit()
        elif builder_status == 'BuilderStatus.WAITING':
            # Build has finished. Delegate handling to the build itself.
            builder = builder_factory[vitals.name]
            behaviour = behaviour_factory(vitals.build_queue, builder, slave)
            yield behaviour.handleStatus(
                vitals.build_queue, cls.extractBuildStatus(slave_status),
                slave_status)
        else:
            raise AssertionError("Unknown status %s" % builder_status)

    @staticmethod
    def _getSlaveScannerLogger():
        """Return the logger instance from buildd-slave-scanner.py."""
        # XXX cprov 20071120: Ideally the Launchpad logging system
        # should be able to configure the root-logger instead of creating
        # a new object, then the logger lookups won't require the specific
        # name argument anymore. See bug 164203.
        logger = logging.getLogger('slave-scanner')
        return logger
