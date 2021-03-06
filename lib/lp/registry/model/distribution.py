# Copyright 2009-2021 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Database classes for implementing distribution items."""

__metaclass__ = type
__all__ = [
    'Distribution',
    'DistributionSet',
    ]

from collections import defaultdict
import itertools
from operator import itemgetter

import six
from sqlobject import (
    BoolCol,
    ForeignKey,
    SQLObjectNotFound,
    StringCol,
    )
from storm.expr import (
    And,
    Desc,
    Exists,
    Join,
    LeftJoin,
    Max,
    Not,
    Or,
    Select,
    SQL,
    )
from storm.info import ClassAlias
from storm.locals import (
    Int,
    Reference,
    )
from storm.store import Store
from zope.component import getUtility
from zope.interface import implementer
from zope.security.interfaces import Unauthorized

from lp.answers.enums import QUESTION_STATUS_DEFAULT_SEARCH
from lp.answers.model.faq import (
    FAQ,
    FAQSearch,
    )
from lp.answers.model.question import (
    QuestionTargetMixin,
    QuestionTargetSearch,
    )
from lp.app.enums import (
    FREE_INFORMATION_TYPES,
    InformationType,
    ServiceUsage,
    )
from lp.app.errors import NotFoundError
from lp.app.interfaces.launchpad import (
    IHasIcon,
    IHasLogo,
    IHasMugshot,
    ILaunchpadCelebrities,
    ILaunchpadUsage,
    IServiceUsage,
    )
from lp.app.validators.name import (
    sanitize_name,
    valid_name,
    )
from lp.archivepublisher.debversion import Version
from lp.blueprints.model.specification import (
    HasSpecificationsMixin,
    Specification,
    )
from lp.blueprints.model.specificationsearch import search_specifications
from lp.blueprints.model.sprint import HasSprintsMixin
from lp.bugs.interfaces.bugsummary import IBugSummaryDimension
from lp.bugs.interfaces.bugsupervisor import IHasBugSupervisor
from lp.bugs.interfaces.bugtaskfilter import OrderedBugTask
from lp.bugs.model.bugtarget import (
    BugTargetBase,
    OfficialBugTagTargetMixin,
    )
from lp.bugs.model.structuralsubscription import (
    StructuralSubscriptionTargetMixin,
    )
from lp.code.interfaces.seriessourcepackagebranch import (
    IFindOfficialBranchLinks,
    )
from lp.oci.interfaces.ociregistrycredentials import IOCIRegistryCredentialsSet
from lp.registry.enums import (
    BranchSharingPolicy,
    BugSharingPolicy,
    DistributionDefaultTraversalPolicy,
    SpecificationSharingPolicy,
    VCSType,
    )
from lp.registry.errors import NoSuchDistroSeries
from lp.registry.interfaces.accesspolicy import IAccessPolicySource
from lp.registry.interfaces.distribution import (
    IDistribution,
    IDistributionSet,
    NoOCIAdminForDistribution,
    )
from lp.registry.interfaces.distributionmirror import (
    IDistributionMirror,
    MirrorContent,
    MirrorFreshness,
    MirrorStatus,
    )
from lp.registry.interfaces.ociproject import (
    IOCIProjectSet,
    OCI_PROJECT_ALLOW_CREATE,
    )
from lp.registry.interfaces.oopsreferences import IHasOOPSReferences
from lp.registry.interfaces.person import (
    validate_person,
    validate_person_or_closed_team,
    validate_public_person,
    )
from lp.registry.interfaces.pillar import IPillarNameSet
from lp.registry.interfaces.pocket import suffixpocket
from lp.registry.interfaces.role import IPersonRoles
from lp.registry.interfaces.series import SeriesStatus
from lp.registry.interfaces.sourcepackagename import ISourcePackageName
from lp.registry.model.announcement import MakesAnnouncements
from lp.registry.model.distributionmirror import (
    DistributionMirror,
    MirrorCDImageDistroSeries,
    MirrorDistroArchSeries,
    MirrorDistroSeriesSource,
    )
from lp.registry.model.distributionsourcepackage import (
    DistributionSourcePackage,
    )
from lp.registry.model.distroseries import DistroSeries
from lp.registry.model.distroseriesparent import DistroSeriesParent
from lp.registry.model.hasdrivers import HasDriversMixin
from lp.registry.model.karma import KarmaContextMixin
from lp.registry.model.milestone import (
    HasMilestonesMixin,
    Milestone,
    )
from lp.registry.model.ociprojectname import OCIProjectName
from lp.registry.model.oopsreferences import referenced_oops
from lp.registry.model.pillar import HasAliasMixin
from lp.registry.model.sourcepackagename import SourcePackageName
from lp.services.database.bulk import load_referencing
from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.decoratedresultset import DecoratedResultSet
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import (
    SQLBase,
    sqlvalues,
    )
from lp.services.database.stormexpr import (
    fti_search,
    rank_by_fti,
    )
from lp.services.features import getFeatureFlag
from lp.services.helpers import (
    backslashreplace,
    shortlist,
    )
from lp.services.propertycache import (
    cachedproperty,
    get_property_cache,
    )
from lp.services.webapp.url import urlparse
from lp.services.worlddata.model.country import Country
from lp.soyuz.enums import (
    ArchivePurpose,
    ArchiveStatus,
    PackagePublishingStatus,
    PackageUploadStatus,
    )
from lp.soyuz.interfaces.archive import (
    IArchiveSet,
    MAIN_ARCHIVE_PURPOSES,
    )
from lp.soyuz.interfaces.archivepermission import IArchivePermissionSet
from lp.soyuz.interfaces.binarypackagebuild import IBinaryPackageBuildSet
from lp.soyuz.interfaces.buildrecords import IHasBuildRecords
from lp.soyuz.interfaces.publishing import active_publishing_status
from lp.soyuz.model.archive import Archive
from lp.soyuz.model.archivefile import ArchiveFile
from lp.soyuz.model.binarypackagename import BinaryPackageName
from lp.soyuz.model.distributionsourcepackagerelease import (
    DistributionSourcePackageRelease,
    )
from lp.soyuz.model.distroarchseries import DistroArchSeries
from lp.soyuz.model.publishing import (
    BinaryPackagePublishingHistory,
    get_current_source_releases,
    SourcePackagePublishingHistory,
    )
from lp.translations.enums import TranslationPermission
from lp.translations.model.hastranslationimports import (
    HasTranslationImportsMixin,
    )
from lp.translations.model.translationpolicy import TranslationPolicyMixin


@implementer(
    IBugSummaryDimension, IDistribution, IHasBugSupervisor,
    IHasBuildRecords, IHasIcon, IHasLogo, IHasMugshot,
    IHasOOPSReferences, ILaunchpadUsage, IServiceUsage)
class Distribution(SQLBase, BugTargetBase, MakesAnnouncements,
                   HasSpecificationsMixin, HasSprintsMixin, HasAliasMixin,
                   HasTranslationImportsMixin, KarmaContextMixin,
                   OfficialBugTagTargetMixin, QuestionTargetMixin,
                   StructuralSubscriptionTargetMixin, HasMilestonesMixin,
                   HasDriversMixin, TranslationPolicyMixin):
    """A distribution of an operating system, e.g. Debian GNU/Linux."""

    _table = 'Distribution'
    _defaultOrder = 'name'

    name = StringCol(notNull=True, alternateID=True, unique=True)
    display_name = StringCol(dbName='displayname', notNull=True)
    _title = StringCol(dbName='title', notNull=True)
    summary = StringCol(notNull=True)
    description = StringCol(notNull=True)
    homepage_content = StringCol(default=None)
    icon = ForeignKey(
        dbName='icon', foreignKey='LibraryFileAlias', default=None)
    logo = ForeignKey(
        dbName='logo', foreignKey='LibraryFileAlias', default=None)
    mugshot = ForeignKey(
        dbName='mugshot', foreignKey='LibraryFileAlias', default=None)
    domainname = StringCol(notNull=True)
    owner = ForeignKey(
        dbName='owner', foreignKey='Person',
        storm_validator=validate_person_or_closed_team, notNull=True)
    registrant = ForeignKey(
        dbName='registrant', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)
    bug_supervisor = ForeignKey(
        dbName='bug_supervisor', foreignKey='Person',
        storm_validator=validate_person,
        notNull=False,
        default=None)
    bug_reporting_guidelines = StringCol(default=None)
    bug_reported_acknowledgement = StringCol(default=None)
    driver = ForeignKey(
        dbName="driver", foreignKey="Person",
        storm_validator=validate_public_person, notNull=False, default=None)
    members = ForeignKey(
        dbName='members', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)
    mirror_admin = ForeignKey(
        dbName='mirror_admin', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)
    oci_project_admin = ForeignKey(
        dbName='oci_project_admin', foreignKey='Person',
        storm_validator=validate_public_person, notNull=False, default=None)
    translationgroup = ForeignKey(
        dbName='translationgroup', foreignKey='TranslationGroup',
        notNull=False, default=None)
    translationpermission = EnumCol(
        dbName='translationpermission', notNull=True,
        schema=TranslationPermission, default=TranslationPermission.OPEN)
    active = True
    official_packages = BoolCol(notNull=True, default=False)
    supports_ppas = BoolCol(notNull=True, default=False)
    supports_mirrors = BoolCol(notNull=True, default=False)
    package_derivatives_email = StringCol(notNull=False, default=None)
    redirect_release_uploads = BoolCol(notNull=True, default=False)
    development_series_alias = StringCol(notNull=False, default=None)
    vcs = EnumCol(enum=VCSType, notNull=False)
    default_traversal_policy = EnumCol(
        enum=DistributionDefaultTraversalPolicy, notNull=False,
        default=DistributionDefaultTraversalPolicy.SERIES)
    redirect_default_traversal = BoolCol(notNull=False, default=False)
    oci_registry_credentials_id = Int(name='oci_credentials', allow_none=True)
    oci_registry_credentials = Reference(
        oci_registry_credentials_id, "OCIRegistryCredentials.id")

    def __init__(self, name, display_name, title, description, summary,
                 domainname, members, owner, registrant, mugshot=None,
                 logo=None, icon=None, vcs=None):
        try:
            self.name = name
            self.display_name = display_name
            self._title = title
            self.description = description
            self.summary = summary
            self.domainname = domainname
            self.members = members
            self.mirror_admin = owner
            self.owner = owner
            self.registrant = registrant
            self.mugshot = mugshot
            self.logo = logo
            self.icon = icon
            self.vcs = vcs
        except Exception:
            IStore(self).remove(self)
            raise

    def __repr__(self):
        display_name = backslashreplace(self.display_name)
        return "<%s '%s' (%s)>" % (
            self.__class__.__name__, display_name, self.name)

    @property
    def displayname(self):
        return self.display_name

    @property
    def title(self):
        return self.display_name

    @property
    def pillar(self):
        """See `IBugTarget`."""
        return self

    @property
    def pillar_category(self):
        """See `IPillar`."""
        return "Distribution"

    @property
    def branch_sharing_policy(self):
        """See `IHasSharingPolicies."""
        # Sharing policy for distributions is always PUBLIC.
        return BranchSharingPolicy.PUBLIC

    @property
    def bug_sharing_policy(self):
        """See `IHasSharingPolicies."""
        # Sharing policy for distributions is always PUBLIC.
        return BugSharingPolicy.PUBLIC

    @property
    def specification_sharing_policy(self):
        """See `IHasSharingPolicies."""
        # Sharing policy for distributions is always PUBLIC.
        return SpecificationSharingPolicy.PUBLIC

    @property
    def uploaders(self):
        """See `IDistribution`."""
        # Get all the distribution archives and find out the uploaders
        # for each.
        distro_uploaders = []
        permission_set = getUtility(IArchivePermissionSet)
        for archive in self.all_distro_archives:
            uploaders = permission_set.uploadersForComponent(archive)
            distro_uploaders.extend(uploaders)

        return distro_uploaders

    official_answers = BoolCol(dbName='official_answers', notNull=True,
        default=False)
    official_blueprints = BoolCol(dbName='official_blueprints', notNull=True,
        default=False)
    official_malone = BoolCol(dbName='official_malone', notNull=True,
        default=False)

    @property
    def official_codehosting(self):
        # XXX: Aaron Bentley 2008-01-22
        # At this stage, we can't directly associate branches with source
        # packages or anything else resulting in a distribution, so saying
        # that a distribution supports codehosting at this stage makes
        # absolutely no sense at all.
        return False

    @property
    def official_anything(self):
        return True in (self.official_malone,
                        self.translations_usage == ServiceUsage.LAUNCHPAD,
                        self.official_blueprints, self.official_answers)

    _answers_usage = EnumCol(
        dbName="answers_usage", notNull=True,
        schema=ServiceUsage, default=ServiceUsage.UNKNOWN)

    def _get_answers_usage(self):
        if self._answers_usage != ServiceUsage.UNKNOWN:
            # If someone has set something with the enum, use it.
            return self._answers_usage
        elif self.official_answers:
            return ServiceUsage.LAUNCHPAD
        return self._answers_usage

    def _set_answers_usage(self, val):
        self._answers_usage = val
        if val == ServiceUsage.LAUNCHPAD:
            self.official_answers = True
        else:
            self.official_answers = False

    answers_usage = property(
        _get_answers_usage,
        _set_answers_usage,
        doc="Indicates if the product uses the answers service.")

    _blueprints_usage = EnumCol(
        dbName="blueprints_usage", notNull=True,
        schema=ServiceUsage,
        default=ServiceUsage.UNKNOWN)

    def _get_blueprints_usage(self):
        if self._blueprints_usage != ServiceUsage.UNKNOWN:
            # If someone has set something with the enum, use it.
            return self._blueprints_usage
        elif self.official_blueprints:
            return ServiceUsage.LAUNCHPAD
        return self._blueprints_usage

    def _set_blueprints_usage(self, val):
        self._blueprints_usage = val
        if val == ServiceUsage.LAUNCHPAD:
            self.official_blueprints = True
        else:
            self.official_blueprints = False

    blueprints_usage = property(
        _get_blueprints_usage,
        _set_blueprints_usage,
        doc="Indicates if the product uses the blueprints service.")

    translations_usage = EnumCol(
        dbName="translations_usage", notNull=True,
        schema=ServiceUsage, default=ServiceUsage.UNKNOWN)

    @property
    def codehosting_usage(self):
        return ServiceUsage.NOT_APPLICABLE

    @property
    def bug_tracking_usage(self):
        if not self.official_malone:
            return ServiceUsage.UNKNOWN
        else:
            return ServiceUsage.LAUNCHPAD

    @property
    def uses_launchpad(self):
        """Does this distribution actually use Launchpad?"""
        return self.official_anything

    enable_bug_expiration = BoolCol(dbName='enable_bug_expiration',
        notNull=True, default=False)
    translation_focus = ForeignKey(dbName='translation_focus',
        foreignKey='DistroSeries', notNull=False, default=None)
    date_created = UtcDateTimeCol(notNull=False, default=UTC_NOW)
    language_pack_admin = ForeignKey(
        dbName='language_pack_admin', foreignKey='Person',
        storm_validator=validate_public_person, notNull=False, default=None)

    @cachedproperty
    def main_archive(self):
        """See `IDistribution`."""
        return Store.of(self).find(Archive, distribution=self,
            purpose=ArchivePurpose.PRIMARY).one()

    @cachedproperty
    def all_distro_archives(self):
        """See `IDistribution`."""
        return Store.of(self).find(
            Archive,
            Archive.distribution == self,
            Archive.purpose.is_in(MAIN_ARCHIVE_PURPOSES))

    @cachedproperty
    def all_distro_archive_ids(self):
        """See `IDistribution`."""
        return [archive.id for archive in self.all_distro_archives]

    def _getMilestoneCondition(self):
        """See `HasMilestonesMixin`."""
        return (Milestone.distribution == self)

    def getArchiveIDList(self, archive=None):
        """See `IDistribution`."""
        if archive is None:
            return self.all_distro_archive_ids
        else:
            return [archive.id]

    def _getMirrors(self, content=None, enabled=True,
                    status=MirrorStatus.OFFICIAL, by_country=False,
                    needs_fresh=False, needs_cdimage_series=False):
        """Builds the query to get the mirror data for various purposes."""
        clauses = [
            DistributionMirror.distribution == self.id,
            DistributionMirror.status == status,
            ]
        if content is not None:
            clauses.append(DistributionMirror.content == content)
        if enabled is not None:
            clauses.append(DistributionMirror.enabled == enabled)
        if status != MirrorStatus.UNOFFICIAL:
            clauses.append(DistributionMirror.official_candidate == True)
        mirrors = list(Store.of(self).find(DistributionMirror, And(*clauses)))

        if by_country and mirrors:
            # Since country data is needed, fetch countries into the cache.
            list(Store.of(self).find(
                Country,
                Country.id.is_in(mirror.countryID for mirror in mirrors)))

        if needs_fresh and mirrors:
            # Preload the distribution_mirrors' cache for mirror freshness.
            mirror_ids = [mirror.id for mirror in mirrors]

            arch_mirrors = list(Store.of(self).find(
                (MirrorDistroArchSeries.distribution_mirrorID,
                 Max(MirrorDistroArchSeries.freshness)),
                MirrorDistroArchSeries.distribution_mirrorID.is_in(
                    mirror_ids)).group_by(
                        MirrorDistroArchSeries.distribution_mirrorID))
            arch_mirror_freshness = {}
            arch_mirror_freshness.update(
                [(mirror_id, MirrorFreshness.items[mirror_freshness]) for
                 (mirror_id, mirror_freshness) in arch_mirrors])

            source_mirrors = list(Store.of(self).find(
                (MirrorDistroSeriesSource.distribution_mirrorID,
                 Max(MirrorDistroSeriesSource.freshness)),
                MirrorDistroSeriesSource.distribution_mirrorID.is_in(
                    [mirror.id for mirror in mirrors])).group_by(
                        MirrorDistroSeriesSource.distribution_mirrorID))
            source_mirror_freshness = {}
            source_mirror_freshness.update(
                [(mirror_id, MirrorFreshness.items[mirror_freshness]) for
                 (mirror_id, mirror_freshness) in source_mirrors])

            for mirror in mirrors:
                cache = get_property_cache(mirror)
                cache.arch_mirror_freshness = arch_mirror_freshness.get(
                    mirror.id, None)
                cache.source_mirror_freshness = source_mirror_freshness.get(
                    mirror.id, None)

        if needs_cdimage_series and mirrors:
            all_cdimage_series = load_referencing(
                MirrorCDImageDistroSeries, mirrors, ["distribution_mirrorID"])
            cdimage_series = defaultdict(list)
            for series in all_cdimage_series:
                cdimage_series[series.distribution_mirrorID].append(series)
            for mirror in mirrors:
                cache = get_property_cache(mirror)
                cache.cdimage_series = cdimage_series.get(mirror.id, [])

        return mirrors

    @property
    def archive_mirrors(self):
        """See `IDistribution`."""
        return self._getMirrors(content=MirrorContent.ARCHIVE)

    @property
    def archive_mirrors_by_country(self):
        """See `IDistribution`."""
        return self._getMirrors(
            content=MirrorContent.ARCHIVE,
            by_country=True,
            needs_fresh=True)

    @property
    def cdimage_mirrors(self, by_country=False):
        """See `IDistribution`."""
        return self._getMirrors(
            content=MirrorContent.RELEASE,
            needs_cdimage_series=True)

    @property
    def cdimage_mirrors_by_country(self):
        """See `IDistribution`."""
        return self._getMirrors(
            content=MirrorContent.RELEASE,
            by_country=True,
            needs_cdimage_series=True)

    @property
    def disabled_mirrors(self):
        """See `IDistribution`."""
        return self._getMirrors(
            enabled=False,
            by_country=True,
            needs_fresh=True)

    @property
    def unofficial_mirrors(self):
        """See `IDistribution`."""
        return self._getMirrors(
            enabled=None,
            status=MirrorStatus.UNOFFICIAL,
            by_country=True,
            needs_fresh=True)

    @property
    def pending_review_mirrors(self):
        """See `IDistribution`."""
        return self._getMirrors(
            enabled=None,
            by_country=True,
            status=MirrorStatus.PENDING_REVIEW)

    @property
    def drivers(self):
        """See `IDistribution`."""
        if self.driver is not None:
            return [self.driver]
        else:
            return [self.owner]

    @property
    def _sort_key(self):
        """Return something that can be used to sort distributions,
        putting Ubuntu and its major derivatives first.

        This is used to ensure that the list of distributions displayed in
        Soyuz generally puts Ubuntu at the top.
        """
        if self.name == 'ubuntu':
            return (0, 'ubuntu')
        if self.name in ['kubuntu', 'xubuntu', 'edubuntu']:
            return (1, self.name)
        if 'buntu' in self.name:
            return (2, self.name)
        return (3, self.name)

    @cachedproperty
    def series(self):
        """See `IDistribution`."""
        ret = Store.of(self).find(
            DistroSeries,
            distribution=self)
        return sorted(ret, key=lambda a: Version(a.version), reverse=True)

    @cachedproperty
    def derivatives(self):
        """See `IDistribution`."""
        ParentDistroSeries = ClassAlias(DistroSeries)
        # XXX rvb 2011-04-08 bug=754750: The clause
        # 'DistroSeries.distributionID!=self.id' is only required
        # because the previous_series attribute has been (mis-)used
        # to denote other relations than proper derivation
        # relashionships. We should be rid of this condition once
        # the bug is fixed.
        ret = Store.of(self).find(
            DistroSeries,
            ParentDistroSeries.id == DistroSeries.previous_seriesID,
            ParentDistroSeries.distributionID == self.id,
            DistroSeries.distributionID != self.id)
        return ret.config(
            distinct=True).order_by(Desc(DistroSeries.date_created))

    @property
    def architectures(self):
        """See `IDistribution`."""
        architectures = []

        # Concatenate architectures list since they are distinct.
        for series in self.series:
            architectures += series.architectures

        return architectures

    @property
    def bugtargetdisplayname(self):
        """See IBugTarget."""
        return self.display_name

    @property
    def bugtargetname(self):
        """See `IBugTarget`."""
        return self.name

    def getBugSummaryContextWhereClause(self):
        """See BugTargetBase."""
        # Circular fail.
        from lp.bugs.model.bugsummary import BugSummary
        return And(
            BugSummary.distribution_id == self.id,
            BugSummary.sourcepackagename_id == None,
            BugSummary.ociproject_id == None)

    def _customizeSearchParams(self, search_params):
        """Customize `search_params` for this distribution."""
        search_params.setDistribution(self)

    def getBranchTips(self, user=None, since=None):
        """See `IDistribution`."""
        from lp.code.model.branch import (
            Branch, get_branch_privacy_filter)
        from lp.code.model.seriessourcepackagebranch import (
            SeriesSourcePackageBranch)

        # This method returns thousands of branch unique names in a
        # single call, so the query is perilous and awkwardly tuned to
        # get a good plan with the normal dataset (the charms distro).
        OfficialSeries = ClassAlias(DistroSeries)

        ds_ids = Select(
            DistroSeries.id, tables=[DistroSeries],
            where=DistroSeries.distributionID == self.id)
        clauses = [
            DistroSeries.id.is_in(ds_ids),
            get_branch_privacy_filter(user),
        ]

        if since is not None:
            # If "since" was provided, take into account.
            clauses.append(Branch.last_scanned > since)

        branches = IStore(self).using(
            Branch,
            Join(DistroSeries,
                 DistroSeries.id == Branch.distroseriesID),
            LeftJoin(
                Join(
                    SeriesSourcePackageBranch,
                    OfficialSeries,
                    OfficialSeries.id ==
                        SeriesSourcePackageBranch.distroseriesID),
                And(SeriesSourcePackageBranch.branchID == Branch.id,
                    SeriesSourcePackageBranch.distroseriesID.is_in(ds_ids))),
        ).find(
            (Branch.unique_name, Branch.last_scanned_id, OfficialSeries.name),
            And(*clauses)
        ).order_by(
            Branch.unique_name,
            Branch.last_scanned_id
        )

        # Group on location (unique_name) and revision (last_scanned_id).
        result = []
        for key, group in itertools.groupby(branches, itemgetter(0, 1)):
            result.append(list(key))
            # Pull out all the official series names and append them as a list
            # to the end of the current record.
            result[-1].append(list(filter(None, map(itemgetter(2), group))))

        return result

    def getMirrorByName(self, name):
        """See `IDistribution`."""
        return Store.of(self).find(
            DistributionMirror,
            distribution=self,
            name=name).one()

    def getCountryMirror(self, country, mirror_type):
        """See `IDistribution`."""
        return Store.of(self).find(
            DistributionMirror,
            distribution=self,
            country=country,
            content=mirror_type,
            country_dns_mirror=True).one()

    def newMirror(self, owner, speed, country, content, display_name=None,
                  description=None, http_base_url=None, https_base_url=None,
                  ftp_base_url=None, rsync_base_url=None,
                  official_candidate=False, enabled=False,
                  whiteboard=None):
        """See `IDistribution`."""
        # NB this functionality is only available to distributions that have
        # the full functionality of Launchpad enabled. This is Ubuntu and
        # commercial derivatives that have been specifically given this
        # ability
        if not self.supports_mirrors:
            return None

        urls = {'http_base_url': http_base_url,
                'https_base_url': https_base_url,
                'ftp_base_url': ftp_base_url,
                'rsync_base_url': rsync_base_url}
        for name, value in urls.items():
            if value is not None:
                urls[name] = IDistributionMirror[name].normalize(value)

        url = (urls['https_base_url'] or urls['http_base_url'] or
               urls['ftp_base_url'])
        assert url is not None, (
            "A mirror must provide at least one HTTP/HTTPS/FTP URL.")
        dummy, host, dummy, dummy, dummy, dummy = urlparse(url)
        name = sanitize_name('%s-%s' % (host, content.name.lower()))

        orig_name = name
        count = 1
        while self.getMirrorByName(name=name) is not None:
            count += 1
            name = '%s%s' % (orig_name, count)

        return DistributionMirror(
            distribution=self, owner=owner, name=name, speed=speed,
            country=country, content=content, display_name=display_name,
            description=description, http_base_url=urls['http_base_url'],
            https_base_url=urls['https_base_url'],
            ftp_base_url=urls['ftp_base_url'],
            rsync_base_url=urls['rsync_base_url'],
            official_candidate=official_candidate, enabled=enabled,
            whiteboard=whiteboard)

    @property
    def currentseries(self):
        """See `IDistribution`."""
        # XXX kiko 2006-03-18:
        # This should be just a selectFirst with a case in its
        # order by clause.

        # If we have a frozen one, return that.
        for series in self.series:
            if series.status == SeriesStatus.FROZEN:
                return series
        # If we have one in development, return that.
        for series in self.series:
            if series.status == SeriesStatus.DEVELOPMENT:
                return series
        # If we have a stable one, return that.
        for series in self.series:
            if series.status == SeriesStatus.CURRENT:
                return series
        # If we have ANY, return the first one.
        if len(self.series) > 0:
            return self.series[0]
        return None

    def __getitem__(self, name):
        for series in self.series:
            if series.name == name:
                return series
        raise NotFoundError(name)

    def __iter__(self):
        return iter(self.series)

    def getArchive(self, name):
        """See `IDistribution.`"""
        return getUtility(
            IArchiveSet).getByDistroAndName(self, name)

    def resolveSeriesAlias(self, name):
        """See `IDistribution`."""
        if self.development_series_alias == name:
            currentseries = self.currentseries
            if currentseries is not None:
                return currentseries
        raise NoSuchDistroSeries(name)

    def getSeries(self, name_or_version, follow_aliases=False):
        """See `IDistribution`."""
        distroseries = Store.of(self).find(DistroSeries,
               Or(DistroSeries.name == name_or_version,
               DistroSeries.version == name_or_version),
            DistroSeries.distribution == self).one()
        if distroseries:
            return distroseries
        if follow_aliases:
            return self.resolveSeriesAlias(name_or_version)
        raise NoSuchDistroSeries(name_or_version)

    def getDevelopmentSeries(self):
        """See `IDistribution`."""
        return Store.of(self).find(
            DistroSeries,
            distribution=self,
            status=SeriesStatus.DEVELOPMENT)

    def getNonObsoleteSeries(self):
        """See `IDistribution`."""
        for series in self.series:
            if series.status != SeriesStatus.OBSOLETE:
                yield series

    def getMilestone(self, name):
        """See `IDistribution`."""
        return Store.of(self).find(
            Milestone, distribution=self, name=name).one()

    def getOCIProject(self, name):
        oci_project = getUtility(IOCIProjectSet).getByPillarAndName(
            self, name)
        return oci_project

    def getSourcePackage(self, name):
        """See `IDistribution`."""
        if ISourcePackageName.providedBy(name):
            sourcepackagename = name
        else:
            try:
                sourcepackagename = SourcePackageName.byName(name)
            except SQLObjectNotFound:
                return None
        return DistributionSourcePackage(self, sourcepackagename)

    def getSourcePackageRelease(self, sourcepackagerelease):
        """See `IDistribution`."""
        return DistributionSourcePackageRelease(self, sourcepackagerelease)

    def getCurrentSourceReleases(self, source_package_names):
        """See `IDistribution`."""
        return getUtility(IDistributionSet).getCurrentSourceReleases(
            {self: source_package_names})

    def specifications(self, user, sort=None, quantity=None, filter=None,
                       need_people=True, need_branches=True,
                       need_workitems=False):
        """See `IHasSpecifications`.

        In the case of distributions, there are two kinds of filtering,
        based on:

          - completeness: we want to show INCOMPLETE if nothing is said
          - informationalness: we will show ANY if nothing is said

        """
        base_clauses = [Specification.distributionID == self.id]
        return search_specifications(
            self, base_clauses, user, sort, quantity, filter,
            need_people=need_people, need_branches=need_branches,
            need_workitems=need_workitems)

    def getSpecification(self, name):
        """See `ISpecificationTarget`."""
        return Specification.selectOneBy(distribution=self, name=name)

    def getAllowedSpecificationInformationTypes(self):
        """See `ISpecificationTarget`."""
        return (InformationType.PUBLIC,)

    def getDefaultSpecificationInformationType(self):
        """See `ISpecificationTarget`."""
        return InformationType.PUBLIC

    def searchQuestions(self, search_text=None,
                        status=QUESTION_STATUS_DEFAULT_SEARCH,
                        language=None, sort=None, owner=None,
                        needs_attention_from=None, unsupported=False):
        """See `IQuestionCollection`."""
        if unsupported:
            unsupported_target = self
        else:
            unsupported_target = None

        return QuestionTargetSearch(
            distribution=self,
            search_text=search_text, status=status,
            language=language, sort=sort, owner=owner,
            needs_attention_from=needs_attention_from,
            unsupported_target=unsupported_target).getResults()

    def getTargetTypes(self):
        """See `QuestionTargetMixin`.

        Defines distribution as self and sourcepackagename as None.
        """
        return {'distribution': self,
                'sourcepackagename': None}

    def questionIsForTarget(self, question):
        """See `QuestionTargetMixin`.

        Return True when the Question's distribution is self.
        """
        if question.distribution is not self:
            return False
        return True

    def newFAQ(self, owner, title, content, keywords=None, date_created=None):
        """See `IFAQTarget`."""
        return FAQ.new(
            owner=owner, title=title, content=content, keywords=keywords,
            date_created=date_created, distribution=self)

    def findReferencedOOPS(self, start_date, end_date):
        """See `IHasOOPSReferences`."""
        return list(referenced_oops(
            start_date, end_date, "distribution=%(distribution)s",
            {'distribution': self.id}))

    def findSimilarFAQs(self, summary):
        """See `IFAQTarget`."""
        return FAQ.findSimilar(summary, distribution=self)

    def getFAQ(self, id):
        """See `IFAQCollection`."""
        return FAQ.getForTarget(id, self)

    def searchFAQs(self, search_text=None, owner=None, sort=None):
        """See `IFAQCollection`."""
        return FAQSearch(
            search_text=search_text, owner=owner, sort=sort,
            distribution=self).getResults()

    def getDistroSeriesAndPocket(self, distroseries_name,
                                 follow_aliases=False):
        """See `IDistribution`."""
        # Get the list of suffixes.
        suffixes = [suffix for suffix, ignored in suffixpocket.items()]
        # Sort it longest string first.
        suffixes.sort(key=len, reverse=True)

        for suffix in suffixes:
            if distroseries_name.endswith(suffix):
                left_size = len(distroseries_name) - len(suffix)
                left = distroseries_name[:left_size]
                try:
                    return self[left], suffixpocket[suffix]
                except KeyError:
                    if follow_aliases:
                        try:
                            resolved = self.resolveSeriesAlias(left)
                            return resolved, suffixpocket[suffix]
                        except NoSuchDistroSeries:
                            pass
                    # Swallow KeyError to continue round the loop.

        raise NotFoundError(distroseries_name)

    def getSeriesByStatus(self, status):
        """See `IDistribution`."""
        return Store.of(self).find(DistroSeries,
            DistroSeries.distribution == self,
            DistroSeries.status == status)

    def getBuildRecords(self, build_state=None, name=None, pocket=None,
                        arch_tag=None, user=None, binary_only=True):
        """See `IHasBuildRecords`"""
        # Ignore "user", since it would not make any difference to the
        # records returned here (private builds are only in PPA right
        # now).
        # The "binary_only" option is not yet supported for
        # IDistribution.
        return getUtility(IBinaryPackageBuildSet).getBuildsForDistro(
            self, build_state, name, pocket, arch_tag)

    def searchSourcePackageCaches(
        self, text, has_packaging=None, publishing_distroseries=None):
        """See `IDistribution`."""
        from lp.registry.model.packaging import Packaging
        from lp.soyuz.model.distributionsourcepackagecache import (
            DistributionSourcePackageCache,
            )
        # The query below tries exact matching on the source package
        # name as well; this is because source package names are
        # notoriously bad for fti matching -- they can contain dots, or
        # be short like "at", both things which users do search for.
        store = Store.of(self)
        find_spec = (
            DistributionSourcePackageCache,
            SourcePackageName,
            SQL('ts_rank(fti, ftq(?)) AS rank', params=(text,)),
            )
        origin = [
            DistributionSourcePackageCache,
            Join(
                SourcePackageName,
                DistributionSourcePackageCache.sourcepackagename ==
                    SourcePackageName.id),
            ]

        conditions = [
            DistributionSourcePackageCache.distribution == self,
            Or(
                DistributionSourcePackageCache.archiveID.is_in(
                    self.all_distro_archive_ids),
                DistributionSourcePackageCache.archive == None),
            Or(
                fti_search(DistributionSourcePackageCache, text),
                DistributionSourcePackageCache.name.contains_string(
                    text.lower()))]

        if has_packaging is not None:
            packaging_query = Exists(Select(
                1, tables=[Packaging],
                where=(Packaging.sourcepackagenameID == SourcePackageName.id)))
            if has_packaging is False:
                packaging_query = Not(packaging_query)
            conditions.append(packaging_query)

        if publishing_distroseries is not None:
            origin.append(
                Join(
                    SourcePackagePublishingHistory,
                    SourcePackagePublishingHistory.sourcepackagenameID ==
                        DistributionSourcePackageCache.sourcepackagenameID))
            conditions.extend([
                SourcePackagePublishingHistory.distroseries ==
                    publishing_distroseries,
                SourcePackagePublishingHistory.archiveID.is_in(
                    self.all_distro_archive_ids),
                ])

        dsp_caches_with_ranks = store.using(*origin).find(
            find_spec, *conditions).order_by(
                Desc(SQL('rank')), DistributionSourcePackageCache.name)
        dsp_caches_with_ranks.config(distinct=True)
        return dsp_caches_with_ranks

    def searchSourcePackages(
        self, text, has_packaging=None, publishing_distroseries=None):
        """See `IDistribution`."""

        dsp_caches_with_ranks = self.searchSourcePackageCaches(
            text, has_packaging=has_packaging,
            publishing_distroseries=publishing_distroseries)

        # Create a function that will decorate the resulting
        # DistributionSourcePackageCaches, converting
        # them from the find_spec above into DSPs:
        def result_to_dsp(result):
            cache, source_package_name, rank = result
            return DistributionSourcePackage(
                self,
                source_package_name)

        # Return the decorated result set so the consumer of these
        # results will only see DSPs
        return DecoratedResultSet(dsp_caches_with_ranks, result_to_dsp)

    def searchBinaryPackages(self, package_name, exact_match=False):
        """See `IDistribution`."""
        from lp.soyuz.model.distributionsourcepackagecache import (
            DistributionSourcePackageCache,
            )
        store = Store.of(self)

        select_spec = (DistributionSourcePackageCache,)

        find_spec = (
            DistributionSourcePackageCache.distribution == self,
            DistributionSourcePackageCache.archiveID.is_in(
                self.all_distro_archive_ids))

        if exact_match:
            # To match BinaryPackageName.name exactly requires a very
            # slow 8 table join. So let's instead use binpkgnames, with
            # an ugly set of LIKEs matching spaces or either end of the
            # string on either side of the name. A regex is several
            # times slower and harder to escape.
            match_clause = (Or(
                DistributionSourcePackageCache.binpkgnames.like(
                    '%% %s %%' % package_name.lower()),
                DistributionSourcePackageCache.binpkgnames.like(
                    '%% %s' % package_name.lower()),
                DistributionSourcePackageCache.binpkgnames.like(
                    '%s %%' % package_name.lower()),
                DistributionSourcePackageCache.binpkgnames ==
                    package_name.lower()), )
        else:
            # In this case we can use a simplified find-spec as the
            # binary package names are present on the
            # DistributionSourcePackageCache records.
            match_clause = (
                DistributionSourcePackageCache.binpkgnames.like(
                    "%%%s%%" % package_name.lower()),)

        result_set = store.find(
            *(select_spec + find_spec + match_clause)).config(distinct=True)

        return result_set.order_by(DistributionSourcePackageCache.name)

    def searchOCIProjects(self, text=None):
        """See `IDistribution`."""
        # circular import
        from lp.registry.model.ociproject import OCIProject
        store = Store.of(self)
        clauses = [OCIProject.distribution == self]
        if text is not None:
            clauses += [
                OCIProject.ociprojectname_id == OCIProjectName.id,
                OCIProjectName.name.contains_string(text)]
        return store.find(
            OCIProject,
            *clauses)

    def guessPublishedSourcePackageName(self, pkgname):
        """See `IDistribution`"""
        assert isinstance(pkgname, six.string_types), (
            "Expected string. Got: %r" % pkgname)

        pkgname = pkgname.strip().lower()
        if not valid_name(pkgname):
            raise NotFoundError('Invalid package name: %s' % pkgname)

        if self.currentseries is None:
            # Distribution with no series can't have anything
            # published in it.
            raise NotFoundError('%s has no series; %r was never '
                                'published in it'
                                % (self.displayname, pkgname))

        sourcepackagename = SourcePackageName.selectOneBy(name=pkgname)
        if sourcepackagename:
            # Note that in the source package case, we don't restrict
            # the search to the distribution release, making a best
            # effort to find a package.
            publishing = IStore(SourcePackagePublishingHistory).find(
                SourcePackagePublishingHistory,
                # We use an extra query to get the IDs instead of an
                # inner join on archive because of the skewness in the
                # archive data. (There are many, many PPAs to consider
                # and PostgreSQL picks a bad query plan resulting in
                # timeouts).
                SourcePackagePublishingHistory.archiveID.is_in(
                    self.all_distro_archive_ids),
                SourcePackagePublishingHistory.sourcepackagename ==
                    sourcepackagename,
                SourcePackagePublishingHistory.status.is_in(
                    active_publishing_status),
                ).order_by(
                    Desc(SourcePackagePublishingHistory.id)).first()
            if publishing is not None:
                return sourcepackagename

            # Look to see if there is an official source package branch.
            # That's considered "published" enough.
            branch_links = getUtility(IFindOfficialBranchLinks)
            results = branch_links.findForDistributionSourcePackage(
                self.getSourcePackage(sourcepackagename))
            if results.any() is not None:
                return sourcepackagename

        # At this point we don't have a published source package by
        # that name, so let's try to find a binary package and work
        # back from there.
        binarypackagename = BinaryPackageName.selectOneBy(name=pkgname)
        if binarypackagename:
            # Ok, so we have a binarypackage with that name. Grab its
            # latest publication in the distribution (this may be an old
            # package name the end-user is groping for) -- and then get
            # the sourcepackagename from that.
            bpph = IStore(BinaryPackagePublishingHistory).find(
                BinaryPackagePublishingHistory,
                # See comment above for rationale for using an extra query
                # instead of an inner join. (Bottom line, it would time out
                # otherwise.)
                BinaryPackagePublishingHistory.archiveID.is_in(
                    self.all_distro_archive_ids),
                BinaryPackagePublishingHistory.binarypackagename ==
                    binarypackagename,
                BinaryPackagePublishingHistory.status.is_in(
                    active_publishing_status),
                ).order_by(
                    Desc(BinaryPackagePublishingHistory.id)).first()
            if bpph is not None:
                spr = bpph.binarypackagerelease.build.source_package_release
                return spr.sourcepackagename

        # We got nothing so signal an error.
        if sourcepackagename is None:
            # Not a binary package name, not a source package name,
            # game over!
            if binarypackagename:
                raise NotFoundError('Binary package %s not published in %s'
                                    % (pkgname, self.displayname))
            else:
                raise NotFoundError('Unknown package: %s' % pkgname)
        else:
            raise NotFoundError('Package %s not published in %s'
                                % (pkgname, self.displayname))

    # XXX cprov 20071024:  move this API to IArchiveSet, Distribution is
    # already too long and complicated.
    def getAllPPAs(self):
        """See `IDistribution`"""
        return Store.of(self).find(
            Archive,
            distribution=self,
            purpose=ArchivePurpose.PPA).order_by('id')

    def searchPPAs(self, text=None, show_inactive=False, user=None):
        """See `IDistribution`."""
        clauses = ["""
        Archive.purpose = %s AND
        Archive.distribution = %s AND
        Archive.owner = ValidPersonOrTeamCache.id
        """ % sqlvalues(ArchivePurpose.PPA, self)]

        clauseTables = ['ValidPersonOrTeamCache']
        orderBy = ['Archive.displayname']

        if not show_inactive:
            clauses.append("""
            Archive.id IN (
                SELECT archive FROM SourcepackagePublishingHistory
                WHERE status IN %s)
            """ % sqlvalues(active_publishing_status))

        if text:
            orderBy.insert(0, rank_by_fti(Archive, text))
            clauses.append(fti_search(Archive, text))

        if user is not None:
            if not user.inTeam(getUtility(ILaunchpadCelebrities).admin):
                clauses.append("""
                ((Archive.private = FALSE AND Archive.enabled = TRUE) OR
                 Archive.owner = %s OR
                 %s IN (SELECT TeamParticipation.person
                        FROM TeamParticipation
                        WHERE TeamParticipation.person = %s AND
                              TeamParticipation.team = Archive.owner)
                )
                """ % sqlvalues(user, user, user))
        else:
            clauses.append(
                "Archive.private = FALSE AND Archive.enabled = TRUE")

        return Archive.select(
            And(*clauses), orderBy=orderBy, clauseTables=clauseTables)

    def getPendingAcceptancePPAs(self):
        """See `IDistribution`."""
        query = """
        Archive.purpose = %s AND
        Archive.distribution = %s AND
        PackageUpload.archive = Archive.id AND
        PackageUpload.status = %s
        """ % sqlvalues(ArchivePurpose.PPA, self,
                        PackageUploadStatus.ACCEPTED)

        return Archive.select(
            query, clauseTables=['PackageUpload'],
            orderBy=['archive.id'], distinct=True)

    def getPendingPublicationPPAs(self):
        """See `IDistribution`."""
        src_archives = IStore(Archive).find(
            Archive,
            Archive.purpose == ArchivePurpose.PPA,
            Archive.distribution == self,
            SourcePackagePublishingHistory.archive == Archive.id,
            SourcePackagePublishingHistory.scheduleddeletiondate == None,
            SourcePackagePublishingHistory.dateremoved == None,
            Or(
                And(
                    SourcePackagePublishingHistory.status.is_in(
                        active_publishing_status),
                    SourcePackagePublishingHistory.datepublished == None),
                SourcePackagePublishingHistory.status ==
                    PackagePublishingStatus.DELETED,
                )).order_by(Archive.id).config(distinct=True)

        bin_archives = IStore(Archive).find(
            Archive,
            Archive.purpose == ArchivePurpose.PPA,
            Archive.distribution == self,
            BinaryPackagePublishingHistory.archive == Archive.id,
            BinaryPackagePublishingHistory.scheduleddeletiondate == None,
            BinaryPackagePublishingHistory.dateremoved == None,
            Or(
                And(
                    BinaryPackagePublishingHistory.status.is_in(
                        active_publishing_status),
                    BinaryPackagePublishingHistory.datepublished == None),
                BinaryPackagePublishingHistory.status ==
                    PackagePublishingStatus.DELETED,
                )).order_by(Archive.id).config(distinct=True)

        reapable_af_archives = IStore(Archive).find(
            Archive,
            Archive.purpose == ArchivePurpose.PPA,
            Archive.distribution == self,
            ArchiveFile.archive == Archive.id,
            ArchiveFile.scheduled_deletion_date < UTC_NOW,
            ).order_by(Archive.id).config(distinct=True)

        dirty_suites_archives = IStore(Archive).find(
            Archive,
            Archive.purpose == ArchivePurpose.PPA,
            Archive.distribution == self,
            Archive.dirty_suites != None,
            ).order_by(Archive.id)

        deleting_archives = IStore(Archive).find(
            Archive,
            Archive.purpose == ArchivePurpose.PPA,
            Archive.distribution == self,
            Archive.status == ArchiveStatus.DELETING,
            ).order_by(Archive.id)

        return src_archives.union(bin_archives).union(
            reapable_af_archives).union(dirty_suites_archives).union(
            deleting_archives)

    def getArchiveByComponent(self, component_name):
        """See `IDistribution`."""
        # XXX Julian 2007-08-16
        # These component names should be Soyuz-wide constants.
        componentMapToArchivePurpose = {
            'main': ArchivePurpose.PRIMARY,
            'restricted': ArchivePurpose.PRIMARY,
            'universe': ArchivePurpose.PRIMARY,
            'multiverse': ArchivePurpose.PRIMARY,
            'partner': ArchivePurpose.PARTNER,
            'contrib': ArchivePurpose.PRIMARY,
            'non-free': ArchivePurpose.PRIMARY,
            }

        try:
            # Map known components.
            return getUtility(IArchiveSet).getByDistroPurpose(self,
                componentMapToArchivePurpose[component_name])
        except KeyError:
            # Otherwise we defer to the caller.
            return None

    def getAllowedBugInformationTypes(self):
        """See `IDistribution.`"""
        return FREE_INFORMATION_TYPES

    def getDefaultBugInformationType(self):
        """See `IDistribution.`"""
        return InformationType.PUBLIC

    def userCanEdit(self, user):
        """See `IDistribution`."""
        if user is None:
            return False
        admins = getUtility(ILaunchpadCelebrities).admin
        return user.inTeam(self.owner) or user.inTeam(admins)

    def canAdministerOCIProjects(self, person):
        """See `IDistribution`."""
        if person is None:
            return False
        if person.inTeam(self.oci_project_admin):
            return True
        person_roles = IPersonRoles(person)
        if person_roles.in_admin or person_roles.isOwner(self):
            return True
        return False

    def newSeries(self, name, display_name, title, summary,
                  description, version, previous_series, registrant):
        """See `IDistribution`."""
        series = DistroSeries(
            distribution=self,
            name=name,
            display_name=display_name,
            title=title,
            summary=summary,
            description=description,
            version=version,
            status=SeriesStatus.EXPERIMENTAL,
            previous_series=previous_series,
            registrant=registrant)
        if (registrant.inTeam(self.driver)
            and not registrant.inTeam(self.owner)):
            # This driver is a release manager.
            series.driver = registrant

        # May wish to add this to the series rather than clearing the cache --
        # RBC 20100816.
        del get_property_cache(self).series

        return series

    @property
    def has_published_binaries(self):
        """See `IDistribution`."""
        store = Store.of(self)
        results = store.find(
            BinaryPackagePublishingHistory,
            DistroArchSeries.distroseries == DistroSeries.id,
            DistroSeries.distribution == self,
            BinaryPackagePublishingHistory.distroarchseries ==
                DistroArchSeries.id,
            BinaryPackagePublishingHistory.status ==
                PackagePublishingStatus.PUBLISHED).config(limit=1)

        return not results.is_empty()

    def sharesTranslationsWithOtherSide(self, person, language,
                                        sourcepackage=None,
                                        purportedly_upstream=False):
        """See `ITranslationPolicy`."""
        assert sourcepackage is not None, (
            "Translations sharing policy requires a SourcePackage.")

        if not sourcepackage.has_sharing_translation_templates:
            # There is no known upstream template or series.  Take the
            # uploader's word for whether these are upstream translations
            # (in which case they're shared) or not.
            # What are the consequences if that value is incorrect?  In
            # the case where translations from upstream are purportedly
            # from Ubuntu, we miss a chance at sharing when the package
            # is eventually matched up with a productseries.  An import
            # or sharing-script run will fix that.  In the case where
            # Ubuntu translations are purportedly from upstream, an
            # import can fix it once a productseries is selected; or a
            # merge done by a script will give precedence to the Product
            # translations for upstream.
            return purportedly_upstream

        productseries = sourcepackage.productseries
        return productseries.product.invitesTranslationEdits(person, language)

    def getBugTaskWeightFunction(self):
        """Provide a weight function to determine optimal bug task.

        Full weight is given to tasks for this distribution.

        Given that there must be a distribution task for a series of that
        distribution to have a task, we give no more weighting to a
        distroseries task than any other.
        """
        distributionID = self.id

        def weight_function(bugtask):
            if bugtask.distribution_id == distributionID:
                return OrderedBugTask(1, bugtask.id, bugtask)
            return OrderedBugTask(2, bugtask.id, bugtask)

        return weight_function

    @property
    def has_published_sources(self):
        for archive in self.all_distro_archives:
            if not archive.getPublishedSources().order_by().is_empty():
                return True
        return False

    def newOCIProject(self, registrant, name, description=None):
        """Create an `IOCIProject` for this distro."""
        if (not getFeatureFlag(OCI_PROJECT_ALLOW_CREATE) and not
                self.canAdministerOCIProjects(registrant)):
            raise Unauthorized("Creating new OCI projects is not allowed.")
        return getUtility(IOCIProjectSet).new(
            pillar=self, registrant=registrant, name=name,
            description=description)

    def setOCICredentials(self, registrant, registry_url,
                          region, username, password):
        """See `IDistribution`."""
        if not self.oci_project_admin:
            raise NoOCIAdminForDistribution()
        new_credentials = getUtility(IOCIRegistryCredentialsSet).getOrCreate(
            registrant,
            self.oci_project_admin,
            registry_url,
            {"username": username, "password": password, "region": region},
            override_owner=True)
        old_credentials = self.oci_registry_credentials
        if self.oci_registry_credentials != new_credentials:
            # Remove the old credentials as we're assigning new ones
            # or clearing them
            self.oci_registry_credentials = new_credentials
            if old_credentials:
                old_credentials.destroySelf()

    def deleteOCICredentials(self):
        """See `IDistribution`."""
        old_credentials = self.oci_registry_credentials
        if old_credentials:
            self.oci_registry_credentials = None
            old_credentials.destroySelf()


@implementer(IDistributionSet)
class DistributionSet:
    """This class is to deal with Distribution related stuff"""
    title = "Registered Distributions"

    def __iter__(self):
        """See `IDistributionSet`."""
        return iter(self.getDistros())

    def __getitem__(self, name):
        """See `IDistributionSet`."""
        distribution = self.getByName(name)
        if distribution is None:
            raise NotFoundError(name)
        return distribution

    def get(self, distributionid):
        """See `IDistributionSet`."""
        return Distribution.get(distributionid)

    def count(self):
        """See `IDistributionSet`."""
        return Distribution.select().count()

    def getDistros(self):
        """See `IDistributionSet`."""
        distros = Distribution.select()
        return sorted(
            shortlist(distros, 100), key=lambda distro: distro._sort_key)

    def getByName(self, name):
        """See `IDistributionSet`."""
        pillar = getUtility(IPillarNameSet).getByName(name)
        if not IDistribution.providedBy(pillar):
            return None
        return pillar

    def new(self, name, display_name, title, description, summary, domainname,
            members, owner, registrant, mugshot=None, logo=None, icon=None,
            vcs=None):
        """See `IDistributionSet`."""
        distro = Distribution(
            name=name,
            display_name=display_name,
            title=title,
            description=description,
            summary=summary,
            domainname=domainname,
            members=members,
            owner=owner,
            registrant=registrant,
            mugshot=mugshot,
            logo=logo,
            icon=icon,
            vcs=vcs)
        IStore(distro).add(distro)
        getUtility(IArchiveSet).new(distribution=distro,
            owner=owner, purpose=ArchivePurpose.PRIMARY)
        policies = itertools.product(
            (distro,), (InformationType.USERDATA,
                InformationType.PRIVATESECURITY))
        getUtility(IAccessPolicySource).create(policies)
        return distro

    def getCurrentSourceReleases(self, distro_source_packagenames):
        """See `IDistributionSet`."""
        releases = get_current_source_releases(
            distro_source_packagenames,
            lambda distro: distro.all_distro_archive_ids,
            lambda distro: DistroSeries.distribution == distro,
            [SourcePackagePublishingHistory.distroseriesID
                == DistroSeries.id],
            DistroSeries.distributionID)
        result = {}
        for spr, distro_id in releases:
            distro = getUtility(IDistributionSet).get(distro_id)
            result[distro.getSourcePackage(spr.sourcepackagename)] = (
                DistributionSourcePackageRelease(distro, spr))
        return result

    def getDerivedDistributions(self):
        """See `IDistributionSet`."""
        ubuntu_id = getUtility(ILaunchpadCelebrities).ubuntu.id
        return IStore(DistroSeries).find(
            Distribution,
            Distribution.id == DistroSeries.distributionID,
            DistroSeries.id == DistroSeriesParent.derived_series_id,
            DistroSeries.distributionID != ubuntu_id).config(distinct=True)
