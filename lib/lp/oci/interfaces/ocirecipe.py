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
    'OCIRecipeNotOwner'
    ]

import httplib

from lazr.restful.declarations import error_status
from lazr.restful.fields import Reference

from zope.interface import Interface
from zope.schema import (
    Bool,
    Datetime,
    Int,
    Text,
    )
from zope.security.interfaces import Unauthorized

from lp import _
from lp.registry.interfaces.role import IHasOwner
from lp.registry.interfaces.ociproject import IOCIProject
from lp.services.fields import PublicPersonChoice


@error_status(httplib.UNAUTHORIZED)
class OCIRecipeNotOwner(Unauthorized):
    """The registrant/requester is not the owner or a member of its team."""


@error_status(httplib.BAD_REQUEST)
class OCIBuildAlreadyPending(Exception):
    """A build was requested when an identical build was already pending."""

    def __init__(self):
        super(OCIBuildAlreadyPending, self).__init__(
            "An identical build of this snap package is already pending.")


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


class IOCIRecipeEdit(Interface):
    """`IOCIRecipe` methods that require launchpad.Edit permission."""

    def destroySelf():
        """Delete this snap package, provided that it has no builds."""


class IOCIRecipeEditableAttributes(IHasOwner):
    """`IOCIRecipe` attributes that can be edited.

    These attributes need launchpad.View to see, and launchpad.Edit to change.
    """

    ociproject = Reference(
        IOCIProject,
        title=_("The OCI project that this recipe is for."),
        required=True,
        readonly=True)
    ociproject_default = Bool(
        title=_("OCI Project default"), required=True, default=False)

    description = Text(title=_("A short description of this recipe."))

    require_virtualized = Bool(
        title=_("Require virtualized"), required=True, default=True)


class IOCIRecipe(IOCIRecipeView, IOCIRecipeEdit, IOCIRecipeEditableAttributes):
    """A recipe for building Open Container Initiative images."""


class IOCIRecipeSet(Interface):
    """A utility to create and access OCI Recipes."""

    def new(registrant, owner, ociproject, ociproject_default,
            require_virtualized):
        """Create an IOCIRecipe."""
