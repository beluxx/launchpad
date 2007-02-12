# Copyright 2006 Canonical Ltd.  All rights reserved.

__metaclass__ = type
__all__ = ['EmailAddress', 'EmailAddressSet']

from zope.interface import implements

from sqlobject import ForeignKey, StringCol

from canonical.database.sqlbase import quote, SQLBase
from canonical.database.enumcol import EnumCol

from canonical.lp.dbschema import EmailAddressStatus

from canonical.launchpad.interfaces import (
    EmailAddressAlreadyTaken, IEmailAddress, IEmailAddressSet)


class EmailAddress(SQLBase):
    implements(IEmailAddress)

    _table = 'EmailAddress'
    _defaultOrder = ['email']

    email = StringCol(dbName='email', notNull=True, unique=True)
    status = EnumCol(dbName='status', schema=EmailAddressStatus, notNull=True)
    person = ForeignKey(dbName='person', foreignKey='Person', notNull=True)

    @property
    def statusname(self):
        return self.status.title


class EmailAddressSet:
    implements(IEmailAddressSet)

    def getByPerson(self, person):
        """See IEmailAddressSet."""
        return EmailAddress.selectBy(person=person, orderBy='email')

    def getByEmail(self, email):
        """See IEmailAddressSet."""
        return EmailAddress.selectOne(
            "lower(email) = %s" % quote(email.strip().lower()))

    def new(self, email, person, status=EmailAddressStatus.NEW):
        """See IEmailAddressSet."""
        email = email.strip()
        if self.getByEmail(email) is not None:
            raise EmailAddressAlreadyTaken(
                "The email address %s is already registered." % email)
        assert status in EmailAddressStatus.items
        return EmailAddress(email=email, status=status, person=person)

