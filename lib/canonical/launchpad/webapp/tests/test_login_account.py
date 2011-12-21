# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import cgi
from datetime import datetime

import lazr.uri
from zope.component import getUtility
from zope.event import notify
from zope.session.interfaces import ISession

from canonical.config import config
from canonical.launchpad.ftests import (
    ANONYMOUS,
    login,
    )
from canonical.launchpad.webapp.authentication import LaunchpadPrincipal
from canonical.launchpad.webapp.interfaces import (
    CookieAuthLoggedInEvent,
    ILaunchpadPrincipal,
    IPlacelessAuthUtility,
    )
from canonical.launchpad.webapp.login import (
    CookieLogoutPage,
    logInPrincipal,
    logoutPerson,
    )
from canonical.launchpad.webapp.servers import LaunchpadTestRequest
from canonical.testing.layers import DatabaseFunctionalLayer
from lp.services.identity.interfaces.account import (
    AccountCreationRationale,
    IAccountSet,
    )
from lp.testing import TestCaseWithFactory


class TestLoginAndLogout(TestCaseWithFactory):
    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.request = LaunchpadTestRequest()
        # We create an account without a Person here just to make sure the
        # person and account created later don't end up with the same IDs,
        # which could happen since they're both sequential.
        # We need them to be different for one of our tests here.
        getUtility(IAccountSet).new(
            AccountCreationRationale.UNKNOWN, 'Dummy name')
        person = self.factory.makePerson('foo.bar@example.com')
        self.failIfEqual(person.id, person.account.id)
        self.principal = LaunchpadPrincipal(
            person.account.id, person.displayname,
            person.displayname, person)

    def test_logging_in_and_logging_out(self):
        # A test showing that we can authenticate the request after
        # logInPrincipal() is called, and after logoutPerson() we can no
        # longer authenticate it.

        # This is to setup an interaction so that we can call logInPrincipal
        # below.
        login('foo.bar@example.com')

        logInPrincipal(self.request, self.principal, 'foo.bar@example.com')
        session = ISession(self.request)
        # logInPrincipal() stores the account ID in a variable named
        # 'accountid'.
        self.failUnlessEqual(
            session['launchpad.authenticateduser']['accountid'],
            self.principal.id)

        # Ensure we are using cookie auth.
        self.assertIsNotNone(
            self.request.response.getCookie(config.launchpad_session.cookie)
            )

        principal = getUtility(IPlacelessAuthUtility).authenticate(
            self.request)
        self.failUnlessEqual(self.principal.id, principal.id)

        logoutPerson(self.request)

        principal = getUtility(IPlacelessAuthUtility).authenticate(
            self.request)
        self.failUnless(principal is None)

    def test_CookieLogoutPage(self):
        # This test shows that the CookieLogoutPage redirects as we expect:
        # first to loggerhead for it to log out (see bug 574493) and then
        # to our OpenId provider for it to log out (see bug 568106).  This
        # will need to be readdressed when we want to accept other OpenId
        # providers, unfortunately.

        # This is to setup an interaction so that we can call logInPrincipal
        # below.
        login('foo.bar@example.com')

        logInPrincipal(self.request, self.principal, 'foo.bar@example.com')

        # Normally CookieLogoutPage is magically mixed in with a base class
        # that accepts context and request and sets up other things.  We're
        # just going to put the request on the base class ourselves for this
        # test.

        view = CookieLogoutPage()
        view.request = self.request

        # We need to set the session cookie so it can be expired.
        self.request.response.setCookie(
            config.launchpad_session.cookie, 'xxx')

        # Now we logout.

        result = view.logout()

        # We should, in fact, be logged out (this calls logoutPerson).

        principal = getUtility(IPlacelessAuthUtility).authenticate(
            self.request)
        self.failUnless(principal is None)

        # The view should have redirected us, with no actual response body.

        self.assertEquals(self.request.response.getStatus(), 302)
        self.assertEquals(result, '')

        # We are redirecting to Loggerhead, to ask it to logout.

        location = lazr.uri.URI(self.request.response.getHeader('location'))
        self.assertEquals(location.host, 'bazaar.launchpad.dev')
        self.assertEquals(location.scheme, 'https')
        self.assertEquals(location.path, '/+logout')

        # That page should then redirect to our OpenId provider to logout,
        # which we provide in our query string.  See
        # launchpad_loggerhead.tests.TestLogout for the pertinent tests.

        query = cgi.parse_qs(location.query)
        self.assertEquals(
            query['next_to'][0], 'http://testopenid.dev/+logout')

    def test_logging_in_and_logging_out_the_old_way(self):
        # A test showing that we can authenticate a request that had the
        # person/account ID stored in the 'personid' session variable instead
        # of 'accountid' -- where it's stored by logInPrincipal(). Also shows
        # that after logoutPerson() we can no longer authenticate it.
        # This is just for backwards compatibility.

        # This is to setup an interaction so that we can do the same thing
        # that's done by logInPrincipal() below.
        login('foo.bar@example.com')

        session = ISession(self.request)
        authdata = session['launchpad.authenticateduser']
        self.request.setPrincipal(self.principal)
        authdata['personid'] = self.principal.person.id
        authdata['logintime'] = datetime.utcnow()
        authdata['login'] = 'foo.bar@example.com'
        notify(CookieAuthLoggedInEvent(self.request, 'foo.bar@example.com'))

        # This is so that the authenticate() call below uses cookie auth.
        self.request.response.setCookie(
            config.launchpad_session.cookie, 'xxx')

        principal = getUtility(IPlacelessAuthUtility).authenticate(
            self.request)
        self.failUnlessEqual(self.principal.id, principal.id)
        self.failUnlessEqual(self.principal.person, principal.person)

        logoutPerson(self.request)

        principal = getUtility(IPlacelessAuthUtility).authenticate(
            self.request)
        self.failUnless(principal is None)


class TestLoggingInWithPersonlessAccount(TestCaseWithFactory):
    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.request = LaunchpadTestRequest()
        login(ANONYMOUS)
        account_set = getUtility(IAccountSet)
        account, email = account_set.createAccountAndEmail(
            'foo@example.com', AccountCreationRationale.UNKNOWN,
            'Display name', 'password')
        self.principal = LaunchpadPrincipal(
            account.id, account.displayname, account.displayname, account)
        login('foo@example.com')

    def test_logInPrincipal(self):
        # logInPrincipal() will log the given principal in and not worry about
        # its lack of an associated Person.
        logInPrincipal(self.request, self.principal, 'foo@example.com')

        # Ensure we are using cookie auth.
        self.assertIsNotNone(
            self.request.response.getCookie(config.launchpad_session.cookie)
            )

        placeless_auth_utility = getUtility(IPlacelessAuthUtility)
        principal = placeless_auth_utility.authenticate(self.request)
        self.failUnless(ILaunchpadPrincipal.providedBy(principal))
        self.failUnless(principal.person is None)
