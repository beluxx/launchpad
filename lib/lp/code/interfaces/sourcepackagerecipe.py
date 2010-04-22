# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# pylint: disable-msg=E0211,E0213,F0401

"""Interface of the `SourcePackageRecipe` content type."""


__metaclass__ = type


__all__ = [
    'ForbiddenInstruction',
    'ISourcePackageRecipe',
    'ISourcePackageRecipeData',
    'ISourcePackageRecipeSource',
    'TooNewRecipeFormat',
    ]


from lazr.restful.declarations import export_as_webservice_entry
from lazr.restful.fields import CollectionField, Reference

from zope.interface import Attribute, Interface
from zope.schema import Bool, Datetime, Object, Text, TextLine

from canonical.launchpad import _
from canonical.launchpad.validators.name import name_validator

from lp.code.interfaces.branch import IBranch
from lp.registry.interfaces.person import IPerson
from lp.registry.interfaces.role import IHasOwner
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.registry.interfaces.sourcepackagename import ISourcePackageName


class ForbiddenInstruction(Exception):
    """A forbidden instruction was found in the recipe."""

    def __init__(self, instruction_name):
        super(ForbiddenInstruction, self).__init__()
        self.instruction_name = instruction_name


class TooNewRecipeFormat(Exception):
    """The format of the recipe supplied was too new."""

    def __init__(self, supplied_format, newest_supported):
        super(TooNewRecipeFormat, self).__init__()
        self.supplied_format = supplied_format
        self.newest_supported = newest_supported


class ISourcePackageRecipeData(Interface):
    """A recipe as database data, not text."""

    base_branch = Object(
        schema=IBranch, title=_("Base branch"), description=_(
            "The base branch to use when building the recipe."))

    deb_version_template = TextLine(
        title=_('deb-version template'),
        description = _(
            'The template that will be used to generate a deb version.'),)

    def getReferencedBranches():
        """An iterator of the branches referenced by this recipe."""



class ISourcePackageRecipe(IHasOwner, ISourcePackageRecipeData):
    """An ISourcePackageRecipe describes how to build a source package.

    More precisely, it describes how to combine a number of branches into a
    debianized source tree.
    """
    export_as_webservice_entry()

    date_created = Datetime(required=True, readonly=True)
    date_last_modified = Datetime(required=True, readonly=True)

    registrant = Reference(
        IPerson, title=_("The person who created this recipe"), readonly=True)
    owner = Reference(
        IPerson, title=_("The person or team who can edit this recipe"),
        readonly=False)
    distroseries = CollectionField(
        Reference(IDistroSeries), title=_("The distroseries this recipe will"
            " build a source package for"),
        readonly=False)
    build_daily = Bool(
        title=_("If true, the recipe should be built daily."))
    sourcepackagename = Reference(
        ISourcePackageName, title=_("The name of the source package this "
                                    "recipe will build a source package"),
        readonly=True)

    name = TextLine(
            title=_("Name"), required=True,
            constraint=name_validator,
            description=_("The name of this recipe."))

    description = Text(
        title=_('Description'), required=True,
        description=_('A short description of the recipe.'))

    builder_recipe = Attribute(
        _("The bzr-builder data structure for the recipe."))

    base_branch = Reference(
        IBranch, title=_("The base branch used by this recipe."),
        required=True, readonly=True)

    def requestBuild(archive, distroseries, requester, pocket):
        """Request that the recipe be built in to the specified archive.

        :param archive: The IArchive which you want the build to end up in.
        :param requester: the person requesting the build.
        :param pocket: the pocket that should be targeted.
        :raises: various specific upload errors if the requestor is not
            able to upload to the archive.
        """

    def getBuilds(pending=False):
        """Return a ResultSet of all the builds in the given state.

        :param pending: If True, select all builds that are pending.  If
            False, select all builds that are not pending.
        """

    def destroySelf():
        """Remove this SourcePackageRecipe from the database.

        This requires deleting any rows with non-nullable foreign key
        references to this object.
        """


class ISourcePackageRecipeSource(Interface):
    """A utility of this interface can be used to create and access recipes.
    """

    def new(registrant, owner, distroseries, sourcepackagename, name,
            builder_recipe, description):
        """Create an `ISourcePackageRecipe`."""
