# Copyright 2005 Canonical Ltd.  All rights reserved.

"""Classes to represent source packages in a distribution."""

__metaclass__ = type

__all__ = [
    'DistributionSourcePackage',
    ]

import apt_pkg
apt_pkg.InitSystem()

from sqlobject import SQLObjectNotFound

from zope.interface import implements

from canonical.lp.dbschema import PackagePublishingStatus

from canonical.launchpad.interfaces import (
    IDistributionSourcePackage, DuplicateBugContactError, DeleteBugContactError)
from canonical.launchpad.database.bugtarget import BugTargetBase
from canonical.database.sqlbase import sqlvalues
from canonical.launchpad.database.bug import (
    BugSet, get_bug_tags, get_bug_tags_open_count)
from canonical.launchpad.database.bugtask import BugTask, BugTaskSet
from canonical.launchpad.database.distributionsourcepackagecache import (
    DistributionSourcePackageCache)
from canonical.launchpad.database.distributionsourcepackagerelease import (
    DistributionSourcePackageRelease)
from canonical.launchpad.database.packagebugcontact import PackageBugContact
from canonical.launchpad.database.publishing import (
    SourcePackagePublishingHistory)
from canonical.launchpad.database.sourcepackagerelease import (
    SourcePackageRelease)
from canonical.launchpad.database.sourcepackage import SourcePackage
from canonical.launchpad.database.supportcontact import SupportContact
from canonical.launchpad.database.ticket import Ticket, TicketSet
from canonical.launchpad.helpers import shortlist

_arg_not_provided = object()

class DistributionSourcePackage(BugTargetBase):
    """This is a "Magic Distribution Source Package". It is not an
    SQLObject, but instead it represents a source package with a particular
    name in a particular distribution. You can then ask it all sorts of
    things about the releases that are published under its name, the latest
    or current release, etc.
    """

    implements(IDistributionSourcePackage)

    def __init__(self, distribution, sourcepackagename):
        self.distribution = distribution
        self.sourcepackagename = sourcepackagename

    @property
    def name(self):
        """See IDistributionSourcePackage."""
        return self.sourcepackagename.name

    @property
    def displayname(self):
        """See IDistributionSourcePackage."""
        return '%s in %s' % (
            self.sourcepackagename.name, self.distribution.name)

    @property
    def bugtargetname(self):
        """See IBugTarget."""
        return "%s (%s)" % (self.name, self.distribution.displayname)

    @property
    def title(self):
        """See IDistributionSourcePackage."""
        return 'Source Package "%s" in %s' % (
            self.sourcepackagename.name, self.distribution.title)

    def __getitem__(self, version):
        return self.getVersion(version)

    def getVersion(self, version):
        """See IDistributionSourcePackage."""
        spph = SourcePackagePublishingHistory.select("""
            SourcePackagePublishingHistory.distrorelease =
                DistroRelease.id AND
            DistroRelease.distribution = %s AND
            SourcePackagePublishingHistory.sourcepackagerelease =
                SourcePackageRelease.id AND
            SourcePackageRelease.sourcepackagename = %s AND
            SourcePackageRelease.version = %s AND
            SourcePackagePublishingHistory.status != %s
            """ % sqlvalues(self.distribution, self.sourcepackagename,
                            version, PackagePublishingStatus.REMOVED),
            orderBy='-datecreated',
            prejoinClauseTables=['SourcePackageRelease'],
            clauseTables=['DistroRelease', 'SourcePackageRelease'])
        if spph.count() == 0:
            return None
        return DistributionSourcePackageRelease(
            distribution=self.distribution,
            sourcepackagerelease=spph[0].sourcepackagerelease)

    @property
    def currentrelease(self):
        """See IDistributionSourcePackage."""
        sprs = SourcePackageRelease.select("""
            SourcePackageRelease.sourcepackagename = %s AND
            SourcePackageRelease.id =
                SourcePackagePublishingHistory.sourcepackagerelease AND
            SourcePackagePublishingHistory.distrorelease =
                DistroRelease.id AND
            DistroRelease.distribution = %s AND
            SourcePackagePublishingHistory.status != %s
            """ % sqlvalues(self.sourcepackagename, self.distribution,
                            PackagePublishingStatus.REMOVED),
            orderBy='datecreated',
            clauseTables=['SourcePackagePublishingHistory', 'DistroRelease'])

        # safely sort by version
        compare = lambda a,b: apt_pkg.VersionCompare(a.version, b.version)
        releases = sorted(shortlist(sprs, 30), cmp=compare)
        if len(releases) == 0:
            return None

        return DistributionSourcePackageRelease(
            distribution=self.distribution,
            sourcepackagerelease=releases[-1])

    def bugtasks(self, quantity=None):
        """See IDistributionSourcePackage."""
        return BugTask.select("""
            distribution=%s AND
            sourcepackagename=%s
            """ % sqlvalues(self.distribution.id,
                            self.sourcepackagename.id),
            orderBy='-datecreated',
            limit=quantity)

    @property
    def bugcontacts(self):
        """See IDistributionSourcePackage."""
        # Use "list" here because it's possible that this list will be longer
        # than a "shortlist", though probably uncommon.
        contacts = PackageBugContact.selectBy(
            distribution=self.distribution,
            sourcepackagename=self.sourcepackagename)
        contacts.prejoin(["bugcontact"])
        return list(contacts)

    def addBugContact(self, person):
        """See IDistributionSourcePackage."""
        contact_already_exists = self.isBugContact(person)

        if contact_already_exists:
            raise DuplicateBugContactError(
                "%s is already one of the bug contacts for %s." %
                (person.name, self.displayname))
        else:
            PackageBugContact(
                distribution=self.distribution,
                sourcepackagename=self.sourcepackagename,
                bugcontact=person)

    def removeBugContact(self, person):
        """See IDistributionSourcePackage."""
        contact_to_remove = self.isBugContact(person)

        if not contact_to_remove:
            raise DeleteBugContactError("%s is not a bug contact for this package.")
        else:
            contact_to_remove.destroySelf()

    def isBugContact(self, person):
        """See IDistributionSourcePackage."""
        package_bug_contact = PackageBugContact.selectOneBy(
            distribution=self.distribution,
            sourcepackagename=self.sourcepackagename,
            bugcontact=person)

        if package_bug_contact:
            return package_bug_contact
        else:
            return False

    @property
    def binary_package_names(self):
        """See IDistributionSourcePackage."""
        cache = DistributionSourcePackageCache.selectOne("""
            distribution = %s AND
            sourcepackagename = %s
            """ % sqlvalues(self.distribution.id, self.sourcepackagename.id))
        if cache is None:
            return None
        return cache.binpkgnames

    @property
    def by_distroreleases(self):
        """See IDistributionSourcePackage."""
        result = []
        for release in self.distribution.releases:
            candidate = SourcePackage(self.sourcepackagename, release)
            if candidate.currentrelease:
                result.append(candidate)
        return result

    @property
    def publishing_history(self):
        """See IDistributionSourcePackage."""
        return self._getPublishingHistoryQuery()

    @property
    def current_publishing_records(self):
        """See IDistributionSourcePackage."""
        status = PackagePublishingStatus.PUBLISHED
        return self._getPublishingHistoryQuery(status)

    def _getPublishingHistoryQuery(self, status=None):
        query = """
            DistroRelease.distribution = %s AND
            SourcePackagePublishingHistory.distrorelease =
                DistroRelease.id AND
            SourcePackagePublishingHistory.sourcepackagerelease =
                SourcePackageRelease.id AND
            SourcePackageRelease.sourcepackagename = %s
            """ % sqlvalues(self.distribution.id,
                            self.sourcepackagename.id)

        if status is not None:
            query += ("AND SourcePackagePublishingHistory.status = %s"
                      % sqlvalues(status))

        return SourcePackagePublishingHistory.select(query,
            clauseTables=['DistroRelease', 'SourcePackageRelease'],
            prejoinClauseTables=['SourcePackageRelease'],
            orderBy='-datecreated')

    @property
    def releases(self):
        """See IDistributionSourcePackage."""
        ret = SourcePackagePublishingHistory.select("""
            sourcepackagepublishinghistory.distrorelease = distrorelease.id AND
            distrorelease.distribution = %s AND
            sourcepackagepublishinghistory.sourcepackagerelease =
                sourcepackagerelease.id AND
            sourcepackagerelease.sourcepackagename = %s
            """ % sqlvalues(self.distribution.id, self.sourcepackagename.id),
            orderBy='-datecreated',
            clauseTables=['distrorelease', 'sourcepackagerelease'])
        result = []
        versions = set()
        for spp in ret:
            if spp.sourcepackagerelease.version not in versions:
                versions.add(spp.sourcepackagerelease.version)
                dspr = DistributionSourcePackageRelease(
                    distribution=self.distribution,
                    sourcepackagerelease=spp.sourcepackagerelease)
                result.append(dspr)
        return result

    # ticket related interfaces
    def tickets(self, quantity=None):
        """See ITicketTarget."""
        return Ticket.select("""
            distribution=%s AND
            sourcepackagename=%s
            """ % sqlvalues(self.distribution.id,
                            self.sourcepackagename.id),
            orderBy='-datecreated',
            limit=quantity)

    def newTicket(self, owner, title, description):
        """See ITicketTarget."""
        return TicketSet().new(
            title=title, description=description, owner=owner,
            distribution=self.distribution,
            sourcepackagename=self.sourcepackagename)

    def getTicket(self, ticket_num):
        """See ITicketTarget."""
        # first see if there is a ticket with that number
        try:
            ticket = Ticket.get(ticket_num)
        except SQLObjectNotFound:
            return None
        # now verify that that ticket is actually for this target
        if ticket.distribution != self.distribution:
            return None
        if ticket.sourcepackagename != self.sourcepackagename:
            return None
        return ticket

    def addSupportContact(self, person):
        """See ITicketTarget."""
        if person in self.support_contacts:
            return False
        SupportContact(
            product=None, person=person,
            sourcepackagename=self.sourcepackagename,
            distribution=self.distribution)
        return True

    def removeSupportContact(self, person):
        """See ITicketTarget."""
        if person not in self.support_contacts:
            return False
        support_contact_entry = SupportContact.selectOneBy(
            distribution=self.distribution,
            sourcepackagename=self.sourcepackagename,
            person=person)
        support_contact_entry.destroySelf()
        return True

    @property
    def support_contacts(self):
        """See ITicketTarget."""
        support_contacts = SupportContact.selectBy(
            distribution=self.distribution,
            sourcepackagename=self.sourcepackagename)

        return shortlist([
            support_contact.person for support_contact in support_contacts
            ],
            longest_expected=100)

    def __eq__(self, other):
        """See IDistributionSourcePackage."""
        return (
            (IDistributionSourcePackage.providedBy(other)) and
            (self.distribution.id == other.distribution.id) and
            (self.sourcepackagename.id == other.sourcepackagename.id))

    def __ne__(self, other):
        """See IDistributionSourcePackage."""
        return not self.__eq__(other)

    def _getBugTaskContextWhereClause(self):
        """See BugTargetBase."""
        return (
            "BugTask.distribution = %d AND BugTask.sourcepackagename = %d" % (
            self.id, self.sourcepackagename.id))

    def searchTasks(self, search_params):
        """See IBugTarget."""
        search_params.setSourcePackage(self)
        return BugTaskSet().search(search_params)

    def getUsedBugTags(self):
        """See IBugTarget."""
        return self.distribution.getUsedBugTags()

    def getUsedBugTagsWithOpenCounts(self, user):
        """See IBugTarget."""
        return get_bug_tags_open_count(
            "BugTask.distribution = %s" % sqlvalues(self.distribution),
            user,
            count_subcontext_clause="BugTask.sourcepackagename = %s" % (
                sqlvalues(self.sourcepackagename)))

    def createBug(self, bug_params):
        """See IBugTarget."""
        bug_params.setBugTarget(
            distribution=self.distribution,
            sourcepackagename=self.sourcepackagename)
        return BugSet().createBug(bug_params)
