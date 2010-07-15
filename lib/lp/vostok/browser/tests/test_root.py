# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""XXX: Module docstring goes here."""

__metaclass__ = type

import unittest

from zope.app.publisher.browser import getDefaultViewName
from z3c.ptcompat import ViewPageTemplateFile
from zope.component import getMultiAdapter

from canonical.testing.layers import FunctionalLayer

from lp.testing import TestCase
from lp.vostok.browser.root import VostokRootView
from lp.vostok.browser.tests.request import VostokTestRequest
from lp.vostok.publisher import VostokRoot

class TestRootRegistrations(TestCase):

    layer = FunctionalLayer

    def test_root_default_view_name(self):
        # The default view for the vostok root object is called "+index".
        view_name = getDefaultViewName(VostokRoot(), VostokTestRequest())
        self.assertEquals('+index', view_name)

    def test_root_index_view(self):
        # VostokRootView is registered as the view for the VostokRoot object.
        view = getMultiAdapter(
            (VostokRoot(), VostokTestRequest()), name='+index')
        view.initialize()
        self.assertIsInstance(view, VostokRootView)


class FakeDistribution:
    pass


class FakeRootView:

    page = ViewPageTemplateFile('../../templates/root.pt')

    @property
    def distributions(self):
        return [FakeDistribution()]


class TestRootTemplate(TestCase):

    layer = FunctionalLayer

    def test_render(self):
        view = FakeRootView()
        view.request = VostokTestRequest()
        view.context = VostokRoot()
        print view.page()


def test_suite():
    return unittest.TestLoader().loadTestsFromName(__name__)
