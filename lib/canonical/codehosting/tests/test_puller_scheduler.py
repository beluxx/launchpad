import logging
import os
import shutil
import tempfile
import unittest

import bzrlib

from twisted.internet import defer, error
from twisted.python import failure
from twisted.trial.unittest import TestCase as TrialTestCase

from canonical.codehosting import branch_id_to_path
from canonical.launchpad.interfaces import BranchType
from canonical.codehosting.tests.helpers import create_branch
from canonical.codehosting.puller import scheduler
from canonical.authserver.tests.harness import AuthserverTacTestSetup
from canonical.testing import LaunchpadZopelessLayer, reset_logging


class TestJobManager(unittest.TestCase):

    def setUp(self):
        self.masterlock = 'master.lock'
        # We set the log level to CRITICAL so that the log messages
        # are suppressed.
        logging.basicConfig(level=logging.CRITICAL)

    def tearDown(self):
        reset_logging()

    def makeFakeClient(self, hosted, mirrored, imported):
        return FakeBranchStatusClient(
            {'HOSTED': hosted, 'MIRRORED': mirrored, 'IMPORTED': imported})

    def makeJobManager(self, branch_type, branch_tuples):
        if branch_type == BranchType.HOSTED:
            client = self.makeFakeClient(branch_tuples, [], [])
        elif branch_type == BranchType.MIRRORED:
            client = self.makeFakeClient([], branch_tuples, [])
        elif branch_type == BranchType.IMPORTED:
            client = self.makeFakeClient([], [], branch_tuples)
        else:
            self.fail("Unknown branch type: %r" % (branch_type,))
        return scheduler.JobManager(client, logging.getLogger(), branch_type)

    def testManagerCreatesLocks(self):
        try:
            manager = self.makeJobManager(BranchType.HOSTED, [])
            manager.lockfilename = self.masterlock
            manager.lock()
            self.failUnless(os.path.exists(self.masterlock))
            manager.unlock()
        finally:
            self._removeLockFile()

    def testManagerEnforcesLocks(self):
        try:
            manager = self.makeJobManager(BranchType.HOSTED, [])
            manager.lockfilename = self.masterlock
            manager.lock()
            anothermanager = self.makeJobManager(BranchType.HOSTED, [])
            anothermanager.lockfilename = self.masterlock
            self.assertRaises(scheduler.LockError, anothermanager.lock)
            self.failUnless(os.path.exists(self.masterlock))
            manager.unlock()
        finally:
            self._removeLockFile()

    def _removeLockFile(self):
        if os.path.exists(self.masterlock):
            os.unlink(self.masterlock)


class TestJobManagerInLaunchpad(TrialTestCase):
    layer = LaunchpadZopelessLayer

    testdir = None

    def setUp(self):
        self.testdir = tempfile.mkdtemp()
        # Change the HOME environment variable in order to ignore existing
        # user config files.
        os.environ.update({'HOME': self.testdir})
        self.authserver = AuthserverTacTestSetup()
        self.authserver.setUp()

    def tearDown(self):
        shutil.rmtree(self.testdir)
        self.authserver.tearDown()

    def _getBranchDir(self, branchname):
        return os.path.join(self.testdir, branchname)

    def assertMirrored(self, branch_to_mirror):
        """Assert that branch_to_mirror's source and destinations have the same
        revisions.

        :param branch_to_mirror: a BranchToMirror instance.
        """
        source_branch = bzrlib.branch.Branch.open(branch_to_mirror.source_url)
        dest_branch = bzrlib.branch.Branch.open(
            branch_to_mirror.destination_url)
        self.assertEqual(
            source_branch.last_revision(), dest_branch.last_revision())

    def testJobRunner(self):
        return
        client = scheduler.BranchStatusClient()
        manager = scheduler.JobManager(
            client, logging.getLogger(), BranchType.HOSTED)

        branches = [
            self._makeBranch(manager, "brancha", 1),
            self._makeBranch(manager, "branchb", 2),
            self._makeBranch(manager, "branchc", 3),
            self._makeBranch(manager, "branchd", 4),
            self._makeBranch(manager, "branche", 5)]

        deferred = manager._run(branches)

        def check_mirrored(ignored):
            for branch in branches:
                self.assertMirrored(branch)

        return deferred.addCallback(check_mirrored)

    def _makeBranch(self, manager, branch_src, branch_id):
        """Given a relative directory, make a strawman branch and return it.
        """
        unique_name = '~testuser/+junk/' + branch_src
        branch_src = os.path.join(self.testdir, branch_src)
        create_branch(branch_src)
        branch = manager.getBranchToMirror(branch_id, branch_src, unique_name)
        branch.destination_url = os.path.join(
            self.testdir, branch_id_to_path(branch_id))
        return branch


class FakeBranchStatusClient:
    """A dummy branch status client implementation for testing getBranches()"""

    def __init__(self, branch_queues):
        self.branch_queues = branch_queues

    def getBranchPullQueue(self, branch_type):
        return self.branch_queues[branch_type]


class TestPullerMasterProtocol(TrialTestCase):
    """Tests for the process protocol used by the job manager."""

    class PullerListener:
        """Fake listener object that records calls."""

        def __init__(self):
            self.calls = []

        def startMirroring(self):
            self.calls.append('startMirroring')

        def mirrorSucceeded(self, last_revision):
            self.calls.append(('mirrorSucceeded', last_revision))

        def mirrorFailed(self, message, oops):
            self.calls.append(('mirrorFailed', message, oops))


    class FakeTransport:
        """Fake transport that only implements loseConnection.

        We're manually feeding data to the protocol, so we don't need a real
        transport.
        """
        def loseConnection(self):
            pass


    def setUp(self):
        arbitrary_timeout_period = 20
        self.arbitrary_branch_id = 1
        self.listener = TestPullerMasterProtocol.PullerListener()
        self.termination_deferred = defer.Deferred()
        self.protocol = scheduler.PullerMasterProtocol(
            self.termination_deferred, arbitrary_timeout_period,
            self.listener)
        self.protocol.transport = TestPullerMasterProtocol.FakeTransport()

    def convertToNetstring(self, string):
        return '%d:%s,' % (len(string), string)

    def test_startMirroring(self):
        """Receiving a startMirroring message notifies the listener."""
        self.protocol.outReceived(self.convertToNetstring('startMirroring'))
        self.assertEqual(['startMirroring'], self.listener.calls)

    def test_mirrorSucceeded(self):
        """Receiving a mirrorSucceeded message notifies the listener."""
        self.protocol.outReceived(self.convertToNetstring('startMirroring'))
        self.listener.calls = []
        self.protocol.outReceived(
            self.convertToNetstring('mirrorSucceeded'))
        self.protocol.outReceived(self.convertToNetstring('1234'))
        self.assertEqual([('mirrorSucceeded', '1234')], self.listener.calls)

    def test_mirrorFailed(self):
        """Receiving a mirrorFailed message notifies the listener."""
        self.protocol.outReceived(self.convertToNetstring('startMirroring'))
        self.listener.calls = []
        self.protocol.outReceived(
            self.convertToNetstring('mirrorFailed'))
        self.protocol.outReceived(self.convertToNetstring('Error Message'))
        self.protocol.outReceived(self.convertToNetstring('OOPS'))
        self.assertEqual(
            [('mirrorFailed', 'Error Message', 'OOPS')], self.listener.calls)

    def test_processTermination(self):
        """The protocol fires a Deferred when it is terminated."""
        self.protocol.processEnded(failure.Failure(error.ProcessDone(None)))
        return self.termination_deferred

    def test_unexpectedError(self):
        """When the child process terminates with an unexpected error, raise
        an error that includes the contents of stderr and the exit condition.
        """

        def check_failure(failure):
            self.assertEqual('error message', failure.error)
            return failure

        self.termination_deferred.addErrback(check_failure)
        deferred = self.assertFailure(
            self.termination_deferred, error.ProcessTerminated)

        self.protocol.errReceived('error ')
        self.protocol.errReceived('message')
        self.protocol.processEnded(
            failure.Failure(error.ProcessTerminated(exitCode=1)))

        return deferred

    def test_stderrFailsProcess(self):
        """If the process prints to stderr, then the Deferred fires an
        errback, even if it terminated successfully.
        """

        def check_failure(failure):
            self.assertEqual('error message', failure.error)
            return failure

        self.termination_deferred.addErrback(check_failure)

        self.protocol.errReceived('error ')
        self.protocol.errReceived('message')
        self.protocol.processEnded(failure.Failure(error.ProcessDone(None)))

        return self.termination_deferred

#     def test_unrecognizedMessage(self):
#         """The protocol notifies the listener when it receives an unrecognized
#         message.
#         """
#         # XXX: How do we best deal with the aberrant child process?
#         self.protocol.outReceived(self.convertToNetstring('foo'))

#         def check_failure(exception):
#             self.assertTrue('foo' in str(exception))

#         deferred = self.assertFailure(
#             self.termination_deferred, jobmanager.BadMessage)

#         return deferred.addCallback(check_failure)

#     def test_invalidNetstring(self):
#         """The protocol terminates the session if it receives an unparsable
#         netstring.
#         """
#         # XXX: How do we best deal with the aberrant child process?
#         self.protocol.outReceived('foo')

#         def check_failure(exception):
#             self.assertTrue('foo' in str(exception))

#         deferred = self.assertFailure(
#             self.termination_deferred, jobmanager.BadMessage)

#         return deferred.addCallback(check_failure)


class TestMirroringEvents(TrialTestCase):
    layer = LaunchpadZopelessLayer

    class BranchStatusClient:

        def __init__(self):
            self.calls = []

        def startMirroring(self, branch_id):
            self.calls.append(('startMirroring', branch_id))
            return defer.succeed(None)

        def mirrorComplete(self, branch_id, revision_id):
            self.calls.append(('mirrorComplete', branch_id, revision_id))
            return defer.succeed(None)

        def mirrorFailed(self, branch_id, revision_id):
            self.calls.append(('mirrorFailed', branch_id, revision_id))
            return defer.succeed(None)

    def setUp(self):
        self.status_client = TestMirroringEvents.BranchStatusClient()
        self.arbitrary_branch_id = 1
        self.eventHandler = scheduler.BranchToMirror(
            self.arbitrary_branch_id, 'arbitrary-source', 'arbitrary-dest',
            BranchType.HOSTED, logging.getLogger(), self.status_client)

    def test_startMirroring(self):
        deferred = self.eventHandler.startMirroring()

        def checkMirrorStarted(ignored):
            self.assertEqual(
                [('startMirroring', self.arbitrary_branch_id)],
                self.status_client.calls)

        return deferred.addCallback(checkMirrorStarted)

    def test_mirrorComplete(self):
        arbitrary_revision_id = 'rev1'
        deferred = self.eventHandler.startMirroring()

        def mirrorSucceeded(ignored):
            self.status_client.calls = []
            return self.eventHandler.mirrorSucceeded(arbitrary_revision_id)
        deferred.addCallback(mirrorSucceeded)

        def checkMirrorCompleted(ignored):
            self.assertEqual(
                [('mirrorComplete', self.arbitrary_branch_id,
                  arbitrary_revision_id)],
                self.status_client.calls)
        return deferred.addCallback(checkMirrorCompleted)

    def test_mirrorFailed(self):
        arbitrary_error_message = 'failed'

        deferred = self.eventHandler.startMirroring()

        def mirrorFailed(ignored):
            self.status_client.calls = []
            return self.eventHandler.mirrorFailed(
                arbitrary_error_message, 'oops')
        deferred.addCallback(mirrorFailed)

        def checkMirrorFailed(ignored):
            self.assertEqual(
                [('mirrorFailed', self.arbitrary_branch_id,
                  arbitrary_error_message)],
                self.status_client.calls)
        return deferred.addCallback(checkMirrorFailed)


def test_suite():
    return unittest.TestLoader().loadTestsFromName(__name__)
