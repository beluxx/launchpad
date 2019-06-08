# Copyright 2012-2017 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for core services infrastructure."""

from fixtures import FakeLogger
from lazr.restful.interfaces._rest import IHTTPResource
from zope.component import getUtility
from zope.interface import implementer
from zope.publisher.interfaces import NotFound

from lp.app.interfaces.services import (
    IService,
    IServiceFactory,
    )
from lp.services.webapp.interaction import ANONYMOUS
from lp.testing import (
    FakeAdapterMixin,
    login,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.publication import test_traverse


class IFakeService(IService):
    """Fake service interface."""


@implementer(IFakeService, IHTTPResource)
class FakeService:

    name = 'fake_service'


class TestServiceFactory(TestCaseWithFactory, FakeAdapterMixin):
    """Tests for the ServiceFactory"""

    layer = DatabaseFunctionalLayer

    def test_service_traversal(self):
        # Test that traversal to the named service works.
        login(ANONYMOUS)
        fake_service = FakeService()
        self.registerUtility(fake_service, IService, "fake")
        context, view, request = test_traverse(
            'https://launchpad.test/api/devel/+services/fake')
        self.assertEqual(getUtility(IServiceFactory), context)
        self.assertEqual(fake_service, view)

    def test_invalid_traversal(self):
        # Test that traversal to +services without a service specified fails.
        self.useFixture(FakeLogger())
        self.assertRaises(
            NotFound, self.getUserBrowser,
            'https://launchpad.test/api/devel/+services')

    def test_invalid_service(self):
        # Test that traversal an invalid service name fails.
        self.useFixture(FakeLogger())
        self.assertRaises(
            NotFound, self.getUserBrowser,
            'https://launchpad.test/api/devel/+services/invalid')
