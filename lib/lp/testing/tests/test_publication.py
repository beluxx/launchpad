# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the helpers in `lp.testing.publication`."""

__metaclass__ = type

from lazr.restful import EntryResource
from zope.app.pagetemplate.simpleviewclass import simple
from zope.component import (
    getSiteManager,
    getUtility,
    )
from zope.interface import Interface
from zope.publisher.interfaces.browser import IDefaultBrowserLayer
from zope.security.checker import (
    Checker,
    CheckerPublic,
    defineChecker,
    )

from canonical.launchpad.webapp.interfaces import (
    ILaunchBag,
    ILaunchpadRoot,
    )
from canonical.launchpad.webapp.publisher import get_current_browser_request
from canonical.launchpad.webapp.servers import LaunchpadTestRequest
from canonical.testing.layers import DatabaseFunctionalLayer
from lp.testing import (
    ANONYMOUS,
    login,
    login_person,
    TestCaseWithFactory,
    )
from lp.testing.publication import test_traverse


class TestTestTraverse(TestCaseWithFactory):
    # Tests for `test_traverse`

    layer = DatabaseFunctionalLayer

    def registerViewCallable(self, view_callable):
        """Return a URL traversing to which will call `view_callable`.

        :param view_callable: Will be called with no arguments during
            traversal.
        """
        # This method is completely out of control.  Thanks, Zope.
        name = '+' + self.factory.getUniqueString()

        class new_class(simple):
            def __init__(self, context, request):
                self.context = context
                view_callable()
        required = {}
        for n in ('browserDefault', '__call__', 'publishTraverse'):
            required[n] = CheckerPublic
        defineChecker(new_class, Checker(required))
        getSiteManager().registerAdapter(
            new_class, (ILaunchpadRoot, IDefaultBrowserLayer), Interface,
            name)
        self.addCleanup(
            getSiteManager().unregisterAdapter, new_class,
            (ILaunchpadRoot, IDefaultBrowserLayer), Interface, name)
        return 'https://launchpad.dev/' + name

    def test_traverse_simple(self):
        # test_traverse called with a product URL returns the product
        # as the traversed object.
        login(ANONYMOUS)
        product = self.factory.makeProduct()
        context, view, request = test_traverse(
            'https://launchpad.dev/' + product.name)
        self.assertEqual(product, context)

    def test_request_is_current_during_traversal(self):
        # The request that test_traverse creates is current during
        # traversal in the sense of get_current_browser_request.
        login(ANONYMOUS)
        requests = []

        def record_current_request():
            requests.append(get_current_browser_request())
        context, view, request = test_traverse(
            self.registerViewCallable(record_current_request))
        self.assertEqual(1, len(requests))
        self.assertIs(request, requests[0])

    def test_participation_restored(self):
        # test_traverse restores the interaction (and hence
        # participation) that was present before it was called.
        request = LaunchpadTestRequest()
        login(ANONYMOUS, request)
        product = self.factory.makeProduct()
        test_traverse('https://launchpad.dev/' + product.name)
        self.assertIs(request, get_current_browser_request())

    def test_uses_current_user(self):
        # test_traverse performs the traversal as the currently logged
        # in user.
        person = self.factory.makePerson()
        login_person(person)
        users = []

        def record_user():
            users.append(getUtility(ILaunchBag).user)
        context, view, request = test_traverse(
            self.registerViewCallable(record_user))
        self.assertEqual(1, len(users))
        self.assertEqual(person, users[0])

    def test_webservice_traverse(self):
        login(ANONYMOUS)
        product = self.factory.makeProduct()
        context, view, request = test_traverse(
            'http://api.launchpad.dev/devel/' + product.name)
        self.assertEqual(product, context)
        self.assertIsInstance(view, EntryResource)
