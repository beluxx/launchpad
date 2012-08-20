# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# pylint: disable-msg=E0211,E0213

"""Queue interfaces."""

__metaclass__ = type

__all__ = [
    'IHasQueueItems',
    'IPackageUploadQueue',
    'IPackageUpload',
    'IPackageUploadBuild',
    'IPackageUploadSource',
    'IPackageUploadCustom',
    'IPackageUploadSet',
    'NonBuildableSourceUploadError',
    'QueueAdminUnauthorizedError',
    'QueueBuildAcceptError',
    'QueueInconsistentStateError',
    'QueueSourceAcceptError',
    'QueueStateWriteProtectedError',
    ]

import httplib

from lazr.enum import DBEnumeratedType
from lazr.restful.declarations import (
    call_with,
    error_status,
    export_as_webservice_entry,
    export_read_operation,
    export_write_operation,
    exported,
    operation_for_version,
    operation_parameters,
    REQUEST_USER,
    )
from lazr.restful.fields import Reference
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Choice,
    Datetime,
    Dict,
    Int,
    List,
    TextLine,
    )
from zope.security.interfaces import Unauthorized

from lp import _
from lp.soyuz.enums import PackageUploadStatus
from lp.soyuz.interfaces.packagecopyjob import IPackageCopyJob


class QueueStateWriteProtectedError(Exception):
    """This exception prevent directly set operation in queue state.

    The queue state machine is controlled by its specific provided methods,
    like: setNew, setAccepted and so on.
    """


@error_status(httplib.BAD_REQUEST)
class QueueInconsistentStateError(Exception):
    """Queue state machine error.

    It's generated when the solicited state makes the record
    inconsistent against the current system constraints.
    """


class QueueAdminUnauthorizedError(Unauthorized):
    """User not permitted to perform a queue administration operation."""


class NonBuildableSourceUploadError(QueueInconsistentStateError):
    """Source upload will not result in any build record.

    This error is raised when trying to accept a source upload that is
    consistent but will not build in any of the architectures supported
    in its targeted distroseries.
    """


class QueueSourceAcceptError(Exception):
    """It prevents a PackageUploadSource from being ACCEPTED.

    It is generated by Component and/or Section mismatching in a DistroSeries.
    """


class QueueBuildAcceptError(Exception):
    """It prevents a PackageUploadBuild from being ACCEPTED.

    It is generated by Component and/or Section mismatching in a DistroSeries.
    """


class IPackageUploadQueue(Interface):
    """Used to establish permission to a group of package uploads.

    Receives an IDistroSeries and a PackageUploadStatus dbschema
    on initialization.
    No attributes exposed via interface, only used to check permissions.
    """


class IPackageUpload(Interface):
    """A Queue item for the archive uploader."""

    export_as_webservice_entry(publish_web_link=False)

    id = exported(
        Int(
            title=_("ID"), required=True, readonly=True,
            ))

    status = exported(
        Choice(
            vocabulary=PackageUploadStatus,
            description=_("The status of this upload."),
            title=_("Queue status"), required=False, readonly=True,
            ))

    distroseries = exported(
        Reference(
            # Really IDistroSeries, patched in
            # _schema_circular_imports.py
            schema=Interface,
            description=_("The distroseries targeted by this upload."),
            title=_("Series"), required=True, readonly=False,
            ))

    pocket = exported(
        Choice(
            # Really PackagePublishingPocket, patched in
            # _schema_circular_imports.py
            vocabulary=DBEnumeratedType,
            description=_("The pocket targeted by this upload."),
            title=_("The pocket"), required=True, readonly=False,
            ))

    date_created = exported(
        Datetime(
            title=_('Date created'),
            description=_("The date this package upload was done.")))

    changesfile = Attribute("The librarian alias for the changes file "
                            "associated with this upload")
    changes_file_url = exported(
        TextLine(
            title=_("Changes file URL"),
            description=_("Librarian URL for the changes file associated with "
                          "this upload. Will be None if the upload was copied "
                          "from another series."),
            required=False, readonly=True),
        as_of="devel")

    signing_key = Attribute("Changesfile Signing Key.")

    package_copy_job = Reference(
        schema=IPackageCopyJob,
        description=_("The PackageCopyJob for this upload, if it has one."),
        title=_("Raw Package Copy Job"), required=False, readonly=True)

    concrete_package_copy_job = Reference(
        schema=IPackageCopyJob,
        description=_("Concrete IPackageCopyJob implementation, if any."),
        title=_("Package Copy Job"), required=False, readonly=True)

    archive = exported(
        Reference(
            # Really IArchive, patched in _schema_circular_imports.py
            schema=Interface,
            description=_("The archive for this upload."),
            title=_("Archive"), required=True, readonly=True))
    sources = Attribute("The queue sources associated with this queue item")
    builds = Attribute("The queue builds associated with the queue item")

    customfiles = Attribute("Custom upload files associated with this "
                            "queue item")
    custom_file_urls = exported(
        List(
            title=_("Custom file URLs"),
            description=_("Librarian URLs for all the custom files attached "
                          "to this upload."),
            value_type=TextLine(),
            required=False,
            readonly=True),
        ("devel", dict(exported=False)), exported=True)

    displayname = exported(
        TextLine(
            title=_("Generic displayname for a queue item"), readonly=True),
        exported_as="display_name")
    displayversion = exported(
        TextLine(
            title=_("This item's displayable source package version"),
            readonly=True),
        exported_as="display_version")
    displayarchs = exported(
        TextLine(
            title=_("Architectures related to this item"), readonly=True),
        exported_as="display_arches")

    sourcepackagerelease = Attribute(
        "The source package release for this item")

    package_name = exported(
        TextLine(
            title=_("Name of the uploaded source package"), readonly=True),
        as_of="devel")

    package_version = exported(
        TextLine(title=_("Source package version"), readonly=True),
        as_of="devel")

    component_name = exported(
        TextLine(title=_("Source package component name"), readonly=True),
        as_of="devel")

    section_name = exported(
        TextLine(title=_("Source package section name"), readonly=True),
        as_of="devel")

    contains_source = exported(
        Bool(
            title=_("Whether or not this upload contains sources"),
            readonly=True),
        as_of="devel")
    contains_build = exported(
        Bool(
            title=_("Whether or not this upload contains binaries"),
            readonly=True),
        as_of="devel")
    contains_copy = exported(
        Bool(
            title=_("Whether or not this upload contains a copy from another "
                    "series."),
            readonly=True),
        as_of="devel")
    contains_installer = Attribute(
        "whether or not this upload contains installers images")
    contains_translation = Attribute(
        "whether or not this upload contains translations")
    contains_upgrader = Attribute(
        "whether or not this upload contains upgrader images")
    contains_ddtp = Attribute(
        "whether or not this upload contains DDTP images")
    contains_uefi = Attribute(
        "whether or not this upload contains a signed UEFI boot loader image")
    isPPA = Attribute(
        "Return True if this PackageUpload is a PPA upload.")
    is_delayed_copy = Attribute(
        "Whether or not this PackageUpload record is a delayed-copy.")

    components = Attribute(
        """The set of components used in this upload.

        For sources, this is the component on the associated
        sourcepackagerelease.  For binaries, this is all the components
        on all the binarypackagerelease records arising from the build.
        """)

    @export_read_operation()
    @operation_for_version("devel")
    def sourceFileUrls():
        """URLs for all the source files attached to this upload.

        :return: A collection of URLs for this upload.
        """

    @export_read_operation()
    @operation_for_version("devel")
    def binaryFileUrls():
        """URLs for all the binary files attached to this upload.

        :return: A collection of URLs for this upload.
        """

    @export_read_operation()
    @operation_for_version("devel")
    def customFileUrls():
        """URLs for all the custom files attached to this upload.

        :return: A collection of URLs for this upload.
        """

    @export_read_operation()
    @operation_for_version("devel")
    def getBinaryProperties():
        """The properties of the binaries associated with this queue item.

        :return: A list of dictionaries, each containing the properties of a
            single binary.
        """

    def getFileByName(filename):
        """Return the corresponding `ILibraryFileAlias` in this context.

        The following file types (and extension) can be looked up in the
        PackageUpload context:

         * Changes files: '.changes';
         * Source files: '.orig.tar.gz', 'tar.gz', '.diff.gz' and '.dsc'.
         * Custom files: '.tar.gz'.

        :param filename: the exact filename to be looked up.

        :raises NotFoundError if no file could be found.

        :return the corresponding `ILibraryFileAlias` if the file was found.
        """

    def setNew():
        """Set queue state to NEW."""

    def setUnapproved():
        """Set queue state to UNAPPROVED."""

    def setAccepted():
        """Set queue state to ACCEPTED.

        Perform the required checks on its content, so we guarantee data
        integrity by code.
        """

    def setDone():
        """Set queue state to DONE."""

    def setRejected():
        """Set queue state to REJECTED."""

    def acceptFromUploader(changesfile_path, logger=None):
        """Perform upload acceptance during upload-time.

         * Move the upload to accepted queue in all cases.
         * Publish and close bugs for 'single-source' uploads.
         * Skip bug-closing for PPA uploads.
         * Grant karma to people involved with the upload.

        :raises: AssertionError if the context is a delayed-copy.
        """

    def acceptFromCopy():
        """Perform upload acceptance for a delayed-copy record.

         * Move the upload to accepted queue in all cases.

        :raises: AssertionError if the context is not a delayed-copy or
            has no sources associated to it.
        """

    @export_write_operation()
    @call_with(user=REQUEST_USER)
    @operation_for_version("devel")
    def acceptFromQueue(logger=None, dry_run=False, user=None):
        """Call setAccepted, do a syncUpdate, and send notification email.

         * Grant karma to people involved with the upload.

        :raises: AssertionError if the context is a delayed-copy.
        """

    @export_write_operation()
    @call_with(user=REQUEST_USER)
    @operation_for_version("devel")
    def rejectFromQueue(logger=None, dry_run=False, user=None):
        """Call setRejected, do a syncUpdate, and send notification email."""

    def realiseUpload(logger=None):
        """Take this ACCEPTED upload and create the publishing records for it
        as appropriate.

        When derivation is taken into account, this may result in queue items
        being created for derived distributions.

        If a logger is provided, messages will be written to it as the upload
        is entered into the publishing records.

        Return a list containing the publishing records created.
        """

    def addSource(spr):
        """Add the provided source package release to this queue entry."""

    def addBuild(build):
        """Add the provided build to this queue entry."""

    def addCustom(library_file, custom_type):
        """Add the provided library file alias as a custom queue entry of
        the given custom type.
        """

    def syncUpdate():
        """Write updates made on this object to the database.

        This should be used when you can't wait until the transaction is
        committed to have some updates actually written to the database.
        """

    def notify(summary_text=None, changes_file_object=None, logger=None):
        """Notify by email when there is a new distroseriesqueue entry.

        This will send new, accept, announce and rejection messages as
        appropriate.

        :param summary_text: Any additional text to append to the auto-
            generated summary.  This is also the only text used if there is
            a rejection message generated.

        :param changes_file_object: An open file object pointing at the
            changes file.  Current, only nascentupload need supply this
            as the transaction is not committed to the DB at that point so
            data needs to be obtained from the changes file.

        :param logger: Specify a logger object if required.  Mainly for tests.
        """

    @operation_parameters(
        new_component=TextLine(title=u"The new component name."),
        new_section=TextLine(title=u"The new section name."))
    @call_with(allowed_components=None, user=REQUEST_USER)
    @export_write_operation()
    @operation_for_version('devel')
    def overrideSource(new_component=None, new_section=None,
                       allowed_components=None, user=None):
        """Override the source package contained in this queue item.

        :param new_component: An IComponent to replace the existing one
            in the upload's source.
        :param new_section: An ISection to replace the existing one
            in the upload's source.
        :param allowed_components: A sequence of components that the
            callsite is allowed to override from and to.
        :param user: The user requesting the override change, used if
            allowed_components is None.

        :raises QueueInconsistentStateError: if either the existing
            or the new_component are not in the allowed_components
            sequence.

        The override values may be None, in which case they are not
        changed.

        :return: True if the source was overridden.
        """

    @operation_parameters(
        changes=List(
            title=u"A sequence of changes to apply.",
            description=(
                u"Each item may have a 'name' item which specifies the binary "
                "package name to override; otherwise, the change applies to "
                "all binaries in the upload. It may also have 'component', "
                "'section', and 'priority' items which replace the "
                "corresponding existing one in the upload's overridden "
                "binaries."),
            value_type=Dict(key_type=TextLine())))
    @call_with(allowed_components=None, user=REQUEST_USER)
    @export_write_operation()
    @operation_for_version('devel')
    def overrideBinaries(changes, allowed_components=None, user=None):
        """Override binary packages in a binary queue item.

        :param changes: A sequence of mappings of changes to apply. Each
            change mapping may have a "name" item which specifies the binary
            package name to override; otherwise, the change applies to all
            binaries in the upload. It may also have "component", "section",
            and "priority" items which replace the corresponding existing
            one in the upload's overridden binaries. Any missing items are
            left unchanged.
        :param allowed_components: A sequence of components that the
            callsite is allowed to override from and to.
        :param user: The user requesting the override change, used if
            allowed_components is None.

        :raises QueueInconsistentStateError: if either the existing
            or the new_component are not in the allowed_components
            sequence.

        :return: True if any binaries were overridden.
        """


class IPackageUploadBuild(Interface):
    """A Queue item's related builds."""

    id = Int(
            title=_("ID"), required=True, readonly=True,
            )

    packageupload = Int(
            title=_("PackageUpload"), required=True,
            readonly=False,
            )

    build = Int(
            title=_("The related build"), required=True, readonly=False,
            )

    def binaries():
        """Returns the properties of the binaries in this build.

        For fast retrieval over the webservice, these are returned as a list
        of dictionaries, one per binary.
        """

    def publish(logger=None):
        """Publish this queued source in the distroseries referred to by
        the parent queue item.

        We determine the distroarchseries by matching architecturetags against
        the distroarchseries the build was compiled for.

        This method can raise NotFoundError if the architecturetag can't be
        matched up in the queue item's distroseries.

        Returns a list of the secure binary package publishing history
        objects in case it is of use to the caller. This may include records
        published into other distroarchseriess if this build contained arch
        independant packages.

        If a logger is provided, information pertaining to the publishing
        process will be logged to it.
        """


class IPackageUploadSource(Interface):
    """A Queue item's related sourcepackagereleases."""

    id = Int(
            title=_("ID"), required=True, readonly=True,
            )

    packageupload = Int(
            title=_("PackageUpload"), required=True,
            readonly=False,
            )

    sourcepackagerelease = Int(
            title=_("The related source package release"), required=True,
            readonly=False,
            )

    def getSourceAncestryForDiffs():
        """Return a suitable ancestry publication for this context.

        The possible ancestries locations for a give source upload, assuming
        that only PRIMARY archive allows post-RELEASE pockets are:

         1. original archive, original distroseries and pocket (old
            DEVELOPMENT/SRU/PPA uploads).
         2. primary archive, original distroseries and release pocket (NEW
            SRU/PPA uploads fallback).
         3. primary_archive, any distroseries and release pocket (BACKPORTS)

        We lookup a source publication with the same name in those location
        and in that order. If an ancestry is found it is returned, otherwise
        it returns None.

        :return: `ISourcePackagePublishingHistory` for the corresponding
             ancestry or None if it wasn't found.
        """

    def verifyBeforeAccept():
        """Perform overall checks before promoting source to ACCEPTED queue.

        If two queue items have the same (name, version) pair there is
        an inconsistency. To identify this situation we check the accepted
        & done queue items for each distroseries for such duplicates and
        raise an exception if any are found.
        See bug #31038 & #62976 for details.
        """

    def verifyBeforePublish():
        """Perform overall checks before publishing a source queue record.

        Check if the source package files do not collide with the
        ones already published in the archive. We need this to catch
        inaccurate  *epoched* versions, which would pass the upload version
        check but would collide with diff(s) or dsc(s) previously published
        on disk. This inconsistency is well known in debian-like archives
        and happens because filenames do not contain epoch. For further
        information see bug #119753.
        """

    def checkComponentAndSection():
        """Verify the current Component and Section via Selection table.

        Check if the current sourcepackagerelease component and section
        matches with those included in the target distribution series,
        if not raise QueueSourceAcceptError exception.
        """

    def publish(logger=None):
        """Publish this queued source in the distroseries referred to by
        the parent queue item.

        Returns the secure source package publishing history object in case
        it is of use to the caller.

        If a logger is provided, information pertaining to the publishing
        process will be logged to it.
        """


class IPackageUploadCustom(Interface):
    """Stores anything else than source and binaries that needs publication.

    It is essentially a map between DistroSeries/Pocket/LibrarianFileAlias.

    The LibrarianFileAlias usually is a TGZ containing an specific format.
    Currently we support:
     [Debian-Installer, Rosetta-Translation, Dist-Upgrader, DDTP-Tarball]

    Each one has an processor which is invoked by the publish method.
    """

    id = Int(
            title=_("ID"), required=True, readonly=True,
            )

    packageupload = Int(
            title=_("PackageUpload"), required=True,
            readonly=False,
            )

    customformat = Int(
            title=_("The custom format for the file"), required=True,
            readonly=False,
            )

    libraryfilealias = Int(
            title=_("The file"), required=True, readonly=False,
            )

    def temp_filename():
        """Return a filename containing the libraryfile for this upload.

        This filename will be in a temporary directory and can be the
        ensure dir can be deleted once whatever needed the file is finished
        with it.
        """

    def publish(logger=None):
        """Publish this custom item directly into the filesystem.

        This can only be run by a process which has filesystem access to
        the archive (or wherever else the content will go).

        If a logger is provided, information pertaining to the publishing
        process will be logged to it.
        """

    def publishDebianInstaller(logger=None):
        """Publish this custom item as a raw installer tarball.

        This will write the installer tarball out to the right part of
        the archive.

        If a logger is provided, information pertaining to the publishing
        process will be logged to it.
        """

    def publishDistUpgrader(logger=None):
        """Publish this custom item as a raw dist-upgrader tarball.

        This will write the dist-upgrader tarball out to the right part of
        the archive.

        If a logger is provided, information pertaining to the publishing
        process will be logged to it.
        """

    def publishDdtpTarball(logger=None):
        """Publish this custom item as a raw ddtp-tarball.

        This will write the ddtp-tarball out to the right part of
        the archive.

        If a logger is provided, information pertaining to the publishing
        process will be logged to it.
        """

    def publishRosettaTranslations(logger=None):
        """Publish this custom item as a rosetta tarball.

        Essentially this imports the tarball into rosetta.

        If a logger is provided, information pertaining to the publishing
        process will be logged to it.
        """

    def publishStaticTranslations(logger):
        """Publish this custom item as a static translations tarball.

        This is currently a no-op as we don't publish these files, they only
        reside in the librarian for later retrieval using the webservice.
        """

    def publishMetaData(logger):
        """Publish this custom item as a meta-data file.

        This method writes the meta-data custom file to the archive in
        the location matching this schema:
        /<person>/meta/<ppa_name>/<filename>

        It's not written to the main archive location because that could be
        protected by htaccess in the case of private archives.
        """


class IPackageUploadSet(Interface):
    """Represents a set of IPackageUploads"""

    def __iter__():
        """IPackageUpload iterator"""

    def __getitem__(queue_id):
        """Retrieve an IPackageUpload by a given id"""

    def get(queue_id):
        """Retrieve an IPackageUpload by a given id"""

    def count(status=None, distroseries=None, pocket=None):
        """Number of IPackageUpload present in a given status.

        If status is ommitted return the number of all entries.
        'distroseries' is optional and restrict the results in given
        distroseries, same for pocket.
        """

    def createDelayedCopy(archive, distroseries, pocket, signing_key):
        """Return a `PackageUpload` record for a delayed-copy operation.

        :param archive: target `IArchive`,
        :param distroseries: target `IDistroSeries`,
        :param pocket: target `PackagePublishingPocket`,
        :param signing_key: `IGPGKey` of the user requesting this copy.

        :return: an `IPackageUpload` record in NEW state.
        """

    def getAll(distroseries, created_since_date=None, status=None,
               archive=None, pocket=None, custom_type=None,
               name=None, version=None, exact_match=False):
        """Get package upload records for a series with optional filtering.

        :param distroseries: the `IDistroSeries` to consider.
        :param status: Filter results by this `PackageUploadStatus`, or list
            of statuses.
        :param created_since_date: If specified, only returns items uploaded
            since the timestamp supplied.
        :param archive: Filter results for this `IArchive`
        :param pocket: Filter results by this `PackagePublishingPocket`
        :param custom_type: Filter results by this `PackageUploadCustomFormat`
        :param name: Filter results by this package or file name.
        :param version: Filter results by this version number string.
        :param exact_match: If True, look for exact string matches on the
            `name` and `version` filters.  If False, look for a substring
            match so that e.g. a package "kspreadsheetplusplus" would match
            the search string "spreadsheet".  Defaults to False.
        :return: A result set containing `IPackageUpload`s
        """

    def findSourceUpload(name, version, archive, distribution):
        """Return a `PackageUpload` for a matching source.

        :param name: a string with the exact source name.
        :param version: a string with the exact source version.
        :param archive: source upload target `IArchive`.
        :param distribution: source upload target `IDistribution`.

        :return: a matching `IPackageUpload` object.
        """

    def getBuildsForSources(distroseries, status=None, pockets=None,
                            names=None):
        """Return binary package upload records for a series with optional
        filtering.

        :param distroseries: the `IDistroSeries` to consider.
        :param status: Filter results by this list of `PackageUploadStatus`s.
        :param pockets: Filter results by this list of
            `PackagePublishingPocket`s.
        :param names: Filter results by this list of package names.

        :return: A result set containing `IPackageUpload`s.
        """

    def getBuildByBuildIDs(build_ids):
        """Return `PackageUploadBuilds`s for the supplied build IDs."""

    def getSourceBySourcePackageReleaseIDs(spr_ids):
        """Return `PackageUploadSource`s for the sourcepackagerelease IDs."""

    def getByPackageCopyJobIDs(pcj_ids):
        """Return `PackageUpload`s using `PackageCopyJob`s.

        :param pcj_ids: A list of `PackageCopyJob` IDs.
        :return: all the `PackageUpload`s that reference the supplied IDs.
        """


class IHasQueueItems(Interface):
    """An Object that has queue items"""

    def getPackageUploadQueue(state):
        """Return an IPackageUploadQueue according to the given state."""
