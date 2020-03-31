# Copyright 2019-2020 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""OCI Project interfaces."""

from __future__ import absolute_import, print_function, unicode_literals

__metaclass__ = type
__all__ = [
    'IOCIProject',
    'IOCIProjectSet',
    ]

from lazr.restful.declarations import (
    call_with,
    export_as_webservice_entry,
    export_factory_operation,
    exported,
    operation_for_version,
    operation_parameters,
    REQUEST_USER,
    )
from lazr.restful.fields import (
    CollectionField,
    Reference,
    ReferenceChoice,
    )
from lp.registry.interfaces.person import IPerson
from zope.interface import Interface
from zope.schema import (
    Bool,
    Datetime,
    Int,
    Text,
    TextLine,
    )

from lp import _
from lp.app.validators.name import name_validator
from lp.bugs.interfaces.bugtarget import IBugTarget
from lp.code.interfaces.gitref import IGitRef
from lp.code.interfaces.hasgitrepositories import IHasGitRepositories
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.ociprojectname import IOCIProjectName
from lp.registry.interfaces.series import SeriesStatus
from lp.services.database.constants import DEFAULT
from lp.services.fields import PublicPersonChoice


class IOCIProjectView(IHasGitRepositories, Interface):
    """IOCIProject attributes that require launchpad.View permission."""

    id = Int(title=_("ID"), required=True, readonly=True)
    date_created = exported(Datetime(
        title=_("Date created"), required=True, readonly=True))
    date_last_modified = exported(Datetime(
        title=_("Date last modified"), required=True, readonly=True))

    registrant = exported(PublicPersonChoice(
        title=_("Registrant"),
        description=_("The person that registered this project."),
        vocabulary='ValidPersonOrTeam', required=True, readonly=True))

    series = exported(CollectionField(
        title=_("Series inside this OCI project."),
        # Really IOCIProjectSeries
        value_type=Reference(schema=Interface)))

    display_name = exported(TextLine(
        title=_("Display name for this OCI project."),
        required=True, readonly=True))

    def getSeriesByName(name):
        """Get an OCIProjectSeries for this OCIProject by series' name."""


class IOCIProjectEditableAttributes(IBugTarget):
    """IOCIProject attributes that can be edited.

    These attributes need launchpad.View to see, and launchpad.Edit to change.
    """

    distribution = exported(ReferenceChoice(
        title=_("The distribution that this OCI project is associated with."),
        schema=IDistribution, vocabulary="Distribution",
        required=True, readonly=False))
    name = exported(TextLine(
        title=_("Name"), required=True, readonly=False,
        constraint=name_validator,
        description=_("The name of this OCI project.")))
    ociprojectname = Reference(
        IOCIProjectName,
        title=_("The name of this OCI project, as an `IOCIProjectName`."),
        required=True,
        readonly=True)
    description = exported(Text(
        title=_("The description for this OCI project."),
        required=True, readonly=False))
    pillar = exported(Reference(
        IDistribution,
        title=_("The pillar containing this target."), readonly=True))


class IOCIProjectEdit(Interface):
    """IOCIProject attributes that require launchpad.Edit permission."""

    def newSeries(name, summary, registrant,
                  status=SeriesStatus.DEVELOPMENT, date_created=DEFAULT):
        """Creates a new `IOCIProjectSeries`."""


class IOCIProjectLegitimate(Interface):
    """IOCIProject methods that require launchpad.AnyLegitimatePerson
    permission.
    """
    @call_with(registrant=REQUEST_USER)
    @operation_parameters(
        name=Text(
            title=_("OCI Recipe name."),
            description=_("The name of the new OCI Recipe.")),
        owner=Reference(
            IPerson, title=_("Person or team that owns the new OCI Recipe.")),
        git_ref=Reference(IGitRef, title=_("Git branch.")),
        build_file=TextLine(
            title=_("Build file path."),
            description=_(
                "The relative path to the file within this recipe's "
                "branch that defines how to build the recipe.")),
        description=Text(
            title=_("Description for this recipe."),
            description=_("A short description of this recipe.")),
        official=Bool(
            title=_("Is this the official recipe?"),
            description=_("True if this recipe is official for its "
                          "OCI project.")))
    @export_factory_operation(Interface, [])
    @operation_for_version("devel")
    def newRecipe(name, registrant, owner, git_ref, build_file,
                  description=None, official=False, require_virtualized=True):
        """Create an IOCIRecipe for this project."""


class IOCIProject(IOCIProjectView, IOCIProjectEdit,
                  IOCIProjectEditableAttributes, IOCIProjectLegitimate):
    """A project containing Open Container Initiative recipes."""

    export_as_webservice_entry(
        publish_web_link=True, as_of="devel", singular_name="oci_project")


class IOCIProjectSet(Interface):
    """A utility to create and access OCI Projects."""

    def new(registrant, pillar, ociprojectname,
            date_created=None, description=None,
            bug_reporting_guidelines=None, bug_reported_acknowledgement=None,
            bugfiling_duplicate_search=False):
        """Create an `IOCIProject`."""

    def getByDistributionAndName(distribution, name):
        """Get the OCIProjects for a given distribution."""
