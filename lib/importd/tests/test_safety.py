# Copyright 2006 Canonical Ltd.  All rights reserved.

"""Test safety checks in importd.

We do some simple safety checks on imports to avoid putting excessive
load on the servers we are connecting to. These checks are only
performed on the initial import, because the system guarantees that
syncs are only run on published imports and once a vcs import is
published, its details can only be changed by a privileged operator.

SVN repositories are typically laid out as:

    product/
         branches/
         tags/
         trunk/

Less often, they are laid out as:

    trunk/
         productA/
         productB/
         ...
    branches/
         ...

In the first example, if a client attempts to fetch svn://repo/product
(e.g. to import it to bzr), the server will send them the full text of
every single branch and tag, which is much larger than the actual size
of the repository.
"""

__metaclass__ = type

from importd.tests import testutil, helpers
from importd.JobStrategy import SVNStrategy, ImportSafetyError


class CheckSafetyCalled(Exception):
    """Raised to indicate that the _checkSafety method was called."""

class SafetyIsOverriddenCalled(Exception):
    """Raised to indicate that _safetyIsOverriden was called."""


class SvnSafetyTestCase(helpers.JobTestCase):
    """Base class for Subversion safety tests."""

    def setUp(self):
        helpers.JobTestCase.setUp(self)
        self.logger = testutil.makeSilentLogger()

    def makeTestingSvnJob(self, svn_url):
        """Create a job with svn details, to test svn safety checking."""
        job = self.job_helper.makeJob()
        job.repository = svn_url
        return job

    def makeTestingSvnStrategy(self, svn_url):
        """Create a a SVNStrategy to test safety checking."""
        job = self.makeTestingSvnJob(svn_url)
        strategy = SVNStrategy()
        strategy.job = job
        strategy.aJob = job
        strategy.dir = '.'
        strategy.logger = self.logger
        return strategy


class TestSvnSafety(SvnSafetyTestCase):
    """Test safety checks of SVN job strategy."""

    def testImportCallsCheckSafety(self):
        # SvnStrategy.Import calls _checkSafety before trying the import.
        strategy = SVNStrategy()
        def check_safety():
            raise CheckSafetyCalled()
        strategy._checkSafety = check_safety
        # Since the job does not have the information necessary to perform an
        # import, CheckSafetyCalled is only raised if _checkSafety is called
        # before doing anything.
        invalid_url = None
        job = self.makeTestingSvnJob(invalid_url)
        self.assertRaises(CheckSafetyCalled,
            strategy.Import, job, '.', self.logger)

    def testCheckSafetyCallsSafetyIsOverriden(self):
        # SvnStrategy._checkSafety calls SvnStrategy._safetyIsOverriden
        #
        # Use an obviously invalid svn url, so SafetyrIsOverridenCalled is only
        # raised if _safetyIsOverriden is called early on.
        invalid_url = None
        strategy = self.makeTestingSvnStrategy(invalid_url)
        def safety_is_overridden():
            raise SafetyIsOverriddenCalled()
        strategy._safetyIsOverridden = safety_is_overridden
        self.assertRaises(SafetyIsOverriddenCalled, strategy._checkSafety)

    def testSafetyIsOverridenFalse(self):
        # SvnStrategy._safetyIsOverriden returns false for an URL not in the
        # exception list
        not_whitelisted_url = 'svn://example.com/trunk'
        strategy = self.makeTestingSvnStrategy(not_whitelisted_url)
        self.assertFalse(not_whitelisted_url in strategy._svn_url_whitelist)
        self.assertFalse(strategy._safetyIsOverridden())

    def testSafetyIsOverridenTrue(self):
        # SvnStrategy._safetyIsOverriden returns true for an URL in the
        # exception list
        unsafe_url = 'svn://example.com/bogus'
        strategy = self.makeTestingSvnStrategy(unsafe_url)
        strategy._svn_url_whitelist.add(unsafe_url)
        self.assertTrue(strategy._safetyIsOverridden())

    def testCheckSafetyNoTrunk(self):
        # SvnStrategy._checkSafety raises for URL w/o trunk
        unsafe_url = 'svn://example.com/bogus'
        strategy = self.makeTestingSvnStrategy(unsafe_url)
        self.assertRaises(ImportSafetyError, strategy._checkSafety)

    def testCheckSafetyUrlIncludesTrunk(self):
        # SvnStrategy._checkSafety does not raise for URL including '/trunk/'
        good_url = 'svn://example.com/trunk/foo'
        strategy = self.makeTestingSvnStrategy(good_url)
        strategy._checkSafety() # test that it does not raise

    def testCheckSafetyUrlEndswithTrunk(self):
        # SvnStrategy._checkSafety does not raise for URL ending in '/trunk'
        good_url = 'svn://example.com/foo/trunk'
        strategy = self.makeTestingSvnStrategy(good_url)
        strategy._checkSafety() # test that it does not raise

    def testCheckSafetyUrlsEndswithSlash(self):
        # SvnStrategy._checkSafety raises for URL with a trailing slash
        url_slash = 'svn://example.com/foo/trunk/'
        strategy = self.makeTestingSvnStrategy(url_slash)
        self.assertRaises(ImportSafetyError, strategy._checkSafety)

    def testCheckSafetyCanBeOverridden(self):
        # SvnStrategy._checkSafety does not raise for a bad URL if
        # _safetyIsOverridenReturns is true.
        unsafe_url = 'svn://example.com/bogus'
        strategy = self.makeTestingSvnStrategy(unsafe_url)
        def safety_is_overridden():
            return True
        strategy._safetyIsOverridden = safety_is_overridden
        strategy._checkSafety() # test that it does not raise



testutil.register(__name__)
