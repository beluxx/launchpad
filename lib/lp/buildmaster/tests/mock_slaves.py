# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Mock Build objects for tests soyuz buildd-system."""

__metaclass__ = type

__all__ = [
    'AbortedSlave',
    'AbortingSlave',
    'BrokenSlave',
    'BuildingSlave',
    'CorruptBehavior',
    'DeadProxy',
    'LostBuildingBrokenSlave',
    'make_publisher',
    'MockBuilder',
    'OkSlave',
    'SlaveTestHelpers',
    'TrivialBehavior',
    'WaitingSlave',
    ]

import fixtures
import os

from StringIO import StringIO
import xmlrpclib

from testtools.content import Content
from testtools.content_type import UTF8_TEXT

from twisted.internet import defer
from twisted.web import xmlrpc

from canonical.buildd.tests.harness import BuilddSlaveTestSetup

from lp.buildmaster.interfaces.builder import (
    CannotFetchFile,
    CorruptBuildCookie,
    )
from lp.buildmaster.model.builder import (
    BuilderSlave,
    rescueBuilderIfLost,
    updateBuilderStatus,
    )
from lp.soyuz.model.binarypackagebuildbehavior import (
    BinaryPackageBuildBehavior,
    )
from lp.testing.sampledata import I386_ARCHITECTURE_NAME


def make_publisher():
    """Make a Soyuz test publisher."""
    # Avoid circular imports.
    from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
    return SoyuzTestPublisher()


class MockBuilder:
    """Emulates a IBuilder class."""

    def __init__(self, name, slave, behavior=None):
        if behavior is None:
            self.current_build_behavior = BinaryPackageBuildBehavior(None)
        else:
            self.current_build_behavior = behavior

        self.slave = slave
        self.builderok = True
        self.manual = False
        self.url = 'http://fake:0000'
        slave.url = self.url
        self.name = name
        self.virtualized = True

    def failBuilder(self, reason):
        self.builderok = False
        self.failnotes = reason

    def slaveStatusSentence(self):
        return self.slave.status()

    def verifySlaveBuildCookie(self, slave_build_id):
        return self.current_build_behavior.verifySlaveBuildCookie(
            slave_build_id)

    def cleanSlave(self):
        return self.slave.clean()

    def requestAbort(self):
        return self.slave.abort()

    def resumeSlave(self, logger):
        return ('out', 'err')

    def checkSlaveAlive(self):
        pass

    def rescueIfLost(self, logger=None):
        return rescueBuilderIfLost(self, logger)

    def updateStatus(self, logger=None):
        return defer.maybeDeferred(updateBuilderStatus, self, logger)


# XXX: It would be *really* nice to run some set of tests against the real
# BuilderSlave and this one to prevent interface skew.
class OkSlave:
    """An idle mock slave that prints information about itself.

    The architecture tag can be customised during initialisation."""

    def __init__(self, arch_tag=I386_ARCHITECTURE_NAME):
        self.call_log = []
        self.arch_tag = arch_tag

    def status(self):
        return defer.succeed(('BuilderStatus.IDLE', ''))

    def ensurepresent(self, sha1, url, user=None, password=None):
        self.call_log.append(('ensurepresent', url, user, password))
        return defer.succeed((True, None))

    def build(self, buildid, buildtype, chroot, filemap, args):
        self.call_log.append(
            ('build', buildid, buildtype, chroot, filemap.keys(), args))
        info = 'OkSlave BUILDING'
        return defer.succeed(('BuildStatus.Building', info))

    def echo(self, *args):
        self.call_log.append(('echo',) + args)
        return defer.succeed(args)

    def clean(self):
        self.call_log.append('clean')
        return defer.succeed(None)

    def abort(self):
        self.call_log.append('abort')
        return defer.succeed(None)

    def info(self):
        self.call_log.append('info')
        return defer.succeed(('1.0', self.arch_tag, 'debian'))

    def resume(self):
        self.call_log.append('resume')
        return defer.succeed(("", "", 0))

    def sendFileToSlave(self, sha1, url, username="", password=""):
        d = self.ensurepresent(sha1, url, username, password)
        def check_present((present, info)):
            if not present:
                raise CannotFetchFile(url, info)
        return d.addCallback(check_present)

    def cacheFile(self, logger, libraryfilealias):
        return self.sendFileToSlave(
            libraryfilealias.content.sha1, libraryfilealias.http_url)


class BuildingSlave(OkSlave):
    """A mock slave that looks like it's currently building."""

    def __init__(self, build_id='1-1'):
        super(BuildingSlave, self).__init__()
        self.build_id = build_id

    def status(self):
        self.call_log.append('status')
        buildlog = xmlrpclib.Binary("This is a build log")
        return defer.succeed(
            ('BuilderStatus.BUILDING', self.build_id, buildlog))

    def getFile(self, sum):
        # XXX: This needs to be updated to return a Deferred.
        self.call_log.append('getFile')
        if sum == "buildlog":
            s = StringIO("This is a build log")
            s.headers = {'content-length': 19}
            return s


class WaitingSlave(OkSlave):
    """A mock slave that looks like it's currently waiting."""

    def __init__(self, state='BuildStatus.OK', dependencies=None,
                 build_id='1-1', filemap=None):
        super(WaitingSlave, self).__init__()
        self.state = state
        self.dependencies = dependencies
        self.build_id = build_id
        if filemap is None:
            self.filemap = {}
        else:
            self.filemap = filemap

        # By default, the slave only has a buildlog, but callsites
        # can update this list as needed.
        self.valid_file_hashes = ['buildlog']

    def status(self):
        self.call_log.append('status')
        return defer.succeed((
            'BuilderStatus.WAITING', self.state, self.build_id, self.filemap,
            self.dependencies))

    def getFile(self, hash):
        # XXX: This needs to be updated to return a Deferred.
        self.call_log.append('getFile')
        if hash in self.valid_file_hashes:
            content = "This is a %s" % hash
            s = StringIO(content)
            s.headers = {'content-length': len(content)}
            return s


class AbortingSlave(OkSlave):
    """A mock slave that looks like it's in the process of aborting."""

    def status(self):
        self.call_log.append('status')
        return defer.succeed(('BuilderStatus.ABORTING', '1-1'))


class AbortedSlave(OkSlave):
    """A mock slave that looks like it's aborted."""

    def clean(self):
        self.call_log.append('status')
        return defer.succeed(None)

    def status(self):
        self.call_log.append('clean')
        return defer.succeed(('BuilderStatus.ABORTED', '1-1'))


class LostBuildingBrokenSlave:
    """A mock slave building bogus Build/BuildQueue IDs that can't be aborted.

    When 'aborted' it raises an xmlrpclib.Fault(8002, 'Could not abort')
    """

    def __init__(self):
        self.call_log = []

    def status(self):
        self.call_log.append('status')
        return defer.succeed(('BuilderStatus.BUILDING', '1000-10000'))

    def abort(self):
        self.call_log.append('abort')
        return defer.fail(xmlrpclib.Fault(8002, "Could not abort"))


class BrokenSlave:
    """A mock slave that reports that it is broken."""

    def __init__(self):
        self.call_log = []

    def status(self):
        self.call_log.append('status')
        return defer.fail(xmlrpclib.Fault(8001, "Broken slave"))


class CorruptBehavior:

    def verifySlaveBuildCookie(self, cookie):
        raise CorruptBuildCookie("Bad value: %r" % (cookie,))


class TrivialBehavior:

    def verifySlaveBuildCookie(self, cookie):
        pass


class DeadProxy(xmlrpc.Proxy):
    """An xmlrpc.Proxy that doesn't actually send any messages.

    Used when you want to test timeouts, for example.
    """

    def callRemote(self, *args, **kwargs):
        return defer.Deferred()


class SlaveTestHelpers(fixtures.Fixture):

    # The URL for the XML-RPC service set up by `BuilddSlaveTestSetup`.
    BASE_URL = 'http://localhost:8221'
    TEST_URL = '%s/rpc/' % (BASE_URL,)

    def getServerSlave(self):
        """Set up a test build slave server.

        :return: A `BuilddSlaveTestSetup` object.
        """
        tachandler = self.useFixture(BuilddSlaveTestSetup())
        self.addDetail(
            'xmlrpc-log-file',
            Content(
                UTF8_TEXT,
                lambda: open(tachandler.logfile, 'r').readlines()))
        return tachandler

    def getClientSlave(self, reactor=None, proxy=None):
        """Return a `BuilderSlave` for use in testing.

        Points to a fixed URL that is also used by `BuilddSlaveTestSetup`.
        """
        # Twisted has a bug!  We need to monkey patch
        # QueryProtocol.handleResponse() so that it terminates the
        # connection properly, otherwise the Trial test can leave the
        # reactor dirty which fails the test.
        # See http://twistedmatrix.com/trac/ticket/2518
        saved_handleResponse = xmlrpc.QueryProtocol.handleResponse
        def _handleResponse(self, contents):
            self.factory.parseResponse(contents)
            self.transport.loseConnection()
        xmlrpc.QueryProtocol.handleResponse = _handleResponse
        def restore_handleResponse():
            xmlrpc.QueryProtocol.handleResponse = saved_handleResponse
        self.addCleanup(restore_handleResponse)

        return BuilderSlave.makeBuilderSlave(
            self.TEST_URL, 'vmhost', reactor, proxy)

    def makeCacheFile(self, tachandler, filename):
        """Make a cache file available on the remote slave.

        :param tachandler: The TacTestSetup object used to start the remote
            slave.
        :param filename: The name of the file to create in the file cache
            area.
        """
        path = os.path.join(tachandler.root, 'filecache', filename)
        fd = open(path, 'w')
        fd.write('something')
        fd.close()
        self.addCleanup(os.unlink, path)

    def triggerGoodBuild(self, slave, build_id=None):
        """Trigger a good build on 'slave'.

        :param slave: A `BuilderSlave` instance to trigger the build on.
        :param build_id: The build identifier. If not specified, defaults to
            an arbitrary string.
        :type build_id: str
        :return: The build id returned by the slave.
        """
        if build_id is None:
            build_id = 'random-build-id'
        tachandler = self.getServerSlave()
        chroot_file = 'fake-chroot'
        dsc_file = 'thing'
        self.makeCacheFile(tachandler, chroot_file)
        self.makeCacheFile(tachandler, dsc_file)
        return slave.build(
            build_id, 'debian', chroot_file, {'.dsc': dsc_file},
            {'ogrecomponent': 'main'})
