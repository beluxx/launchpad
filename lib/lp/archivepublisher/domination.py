# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Archive Domination class.

We call 'domination' the procedure used to identify and supersede all
old versions for a given publication, source or binary, inside a suite
(distroseries + pocket, for instance, gutsy or gutsy-updates).

It also processes the superseded publications and makes the ones with
unnecessary files 'eligible for removal', which will then be considered
for archive removal.  See deathrow.py.

In order to judge if a source is 'eligible for removal' it also checks
if its resulting binaries are not necessary any more in the archive, i.e.,
old binary publications can (and should) hold sources in the archive.

Source version life-cycle example:

  * foo_2.1: currently published, source and binary files live in the archive
             pool and it is listed in the archive indexes.

  * foo_2.0: superseded, it's not listed in archive indexes but one of its
             files is used for foo_2.1 (the orig.tar.gz) or foo_2.1 could
             not build for one or more architectures that foo_2.0 could;

  * foo_1.8: eligible for removal, none of its files are required in the
             archive since foo_2.0 was published (new orig.tar.gz) and none
             of its binaries are published (foo_2.0 was completely built)

  * foo_1.0: removed, it already passed through the quarantine period and its
             files got removed from the archive.

Note that:

  * PUBLISHED and SUPERSEDED are publishing statuses.

  * 'eligible for removal' is a combination of SUPERSEDED or DELETED
    publishing status and a defined (non-empty) 'scheduleddeletiondate'.

  * 'removed' is a combination of 'eligible for removal' and a defined
    (non-empy) 'dateremoved'.

The 'domination' procedure is the 2nd step of the publication pipeline and
it is performed for each suite using:

  * judgeAndDominate(distroseries, pocket)

"""

__metaclass__ = type

__all__ = ['Dominator']

from datetime import timedelta

import apt_pkg
from storm.expr import (
    And,
    Count,
    Select,
    )

from canonical.database.constants import UTC_NOW
from canonical.database.sqlbase import (
    flush_database_updates,
    sqlvalues,
    )
from canonical.launchpad.interfaces.lpstorm import IStore
from lp.registry.model.sourcepackagename import SourcePackageName
from lp.soyuz.enums import (
    BinaryPackageFormat,
    PackagePublishingStatus,
    )
from lp.soyuz.interfaces.publishing import inactive_publishing_status
from lp.soyuz.model.binarypackagename import BinaryPackageName
from lp.soyuz.model.binarypackagerelease import BinaryPackageRelease
from lp.soyuz.model.sourcepackagerelease import SourcePackageRelease

# Days before a package will be removed from disk.
STAY_OF_EXECUTION = 1


# Ugly, but works
apt_pkg.InitSystem()


def join_spr_spn():
    """Join condition: SourcePackageRelease/SourcePackageName."""
    return (
        SourcePackageName.id == SourcePackageRelease.sourcepackagenameID)


def join_spph_spr():
    """Join condition: SourcePackageRelease/SourcePackagePublishingHistory.
    """
    # Avoid circular imports.
    from lp.soyuz.model.publishing import SourcePackagePublishingHistory

    return (
        SourcePackageRelease.id ==
            SourcePackagePublishingHistory.sourcepackagereleaseID)


class SourcePublicationTraits:
    """Basic generalized attributes for `SourcePackagePublishingHistory`.

    Used by `GeneralizedPublication` to hide the differences from
    `BinaryPackagePublishingHistory`.
    """
    @staticmethod
    def getPackageName(spph):
        """Return the name of this publication's source package."""
        return spph.sourcepackagerelease.sourcepackagename.name

    @staticmethod
    def getPackageRelease(spph):
        """Return this publication's `SourcePackageRelease`."""
        return spph.sourcepackagerelease


class BinaryPublicationTraits:
    """Basic generalized attributes for `BinaryPackagePublishingHistory`.

    Used by `GeneralizedPublication` to hide the differences from
    `SourcePackagePublishingHistory`.
    """
    @staticmethod
    def getPackageName(bpph):
        """Return the name of this publication's binary package."""
        return bpph.binarypackagerelease.binarypackagename.name

    @staticmethod
    def getPackageRelease(bpph):
        """Return this publication's `BinaryPackageRelease`."""
        return bpph.binarypackagerelease


class GeneralizedPublication:
    """Generalize handling of publication records.

    This allows us to write code that can be dealing with either
    `SourcePackagePublishingHistory`s or `BinaryPackagePublishingHistory`s
    without caring which.  Differences are abstracted away in a traits
    class.
    """
    def __init__(self, is_source=True):
        if is_source:
            self.traits = SourcePublicationTraits
        else:
            self.traits = BinaryPublicationTraits

    def getPackageName(self, pub):
        """Get the package's name."""
        return self.traits.getPackageName(pub)

    def getPackageVersion(self, pub):
        """Obtain the version string for a publicaiton record."""
        return self.traits.getPackageRelease(pub).version

    def compare(self, pub1, pub2):
        """Compare publications by version.

        If both publications are for the same version, their creation dates
        break the tie.
        """
        version_comparison = apt_pkg.VersionCompare(
            self.getPackageVersion(pub1), self.getPackageVersion(pub2))

        if version_comparison == 0:
            # Use dates as tie breaker.
            return cmp(pub1.datecreated, pub2.datecreated)
        else:
            return version_comparison


class Dominator:
    """Manage the process of marking packages as superseded.

    Packages are marked as superseded when they become obsolete.
    """

    def __init__(self, logger, archive):
        """Initialize the dominator.

        This process should be run after the publisher has published
        new stuff into the distribution but before the publisher
        creates the file lists for apt-ftparchive.
        """
        self.logger = logger
        self.archive = archive

    def dominatePackage(self, publications, live_versions, generalization):
        """Dominate publications for a single package.

        The latest publication for any version in `live_versions` stays
        active.  Any older publications (including older publications for
        live versions with multiple publications) are marked as superseded by
        the respective oldest live releases that are newer than the superseded
        ones.

        Any versions that are newer than anything in `live_versions` are
        marked as deleted.  This should not be possible in Soyuz-native
        archives, but it can happen during archive imports when the
        previous latest version of a package has disappeared from the Sources
        list we import.

        :param publications: Iterable of publications for the same package,
            in the same archive, series, and pocket, all with status
            `PackagePublishingStatus.PUBLISHED`.
        :param live_versions: Iterable of version strings that are still
            considered live for this package.  The given publications will
            remain active insofar as they represent any of these versions;
            older publications will be marked as superseded and newer ones
            as deleted.
        :param generalization: A `GeneralizedPublication` helper representing
            the kind of publications these are--source or binary.
        """
        # Go through publications from latest version to oldest.  This
        # makes it easy to figure out which release superseded which:
        # the dominant is always the oldest live release that is newer
        # than the one being superseded.
        publications = sorted(
            publications, cmp=generalization.compare, reverse=True)

        current_dominant = None
        dominant_version = None

        for pub in publications:
            version = generalization.getPackageVersion(pub)
            if version == dominant_version:
                # This publication is for a live version, but has been
                # superseded by a newer publication of the same version.
                # Supersede it.
                pub.supersede(current_dominant, logger=self.logger)
            elif version in live_versions:
                # This publication stays active; if any publications
                # that follow right after this are to be superseded,
                # this is the release that they are superseded by.
                current_dominant = pub
                dominant_version = version
            elif current_dominant is None:
                # This publication is no longer live, but there is no
                # newer version to supersede it either.  Therefore it
                # must be deleted.
                pub.requestDeletion(None)
            else:
                # This publication is superseded.  This is what we're
                # here to do.
                pub.supersede(current_dominant, logger=self.logger)

    def _dominatePublications(self, pubs, generalization):
        """Perform dominations for the given publications.

        Keep the latest published version for each package active,
        superseding older versions.

        :param pubs: A dict mapping names to a list of publications. Every
            publication must be PUBLISHED or PENDING, and the first in each
            list will be treated as dominant (so should be the latest).
        :param generalization: A `GeneralizedPublication` helper representing
            the kind of publications these are--source or binary.
        """
        self.logger.debug("Dominating packages...")
        for name, publications in pubs.iteritems():
            assert publications, "Empty list of publications for %s." % name
            # Since this always picks the latest version as the live
            # one, this dominatePackage call will never result in a
            # deletion.
            latest_version = generalization.getPackageVersion(publications[0])
            self.dominatePackage(
                publications, [latest_version], generalization)

    def _sortPackages(self, pkglist, generalization):
        """Map out packages by name, and sort by descending version.

        :param pkglist: An iterable of `SourcePackagePublishingHistory` or
            `BinaryPackagePublishingHistory`.
        :param generalization: A `GeneralizedPublication` helper representing
            the kind of publications these are--source or binary.
        :return: A dict mapping each package name to a list of publications
            from `pkglist`, newest first.
        """
        self.logger.debug("Sorting packages...")

        outpkgs = {}
        for inpkg in pkglist:
            key = generalization.getPackageName(inpkg)
            outpkgs.setdefault(key, []).append(inpkg)

        for package_pubs in outpkgs.itervalues():
            package_pubs.sort(cmp=generalization.compare, reverse=True)

        return outpkgs

    def _setScheduledDeletionDate(self, pub_record):
        """Set the scheduleddeletiondate on a publishing record.

        If the status is DELETED we set the date to UTC_NOW, otherwise
        it gets the configured stay of execution period.
        """
        if pub_record.status == PackagePublishingStatus.DELETED:
            pub_record.scheduleddeletiondate = UTC_NOW
        else:
            pub_record.scheduleddeletiondate = (
                UTC_NOW + timedelta(days=STAY_OF_EXECUTION))

    def _judgeSuperseded(self, source_records, binary_records):
        """Determine whether the superseded packages supplied should
        be moved to death row or not.

        Currently this is done by assuming that any superseded binary
        package should be removed. In the future this should attempt
        to supersede binaries in build-sized chunks only, bug 55030.

        Superseded source packages are considered removable when they
        have no binaries in this distroseries which are published or
        superseded

        When a package is considered for death row it is given a
        'scheduled deletion date' of now plus the defined 'stay of execution'
        time provided in the configuration parameter.
        """
        # Avoid circular imports.
        from lp.soyuz.model.publishing import (
            BinaryPackagePublishingHistory,
            SourcePackagePublishingHistory,
            )

        self.logger.debug("Beginning superseded processing...")

        # XXX: dsilvers 2005-09-22 bug=55030:
        # Need to make binaries go in groups but for now this'll do.
        # An example of the concrete problem here is:
        # - Upload foo-1.0, which builds foo and foo-common (arch all).
        # - Upload foo-1.1, ditto.
        # - foo-common-1.1 is built (along with the i386 binary for foo)
        # - foo-common-1.0 is superseded
        # Foo is now uninstallable on any architectures which don't yet
        # have a build of foo-1.1, as the foo-common for foo-1.0 is gone.

        # Essentially we ideally don't want to lose superseded binaries
        # unless the entire group is ready to be made pending removal.
        # In this instance a group is defined as all the binaries from a
        # given build. This assumes we've copied the arch_all binaries
        # from whichever build provided them into each arch-specific build
        # which we publish. If instead we simply publish the arch-all
        # binaries from another build then instead we should scan up from
        # the binary to its source, and then back from the source to each
        # binary published in *this* distroarchseries for that source.
        # if the binaries as a group (in that definition) are all superseded
        # then we can consider them eligible for removal.
        for pub_record in binary_records:
            binpkg_release = pub_record.binarypackagerelease
            self.logger.debug(
                "%s/%s (%s) has been judged eligible for removal",
                binpkg_release.binarypackagename.name, binpkg_release.version,
                pub_record.distroarchseries.architecturetag)
            self._setScheduledDeletionDate(pub_record)
            # XXX cprov 20070820: 'datemadepending' is useless, since it's
            # always equals to "scheduleddeletiondate - quarantine".
            pub_record.datemadepending = UTC_NOW

        for pub_record in source_records:
            srcpkg_release = pub_record.sourcepackagerelease
            # Attempt to find all binaries of this
            # SourcePackageRelease which are/have been in this
            # distroseries...
            considered_binaries = BinaryPackagePublishingHistory.select("""
            binarypackagepublishinghistory.distroarchseries =
                distroarchseries.id AND
            binarypackagepublishinghistory.scheduleddeletiondate IS NULL AND
            binarypackagepublishinghistory.archive = %s AND
            binarypackagebuild.source_package_release = %s AND
            distroarchseries.distroseries = %s AND
            binarypackagepublishinghistory.binarypackagerelease =
            binarypackagerelease.id AND
            binarypackagerelease.build = binarypackagebuild.id AND
            binarypackagepublishinghistory.pocket = %s
            """ % sqlvalues(self.archive, srcpkg_release,
                            pub_record.distroseries, pub_record.pocket),
            clauseTables=['DistroArchSeries', 'BinaryPackageRelease',
                          'BinaryPackageBuild'])

            # There is at least one non-removed binary to consider
            if considered_binaries.count() > 0:
                # However we can still remove *this* record if there's
                # at least one other PUBLISHED for the spr. This happens
                # when a package is moved between components.
                published = SourcePackagePublishingHistory.selectBy(
                    distroseries=pub_record.distroseries,
                    pocket=pub_record.pocket,
                    status=PackagePublishingStatus.PUBLISHED,
                    archive=self.archive,
                    sourcepackagereleaseID=srcpkg_release.id)
                # Zero PUBLISHED for this spr, so nothing to take over
                # for us, so leave it for consideration next time.
                if published.count() == 0:
                    continue

            # Okay, so there's no unremoved binaries, let's go for it...
            self.logger.debug(
                "%s/%s (%s) source has been judged eligible for removal",
                srcpkg_release.sourcepackagename.name, srcpkg_release.version,
                pub_record.id)
            self._setScheduledDeletionDate(pub_record)
            # XXX cprov 20070820: 'datemadepending' is pointless, since it's
            # always equals to "scheduleddeletiondate - quarantine".
            pub_record.datemadepending = UTC_NOW

    def dominateBinaries(self, distroseries, pocket):
        """Perform domination on binary package publications.

        Dominates binaries, restricted to `distroseries`, `pocket`, and
        `self.archive`.
        """
        # Avoid circular imports.
        from lp.soyuz.model.publishing import BinaryPackagePublishingHistory

        generalization = GeneralizedPublication(is_source=False)

        for distroarchseries in distroseries.architectures:
            self.logger.debug(
                "Performing domination across %s/%s (%s)",
                distroseries.name, pocket.title,
                distroarchseries.architecturetag)

            bpph_location_clauses = And(
                BinaryPackagePublishingHistory.status ==
                    PackagePublishingStatus.PUBLISHED,
                BinaryPackagePublishingHistory.distroarchseries ==
                    distroarchseries,
                BinaryPackagePublishingHistory.archive == self.archive,
                BinaryPackagePublishingHistory.pocket == pocket,
                )
            candidate_binary_names = Select(
                BinaryPackageName.id,
                And(
                    BinaryPackageRelease.binarypackagenameID ==
                        BinaryPackageName.id,
                    BinaryPackagePublishingHistory.binarypackagereleaseID ==
                        BinaryPackageRelease.id,
                    bpph_location_clauses,
                ),
                group_by=BinaryPackageName.id,
                having=Count(BinaryPackagePublishingHistory.id) > 1)
            binaries = IStore(BinaryPackagePublishingHistory).find(
                BinaryPackagePublishingHistory,
                BinaryPackageRelease.id ==
                    BinaryPackagePublishingHistory.binarypackagereleaseID,
                BinaryPackageRelease.binarypackagenameID.is_in(
                    candidate_binary_names),
                BinaryPackageRelease.binpackageformat !=
                    BinaryPackageFormat.DDEB,
                bpph_location_clauses)
            self.logger.debug("Dominating binaries...")
            self._dominatePublications(
                self._sortPackages(binaries, generalization), generalization)

    def _composeActiveSourcePubsCondition(self, distroseries, pocket):
        """Compose ORM condition for restricting relevant source pubs."""
        # Avoid circular imports.
        from lp.soyuz.model.publishing import SourcePackagePublishingHistory

        return And(
            SourcePackagePublishingHistory.status ==
                PackagePublishingStatus.PUBLISHED,
            SourcePackagePublishingHistory.distroseries == distroseries,
            SourcePackagePublishingHistory.archive == self.archive,
            SourcePackagePublishingHistory.pocket == pocket,
            )

    def dominateSources(self, distroseries, pocket):
        """Perform domination on source package publications.

        Dominates sources, restricted to `distroseries`, `pocket`, and
        `self.archive`.
        """
        # Avoid circular imports.
        from lp.soyuz.model.publishing import SourcePackagePublishingHistory

        generalization = GeneralizedPublication(is_source=True)

        self.logger.debug(
            "Performing domination across %s/%s (Source)",
            distroseries.name, pocket.title)

        spph_location_clauses = self._composeActiveSourcePubsCondition(
            distroseries, pocket)
        having_multiple_active_publications = (
            Count(SourcePackagePublishingHistory.id) > 1)
        candidate_source_names = Select(
            SourcePackageName.id,
            And(join_spph_spr(), join_spr_spn(), spph_location_clauses),
            group_by=SourcePackageName.id,
            having=having_multiple_active_publications)
        sources = IStore(SourcePackagePublishingHistory).find(
            SourcePackagePublishingHistory,
            join_spph_spr(),
            SourcePackageRelease.sourcepackagenameID.is_in(
                candidate_source_names),
            spph_location_clauses)

        self.logger.debug("Dominating sources...")
        self._dominatePublications(
            self._sortPackages(sources, generalization), generalization)
        flush_database_updates()

    def findPublishedSourcePackageNames(self, distroseries, pocket):
        """Find names of currently published source packages."""
        result = IStore(SourcePackageName).find(
            SourcePackageName.name,
            join_spph_spr(),
            join_spr_spn(),
            self._composeActiveSourcePubsCondition(distroseries, pocket))
        return result.config(distinct=True)

    def findPublishedSPPHs(self, distroseries, pocket, package_name):
        """Find currently published source publications for given package."""
        # Avoid circular imports.
        from lp.soyuz.model.publishing import SourcePackagePublishingHistory

        return IStore(SourcePackagePublishingHistory).find(
            SourcePackagePublishingHistory,
            join_spph_spr(),
            join_spr_spn(),
            SourcePackageName.name == package_name,
            self._composeActiveSourcePubsCondition(distroseries, pocket))

    def dominateRemovedSourceVersions(self, distroseries, pocket,
                                      package_name, live_versions):
        """Dominate source publications based on a set of "live" versions.

        Active publications for the "live" versions will remain active.  All
        other active publications for the same package (and the same archive,
        distroseries, and pocket) are marked superseded.

        Unlike traditional domination, this allows multiple versions of a
        package to stay active in the same distroseries, archive, and pocket.

        :param distroseries: `DistroSeries` to dominate.
        :param pocket: `PackagePublishingPocket` to dominate.
        :param package_name: Source package name, as text.
        :param live_versions: Iterable of all version strings that are to
            remain active.
        """
        generalization = GeneralizedPublication(is_source=True)
        pubs = self.findPublishedSPPHs(distroseries, pocket, package_name)
        self.dominatePackage(pubs, live_versions, generalization)

    def judge(self, distroseries, pocket):
        """Judge superseded sources and binaries."""
        # Avoid circular imports.
        from lp.soyuz.model.publishing import (
             BinaryPackagePublishingHistory,
             SourcePackagePublishingHistory,
             )

        sources = SourcePackagePublishingHistory.select("""
            sourcepackagepublishinghistory.distroseries = %s AND
            sourcepackagepublishinghistory.archive = %s AND
            sourcepackagepublishinghistory.pocket = %s AND
            sourcepackagepublishinghistory.status IN %s AND
            sourcepackagepublishinghistory.scheduleddeletiondate is NULL
            """ % sqlvalues(
                distroseries, self.archive, pocket,
                inactive_publishing_status))

        binaries = BinaryPackagePublishingHistory.select("""
            binarypackagepublishinghistory.distroarchseries =
                distroarchseries.id AND
            distroarchseries.distroseries = %s AND
            binarypackagepublishinghistory.archive = %s AND
            binarypackagepublishinghistory.pocket = %s AND
            binarypackagepublishinghistory.status IN %s AND
            binarypackagepublishinghistory.scheduleddeletiondate is NULL
            """ % sqlvalues(
                distroseries, self.archive, pocket,
                inactive_publishing_status),
            clauseTables=['DistroArchSeries'])

        self._judgeSuperseded(sources, binaries)

    def judgeAndDominate(self, distroseries, pocket):
        """Perform the domination and superseding calculations

        It only works across the distroseries and pocket specified.
        """

        self.dominateBinaries(distroseries, pocket)
        self.dominateSources(distroseries, pocket)
        self.judge(distroseries, pocket)

        self.logger.debug(
            "Domination for %s/%s finished", distroseries.name, pocket.title)
