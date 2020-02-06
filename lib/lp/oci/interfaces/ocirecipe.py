# Copyright 2019 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces related to recipes for OCI Images."""

from __future__ import absolute_import, print_function, unicode_literals

__metaclass__ = type
__all__ = [
    'IOCIRecipe',
    'IOCIRecipeEdit',
    'IOCIRecipeEditableAttributes',
    'IOCIRecipeSet',
    'IOCIRecipeView',
    'OCIRecipeBuildAlreadyPending',
    'OCIRecipeChannelAlreadyExists',
    'OCIRecipeNotOwner',
    ]

import httplib

from lazr.restful.declarations import error_status
from lazr.restful.fields import (
    CollectionField,
    Reference,
    )
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Datetime,
    Int,
    Text,
    )
from zope.security.interfaces import Unauthorized

from lp import _
from lp.code.interfaces.gitrepository import IGitRepository
from lp.registry.interfaces.ociproject import IOCIProject
from lp.registry.interfaces.role import IHasOwner
from lp.services.fields import (
    PersonChoice,
    PublicPersonChoice,
    )


@error_status(httplib.UNAUTHORIZED)
class OCIRecipeNotOwner(Unauthorized):
    """The registrant/requester is not the owner or a member of its team."""


@error_status(httplib.BAD_REQUEST)
class OCIRecipeBuildAlreadyPending(Exception):
    """A build was requested when an identical build was already pending."""

    def __init__(self):
        super(OCIRecipeBuildAlreadyPending, self).__init__(
            "An identical build of this snap package is already pending.")


@error_status(httplib.BAD_REQUEST)
class OCIRecipeChannelAlreadyExists(Exception):
    """A channel with that name already exists for this OCI recipe."""

    def __init__(self):
        super(OCIRecipeChannelAlreadyExists, self).__init__(
            "A channel with that name already exists for this OCI recipe.")


class IOCIRecipeView(Interface):
    """`IOCIRecipe` attributes that require launchpad.View permission."""

    id = Int(title=_("ID"), required=True, readonly=True)
    date_created = Datetime(
        title=_("Date created"), required=True, readonly=True)
    date_last_modified = Datetime(
        title=_("Date last modified"), required=True, readonly=True)

    registrant = PublicPersonChoice(
        title=_("Registrant"),
        description=_("The user who registered this recipe."),
        vocabulary='ValidPersonOrTeam', required=True, readonly=True)

    builds = CollectionField(
        title=_("Completed builds of this OCI recipe."),
        description=_(
            "Completed builds of this OCI recipe, sorted in descending "
            "order of finishing."),
        # Really IOCIRecipeBuild, patched in _schema_circular_imports.
        value_type=Reference(schema=Interface),
        required=True, readonly=True)

    completed_builds = CollectionField(
        title=_("Completed builds of this OCI recipe."),
        description=_(
            "Completed builds of this OCI recipe, sorted in descending "
            "order of finishing."),
        # Really IOCIRecipeBuild, patched in _schema_circular_imports.
        value_type=Reference(schema=Interface), readonly=True)

    pending_builds = CollectionField(
        title=_("Pending builds of this OCI recipe."),
        description=_(
            "Pending builds of this OCI recipe, sorted in descending "
            "order of creation."),
        # Really IOCIRecipeBuild, patched in _schema_circular_imports.
        value_type=Reference(schema=Interface), readonly=True)

    channels = Attribute("The channels that this OCI recipe can be build for.")


class IOCIRecipeEdit(Interface):
    """`IOCIRecipe` methods that require launchpad.Edit permission."""

    def addChannel(name, git_path, build_file):
        """Add a channel to this recipe."""

    def removeChannel(name):
        """Remove a channel from this recipe."""

    def destroySelf():
        """Delete this OCI recipe, provided that it has no builds."""


class IOCIRecipeEditableAttributes(IHasOwner):
    """`IOCIRecipe` attributes that can be edited.

    These attributes need launchpad.View to see, and launchpad.Edit to change.
    """

    owner = PersonChoice(
        title=_("Owner"), required=True, readonly=False,
        vocabulary="AllUserTeamsParticipationPlusSelf",
        description=_("The owner of this OCI recipe."))

    ociproject = Reference(
        IOCIProject,
        title=_("The OCI project that this recipe is for."),
        required=True,
        readonly=True)
    ociproject_default = Bool(
        title=_("OCI Project default"), required=True, default=False,
        description=_("True if this recipe is the default "
                      "for its OCI project."))

    git_repository = Reference(
        IGitRepository,
        title=_("A Git repository with a branch containing an OCI recipe."))

    description = Text(title=_("A short description of this recipe."))

    require_virtualized = Bool(
        title=_("Require virtualized"), required=True, default=True)

    build_daily = Bool(
        title=_("Build daily"), required=True, default=False,
        description=_("If True, this recipe should be built daily."))


class IOCIRecipe(IOCIRecipeView, IOCIRecipeEdit, IOCIRecipeEditableAttributes):
    """A recipe for building Open Container Initiative images."""


class IOCIRecipeSet(Interface):
    """A utility to create and access OCI Recipes."""

    def new(registrant, owner, ociproject, ociproject_default,
            require_virtualized):
        """Create an IOCIRecipe."""
