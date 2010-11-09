# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for structural subscription traversal."""

import unittest

from lazr.restful.testing.webservice import FakeRequest
from zope.publisher.interfaces import NotFound

from canonical.launchpad.ftests import (
    LaunchpadFormHarness,
    login,
    logout,
    )
from canonical.launchpad.webapp.publisher import canonical_url
from canonical.launchpad.webapp.servers import StepsToGo
from canonical.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )
from lp.registry.browser.distribution import DistributionNavigation
from lp.registry.browser.distributionsourcepackage import (
    DistributionSourcePackageNavigation,
    )
from lp.registry.browser.distroseries import DistroSeriesNavigation
from lp.registry.browser.milestone import MilestoneNavigation
from lp.registry.browser.product import ProductNavigation
from lp.registry.browser.productseries import ProductSeriesNavigation
from lp.registry.browser.project import ProjectNavigation
from lp.registry.browser.structuralsubscription import (
    StructuralSubscriptionView)
from lp.registry.enum import BugNotificationLevel
from lp.testing import (
    feature_flags,
    person_logged_in,
    set_feature_flag,
    TestCaseWithFactory,
    )


class FakeLaunchpadRequest(FakeRequest):
    @property
    def stepstogo(self):
        """See `IBasicLaunchpadRequest`."""
        return StepsToGo(self)


class StructuralSubscriptionTraversalTestBase(TestCaseWithFactory):
    """Verify that we can reach a target's structural subscriptions."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(StructuralSubscriptionTraversalTestBase, self).setUp()
        login('foo.bar@canonical.com')
        self.eric = self.factory.makePerson(name='eric')
        self.michael = self.factory.makePerson(name='michael')

        self.setUpTarget()
        self.target.addBugSubscription(self.eric, self.eric)

    def setUpTarget(self):
        self.target = self.factory.makeProduct(name='fooix')
        self.navigation = ProductNavigation

    def test_structural_subscription_traversal(self):
        # Verify that an existing structural subscription can be
        # reached from the target.
        request = FakeLaunchpadRequest([], ['eric'])
        self.assertEqual(
            self.target.getSubscription(self.eric),
            self.navigation(self.target, request).publishTraverse(
                request, '+subscription'))

    def test_missing_structural_subscription_traversal(self):
        # Verify that a NotFound is raised when attempting to reach
        # a structural subscription for an person without one.
        request = FakeLaunchpadRequest([], ['michael'])
        self.assertRaises(
            NotFound,
            self.navigation(self.target, request).publishTraverse,
            request, '+subscription')

    def test_missing_person_structural_subscription_traversal(self):
        # Verify that a NotFound is raised when attempting to reach
        # a structural subscription for a person that does not exist.
        request = FakeLaunchpadRequest([], ['doesnotexist'])
        self.assertRaises(
            NotFound,
            self.navigation(self.target, request).publishTraverse,
            request, '+subscription')

    def test_structural_subscription_canonical_url(self):
        # Verify that the canonical_url of a structural subscription
        # is correct.
        self.assertEqual(
            canonical_url(self.target.getSubscription(self.eric)),
            canonical_url(self.target) + '/+subscription/eric')

    def tearDown(self):
        logout()
        super(StructuralSubscriptionTraversalTestBase, self).tearDown()


class TestProductSeriesStructuralSubscriptionTraversal(
    StructuralSubscriptionTraversalTestBase):
    """Test IStructuralSubscription traversal from IProductSeries."""
    def setUpTarget(self):
        self.target = self.factory.makeProduct(name='fooix').newSeries(
            self.eric, '0.1', '0.1')
        self.navigation = ProductSeriesNavigation


class TestMilestoneStructuralSubscriptionTraversal(
    StructuralSubscriptionTraversalTestBase):
    """Test IStructuralSubscription traversal from IMilestone."""
    def setUpTarget(self):
        self.target = self.factory.makeProduct(name='fooix').newSeries(
            self.eric, '0.1', '0.1').newMilestone('0.1.0')
        self.navigation = MilestoneNavigation


class TestProjectStructuralSubscriptionTraversal(
    StructuralSubscriptionTraversalTestBase):
    """Test IStructuralSubscription traversal from IProjectGroup."""
    def setUpTarget(self):
        self.target = self.factory.makeProject(name='fooix-project')
        self.navigation = ProjectNavigation


class TestDistributionStructuralSubscriptionTraversal(
    StructuralSubscriptionTraversalTestBase):
    """Test IStructuralSubscription traversal from IDistribution."""
    def setUpTarget(self):
        self.target = self.factory.makeDistribution(name='debuntu')
        self.navigation = DistributionNavigation


class TestDistroSeriesStructuralSubscriptionTraversal(
    StructuralSubscriptionTraversalTestBase):
    """Test IStructuralSubscription traversal from IDistroSeries."""
    def setUpTarget(self):
        self.target = self.factory.makeDistribution(name='debuntu').newSeries(
            '5.0', '5.0', '5.0', '5.0', '5.0', '5.0', None, self.eric)
        self.navigation = DistroSeriesNavigation


class TestDistributionSourcePackageStructuralSubscriptionTraversal(
    StructuralSubscriptionTraversalTestBase):
    """Test IStructuralSubscription traversal from IDistributionSourcePackage.
    """
    def setUpTarget(self):
        debuntu = self.factory.makeDistribution(name='debuntu')
        fooix = self.factory.makeSourcePackageName('fooix')
        self.target = debuntu.getSourcePackage(fooix)
        self.navigation = DistributionSourcePackageNavigation


class TestStructuralSubscriptionAdvancedFeaturesBase(TestCaseWithFactory):
    """A base class for testing advanced structural subscription features."""

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestStructuralSubscriptionAdvancedFeaturesBase, self).setUp()
        self.setUpTarget()
        with feature_flags():
            set_feature_flag(u'malone.advanced-subscriptions.enabled', u'on')

    def setUpTarget(self):
        self.target = self.factory.makeProduct()

    def test_subscribe_uses_bug_notification_level(self):
        # When advanced features are turned on for subscriptions a user
        # can specify a bug_notification_level on the +subscribe form.
        with feature_flags():
            # We don't display BugNotificationLevel.NOTHING as an option.
            displayed_levels = [
                level for level in BugNotificationLevel.items
                if level != BugNotificationLevel.NOTHING]
            for level in displayed_levels:
                person = self.factory.makePerson()
                with person_logged_in(person):
                    harness = LaunchpadFormHarness(
                        self.target, StructuralSubscriptionView)
                    form_data = {
                        'field.subscribe_me': 'on',
                        'field.bug_notification_level': level.name,
                        }
                    harness.submit('save', form_data)
                    self.assertFalse(harness.hasErrors())

                subscription = self.target.getSubscription(person)
                self.assertEqual(
                    level, subscription.bug_notification_level,
                    "Bug notification level of subscription should be %s, "
                    "is actually %s." % (
                        level.name, subscription.bug_notification_level.name))

    def test_nothing_is_not_a_valid_level(self):
        # BugNotificationLevel.NOTHING isn't considered valid when a
        # user is subscribing via the web UI.
        person = self.factory.makePerson()
        with feature_flags():
            with person_logged_in(person):
                harness = LaunchpadFormHarness(
                    self.target, StructuralSubscriptionView)
                form_data = {
                    'field.subscribe_me': 'on',
                    'field.bug_notification_level': (
                        BugNotificationLevel.NOTHING),
                    }
                harness.submit('save', form_data)
                self.assertTrue(harness.hasErrors())


def test_suite():
    return unittest.TestLoader().loadTestsFromName(__name__)
