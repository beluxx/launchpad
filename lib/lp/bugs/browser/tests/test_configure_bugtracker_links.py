# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for bug tracker configuration link visibility."""

__metaclass__ = type

import unittest

from canonical.launchpad.ftests import ANONYMOUS, login
from canonical.launchpad.layers import BugsLayer
from canonical.testing import LaunchpadFunctionalLayer

from lp.testing import login_person, TestCaseWithFactory
from lp.testing.views import create_initialized_view

from lp.registry.browser.product import ProductBugsMenu
from lp.registry.browser.distribution import DistributionBugsMenu
from lp.registry.browser.distributionsourcepackage import (
    DistributionSourcePackageBugsMenu)


class TestConfigureBugTrackerBase(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestConfigureBugTrackerBase, self).setUp()
        login('test@canonical.com')
        self.target = self.makeTarget()
        self.menu = self.getMenu()
        self.view = create_initialized_view(self.target, name="+index",
                                            layer=BugsLayer)

    def makeTarget(self):
        raise NotImplementedError

    def getOwner(self):
        return self.target.owner


class TestConfigureBugTrackerProduct(TestConfigureBugTrackerBase):

    def makeTarget(self):
        return self.factory.makeProduct(name="vuvuzela")

    def getMenu(self):
        return ProductBugsMenu(self.target)

    def test_link_visible_to_owner(self):
        login_person(self.getOwner())
        link = self.menu.configure_bugtracker()
        self.assertTrue(link.enabled, "Link not enabled")

    def test_link_visible_to_admin(self):
        login('foo.bar@canonical.com')
        link = self.menu.configure_bugtracker()
        self.assertTrue(link.enabled, "Link not enabled")

    def test_not_visible_to_regular_user(self):
        login('no-priv@canonical.com')
        link = self.menu.configure_bugtracker()
        self.assertFalse(link.enabled, "Link enabled")

    def test_not_visible_to_anon(self):
        login(ANONYMOUS)
        link = self.menu.configure_bugtracker()
        self.assertFalse(link.enabled, "Link enabled")


class TestConfigureBugTrackerDistro(TestConfigureBugTrackerBase):

    def makeTarget(self):
        return self.factory.makeDistribution()

    def getMenu(self):
        return DistributionBugsMenu(self.target)

    def test_link_not_present(self):
        login_person(self.getOwner())
        self.assertFalse(hasattr(self.menu, 'configure_bugtracker'))


class TestConfigureBugTrackerDSP(TestConfigureBugTrackerDistro):

    def makeTarget(self):
        return self.factory.makeDistributionSourcePackage()

    def getMenu(self):
        return DistributionSourcePackageBugsMenu(self.target)

    def getOwner(self):
        return self.target.distribution.owner


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestConfigureBugTrackerProduct))
    suite.addTest(unittest.makeSuite(TestConfigureBugTrackerDistro))
    suite.addTest(unittest.makeSuite(TestConfigureBugTrackerDSP))
    return suite


if __name__ == '__main__':
    unittest.TextTestRunner().run(test_suite())
