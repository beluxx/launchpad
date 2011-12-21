# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# pylint: disable-msg=E0611,W0212

__metaclass__ = type
__all__ = [
    'LoginToken',
    'LoginTokenSet',
    ]

from itertools import chain

import pytz
from sqlobject import (
    ForeignKey,
    SQLObjectNotFound,
    StringCol,
    )
from storm.expr import And
from zope.component import getUtility
from zope.interface import implements
from zope.security.proxy import removeSecurityProxy

from canonical.config import config
from canonical.database.constants import UTC_NOW
from canonical.database.datetimecol import UtcDateTimeCol
from canonical.database.enumcol import EnumCol
from canonical.database.sqlbase import (
    SQLBase,
    sqlvalues,
    )
from canonical.launchpad.components.tokens import (
    create_unique_token_for_table,
    )
from canonical.launchpad.helpers import get_email_template
from lp.services.verification.interfaces.authtoken import LoginTokenType
from lp.services.verification.interfaces.logintoken import (
    ILoginToken,
    ILoginTokenSet,
    )
from canonical.launchpad.interfaces.lpstorm import IMasterObject
from canonical.launchpad.webapp import canonical_url
from canonical.launchpad.webapp.interfaces import (
    IStoreSelector,
    MAIN_STORE,
    MASTER_FLAVOR,
    )
from lp.app.errors import NotFoundError
from lp.app.validators.email import valid_email
from lp.registry.interfaces.gpg import IGPGKeySet
from lp.registry.interfaces.person import IPersonSet
from lp.services.gpg.interfaces import IGPGHandler
from lp.services.identity.interfaces.emailaddress import IEmailAddressSet
from lp.services.mail.sendmail import (
    format_address,
    simple_sendmail,
    )


MAIL_APP = 'services/verification'


class LoginToken(SQLBase):
    implements(ILoginToken)
    _table = 'LoginToken'

    redirection_url = StringCol(default=None)
    requester = ForeignKey(dbName='requester', foreignKey='Person')
    requesteremail = StringCol(dbName='requesteremail', notNull=False,
                               default=None)
    email = StringCol(dbName='email', notNull=True)
    token = StringCol(dbName='token', unique=True)
    tokentype = EnumCol(dbName='tokentype', notNull=True, enum=LoginTokenType)
    date_created = UtcDateTimeCol(dbName='created', notNull=True)
    fingerprint = StringCol(dbName='fingerprint', notNull=False,
                            default=None)
    date_consumed = UtcDateTimeCol(default=None)
    password = ''  # Quick fix for Bug #2481

    title = 'Launchpad Email Verification'

    @property
    def requester_account(self):
        """See `ILoginToken`."""
        if self.requester is None or self.requester.account is None:
            return None
        return IMasterObject(self.requester.account)

    def consume(self):
        """See ILoginToken."""
        self.date_consumed = UTC_NOW

        # Find all the unconsumed tokens that we need to consume. We
        # don't bother with consumed tokens for performance reasons.
        if self.fingerprint is not None:
            tokens = LoginTokenSet().searchByFingerprintRequesterAndType(
                self.fingerprint, self.requester, self.tokentype,
                consumed=False)
        else:
            tokens = LoginTokenSet().searchByEmailRequesterAndType(
                self.email, self.requester, self.tokentype,
                consumed=False)

        for token in tokens:
            token.date_consumed = UTC_NOW

    def _send_email(self, from_name, subject, message, headers=None):
        """Send an email to this token's email address."""
        from_address = format_address(
            from_name, config.canonical.noreply_from_address)
        to_address = str(self.email)
        simple_sendmail(
            from_address, to_address, subject, message,
            headers=headers, bulk=False)

    def sendEmailValidationRequest(self):
        """See ILoginToken."""
        template = get_email_template('validate-email.txt', app=MAIL_APP)
        replacements = {'token_url': canonical_url(self),
                        'requester': self.requester.displayname,
                        'requesteremail': self.requesteremail,
                        'toaddress': self.email}
        message = template % replacements
        subject = "Launchpad: Validate your email address"
        self._send_email("Launchpad Email Validator", subject, message)

    def sendGPGValidationRequest(self, key):
        """See ILoginToken."""
        separator = '\n    '
        formatted_uids = '    ' + separator.join(key.emails)

        assert self.tokentype in (LoginTokenType.VALIDATEGPG,
                                  LoginTokenType.VALIDATESIGNONLYGPG)

        # Craft the confirmation message that will be sent to the user.  There
        # are two chunks of text that will be concatenated together into a
        # single text/plain part.  The first chunk will be the clear text
        # instructions providing some extra help for those people who cannot
        # read the encrypted chunk that follows.  The encrypted chunk will
        # have the actual confirmation token in it, however the ability to
        # read this is highly dependent on the mail reader being used, and how
        # that MUA is configured.

        # Here are the instructions that need to be encrypted.
        template = get_email_template('validate-gpg.txt', app=MAIL_APP)
        replacements = {'requester': self.requester.displayname,
                        'requesteremail': self.requesteremail,
                        'displayname': key.displayname,
                        'fingerprint': key.fingerprint,
                        'uids': formatted_uids,
                        'token_url': canonical_url(self)}

        token_text = template % replacements
        salutation = 'Hello,\n\n'
        instructions = ''
        closing = "Thanks,\n\nThe Launchpad Team"

        # Encrypt this part's content if requested.
        if key.can_encrypt:
            gpghandler = getUtility(IGPGHandler)
            token_text = gpghandler.encryptContent(token_text.encode('utf-8'),
                                                   key.fingerprint)
            # In this case, we need to include some clear text instructions
            # for people who do not have an MUA that can decrypt the ASCII
            # armored text.
            instructions = get_email_template(
                'gpg-cleartext-instructions.txt', app=MAIL_APP)

        # Concatenate the message parts and send it.
        text = salutation + instructions + token_text + closing
        from_name = 'Launchpad OpenPGP Key Confirmation'
        subject = 'Launchpad: Confirm your OpenPGP Key'
        self._send_email(from_name, subject, text)

    def sendProfileCreatedEmail(self, profile, comment):
        """See ILoginToken."""
        template = get_email_template('profile-created.txt', app=MAIL_APP)
        replacements = {'token_url': canonical_url(self),
                        'requester': self.requester.displayname,
                        'comment': comment,
                        'profile_url': canonical_url(profile)}
        message = template % replacements

        headers = {'Reply-To': self.requester.preferredemail.email}
        from_name = "Launchpad"
        subject = "Launchpad profile"
        self._send_email(from_name, subject, message, headers=headers)

    def sendMergeRequestEmail(self):
        """See ILoginToken."""
        template = get_email_template('request-merge.txt', app=MAIL_APP)
        from_name = "Launchpad Account Merge"

        dupe = getUtility(IPersonSet).getByEmail(self.email)
        replacements = {'dupename': "%s (%s)" % (dupe.displayname, dupe.name),
                        'requester': self.requester.name,
                        'requesteremail': self.requesteremail,
                        'toaddress': self.email,
                        'token_url': canonical_url(self)}
        message = template % replacements

        subject = "Launchpad: Merge of Accounts Requested"
        self._send_email(from_name, subject, message)

    def sendTeamEmailAddressValidationEmail(self, user):
        """See ILoginToken."""
        template = get_email_template('validate-teamemail.txt', app=MAIL_APP)

        from_name = "Launchpad Email Validator"
        subject = "Launchpad: Validate your team's contact email address"
        replacements = {'team': self.requester.displayname,
                        'requester': '%s (%s)' % (
                            user.displayname, user.name),
                        'toaddress': self.email,
                        'admin_email': config.canonical.admin_address,
                        'token_url': canonical_url(self)}
        message = template % replacements
        self._send_email(from_name, subject, message)

    def sendClaimProfileEmail(self):
        """See ILoginToken."""
        template = get_email_template('claim-profile.txt', app=MAIL_APP)
        from_name = "Launchpad"
        profile = getUtility(IPersonSet).getByEmail(self.email)
        replacements = {'profile_name': (
                            "%s (%s)" % (profile.displayname, profile.name)),
                        'email': self.email,
                        'token_url': canonical_url(self)}
        message = template % replacements

        subject = "Launchpad: Claim Profile"
        self._send_email(from_name, subject, message)

    def sendClaimTeamEmail(self):
        """See `ILoginToken`."""
        template = get_email_template('claim-team.txt', app=MAIL_APP)
        from_name = "Launchpad"
        profile = getUtility(IPersonSet).getByEmail(self.email)
        replacements = {'profile_name': (
                            "%s (%s)" % (profile.displayname, profile.name)),
                        'requester_name': (
                            "%s (%s)" % (self.requester.displayname,
                                         self.requester.name)),
                        'email': self.email,
                        'token_url': canonical_url(self)}
        message = template % replacements
        subject = "Launchpad: Claim existing team"
        self._send_email(from_name, subject, message)

    @property
    def validation_phrase(self):
        """The phrase used to validate sign-only GPG keys"""
        utctime = self.date_created.astimezone(pytz.UTC)
        return 'Please register %s to the\nLaunchpad user %s.  %s UTC' % (
            self.fingerprint, self.requester.name,
            utctime.strftime('%Y-%m-%d %H:%M:%S'))

    def activateGPGKey(self, key, can_encrypt):
        """See `ILoginToken`."""
        gpgkeyset = getUtility(IGPGKeySet)
        requester = self.requester
        lpkey, new = gpgkeyset.activate(requester, key, can_encrypt)

        self.consume()

        if not new:
            return lpkey, new, [], []

        created, owned_by_others = self.createEmailAddresses(key.emails)
        return lpkey, new, created, owned_by_others

    def createEmailAddresses(self, uids):
        """Create EmailAddresses for the GPG UIDs that do not exist yet.

        For each of the given UIDs, check if it is already registered and, if
        not, register it.

        Return a tuple containing the list of newly created emails (as
        strings) and the emails that exist and are already assigned to another
        person (also as strings).
        """
        emailset = getUtility(IEmailAddressSet)
        requester = self.requester
        account = self.requester_account
        emails = chain(requester.validatedemails, [requester.preferredemail])
        # Must remove the security proxy because the user may not be logged in
        # and thus won't be allowed to view the requester's email addresses.
        emails = [
            removeSecurityProxy(email).email.lower() for email in emails]

        created = []
        existing_and_owned_by_others = []
        for uid in uids:
            # Here we use .lower() because the case of email addresses's chars
            # don't matter to us (e.g. 'foo@baz.com' is the same as
            # 'Foo@Baz.com').  However, note that we use the original form
            # when creating a new email.
            if uid.lower() not in emails:
                # EmailAddressSet.getByEmail() is not case-sensitive, so
                # there's no need to do uid.lower() here.
                if emailset.getByEmail(uid) is not None:
                    # This email address is registered but does not belong to
                    # our user.
                    existing_and_owned_by_others.append(uid)
                else:
                    # The email is not yet registered, so we register it for
                    # our user.
                    email = emailset.new(uid, requester, account=account)
                    created.append(uid)

        return created, existing_and_owned_by_others


class LoginTokenSet:
    implements(ILoginTokenSet)

    def __init__(self):
        self.title = 'Launchpad e-mail address confirmation'

    def get(self, id, default=None):
        """See ILoginTokenSet."""
        try:
            return LoginToken.get(id)
        except SQLObjectNotFound:
            return default

    def searchByEmailRequesterAndType(self, email, requester, type,
                                      consumed=None):
        """See ILoginTokenSet."""
        conditions = And(
            LoginToken.email == email,
            LoginToken.requester == requester,
            LoginToken.tokentype == type)

        if consumed is True:
            conditions = And(conditions, LoginToken.date_consumed != None)
        elif consumed is False:
            conditions = And(conditions, LoginToken.date_consumed == None)
        else:
            assert consumed is None, (
                "consumed should be one of {True, False, None}. Got '%s'."
                % consumed)

        # It's important to always use the MASTER_FLAVOR store here
        # because we don't want replication lag to cause a 404 error.
        store = getUtility(IStoreSelector).get(MAIN_STORE, MASTER_FLAVOR)
        return store.find(LoginToken, conditions)

    def deleteByEmailRequesterAndType(self, email, requester, type):
        """See ILoginTokenSet."""
        for token in self.searchByEmailRequesterAndType(
            email, requester, type):
            token.destroySelf()

    def searchByFingerprintRequesterAndType(self, fingerprint, requester,
                                            type, consumed=None):
        """See ILoginTokenSet."""
        conditions = And(
            LoginToken.fingerprint == fingerprint,
            LoginToken.requester == requester,
            LoginToken.tokentype == type)

        if consumed is True:
            conditions = And(conditions, LoginToken.date_consumed != None)
        elif consumed is False:
            conditions = And(conditions, LoginToken.date_consumed == None)
        else:
            assert consumed is None, (
                "consumed should be one of {True, False, None}. Got '%s'."
                % consumed)

        # It's important to always use the MASTER_FLAVOR store here
        # because we don't want replication lag to cause a 404 error.
        store = getUtility(IStoreSelector).get(MAIN_STORE, MASTER_FLAVOR)
        return store.find(LoginToken, conditions)

    def getPendingGPGKeys(self, requesterid=None):
        """See ILoginTokenSet."""
        query = ('date_consumed IS NULL AND '
                 '(tokentype = %s OR tokentype = %s) '
                 % sqlvalues(LoginTokenType.VALIDATEGPG,
                 LoginTokenType.VALIDATESIGNONLYGPG))

        if requesterid:
            query += 'AND requester=%s' % requesterid

        return LoginToken.select(query)

    def deleteByFingerprintRequesterAndType(self, fingerprint, requester,
                                            type):
        tokens = self.searchByFingerprintRequesterAndType(
            fingerprint, requester, type)
        for token in tokens:
            token.destroySelf()

    def new(self, requester, requesteremail, email, tokentype,
            fingerprint=None, redirection_url=None):
        """See ILoginTokenSet."""
        assert valid_email(email)
        if tokentype not in LoginTokenType.items:
            # XXX: Guilherme Salgado, 2005-12-09:
            # Aha! According to our policy, we shouldn't raise ValueError.
            raise ValueError(
                "tokentype is not an item of LoginTokenType: %s" % tokentype)

        token = create_unique_token_for_table(20, LoginToken.token)
        return LoginToken(requester=requester, requesteremail=requesteremail,
                          email=email, token=token, tokentype=tokentype,
                          created=UTC_NOW, fingerprint=fingerprint,
                          redirection_url=redirection_url)

    def __getitem__(self, tokentext):
        """See ILoginTokenSet."""
        token = LoginToken.selectOneBy(token=tokentext)
        if token is None:
            raise NotFoundError(tokentext)
        return token
