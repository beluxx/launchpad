# Copyright 2021 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Charm recipe interfaces."""

from __future__ import absolute_import, print_function, unicode_literals

__metaclass__ = type
__all__ = [
    "BadCharmRecipeSource",
    "BadCharmRecipeSearchContext",
    "CHARM_RECIPE_ALLOW_CREATE",
    "CHARM_RECIPE_PRIVATE_FEATURE_FLAG",
    "CharmRecipeFeatureDisabled",
    "CharmRecipeNotOwner",
    "CharmRecipePrivacyMismatch",
    "CharmRecipePrivateFeatureDisabled",
    "DuplicateCharmRecipeName",
    "ICharmRecipe",
    "ICharmRecipeSet",
    "NoSourceForCharmRecipe",
    "NoSuchCharmRecipe",
    ]

from lazr.restful.declarations import error_status
from lazr.restful.fields import (
    Reference,
    ReferenceChoice,
    )
from six.moves import http_client
from zope.interface import Interface
from zope.schema import (
    Bool,
    Choice,
    Datetime,
    Dict,
    Int,
    List,
    Text,
    TextLine,
    )
from zope.security.interfaces import Unauthorized

from lp import _
from lp.app.enums import InformationType
from lp.app.errors import NameLookupFailed
from lp.app.interfaces.informationtype import IInformationType
from lp.app.interfaces.launchpad import IPrivacy
from lp.app.validators.name import name_validator
from lp.app.validators.path import path_does_not_escape
from lp.code.interfaces.gitref import IGitRef
from lp.code.interfaces.gitrepository import IGitRepository
from lp.registry.interfaces.product import IProduct
from lp.services.fields import (
    PersonChoice,
    PublicPersonChoice,
    )
from lp.snappy.validators.channels import channels_validator


CHARM_RECIPE_ALLOW_CREATE = "charm.recipe.create.enabled"
CHARM_RECIPE_PRIVATE_FEATURE_FLAG = "charm.recipe.allow_private"


@error_status(http_client.UNAUTHORIZED)
class CharmRecipeFeatureDisabled(Unauthorized):
    """Only certain users can create new charm recipes."""

    def __init__(self):
        super(CharmRecipeFeatureDisabled, self).__init__(
            "You do not have permission to create new charm recipes.")


@error_status(http_client.UNAUTHORIZED)
class CharmRecipePrivateFeatureDisabled(Unauthorized):
    """Only certain users can create private charm recipes."""

    def __init__(self):
        super(CharmRecipePrivateFeatureDisabled, self).__init__(
            "You do not have permission to create private charm recipes.")


@error_status(http_client.BAD_REQUEST)
class DuplicateCharmRecipeName(Exception):
    """Raised for charm recipes with duplicate project/owner/name."""

    def __init__(self):
        super(DuplicateCharmRecipeName, self).__init__(
            "There is already a charm recipe with the same project, owner, "
            "and name.")


@error_status(http_client.UNAUTHORIZED)
class CharmRecipeNotOwner(Unauthorized):
    """The registrant/requester is not the owner or a member of its team."""


class NoSuchCharmRecipe(NameLookupFailed):
    """The requested charm recipe does not exist."""
    _message_prefix = "No such charm recipe with this owner and project"


@error_status(http_client.BAD_REQUEST)
class NoSourceForCharmRecipe(Exception):
    """Charm recipes must have a source (Git branch)."""

    def __init__(self):
        super(NoSourceForCharmRecipe, self).__init__(
            "New charm recipes must have a Git branch.")


@error_status(http_client.BAD_REQUEST)
class BadCharmRecipeSource(Exception):
    """The elements of the source for a charm recipe are inconsistent."""


@error_status(http_client.BAD_REQUEST)
class CharmRecipePrivacyMismatch(Exception):
    """Charm recipe privacy does not match its content."""

    def __init__(self, message=None):
        super(CharmRecipePrivacyMismatch, self).__init__(
            message or
            "Charm recipe contains private information and cannot be public.")


class BadCharmRecipeSearchContext(Exception):
    """The context is not valid for a charm recipe search."""


class ICharmRecipeView(Interface):
    """`ICharmRecipe` attributes that require launchpad.View permission."""

    id = Int(title=_("ID"), required=True, readonly=True)

    date_created = Datetime(
        title=_("Date created"), required=True, readonly=True)
    date_last_modified = Datetime(
        title=_("Date last modified"), required=True, readonly=True)

    registrant = PublicPersonChoice(
        title=_("Registrant"), required=True, readonly=True,
        vocabulary="ValidPersonOrTeam",
        description=_("The person who registered this charm recipe."))

    private = Bool(
        title=_("Private"), required=False, readonly=False,
        description=_("Whether this charm recipe is private."))

    def getAllowedInformationTypes(user):
        """Get a list of acceptable `InformationType`s for this charm recipe.

        If the user is a Launchpad admin, any type is acceptable.
        """

    def visibleByUser(user):
        """Can the specified user see this charm recipe?"""


class ICharmRecipeEdit(Interface):
    """`ICharmRecipe` methods that require launchpad.Edit permission."""

    def destroySelf():
        """Delete this charm recipe, provided that it has no builds."""


class ICharmRecipeEditableAttributes(Interface):
    """`ICharmRecipe` attributes that can be edited.

    These attributes need launchpad.View to see, and launchpad.Edit to change.
    """

    owner = PersonChoice(
        title=_("Owner"), required=True, readonly=False,
        vocabulary="AllUserTeamsParticipationPlusSelf",
        description=_("The owner of this charm recipe."))

    project = ReferenceChoice(
        title=_("The project that this charm recipe is associated with"),
        schema=IProduct, vocabulary="Product",
        required=True, readonly=False)

    name = TextLine(
        title=_("Charm recipe name"), required=True, readonly=False,
        constraint=name_validator,
        description=_("The name of the charm recipe."))

    description = Text(
        title=_("Description"), required=False, readonly=False,
        description=_("A description of the charm recipe."))

    git_repository = ReferenceChoice(
        title=_("Git repository"),
        schema=IGitRepository, vocabulary="GitRepository",
        required=False, readonly=True,
        description=_(
            "A Git repository with a branch containing a charmcraft.yaml "
            "recipe."))

    git_path = TextLine(
        title=_("Git branch path"), required=False, readonly=False,
        description=_(
            "The path of the Git branch containing a charmcraft.yaml "
            "recipe."))

    git_ref = Reference(
        IGitRef, title=_("Git branch"), required=False, readonly=False,
        description=_("The Git branch containing a charmcraft.yaml recipe."))

    build_path = TextLine(
        title=_("Build path"),
        description=_(
            "Subdirectory within the branch containing charmcraft.yaml."),
        constraint=path_does_not_escape, required=False, readonly=False)

    information_type = Choice(
        title=_("Information type"), vocabulary=InformationType,
        required=True, readonly=False, default=InformationType.PUBLIC,
        description=_(
            "The type of information contained in this charm recipe."))

    auto_build = Bool(
        title=_("Automatically build when branch changes"),
        required=True, readonly=False,
        description=_(
            "Whether this charm recipe is built automatically when the branch "
            "containing its charmcraft.yaml recipe changes."))

    auto_build_channels = Dict(
        title=_("Source snap channels for automatic builds"),
        key_type=TextLine(), required=False, readonly=False,
        description=_(
            "A dictionary mapping snap names to channels to use when building "
            "this charm recipe.  Currently only 'core', 'core18', 'core20', "
            "and 'charmcraft' keys are supported."))

    is_stale = Bool(
        title=_("Charm recipe is stale and is due to be rebuilt."),
        required=True, readonly=True)

    store_upload = Bool(
        title=_("Automatically upload to store"),
        required=True, readonly=False,
        description=_(
            "Whether builds of this charm recipe are automatically uploaded "
            "to the store."))

    store_name = TextLine(
        title=_("Registered store name"),
        required=False, readonly=False,
        description=_(
            "The registered name of this charm in the store."))

    store_secrets = List(
        value_type=TextLine(), title=_("Store upload tokens"),
        required=False, readonly=False,
        description=_(
            "Serialized secrets issued by the store and the login service to "
            "authorize uploads of this charm recipe."))

    store_channels = List(
        title=_("Store channels"),
        required=False, readonly=False, constraint=channels_validator,
        description=_(
            "Channels to release this charm to after uploading it to the "
            "store. A channel is defined by a combination of an optional "
            "track, a risk, and an optional branch, e.g. "
            "'2.1/stable/fix-123', '2.1/stable', 'stable/fix-123', or "
            "'stable'."))


class ICharmRecipeAdminAttributes(Interface):
    """`ICharmRecipe` attributes that can be edited by admins.

    These attributes need launchpad.View to see, and launchpad.Admin to change.
    """

    require_virtualized = Bool(
        title=_("Require virtualized builders"), required=True, readonly=False,
        description=_("Only build this charm recipe on virtual builders."))


class ICharmRecipe(
        ICharmRecipeView, ICharmRecipeEdit, ICharmRecipeEditableAttributes,
        ICharmRecipeAdminAttributes, IPrivacy, IInformationType):
    """A buildable charm recipe."""


class ICharmRecipeSet(Interface):
    """A utility to create and access charm recipes."""

    def new(registrant, owner, project, name, description=None, git_ref=None,
            build_path=None, require_virtualized=True,
            information_type=InformationType.PUBLIC, auto_build=False,
            auto_build_channels=None, store_upload=False, store_name=None,
            store_secrets=None, store_channels=None, date_created=None):
        """Create an `ICharmRecipe`."""

    def getByName(owner, project, name):
        """Returns the appropriate `ICharmRecipe` for the given objects."""

    def isValidInformationType(information_type, owner, git_ref=None):
        """Whether the information type context is valid."""

    def findByGitRepository(repository, paths=None):
        """Return all charm recipes for the given Git repository.

        :param repository: An `IGitRepository`.
        :param paths: If not None, only return charm recipes for one of
            these Git reference paths.
        """

    def detachFromGitRepository(repository):
        """Detach all charm recipes from the given Git repository.

        After this, any charm recipes that previously used this repository
        will have no source and so cannot dispatch new builds.
        """
