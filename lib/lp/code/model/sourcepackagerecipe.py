# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# pylint: disable-msg=F0401,W1001

"""Implementation of the `SourcePackageRecipe` content type."""

__metaclass__ = type
__all__ = [
    'get_buildable_distroseries_set',
    'SourcePackageRecipe',
    ]

from datetime import (
    datetime,
    timedelta,
    )

from lazr.delegates import delegates
from pytz import utc
from storm.expr import (
    And,
    Join,
    RightJoin,
    )
from storm.locals import (
    Bool,
    Desc,
    Int,
    Reference,
    ReferenceSet,
    Store,
    Storm,
    Unicode,
    )
from zope.component import getUtility
from zope.interface import (
    classProvides,
    implements,
    )

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.buildmaster.enums import BuildStatus
from lp.buildmaster.model.buildfarmjob import BuildFarmJob
from lp.buildmaster.model.packagebuild import PackageBuild
from lp.code.errors import (
    BuildAlreadyPending,
    BuildNotAllowedForDistro,
    TooManyBuilds,
    )
from lp.code.interfaces.sourcepackagerecipe import (
    ISourcePackageRecipe,
    ISourcePackageRecipeData,
    ISourcePackageRecipeSource,
    )
from lp.code.interfaces.sourcepackagerecipebuild import (
    ISourcePackageRecipeBuildSource,
    )
from lp.code.model.branch import Branch
from lp.code.model.sourcepackagerecipebuild import SourcePackageRecipeBuild
from lp.code.model.sourcepackagerecipedata import SourcePackageRecipeData
from lp.registry.interfaces.distroseries import IDistroSeriesSet
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.model.distroseries import DistroSeries
from lp.services.database.bulk import (
    load_referencing,
    load_related,
    )
from lp.services.database.constants import (
    DEFAULT,
    UTC_NOW,
    )
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.lpstorm import (
    IMasterStore,
    IStore,
    )
from lp.services.database.stormexpr import Greatest
from lp.services.propertycache import (
    cachedproperty,
    get_property_cache,
    )
from lp.soyuz.interfaces.archive import IArchiveSet
from lp.soyuz.model.archive import Archive


def get_buildable_distroseries_set(user):
    ppas = getUtility(IArchiveSet).getPPAsForUser(user)
    supported_distros = set([ppa.distribution for ppa in ppas])
    # Now add in Ubuntu.
    supported_distros.add(getUtility(ILaunchpadCelebrities).ubuntu)
    distros = getUtility(IDistroSeriesSet).search()

    buildables = []
    for distro in distros:
        if distro.active and distro.distribution in supported_distros:
            buildables.append(distro)
    return buildables


def recipe_modified(recipe, event):
    """Update the date_last_modified property when a recipe is modified.

    This method is registered as a subscriber to `IObjectModifiedEvent` events
    on recipes.
    """
    recipe.date_last_modified = UTC_NOW


class NonPPABuildRequest(Exception):
    """A build was requested to a non-PPA and this is currently
    unsupported."""


class _SourcePackageRecipeDistroSeries(Storm):
    """Link table for many-to-many relationship."""

    __storm_table__ = "SourcePackageRecipeDistroSeries"
    id = Int(primary=True)
    sourcepackagerecipe_id = Int(name='sourcepackagerecipe', allow_none=False)
    sourcepackage_recipe = Reference(
        sourcepackagerecipe_id, 'SourcePackageRecipe.id')
    distroseries_id = Int(name='distroseries', allow_none=False)
    distroseries = Reference(distroseries_id, 'DistroSeries.id')


class SourcePackageRecipe(Storm):
    """See `ISourcePackageRecipe` and `ISourcePackageRecipeSource`."""

    __storm_table__ = 'SourcePackageRecipe'

    def __str__(self):
        return '%s/%s' % (self.owner.name, self.name)

    implements(ISourcePackageRecipe)

    classProvides(ISourcePackageRecipeSource)

    delegates(ISourcePackageRecipeData, context='_recipe_data')

    id = Int(primary=True)

    daily_build_archive_id = Int(name='daily_build_archive', allow_none=True)
    daily_build_archive = Reference(daily_build_archive_id, 'Archive.id')

    date_created = UtcDateTimeCol(notNull=True)
    date_last_modified = UtcDateTimeCol(notNull=True)

    owner_id = Int(name='owner', allow_none=True)
    owner = Reference(owner_id, 'Person.id')

    registrant_id = Int(name='registrant', allow_none=True)
    registrant = Reference(registrant_id, 'Person.id')

    distroseries = ReferenceSet(
        id, _SourcePackageRecipeDistroSeries.sourcepackagerecipe_id,
        _SourcePackageRecipeDistroSeries.distroseries_id, DistroSeries.id)

    build_daily = Bool()

    is_stale = Bool()

    @property
    def _sourcepackagename_text(self):
        return self.sourcepackagename.name

    name = Unicode(allow_none=True)
    description = Unicode(allow_none=True)

    @cachedproperty
    def _recipe_data(self):
        return Store.of(self).find(
            SourcePackageRecipeData,
            SourcePackageRecipeData.sourcepackage_recipe == self).one()

    @property
    def builder_recipe(self):
        """Accesses of the recipe go to the SourcePackageRecipeData."""
        return self._recipe_data.getRecipe()

    @property
    def base_branch(self):
        return self._recipe_data.base_branch

    @staticmethod
    def preLoadDataForSourcePackageRecipes(sourcepackagerecipes):
        # Load the referencing SourcePackageRecipeData.
        spr_datas = load_referencing(
            SourcePackageRecipeData,
            sourcepackagerecipes, ['sourcepackage_recipe_id'])
        # Load the related branches.
        load_related(Branch, spr_datas, ['base_branch_id'])
        # Store the SourcePackageRecipeData in the sourcepackagerecipes
        # objects.
        for spr_data in spr_datas:
            cache = get_property_cache(spr_data.sourcepackage_recipe)
            cache._recipe_data = spr_data
        SourcePackageRecipeData.preLoadReferencedBranches(spr_datas)

    def setRecipeText(self, recipe_text):
        parsed = SourcePackageRecipeData.getParsedRecipe(recipe_text)
        self._recipe_data.setRecipe(parsed)

    @property
    def recipe_text(self):
        return self.builder_recipe.get_recipe_text()

    def updateSeries(self, distroseries):
        if distroseries != self.distroseries:
            self.distroseries.clear()
            for distroseries_item in distroseries:
                self.distroseries.add(distroseries_item)

    @staticmethod
    def new(registrant, owner, name, recipe, description,
            distroseries=None, daily_build_archive=None, build_daily=False,
            date_created=DEFAULT):
        """See `ISourcePackageRecipeSource.new`."""
        store = IMasterStore(SourcePackageRecipe)
        sprecipe = SourcePackageRecipe()
        builder_recipe = SourcePackageRecipeData.getParsedRecipe(recipe)
        SourcePackageRecipeData(builder_recipe, sprecipe)
        sprecipe.registrant = registrant
        sprecipe.owner = owner
        sprecipe.name = name
        if distroseries is not None:
            for distroseries_item in distroseries:
                sprecipe.distroseries.add(distroseries_item)
        sprecipe.description = description
        sprecipe.daily_build_archive = daily_build_archive
        sprecipe.build_daily = build_daily
        sprecipe.date_created = date_created
        sprecipe.date_last_modified = date_created
        store.add(sprecipe)
        return sprecipe

    @classmethod
    def findStaleDailyBuilds(cls):
        one_day_ago = datetime.now(utc) - timedelta(hours=23, minutes=50)
        joins = RightJoin(
            Join(
                Join(SourcePackageRecipeBuild, PackageBuild,
                    PackageBuild.id ==
                    SourcePackageRecipeBuild.package_build_id),
                BuildFarmJob,
                And(BuildFarmJob.id == PackageBuild.build_farm_job_id,
                    BuildFarmJob.date_created > one_day_ago)),
            SourcePackageRecipe,
            And(SourcePackageRecipeBuild.recipe == SourcePackageRecipe.id,
                SourcePackageRecipe.daily_build_archive_id ==
                    PackageBuild.archive_id))
        return IStore(cls).using(joins).find(
            cls, cls.is_stale == True, cls.build_daily == True,
            BuildFarmJob.date_created == None).config(distinct=True)

    @staticmethod
    def exists(owner, name):
        """See `ISourcePackageRecipeSource.new`."""
        store = IMasterStore(SourcePackageRecipe)
        recipe = store.find(
            SourcePackageRecipe,
            SourcePackageRecipe.owner == owner,
            SourcePackageRecipe.name == name).one()
        if recipe:
            return True
        else:
            return False

    def destroySelf(self):
        store = Store.of(self)
        self.distroseries.clear()
        self._recipe_data.instructions.find().remove()
        builds = store.find(
            SourcePackageRecipeBuild, SourcePackageRecipeBuild.recipe == self)
        builds.set(recipe_id=None)
        store.remove(self._recipe_data)
        store.remove(self)

    def isOverQuota(self, requester, distroseries):
        """See `ISourcePackageRecipe`."""
        return SourcePackageRecipeBuild.getRecentBuilds(
            requester, self, distroseries).count() >= 5

    def requestBuild(self, archive, requester, distroseries,
                     pocket=PackagePublishingPocket.RELEASE,
                     manual=False):
        """See `ISourcePackageRecipe`."""
        if not archive.is_ppa:
            raise NonPPABuildRequest

        buildable_distros = get_buildable_distroseries_set(archive.owner)
        if distroseries not in buildable_distros:
            raise BuildNotAllowedForDistro(self, distroseries)

        reject_reason = archive.checkUpload(
            requester, self.distroseries, None, archive.default_component,
            pocket)
        if reject_reason is not None:
            raise reject_reason
        if self.isOverQuota(requester, distroseries):
            raise TooManyBuilds(self, distroseries)
        pending = IStore(self).find(SourcePackageRecipeBuild,
            SourcePackageRecipeBuild.recipe_id == self.id,
            SourcePackageRecipeBuild.distroseries_id == distroseries.id,
            PackageBuild.archive_id == archive.id,
            PackageBuild.id == SourcePackageRecipeBuild.package_build_id,
            BuildFarmJob.id == PackageBuild.build_farm_job_id,
            BuildFarmJob.status == BuildStatus.NEEDSBUILD)
        if pending.any() is not None:
            raise BuildAlreadyPending(self, distroseries)

        build = getUtility(ISourcePackageRecipeBuildSource).new(distroseries,
            self, requester, archive)
        build.queueBuild()
        queue_record = build.buildqueue_record
        if manual:
            queue_record.manualScore(queue_record.lastscore + 100)
        return build

    def performDailyBuild(self):
        """See `ISourcePackageRecipe`."""
        builds = []
        self.is_stale = False
        for distroseries in self.distroseries:
            try:
                build = self.requestBuild(
                    self.daily_build_archive, self.owner,
                    distroseries, PackagePublishingPocket.RELEASE)
                builds.append(build)
            except BuildAlreadyPending:
                continue
        return builds

    @property
    def builds(self):
        """See `ISourcePackageRecipe`."""
        order_by = (Desc(Greatest(
                            BuildFarmJob.date_started,
                            BuildFarmJob.date_finished)),
                   Desc(BuildFarmJob.date_created), Desc(BuildFarmJob.id))
        return self._getBuilds(None, order_by)

    @property
    def completed_builds(self):
        """See `ISourcePackageRecipe`."""
        filter_term = BuildFarmJob.status != BuildStatus.NEEDSBUILD
        order_by = (Desc(Greatest(
                            BuildFarmJob.date_started,
                            BuildFarmJob.date_finished)),
                   Desc(BuildFarmJob.id))
        return self._getBuilds(filter_term, order_by)

    @property
    def pending_builds(self):
        """See `ISourcePackageRecipe`."""
        filter_term = BuildFarmJob.status == BuildStatus.NEEDSBUILD
        # We want to order by date_created but this is the same as ordering
        # by id (since id increases monotonically) and is less expensive.
        order_by = Desc(BuildFarmJob.id)
        return self._getBuilds(filter_term, order_by)

    def _getBuilds(self, filter_term, order_by):
        """The actual query to get the builds."""
        query_args = [
            SourcePackageRecipeBuild.recipe == self,
            SourcePackageRecipeBuild.package_build_id == PackageBuild.id,
            PackageBuild.build_farm_job_id == BuildFarmJob.id,
            And(PackageBuild.archive_id == Archive.id,
                Archive._enabled == True),
            ]
        if filter_term is not None:
            query_args.append(filter_term)
        result = Store.of(self).find(SourcePackageRecipeBuild, *query_args)
        result.order_by(order_by)
        return result

    def getPendingBuildInfo(self):
        """See `ISourcePackageRecipe`."""
        builds = self.pending_builds
        result = []
        for build in builds:
            result.append(
                {"distroseries": build.distroseries.displayname,
                 "archive": '%s/%s' %
                           (build.archive.owner.name, build.archive.name)})
        return result

    @property
    def last_build(self):
        """See `ISourcePackageRecipeBuild`."""
        return self._getBuilds(
            True, Desc(BuildFarmJob.date_finished)).first()

    def getMedianBuildDuration(self):
        """Return the median duration of builds of this recipe."""
        store = IStore(self)
        result = store.find(
            BuildFarmJob,
            SourcePackageRecipeBuild.recipe == self.id,
            BuildFarmJob.date_finished != None,
            BuildFarmJob.id == PackageBuild.build_farm_job_id,
            SourcePackageRecipeBuild.package_build_id == PackageBuild.id)
        durations = [build.date_finished - build.date_started for build in
                     result]
        if len(durations) == 0:
            return None
        durations.sort(reverse=True)
        return durations[len(durations) / 2]
