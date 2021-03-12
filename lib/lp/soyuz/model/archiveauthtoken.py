# Copyright 2009-2021 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Database class for table ArchiveAuthToken."""

__metaclass__ = type

__all__ = [
    'ArchiveAuthToken',
    ]

from lazr.uri import URI
import pytz
from storm.locals import (
    DateTime,
    Int,
    Reference,
    Storm,
    Unicode,
    )
from storm.store import Store
from zope.interface import implementer

from lp.registry.model.teammembership import TeamParticipation
from lp.services.database.constants import UTC_NOW
from lp.services.database.interfaces import IStore
from lp.soyuz.enums import ArchiveSubscriberStatus
from lp.soyuz.interfaces.archiveauthtoken import (
    IArchiveAuthToken,
    IArchiveAuthTokenSet,
    )


@implementer(IArchiveAuthToken)
class ArchiveAuthToken(Storm):
    """See `IArchiveAuthToken`."""
    __storm_table__ = 'ArchiveAuthToken'

    id = Int(primary=True)

    archive_id = Int(name='archive', allow_none=False)
    archive = Reference(archive_id, 'Archive.id')

    person_id = Int(name='person', allow_none=True)
    person = Reference(person_id, 'Person.id')

    date_created = DateTime(
        name='date_created', allow_none=False, tzinfo=pytz.UTC)

    date_deactivated = DateTime(
        name='date_deactivated', allow_none=True, tzinfo=pytz.UTC)

    token = Unicode(name='token', allow_none=False)

    name = Unicode(name='name', allow_none=True)

    def deactivate(self):
        """See `IArchiveAuthTokenSet`."""
        self.date_deactivated = UTC_NOW

    @property
    def archive_url(self):
        """Return a custom archive url for basic authentication."""
        normal_url = URI(self.archive.archive_url)
        if self.name:
            name = '+' + self.name
        else:
            name = self.person.name
        auth_url = normal_url.replace(userinfo="%s:%s" % (name, self.token))
        return str(auth_url)

    def asDict(self):
        return {"token": self.token, "archive_url": self.archive_url}


@implementer(IArchiveAuthTokenSet)
class ArchiveAuthTokenSet:
    """See `IArchiveAuthTokenSet`."""
    title = "Archive Tokens in Launchpad"

    def get(self, token_id):
        """See `IArchiveAuthTokenSet`."""
        return IStore(ArchiveAuthToken).get(ArchiveAuthToken, token_id)

    def getByToken(self, token):
        """See `IArchiveAuthTokenSet`."""
        return IStore(ArchiveAuthToken).find(
            ArchiveAuthToken, ArchiveAuthToken.token == token).one()

    def getByArchive(self, archive, valid=False):
        """See `IArchiveAuthTokenSet`."""
        # Circular import.
        from lp.soyuz.model.archivesubscriber import ArchiveSubscriber
        store = Store.of(archive)
        clauses = [
            ArchiveAuthToken.archive == archive,
            ArchiveAuthToken.date_deactivated == None,
            ]
        if valid:
            clauses.extend([
                ArchiveAuthToken.archive_id == ArchiveSubscriber.archive_id,
                ArchiveSubscriber.status == ArchiveSubscriberStatus.CURRENT,
                ArchiveSubscriber.subscriber_id == TeamParticipation.teamID,
                TeamParticipation.personID == ArchiveAuthToken.person_id,
                ])
        return store.find(ArchiveAuthToken, *clauses)

    def getActiveTokenForArchiveAndPerson(self, archive, person):
        """See `IArchiveAuthTokenSet`."""
        return self.getByArchive(archive, valid=True).find(
            ArchiveAuthToken.person == person).one()

    def getActiveTokenForArchiveAndPersonName(self, archive, person_name):
        """See `IArchiveAuthTokenSet`."""
        # Circular import.
        from lp.registry.model.person import Person
        return self.getByArchive(archive, valid=True).find(
            ArchiveAuthToken.person == Person.id,
            Person.name == person_name).one()

    def getActiveNamedTokenForArchive(self, archive, name):
        """See `IArchiveAuthTokenSet`."""
        return self.getByArchive(archive).find(
            ArchiveAuthToken.name == name).one()

    def getActiveNamedTokensForArchive(self, archive, names=None):
        """See `IArchiveAuthTokenSet`."""
        if names:
            return self.getByArchive(archive).find(
                ArchiveAuthToken.name.is_in(names))
        else:
            return self.getByArchive(archive).find(
                ArchiveAuthToken.name != None)

    def deactivateNamedTokensForArchive(self, archive, names):
        """See `IArchiveAuthTokenSet`."""
        tokens = self.getActiveNamedTokensForArchive(archive, names)
        tokens.set(date_deactivated=UTC_NOW)
