# Copyright 2009-2018 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `Account` objects."""

__metaclass__ = type
__all__ = []

from lp.services.identity.interfaces.account import (
    AccountStatus,
    AccountStatusError,
    IAccount,
    )
from lp.testing import (
    login_celebrity,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestAccount(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_account_repr_ansii(self):
        # Verify that ANSI displayname is ascii safe.
        distro = self.factory.makeAccount(u'\xdc-account')
        ignore, displayname, status = repr(distro).rsplit(' ', 2)
        self.assertEqual("'\\xdc-account'", displayname)
        self.assertEqual('(Active)>', status)

    def test_account_repr_unicode(self):
        # Verify that Unicode displayname is ascii safe.
        distro = self.factory.makeAccount(u'\u0170-account')
        ignore, displayname, status = repr(distro).rsplit(' ', 2)
        self.assertEqual("'\\u0170-account'", displayname)

    def assertCannotTransition(self, account, statuses):
        for status in statuses:
            self.assertFalse(
                IAccount['status'].bind(account).constraint(status))
            self.assertRaises(
                AccountStatusError, account.setStatus, status, None, 'Go away')

    def assertCanTransition(self, account, statuses):
        for status in statuses:
            self.assertTrue(
                IAccount['status'].bind(account).constraint(status))
        account.setStatus(status, None, 'No reason')
        self.assertEqual(status, account.status)

    def test_status_from_noaccount(self):
        # The status may change from NOACCOUNT to ACTIVE or CLOSED.
        account = self.factory.makeAccount(status=AccountStatus.NOACCOUNT)
        login_celebrity('admin')
        self.assertCannotTransition(
            account, [AccountStatus.DEACTIVATED, AccountStatus.SUSPENDED])
        self.assertCanTransition(
            account, [AccountStatus.ACTIVE, AccountStatus.CLOSED])

    def test_status_from_active(self):
        # The status may change from ACTIVE to DEACTIVATED, SUSPENDED, or
        # CLOSED.
        account = self.factory.makeAccount(status=AccountStatus.ACTIVE)
        login_celebrity('admin')
        self.assertCannotTransition(account, [AccountStatus.NOACCOUNT])
        self.assertCanTransition(
            account,
            [AccountStatus.DEACTIVATED, AccountStatus.SUSPENDED,
             AccountStatus.CLOSED])

    def test_status_from_deactivated(self):
        # The status may change from DEACTIVATED to ACTIVATED or CLOSED.
        account = self.factory.makeAccount()
        login_celebrity('admin')
        account.setStatus(AccountStatus.DEACTIVATED, None, 'gbcw')
        self.assertCannotTransition(
            account, [AccountStatus.NOACCOUNT, AccountStatus.SUSPENDED])
        self.assertCanTransition(
            account, [AccountStatus.ACTIVE, AccountStatus.CLOSED])

    def test_status_from_suspended(self):
        # The status may change from SUSPENDED to DEACTIVATED or CLOSED.
        account = self.factory.makeAccount()
        login_celebrity('admin')
        account.setStatus(AccountStatus.SUSPENDED, None, 'spammer!')
        self.assertCannotTransition(
            account, [AccountStatus.NOACCOUNT, AccountStatus.ACTIVE])
        self.assertCanTransition(
            account, [AccountStatus.DEACTIVATED, AccountStatus.CLOSED])
