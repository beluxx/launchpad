# Copyright 2004 Canonical Ltd.  All rights reserved.
"""Stuff to do with logging in and logging out."""

__metaclass__ = type

from datetime import datetime

from zope.component import getUtility
from zope.app.session.interfaces import ISession
from zope.event import notify

from canonical.launchpad.webapp.interfaces import IPlacelessLoginSource
from canonical.launchpad.webapp.interfaces import CookieAuthLoggedInEvent
from canonical.launchpad.webapp.interfaces import LoggedOutEvent
from canonical.launchpad.interfaces import ILoginTokenSet, IPersonSet
from canonical.launchpad.mail.sendmail import simple_sendmail
from canonical.lp.dbschema import LoginTokenType
from canonical.auth.browser import well_formed_email


class BasicLoginPage:

    def isSameHost(self, url):
        """Returns True if the url appears to be from the same host as we are.
        """
        return url.startswith(self.request.getApplicationURL())

    def login(self):
        referer = self.request.getHeader('referer')  # Traditional w3c speling
        if referer and self.isSameHost(referer):
            self.request.response.redirect(referer)
        else:
            self.request.response.redirect(self.request.getURL(1))
        return ''


class CookieLoginPage:

    was_logged_in = False
    errortext = None

    def process_form(self):
        """Process the form data.

        If there is an error, assign a string containing a description
        of the error to self.errortext for presentation to the user.
        """
        email = self.request.form.get('email')
        password = self.request.form.get('password')
        submitted = self.request.form.get('SUBMIT')
        if not submitted:
            return ''
        if not email or not password:
            self.errortext = "Enter your email address and password."
            return ''
        loginsource = getUtility(IPlacelessLoginSource)
        principal = loginsource.getPrincipalByLogin(email)
        if principal is not None and principal.validate(password):
            self._logInPerson(principal, email)
            self.was_logged_in = True
        else:
            self.errortext = "The email address and password do not match."
        return ''

    def _logInPerson(self, principal, email):
        session = ISession(self.request)
        authdata = session['launchpad.authenticateduser']
        previous_login = authdata.get('personid')
        authdata['personid'] = principal.id
        authdata['logintime'] = datetime.utcnow()
        authdata['login'] = email
        notify(CookieAuthLoggedInEvent(self.request, email))


class CookieLogoutPage:

    def logout(self):
        session = ISession(self.request)
        authdata = session['launchpad.authenticateduser']
        previous_login = authdata.get('personid')
        authdata['personid'] = None
        authdata['logintime'] = datetime.utcnow()
        notify(LoggedOutEvent(self.request))
        return ''


class ForgottenPasswordPage:

    errortext = None
    submitted = False

    def process_form(self):
        if self.request.method != "POST":
            return

        email = self.request.form.get("email").strip()
        person = getUtility(IPersonSet).getByEmail(email)
        if person is None:
            self.errortext = ("Your account details have not been found. "
                              "Please check your subscription email "
                              "address and try again.")
            return

        logintokenset = getUtility(ILoginTokenSet)
        token = logintokenset.new(person, email, email,
                                  LoginTokenType.PASSWORDRECOVERY)
        sendPasswordResetEmail(token, self.request.getApplicationURL())
        self.submitted = True
        return

    def success(self):
        return self.submitted and not self.errortext


def sendPasswordResetEmail(token, appurl):
    template_file = 'lib/canonical/launchpad/webapp/forgottenpassword.txt'
    template = open(template_file).read()
    fromaddress = "Launchpad Team <noreply@canonical.com>"

    replacements = {'longstring': token.token,
                    'toaddress': token.email, 
                    'appurl': appurl}
    message = template % replacements

    subject = "Launchpad: Forgotten Password"
    simple_sendmail(fromaddress, token.email, subject, message)


class JoinLaunchpadView(object):

    def __init__(self, context, request):
        self.context = context
        self.request = request
        self.errormessage = None
        self.submitted = False
        self.email = None

    def formSubmitted(self):
        if self.request.method != "POST":
            return False

        self.email = self.request.form.get("email").strip()
        person = getUtility(IPersonSet).getByEmail(self.email)
        if person is not None:
            msg = ('The email address %s is already registered in our system. '
                   'If you are sure this is your email address, please go to '
                   'the <a href="/+forgottenpassword">Forgotten Password</a> '
                   'page and follow the instructions to retrieve your '
                   'password.') % self.email
            self.errormessage = msg
            return False

        if not well_formed_email(self.email):
            self.errormessage = ("The email address you provided isn't "
                                 "valid. Please verify it and try again.")
            return False

        logintokenset = getUtility(ILoginTokenSet)
        # New user: requester and requesteremail are None.
        token = logintokenset.new(None, None, self.email,
                                  LoginTokenType.NEWACCOUNT)
        sendNewUserEmail(token, self.request.getApplicationURL())
        self.submitted = True
        return True

    def success(self):
        return self.submitted and not self.errormessage


def sendNewUserEmail(token, appurl):
    template = open('lib/canonical/launchpad/webapp/newuser-email.txt').read()
    replacements = {'longstring': token.token, 'appurl': appurl}
    message = template % replacements

    fromaddress = "The Launchpad Team <noreply@canonical.com>"
    subject = "Launchpad Account Creation Instructions"
    simple_sendmail(fromaddress, token.email, subject, message)

