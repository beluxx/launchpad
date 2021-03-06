# Copyright 2009-2020 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test BuilderInteractor features."""

from __future__ import absolute_import, print_function, unicode_literals

__all__ = [
    'FakeBuildQueue',
    'MockBuilderFactory',
    ]

import hashlib
import os
import signal
import tempfile

from lpbuildd.builder import BuilderStatus
import six
from six.moves import xmlrpc_client
from testtools.matchers import ContainsAll
from testtools.testcase import ExpectedException
from testtools.twistedsupport import (
    assert_fails_with,
    AsynchronousDeferredRunTest,
    AsynchronousDeferredRunTestForBrokenTwisted,
    )
import treq
from twisted.internet import defer
from twisted.internet.task import Clock
from twisted.python.failure import Failure

from lp.buildmaster.enums import (
    BuilderCleanStatus,
    BuilderResetProtocol,
    BuildQueueStatus,
    BuildStatus,
    )
from lp.buildmaster.interactor import (
    BuilderInteractor,
    BuilderSlave,
    extract_vitals_from_db,
    make_download_process_pool,
    shut_down_default_process_pool,
    )
from lp.buildmaster.interfaces.builder import (
    BuildDaemonIsolationError,
    CannotFetchFile,
    CannotResumeHost,
    )
from lp.buildmaster.manager import (
    BaseBuilderFactory,
    PrefetchedBuilderFactory,
    )
from lp.buildmaster.tests.mock_slaves import (
    AbortingSlave,
    BuildingSlave,
    DeadProxy,
    LostBuildingBrokenSlave,
    MockBuilder,
    OkSlave,
    SlaveTestHelpers,
    WaitingSlave,
    )
from lp.services.config import config
from lp.services.twistedsupport.testing import TReqFixture
from lp.services.twistedsupport.treq import check_status
from lp.soyuz.enums import PackagePublishingStatus
from lp.soyuz.model.binarypackagebuildbehaviour import (
    BinaryPackageBuildBehaviour,
    )
from lp.testing import (
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import (
    LaunchpadZopelessLayer,
    ZopelessDatabaseLayer,
    )


class FakeBuildQueue:

    def __init__(self, cookie='PACKAGEBUILD-1'):
        self.build_cookie = cookie
        self.reset = FakeMethod()
        self.status = BuildQueueStatus.RUNNING


class MockBuilderFactory(BaseBuilderFactory):
    """A mock builder factory which uses a preset Builder and BuildQueue."""

    def __init__(self, builder, build_queue):
        self.updateTestData(builder, build_queue)
        self.get_call_count = 0
        self.getVitals_call_count = 0

    def update(self):
        return

    def prescanUpdate(self):
        return

    def updateTestData(self, builder, build_queue):
        self._builder = builder
        self._build_queue = build_queue

    def __getitem__(self, name):
        self.get_call_count += 1
        return self._builder

    def getVitals(self, name):
        self.getVitals_call_count += 1
        return extract_vitals_from_db(self._builder, self._build_queue)


class TestBuilderInteractor(TestCase):

    run_tests_with = AsynchronousDeferredRunTest.make_factory(timeout=30)

    def setUp(self):
        super(TestBuilderInteractor, self).setUp()
        self.addCleanup(shut_down_default_process_pool)

    def test_extractBuildStatus_baseline(self):
        # extractBuildStatus picks the name of the build status out of a
        # dict describing the slave's status.
        slave_status = {'build_status': 'BuildStatus.BUILDING'}
        self.assertEqual(
            'BUILDING', BuilderInteractor.extractBuildStatus(slave_status))

    def test_extractBuildStatus_malformed(self):
        # extractBuildStatus errors out when the status string is not
        # of the form it expects.
        slave_status = {'build_status': 'BUILDING'}
        self.assertRaises(
            AssertionError, BuilderInteractor.extractBuildStatus, slave_status)

    def resumeSlaveHost(self, builder):
        vitals = extract_vitals_from_db(builder)
        return BuilderInteractor.resumeSlaveHost(
            vitals, BuilderInteractor.makeSlaveFromVitals(vitals))

    def test_resumeSlaveHost_nonvirtual(self):
        d = self.resumeSlaveHost(MockBuilder(virtualized=False))
        return assert_fails_with(d, CannotResumeHost)

    def test_resumeSlaveHost_no_vmhost(self):
        d = self.resumeSlaveHost(MockBuilder(virtualized=False, vm_host=None))
        return assert_fails_with(d, CannotResumeHost)

    def test_resumeSlaveHost_success(self):
        reset_config = """
            [builddmaster]
            vm_resume_command: /bin/echo -n snap %(buildd_name)s %(vm_host)s
            """
        config.push('reset', reset_config)
        self.addCleanup(config.pop, 'reset')

        d = self.resumeSlaveHost(MockBuilder(
            url="http://crackle.ppa/", virtualized=True, vm_host="pop"))

        def got_resume(output):
            self.assertEqual((b'snap crackle pop', b''), output)
        return d.addCallback(got_resume)

    def test_resumeSlaveHost_command_failed(self):
        reset_fail_config = """
            [builddmaster]
            vm_resume_command: /bin/false"""
        config.push('reset fail', reset_fail_config)
        self.addCleanup(config.pop, 'reset fail')
        d = self.resumeSlaveHost(MockBuilder(virtualized=True, vm_host="pop"))
        return assert_fails_with(d, CannotResumeHost)

    def test_makeSlaveFromVitals(self):
        # Builder.slave is a BuilderSlave that points at the actual Builder.
        # The Builder is only ever used in scripts that run outside of the
        # security context.
        builder = MockBuilder(virtualized=False)
        vitals = extract_vitals_from_db(builder)
        slave = BuilderInteractor.makeSlaveFromVitals(vitals)
        self.assertEqual(builder.url, slave.url)
        self.assertEqual(10, slave.timeout)

        builder = MockBuilder(virtualized=True)
        vitals = extract_vitals_from_db(builder)
        slave = BuilderInteractor.makeSlaveFromVitals(vitals)
        self.assertEqual(5, slave.timeout)


class TestBuilderInteractorCleanSlave(TestCase):

    run_tests_with = AsynchronousDeferredRunTest

    @defer.inlineCallbacks
    def assertCleanCalls(self, builder, slave, calls, done):
        actually_done = yield BuilderInteractor.cleanSlave(
            extract_vitals_from_db(builder), slave,
            MockBuilderFactory(builder, None))
        self.assertEqual(done, actually_done)
        self.assertEqual(calls, slave.method_log)

    @defer.inlineCallbacks
    def test_virtual_1_1(self):
        # Virtual builders using protocol 1.1 get reset, and once the
        # trigger completes we're happy that it's clean.
        builder = MockBuilder(
            virtualized=True, clean_status=BuilderCleanStatus.DIRTY,
            vm_host='lol', vm_reset_protocol=BuilderResetProtocol.PROTO_1_1)
        yield self.assertCleanCalls(
            builder, OkSlave(), ['resume', 'echo'], True)

    @defer.inlineCallbacks
    def test_virtual_2_0_dirty(self):
        # Virtual builders using protocol 2.0 get reset and set to
        # CLEANING. It's then up to the non-Launchpad reset code to set
        # the builder back to CLEAN using the webservice.
        builder = MockBuilder(
            virtualized=True, clean_status=BuilderCleanStatus.DIRTY,
            vm_host='lol', vm_reset_protocol=BuilderResetProtocol.PROTO_2_0)
        yield self.assertCleanCalls(builder, OkSlave(), ['resume'], False)
        self.assertEqual(BuilderCleanStatus.CLEANING, builder.clean_status)

    @defer.inlineCallbacks
    def test_virtual_2_0_cleaning(self):
        # Virtual builders using protocol 2.0 only get touched when
        # they're DIRTY. Once they're cleaning, they're not our problem
        # until they return to CLEAN, so we ignore them.
        builder = MockBuilder(
            virtualized=True, clean_status=BuilderCleanStatus.CLEANING,
            vm_host='lol', vm_reset_protocol=BuilderResetProtocol.PROTO_2_0)
        yield self.assertCleanCalls(builder, OkSlave(), [], False)
        self.assertEqual(BuilderCleanStatus.CLEANING, builder.clean_status)

    @defer.inlineCallbacks
    def test_virtual_no_protocol(self):
        # Virtual builders fail to clean unless vm_reset_protocol is
        # set.
        builder = MockBuilder(
            virtualized=True, clean_status=BuilderCleanStatus.DIRTY,
            vm_host='lol')
        builder.vm_reset_protocol = None
        with ExpectedException(
                CannotResumeHost, "Invalid vm_reset_protocol: None"):
            yield BuilderInteractor.cleanSlave(
                extract_vitals_from_db(builder), OkSlave(),
                MockBuilderFactory(builder, None))

    @defer.inlineCallbacks
    def test_nonvirtual_idle(self):
        # An IDLE non-virtual slave is already as clean as we can get it.
        yield self.assertCleanCalls(
            MockBuilder(
                virtualized=False, clean_status=BuilderCleanStatus.DIRTY),
            OkSlave(), ['status'], True)

    @defer.inlineCallbacks
    def test_nonvirtual_building(self):
        # A BUILDING non-virtual slave needs to be aborted. It'll go
        # through ABORTING and eventually be picked up from WAITING.
        yield self.assertCleanCalls(
            MockBuilder(
                virtualized=False, clean_status=BuilderCleanStatus.DIRTY),
            BuildingSlave(), ['status', 'abort'], False)

    @defer.inlineCallbacks
    def test_nonvirtual_aborting(self):
        # An ABORTING non-virtual slave must be waited out. It should
        # hit WAITING eventually.
        yield self.assertCleanCalls(
            MockBuilder(
                virtualized=False, clean_status=BuilderCleanStatus.DIRTY),
            AbortingSlave(), ['status'], False)

    @defer.inlineCallbacks
    def test_nonvirtual_waiting(self):
        # A WAITING non-virtual slave just needs clean() called.
        yield self.assertCleanCalls(
            MockBuilder(
                virtualized=False, clean_status=BuilderCleanStatus.DIRTY),
            WaitingSlave(), ['status', 'clean'], True)

    @defer.inlineCallbacks
    def test_nonvirtual_broken(self):
        # A broken non-virtual builder is probably unrecoverable, so the
        # method just crashes.
        builder = MockBuilder(
            virtualized=False, clean_status=BuilderCleanStatus.DIRTY)
        vitals = extract_vitals_from_db(builder)
        slave = LostBuildingBrokenSlave()
        try:
            yield BuilderInteractor.cleanSlave(
                vitals, slave, MockBuilderFactory(builder, None))
        except xmlrpc_client.Fault:
            self.assertEqual(['status', 'abort'], slave.call_log)
        else:
            self.fail("abort() should crash.")


class TestBuilderSlaveStatus(TestCase):
    # Verify what BuilderSlave.status returns with slaves in different
    # states.

    run_tests_with = AsynchronousDeferredRunTest

    @defer.inlineCallbacks
    def assertStatus(self, slave, builder_status=None, build_status=None,
                     build_id=False, logtail=False, filemap=None,
                     dependencies=None):
        status = yield slave.status()

        expected = {}
        if builder_status is not None:
            expected["builder_status"] = builder_status
        if build_status is not None:
            expected["build_status"] = build_status
        if filemap is not None:
            expected["filemap"] = filemap
            expected["dependencies"] = dependencies

        # We don't care so much about the build_id or the content of the
        # logtail, just that they're there.
        if build_id:
            self.assertIn("build_id", status)
            del status["build_id"]
        if logtail:
            tail = status.pop("logtail")
            self.assertIsInstance(tail, xmlrpc_client.Binary)

        self.assertEqual(expected, status)

    def test_status_idle_slave(self):
        self.assertStatus(OkSlave(), builder_status='BuilderStatus.IDLE')

    def test_status_building_slave(self):
        self.assertStatus(
            BuildingSlave(), builder_status='BuilderStatus.BUILDING',
            build_id=True, logtail=True)

    def test_status_waiting_slave(self):
        self.assertStatus(
            WaitingSlave(), builder_status='BuilderStatus.WAITING',
            build_status='BuildStatus.OK', build_id=True, filemap={})

    def test_status_aborting_slave(self):
        self.assertStatus(
            AbortingSlave(), builder_status='BuilderStatus.ABORTING',
            build_id=True)


class TestBuilderInteractorDB(TestCaseWithFactory):
    """BuilderInteractor tests that need a DB."""

    layer = ZopelessDatabaseLayer
    run_tests_with = AsynchronousDeferredRunTest.make_factory(timeout=30)

    def test_getBuildBehaviour_idle(self):
        """An idle builder has no build behaviour."""
        self.assertIs(
            None,
            BuilderInteractor.getBuildBehaviour(None, MockBuilder(), None))

    def test_getBuildBehaviour_building(self):
        """The current behaviour is set automatically from the current job."""
        # Set the builder attribute on the buildqueue record so that our
        # builder will think it has a current build.
        builder = self.factory.makeBuilder(name='builder')
        slave = BuildingSlave()
        build = self.factory.makeBinaryPackageBuild()
        bq = build.queueBuild()
        bq.markAsBuilding(builder)
        behaviour = BuilderInteractor.getBuildBehaviour(bq, builder, slave)
        self.assertIsInstance(behaviour, BinaryPackageBuildBehaviour)
        self.assertEqual(behaviour._builder, builder)
        self.assertEqual(behaviour._slave, slave)

    def _setupBuilder(self):
        processor = self.factory.makeProcessor(name="i386")
        builder = self.factory.makeBuilder(
            processors=[processor], virtualized=True, vm_host="bladh")
        builder.setCleanStatus(BuilderCleanStatus.CLEAN)
        self.patch(BuilderSlave, 'makeBuilderSlave', FakeMethod(OkSlave()))
        distroseries = self.factory.makeDistroSeries()
        das = self.factory.makeDistroArchSeries(
            distroseries=distroseries, architecturetag="i386",
            processor=processor)
        chroot = self.factory.makeLibraryFileAlias(db_only=True)
        das.addOrUpdateChroot(chroot)
        distroseries.nominatedarchindep = das
        return builder, distroseries, das

    def _setupRecipeBuildAndBuilder(self):
        # Helper function to make a builder capable of building a
        # recipe, returning both.
        builder, distroseries, distroarchseries = self._setupBuilder()
        build = self.factory.makeSourcePackageRecipeBuild(
            distroseries=distroseries)
        return builder, build

    def _setupBinaryBuildAndBuilder(self):
        # Helper function to make a builder capable of building a
        # binary package, returning both.
        builder, distroseries, distroarchseries = self._setupBuilder()
        build = self.factory.makeBinaryPackageBuild(
            distroarchseries=distroarchseries, builder=builder)
        return builder, build

    def test_findAndStartJob_returns_candidate(self):
        # findAndStartJob finds the next queued job using findBuildCandidate.
        # We don't care about the type of build at all.
        builder, build = self._setupRecipeBuildAndBuilder()
        candidate = build.queueBuild()
        builder_factory = MockBuilderFactory(builder, candidate)
        # findBuildCandidate is tested elsewhere, we just make sure that
        # findAndStartJob delegates to it.
        builder_factory.findBuildCandidate = FakeMethod(result=candidate)
        vitals = extract_vitals_from_db(builder)
        d = BuilderInteractor.findAndStartJob(
            vitals, builder, OkSlave(), builder_factory)
        return d.addCallback(self.assertEqual, candidate)

    @defer.inlineCallbacks
    def test_findAndStartJob_supersedes_builds(self):
        # findAndStartJob checks whether queued jobs are for superseded
        # source package releases and marks the corresponding build records
        # as SUPERSEDED.
        builder, distroseries, distroarchseries = self._setupBuilder()
        builds = [
            self.factory.makeBinaryPackageBuild(
                distroarchseries=distroarchseries)
            for _ in range(3)]
        candidates = [build.queueBuild() for build in builds]
        builder_factory = PrefetchedBuilderFactory()
        candidates_iter = iter(candidates)
        builder_factory.findBuildCandidate = lambda _: next(candidates_iter)
        vitals = extract_vitals_from_db(builder)

        # Supersede some of the builds' source packages.
        for build in builds[:2]:
            publication = build.current_source_publication
            publication.status = PackagePublishingStatus.SUPERSEDED

        # Starting a job selects a non-superseded candidate, and supersedes
        # the candidates that have superseded source packages.
        candidate = yield BuilderInteractor.findAndStartJob(
            vitals, builder, OkSlave(), builder_factory)
        self.assertEqual(candidates[2], candidate)
        self.assertEqual(
            [BuildStatus.SUPERSEDED, BuildStatus.SUPERSEDED,
             BuildStatus.BUILDING],
            [build.status for build in builds])

    def test_findAndStartJob_starts_job(self):
        # findAndStartJob finds the next queued job using findBuildCandidate
        # and then starts it.
        # We don't care about the type of build at all.
        builder, build = self._setupRecipeBuildAndBuilder()
        candidate = build.queueBuild()
        builder_factory = MockBuilderFactory(builder, candidate)
        builder_factory.findBuildCandidate = FakeMethod(result=candidate)
        vitals = extract_vitals_from_db(builder)
        d = BuilderInteractor.findAndStartJob(
            vitals, builder, OkSlave(), builder_factory)

        def check_build_started(candidate):
            self.assertEqual(candidate.builder, builder)
            self.assertEqual(BuildStatus.BUILDING, build.status)

        return d.addCallback(check_build_started)

    @defer.inlineCallbacks
    def test_findAndStartJob_requires_clean_slave(self):
        # findAndStartJob ensures that its slave starts CLEAN.
        builder, build = self._setupBinaryBuildAndBuilder()
        builder.setCleanStatus(BuilderCleanStatus.DIRTY)
        candidate = build.queueBuild()
        builder_factory = MockBuilderFactory(builder, candidate)
        builder_factory.findBuildCandidate = FakeMethod(result=candidate)
        vitals = extract_vitals_from_db(builder)
        with ExpectedException(
                BuildDaemonIsolationError,
                "Attempted to start build on a dirty slave."):
            yield BuilderInteractor.findAndStartJob(
                vitals, builder, OkSlave(), builder_factory)

    @defer.inlineCallbacks
    def test_findAndStartJob_dirties_slave(self):
        # findAndStartJob marks its builder DIRTY before dispatching.
        builder, build = self._setupBinaryBuildAndBuilder()
        candidate = build.queueBuild()
        builder_factory = MockBuilderFactory(builder, candidate)
        builder_factory.findBuildCandidate = FakeMethod(result=candidate)
        vitals = extract_vitals_from_db(builder)
        yield BuilderInteractor.findAndStartJob(
            vitals, builder, OkSlave(), builder_factory)
        self.assertEqual(BuilderCleanStatus.DIRTY, builder.clean_status)


class TestSlave(TestCase):
    """
    Integration tests for BuilderSlave that verify how it works against a
    real slave server.
    """

    run_tests_with = AsynchronousDeferredRunTest.make_factory(timeout=30)

    def setUp(self):
        super(TestSlave, self).setUp()
        self.slave_helper = self.useFixture(SlaveTestHelpers())
        self.addCleanup(shut_down_default_process_pool)

    @defer.inlineCallbacks
    def test_abort(self):
        slave = self.slave_helper.getClientSlave()
        # We need to be in a BUILDING state before we can abort.
        build_id = 'some-id'
        response = yield self.slave_helper.triggerGoodBuild(slave, build_id)
        self.assertEqual([BuilderStatus.BUILDING, build_id], response)
        response = yield slave.abort()
        self.assertEqual(BuilderStatus.ABORTING, response)

    @defer.inlineCallbacks
    def test_build(self):
        # Calling 'build' with an expected builder type, a good build id,
        # valid chroot & filemaps works and returns a BuilderStatus of
        # BUILDING.
        build_id = 'some-id'
        slave = self.slave_helper.getClientSlave()
        response = yield self.slave_helper.triggerGoodBuild(slave, build_id)
        self.assertEqual([BuilderStatus.BUILDING, build_id], response)

    def test_clean(self):
        slave = self.slave_helper.getClientSlave()
        # XXX: JonathanLange 2010-09-21: Calling clean() on the slave requires
        # it to be in either the WAITING or ABORTED states, and both of these
        # states are very difficult to achieve in a test environment. For the
        # time being, we'll just assert that a clean attribute exists.
        self.assertNotEqual(getattr(slave, 'clean', None), None)

    @defer.inlineCallbacks
    def test_echo(self):
        # Calling 'echo' contacts the server which returns the arguments we
        # gave it.
        self.slave_helper.getServerSlave()
        slave = self.slave_helper.getClientSlave()
        response = yield slave.echo('foo', 'bar', 42)
        self.assertEqual(['foo', 'bar', 42], response)

    @defer.inlineCallbacks
    def test_info(self):
        # Calling 'info' gets some information about the slave.
        self.slave_helper.getServerSlave()
        slave = self.slave_helper.getClientSlave()
        info = yield slave.info()
        # We're testing the hard-coded values, since the version is hard-coded
        # into the remote slave, the supported build managers are hard-coded
        # into the tac file for the remote slave and config is returned from
        # the configuration file.
        self.assertEqual(3, len(info))
        self.assertEqual(['1.0', 'i386'], info[:2])
        self.assertThat(
            info[2],
            ContainsAll(
                ('sourcepackagerecipe', 'translation-templates',
                 'binarypackage', 'livefs', 'snap')))

    @defer.inlineCallbacks
    def test_initial_status(self):
        # Calling 'status' returns the current status of the slave. The
        # initial status is IDLE.
        self.slave_helper.getServerSlave()
        slave = self.slave_helper.getClientSlave()
        status = yield slave.status()
        self.assertEqual(BuilderStatus.IDLE, status['builder_status'])

    @defer.inlineCallbacks
    def test_status_after_build(self):
        # Calling 'status' returns the current status of the slave.  After a
        # build has been triggered, the status is BUILDING.
        slave = self.slave_helper.getClientSlave()
        build_id = 'status-build-id'
        response = yield self.slave_helper.triggerGoodBuild(slave, build_id)
        self.assertEqual([BuilderStatus.BUILDING, build_id], response)
        status = yield slave.status()
        self.assertEqual(BuilderStatus.BUILDING, status['builder_status'])
        self.assertEqual(build_id, status['build_id'])
        self.assertIsInstance(status['logtail'], xmlrpc_client.Binary)

    @defer.inlineCallbacks
    def test_ensurepresent_not_there(self):
        # ensurepresent checks to see if a file is there.
        self.slave_helper.getServerSlave()
        slave = self.slave_helper.getClientSlave()
        response = yield slave.ensurepresent('blahblah', None, None, None)
        self.assertEqual([False, 'No URL'], response)

    @defer.inlineCallbacks
    def test_ensurepresent_actually_there(self):
        # ensurepresent checks to see if a file is there.
        tachandler = self.slave_helper.getServerSlave()
        slave = self.slave_helper.getClientSlave()
        self.slave_helper.makeCacheFile(tachandler, 'blahblah')
        response = yield slave.ensurepresent('blahblah', None, None, None)
        self.assertEqual([True, 'No URL'], response)

    def test_sendFileToSlave_not_there(self):
        self.slave_helper.getServerSlave()
        slave = self.slave_helper.getClientSlave()
        d = slave.sendFileToSlave('blahblah', None, None, None)
        return assert_fails_with(d, CannotFetchFile)

    @defer.inlineCallbacks
    def test_sendFileToSlave_actually_there(self):
        tachandler = self.slave_helper.getServerSlave()
        slave = self.slave_helper.getClientSlave()
        self.slave_helper.makeCacheFile(tachandler, 'blahblah')
        yield slave.sendFileToSlave('blahblah', None, None, None)
        response = yield slave.ensurepresent('blahblah', None, None, None)
        self.assertEqual([True, 'No URL'], response)

    @defer.inlineCallbacks
    def test_resumeHost_success(self):
        # On a successful resume resume() fires the returned deferred
        # callback with (stdout, stderr, subprocess exit code).
        self.slave_helper.getServerSlave()
        slave = self.slave_helper.getClientSlave()

        # The configuration testing command-line.
        self.assertEqual(
            'echo %(vm_host)s', config.builddmaster.vm_resume_command)

        out, err, code = yield slave.resume()
        self.assertEqual(os.EX_OK, code)
        # XXX: JonathanLange 2010-09-23: We should instead pass the
        # expected vm_host into the client slave. Not doing this now,
        # since the SlaveHelper is being moved around.
        self.assertEqual("%s\n" % slave._vm_host, six.ensure_str(out))

    def test_resumeHost_failure(self):
        # On a failed resume, 'resumeHost' fires the returned deferred
        # errorback with the `ProcessTerminated` failure.
        self.slave_helper.getServerSlave()
        slave = self.slave_helper.getClientSlave()

        # Override the configuration command-line with one that will fail.
        failed_config = """
        [builddmaster]
        vm_resume_command: test "%(vm_host)s = 'no-sir'"
        """
        config.push('failed_resume_command', failed_config)
        self.addCleanup(config.pop, 'failed_resume_command')

        # On failures, the response is a twisted `Failure` object containing
        # a tuple.
        def check_resume_failure(failure):
            out, err, code = failure.value
            # The process will exit with a return code of "1".
            self.assertEqual(code, 1)
        d = slave.resume()
        d.addBoth(check_resume_failure)
        return d

    def test_resumeHost_timeout(self):
        # On a resume timeouts, 'resumeHost' fires the returned deferred
        # errorback with the `TimeoutError` failure.

        # Override the configuration command-line with one that will timeout.
        timeout_config = """
        [builddmaster]
        vm_resume_command: sleep 5
        socket_timeout: 1
        """
        config.push('timeout_resume_command', timeout_config)
        self.addCleanup(config.pop, 'timeout_resume_command')

        self.slave_helper.getServerSlave()
        slave = self.slave_helper.getClientSlave()

        # On timeouts, the response is a twisted `Failure` object containing
        # a `TimeoutError` error.
        def check_resume_timeout(failure):
            self.assertIsInstance(failure, Failure)
            out, err, code = failure.value
            self.assertEqual(code, signal.SIGKILL)
        clock = Clock()
        d = slave.resume(clock=clock)
        # Move the clock beyond the socket_timeout but earlier than the
        # sleep 5.  This stops the test having to wait for the timeout.
        # Fast tests FTW!
        clock.advance(2)
        d.addBoth(check_resume_timeout)
        return d


class TestSlaveTimeouts(TestCase):
    # Testing that the methods that call callRemote() all time out
    # as required.

    run_tests_with = AsynchronousDeferredRunTestForBrokenTwisted.make_factory(
        timeout=30)

    def setUp(self):
        super(TestSlaveTimeouts, self).setUp()
        self.slave_helper = self.useFixture(SlaveTestHelpers())
        self.clock = Clock()
        self.proxy = DeadProxy(b"url")
        self.slave = self.slave_helper.getClientSlave(
            reactor=self.clock, proxy=self.proxy)
        self.addCleanup(shut_down_default_process_pool)

    def assertCancelled(self, d, timeout=None):
        self.clock.advance((timeout or config.builddmaster.socket_timeout) + 1)
        return assert_fails_with(d, defer.CancelledError)

    def test_timeout_abort(self):
        return self.assertCancelled(self.slave.abort())

    def test_timeout_clean(self):
        return self.assertCancelled(self.slave.clean())

    def test_timeout_echo(self):
        return self.assertCancelled(self.slave.echo())

    def test_timeout_info(self):
        return self.assertCancelled(self.slave.info())

    def test_timeout_status(self):
        return self.assertCancelled(self.slave.status())

    def test_timeout_ensurepresent(self):
        return self.assertCancelled(
            self.slave.ensurepresent(None, None, None, None),
            config.builddmaster.socket_timeout * 5)

    def test_timeout_build(self):
        return self.assertCancelled(
            self.slave.build(None, None, None, None, None))


class TestSlaveConnectionTimeouts(TestCase):
    # Testing that we can override the default 30 second connection
    # timeout.

    # The timeouts in test_connection_timeout are relative to the artificial
    # Clock rather than to true wallclock time, so it's not a problem for
    # this timeout to be shorter than them.
    run_tests_with = AsynchronousDeferredRunTest.make_factory(timeout=30)

    def setUp(self):
        super(TestSlaveConnectionTimeouts, self).setUp()
        self.slave_helper = self.useFixture(SlaveTestHelpers())
        self.clock = Clock()
        self.addCleanup(shut_down_default_process_pool)

    def test_connection_timeout(self):
        # The default timeout of 30 seconds should not cause a timeout,
        # only the config value should.
        self.pushConfig('builddmaster', socket_timeout=180)

        slave = self.slave_helper.getClientSlave(reactor=self.clock)
        d = slave.echo()
        # Advance past the 30 second timeout.  The real reactor will
        # never call connectTCP() since we're not spinning it up.  This
        # avoids "connection refused" errors and simulates an
        # environment where the endpoint doesn't respond.
        self.clock.advance(31)
        self.assertFalse(d.called)

        self.clock.advance(config.builddmaster.socket_timeout + 1)
        self.assertTrue(d.called)
        return assert_fails_with(d, defer.CancelledError)


class TestSlaveWithLibrarian(TestCaseWithFactory):
    """Tests that need more of Launchpad to run."""

    layer = LaunchpadZopelessLayer
    run_tests_with = AsynchronousDeferredRunTestForBrokenTwisted.make_factory(
        timeout=30)

    def setUp(self):
        super(TestSlaveWithLibrarian, self).setUp()
        self.slave_helper = self.useFixture(SlaveTestHelpers())
        self.addCleanup(shut_down_default_process_pool)

    def test_ensurepresent_librarian(self):
        # ensurepresent, when given an http URL for a file will download the
        # file from that URL and report that the file is present, and it was
        # downloaded.

        # Use the Librarian because it's a "convenient" web server.
        lf = self.factory.makeLibraryFileAlias(
            'HelloWorld.txt', content="Hello World")
        self.layer.txn.commit()
        self.slave_helper.getServerSlave()
        slave = self.slave_helper.getClientSlave()
        d = slave.ensurepresent(lf.content.sha1, lf.http_url, "", "")
        d.addCallback(self.assertEqual, [True, 'Download'])
        return d

    @defer.inlineCallbacks
    def test_retrieve_files_from_filecache(self):
        # Files that are present on the slave can be downloaded with a
        # filename made from the sha1 of the content underneath the
        # 'filecache' directory.
        from twisted.internet import reactor
        content = b"Hello World"
        lf = self.factory.makeLibraryFileAlias(
            'HelloWorld.txt', content=content)
        self.layer.txn.commit()
        expected_url = '%s/filecache/%s' % (
            self.slave_helper.base_url, lf.content.sha1)
        self.slave_helper.getServerSlave()
        slave = self.slave_helper.getClientSlave()
        yield slave.ensurepresent(lf.content.sha1, lf.http_url, "", "")
        client = self.useFixture(TReqFixture(reactor)).client
        response = yield client.get(expected_url).addCallback(check_status)
        got_content = yield treq.content(response)
        self.assertEqual(content, got_content)

    def test_getFiles(self):
        # Test BuilderSlave.getFiles().
        # It also implicitly tests getFile() - I don't want to test that
        # separately because it increases test run time and it's going
        # away at some point anyway, in favour of getFiles().
        contents = ["content1", "content2", "content3"]
        self.slave_helper.getServerSlave()
        slave = self.slave_helper.getClientSlave()
        files = []
        content_map = {}

        def got_files(ignored):
            # Called back when getFiles finishes.  Make sure all the
            # content is as expected.
            for sha1, local_file in files:
                with open(local_file) as f:
                    self.assertEqual(content_map[sha1], f.read())

        def finished_uploading(ignored):
            d = slave.getFiles(files)
            return d.addCallback(got_files)

        # Set up some files on the builder and store details in
        # content_map so we can compare downloads later.
        dl = []
        for content in contents:
            filename = content + '.txt'
            lf = self.factory.makeLibraryFileAlias(filename, content=content)
            content_map[lf.content.sha1] = content
            files.append((lf.content.sha1, tempfile.mkstemp()[1]))
            self.addCleanup(os.remove, files[-1][1])
            # Add the same file contents again with a different name, to
            # ensure that we can tolerate duplication.
            files.append((lf.content.sha1, tempfile.mkstemp()[1]))
            self.addCleanup(os.remove, files[-1][1])
            self.layer.txn.commit()
            d = slave.ensurepresent(lf.content.sha1, lf.http_url, "", "")
            dl.append(d)

        return defer.DeferredList(dl).addCallback(finished_uploading)

    def test_getFiles_open_connections(self):
        # getFiles honours the configured limit on active download
        # connections.
        contents = [self.factory.getUniqueString() for _ in range(10)]
        self.slave_helper.getServerSlave()
        process_pool = make_download_process_pool(min=1, max=2)
        process_pool.start()
        self.addCleanup(process_pool.stop)
        slave = self.slave_helper.getClientSlave(process_pool=process_pool)
        files = []
        content_map = {}

        def got_files(ignored):
            # Called back when getFiles finishes.  Make sure all the
            # content is as expected.
            for sha1, local_file in files:
                with open(local_file) as f:
                    self.assertEqual(content_map[sha1], f.read())
            # Only two workers were used.
            self.assertEqual(2, len(process_pool.processes))

        def finished_uploading(ignored):
            d = slave.getFiles(files)
            return d.addCallback(got_files)

        # Set up some files on the builder and store details in
        # content_map so we can compare downloads later.
        dl = []
        for content in contents:
            filename = content + '.txt'
            lf = self.factory.makeLibraryFileAlias(filename, content=content)
            content_map[lf.content.sha1] = content
            files.append((lf.content.sha1, tempfile.mkstemp()[1]))
            self.addCleanup(os.remove, files[-1][1])
            self.layer.txn.commit()
            d = slave.ensurepresent(lf.content.sha1, lf.http_url, "", "")
            dl.append(d)

        return defer.DeferredList(dl).addCallback(finished_uploading)

    @defer.inlineCallbacks
    def test_getFiles_with_empty_file(self):
        # getFiles works with zero-length files.
        tachandler = self.slave_helper.getServerSlave()
        slave = self.slave_helper.getClientSlave()
        temp_fd, temp_name = tempfile.mkstemp()
        self.addCleanup(os.remove, temp_name)
        empty_sha1 = hashlib.sha1(b'').hexdigest()
        self.slave_helper.makeCacheFile(tachandler, empty_sha1, contents=b'')
        yield slave.getFiles([(empty_sha1, temp_name)])
        with open(temp_name, 'rb') as f:
            self.assertEqual(b'', f.read())
