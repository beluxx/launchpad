# Copyright 2019 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces for a build record for OCI recipes."""

from __future__ import absolute_import, print_function, unicode_literals

__metaclass__ = type
__all__ = [
    'IOCIFile',
    'IOCIRecipeBuild',
    'IOCIRecipeBuildSet',
    ]

from lazr.restful.fields import Reference
from zope.interface import Interface
from zope.schema import TextLine

from lp import _
from lp.buildmaster.interfaces.buildfarmjob import ISpecificBuildFarmJobSource
from lp.buildmaster.interfaces.packagebuild import IPackageBuild
from lp.oci.interfaces.ocirecipe import IOCIRecipe
from lp.services.database.constants import DEFAULT
from lp.services.fields import PublicPersonChoice
from lp.services.librarian.interfaces import ILibraryFileAlias


class IOCIRecipeBuildEdit(Interface):

    # XXX twom 2020-02-10 This will probably need cancel() implementing

    def addFile(lfa, layer_file_digest):
        """Add an OCI file to this build.

        :param lfa: An `ILibraryFileAlias`.
        :param layer_file_digest: Digest for this file, used for image layers.
        :return: An `IOCILayerFile`.
        """


class IOCIRecipeBuildView(IPackageBuild):

    requester = PublicPersonChoice(
        title=_("Requester"),
        description=_("The person who requested this OCI recipe build."),
        vocabulary='ValidPersonOrTeam', required=True, readonly=True)

    recipe = Reference(
        IOCIRecipe,
        title=_("The OCI recipe to build."),
        required=True,
        readonly=True)

    def getFileByFileName():
        """Retrieve a file by filename

        :return: A result set of (`IOCIFile`, `ILibraryFileAlias`,
            `ILibraryFileContent`).
        """

    def getLayerFileByDigest(layer_file_digest):
        """Retrieve a layer file by the digest.

        :param layer_file_digest: The digest to look up.
        :raises NotFoundError: if no file exists with the given digest.
        :return: The corresponding `ILibraryFileAlias`.
        """


class IOCIRecipeBuildAdmin(Interface):
    # XXX twom 2020-02-10 This will probably need rescore() implementing
    pass


class IOCIRecipeBuild(IOCIRecipeBuildAdmin, IOCIRecipeBuildEdit,
                      IOCIRecipeBuildView):
    """A build record for an OCI recipe."""


class IOCIRecipeBuildSet(ISpecificBuildFarmJobSource):
    """A utility to create and access OCIRecipeBuilds."""

    def new(requester, recipe, distro_arch_series,
            date_created=DEFAULT):
        """Create an `IOCIRecipeBuild`."""

    def preloadBuildsData(builds):
        """Load the data related to a list of OCI recipe builds."""


class IOCIFile(Interface):
    """A link between an OCI recipe build and a file in the librarian."""

    build = Reference(
        # Really IOCIBuild, patched in _schema_circular_imports.py.
        Interface,
        title=_("The OCI recipe build producing this file."),
        required=True, readonly=True)

    library_file = Reference(
        ILibraryFileAlias, title=_("A file in the librarian."),
        required=True, readonly=True)

    layer_file_digest = TextLine(
        title=_("Content-addressable hash of the file''s contents, "
                "used for image layers."),
        required=False, readonly=True)
