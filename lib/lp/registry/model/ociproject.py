# Copyright 2019-2020 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""OCI Project implementation."""

from __future__ import absolute_import, print_function, unicode_literals

__metaclass__ = type
__all__ = [
    'OCIProject',
    'OCIProjectSet',
    ]

import pytz
from six import text_type
from storm.locals import (
    Bool,
    DateTime,
    Int,
    Reference,
    Unicode,
    )
from zope.component import getUtility
from zope.interface import implementer
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import (
    FREE_INFORMATION_TYPES,
    ServiceUsage,
    )
from lp.bugs.model.bugtarget import BugTargetBase
from lp.oci.interfaces.ocirecipe import IOCIRecipeSet
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.ociproject import (
    IOCIProject,
    IOCIProjectSet,
    )
from lp.registry.interfaces.ociprojectname import IOCIProjectNameSet
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.product import IProduct
from lp.registry.interfaces.series import SeriesStatus
from lp.registry.model.ociprojectname import OCIProjectName
from lp.registry.model.ociprojectseries import OCIProjectSeries
from lp.registry.model.person import Person
from lp.services.database.bulk import load_related
from lp.services.database.constants import (
    DEFAULT,
    UTC_NOW,
    )
from lp.services.database.interfaces import (
    IMasterStore,
    IStore,
    )
from lp.services.database.stormbase import StormBase


def oci_project_modified(oci_project, event):
    """Update the date_last_modified property when an OCIProject is modified.

    This method is registered as a subscriber to `IObjectModifiedEvent`
    events on OCI projects.
    """
    # This attribute is normally read-only; bypass the security proxy to
    # avoid that.
    removeSecurityProxy(oci_project).date_last_modified = UTC_NOW


@implementer(IOCIProject)
class OCIProject(BugTargetBase, StormBase):
    """See `IOCIProject` and `IOCIProjectSet`."""

    __storm_table__ = "OCIProject"

    id = Int(primary=True)
    date_created = DateTime(
        name="date_created", tzinfo=pytz.UTC, allow_none=False)
    date_last_modified = DateTime(
        name="date_last_modified", tzinfo=pytz.UTC, allow_none=False)

    registrant_id = Int(name='registrant', allow_none=False)
    registrant = Reference(registrant_id, "Person.id")

    distribution_id = Int(name="distribution", allow_none=True)
    distribution = Reference(distribution_id, "Distribution.id")

    project_id = Int(name='project', allow_none=True)
    project = Reference(project_id, 'Product.id')

    ociprojectname_id = Int(name="ociprojectname", allow_none=False)
    ociprojectname = Reference(ociprojectname_id, "OCIProjectName.id")

    description = Unicode(name="description")

    bug_reporting_guidelines = Unicode(name="bug_reporting_guidelines")
    bug_reported_acknowledgement = Unicode(name="bug_reported_acknowledgement")
    enable_bugfiling_duplicate_search = Bool(
        name="enable_bugfiling_duplicate_search")

    answers_usage = ServiceUsage.NOT_APPLICABLE
    blueprints_usage = ServiceUsage.NOT_APPLICABLE
    codehosting_usage = ServiceUsage.NOT_APPLICABLE
    translations_usage = ServiceUsage.NOT_APPLICABLE
    bug_tracking_usage = ServiceUsage.LAUNCHPAD
    uses_launchpad = True

    @property
    def name(self):
        return self.ociprojectname.name

    @name.setter
    def name(self, value):
        self.ociprojectname = getUtility(IOCIProjectNameSet).getOrCreateByName(
            value)

    @property
    def pillar(self):
        """See `IBugTarget`."""
        return self.project if self.project_id else self.distribution

    @pillar.setter
    def pillar(self, pillar):
        if IDistribution.providedBy(pillar):
            self.distribution = pillar
            self.project = None
        elif IProduct.providedBy(pillar):
            self.project = pillar
            self.distribution = None
        else:
            raise ValueError(
                'The target of an OCIProject must be either an IDistribution '
                'or IProduct instance.')

    @property
    def display_name(self):
        """See `IOCIProject`."""
        return "OCI project %s for %s" % (
            self.ociprojectname.name, self.pillar.display_name)

    displayname = display_name
    bugtargetname = display_name
    bugtargetdisplayname = display_name
    title = display_name

    def _customizeSearchParams(self, search_params):
        """Customize `search_params` for this OCI project."""
        search_params.setOCIProject(self)

    @property
    def driver(self):
        """See `IOCIProject`."""
        return self.pillar.driver

    @property
    def bug_supervisor(self):
        """See `IOCIProject`."""
        return self.pillar.bug_supervisor

    def getAllowedBugInformationTypes(self):
        """See `IDistribution.`"""
        return FREE_INFORMATION_TYPES

    def newRecipe(self, name, registrant, owner, git_ref,
                  build_file, description=None, build_daily=False,
                  require_virtualized=True, build_args=None):
        return getUtility(IOCIRecipeSet).new(
            name=name,
            registrant=registrant,
            owner=owner,
            oci_project=self,
            git_ref=git_ref,
            build_file=build_file,
            build_args=build_args,
            description=description,
            require_virtualized=require_virtualized,
            build_daily=build_daily,
        )

    def newSeries(self, name, summary, registrant,
                  status=SeriesStatus.DEVELOPMENT, date_created=DEFAULT):
        """See `IOCIProject`."""
        series = OCIProjectSeries(
            oci_project=self,
            name=name,
            summary=summary,
            registrant=registrant,
            status=status,
        )
        return series

    @property
    def series(self):
        """See `IOCIProject`."""
        ret = IStore(OCIProjectSeries).find(
            OCIProjectSeries,
            OCIProjectSeries.oci_project == self
            ).order_by(OCIProjectSeries.date_created)
        return ret

    def getSeriesByName(self, name):
        return self.series.find(OCIProjectSeries.name == name).one()

    def getRecipes(self):
        """See `IOCIProject`."""
        from lp.oci.model.ocirecipe import OCIRecipe
        rs = IStore(OCIRecipe).find(
            OCIRecipe,
            OCIRecipe.owner_id == Person.id,
            OCIRecipe.oci_project == self)
        return rs.order_by(Person.name, OCIRecipe.name)

    def getRecipeByNameAndOwner(self, recipe_name, owner_name):
        """See `IOCIProject`."""
        from lp.oci.model.ocirecipe import OCIRecipe
        q = self.getRecipes().find(
            OCIRecipe.name == recipe_name,
            Person.name == owner_name)
        return q.one()

    def searchRecipes(self, query):
        """See `IOCIProject`."""
        from lp.oci.model.ocirecipe import OCIRecipe
        q = self.getRecipes().find(
            OCIRecipe.name.contains_string(query) |
            Person.name.contains_string(query))
        return q.order_by(Person.name, OCIRecipe.name)

    def getOfficialRecipe(self):
        """See `IOCIProject`."""
        from lp.oci.model.ocirecipe import OCIRecipe
        return self.getRecipes().find(OCIRecipe._official == True).one()

    def setOfficialRecipe(self, recipe):
        """See `IOCIProject`."""
        if recipe is not None and recipe.oci_project != self:
            raise ValueError(
                "An OCI recipe cannot be set as the official recipe of "
                "another OCI project.")
        # Removing security proxy here because `_official` is a private
        # attribute not declared on the Interface, and we need to set it
        # regardless of security checks on OCIRecipe objects.
        recipe = removeSecurityProxy(recipe)
        previous = removeSecurityProxy(self.getOfficialRecipe())
        if previous != recipe:
            if previous is not None:
                previous._official = False
            if recipe is not None:
                recipe._official = True


@implementer(IOCIProjectSet)
class OCIProjectSet:

    def new(self, registrant, pillar, name,
            date_created=DEFAULT, description=None,
            bug_reporting_guidelines=None,
            bug_reported_acknowledgement=None,
            bugfiling_duplicate_search=False):
        """See `IOCIProjectSet`."""
        if isinstance(name, text_type):
            name = getUtility(IOCIProjectNameSet).getOrCreateByName(
                name)
        store = IMasterStore(OCIProject)
        target = OCIProject()
        target.date_created = date_created
        target.date_last_modified = date_created
        target.pillar = pillar
        target.registrant = registrant
        target.ociprojectname = name
        target.description = description
        target.bug_reporting_guidelines = bug_reporting_guidelines
        target.bug_reported_acknowledgement = bug_reported_acknowledgement
        target.enable_bugfiling_duplicate_search = bugfiling_duplicate_search
        store.add(target)
        return target

    def _get_pillar_attribute(self, pillar):
        """Checks if the provided pillar is a valid one for OCIProject,
        returning the model attribute where this pillar would be stored.

        If pillar is not valid, raises ValueError.

        :param pillar: A Distribution or Product.
        :return: Storm attribute where the pillar would be stored.
                 If pillar is not valid, raises ValueError.
        """
        if IDistribution.providedBy(pillar):
            return OCIProject.distribution
        elif IProduct.providedBy(pillar):
            return OCIProject.project
        else:
            raise ValueError(
                'The target of an OCIProject must be either an '
                'IDistribution or an IProduct instance.')

    def getByPillarAndName(self, pillar, name):
        """See `IOCIProjectSet`."""
        target = IStore(OCIProject).find(
            OCIProject,
            self._get_pillar_attribute(pillar) == pillar,
            OCIProject.ociprojectname == OCIProjectName.id,
            OCIProjectName.name == name).one()
        return target

    def findByPillarAndName(self, pillar, name_substring):
        """See `IOCIProjectSet`."""
        return IStore(OCIProject).find(
            OCIProject,
            self._get_pillar_attribute(pillar) == pillar,
            OCIProject.ociprojectname == OCIProjectName.id,
            OCIProjectName.name.contains_string(name_substring))

    def preloadDataForOCIProjects(self, oci_projects):
        """See `IOCIProjectSet`."""
        oci_projects = [removeSecurityProxy(i) for i in oci_projects]

        person_ids = [i.registrant_id for i in oci_projects]
        list(getUtility(IPersonSet).getPrecachedPersonsFromIDs(
            person_ids, need_validity=True))

        load_related(OCIProjectName, oci_projects, ["ociprojectname_id"])
