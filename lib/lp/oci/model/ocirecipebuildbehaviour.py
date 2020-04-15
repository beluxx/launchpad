# Copyright 2019 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""An `IBuildFarmJobBehaviour` for `OCIRecipeBuild`.

Dispatches OCI image build jobs to build-farm slaves.
"""

from __future__ import absolute_import, print_function, unicode_literals

__metaclass__ = type
__all__ = [
    'OCIRecipeBuildBehaviour',
    ]


import json
import os

from twisted.internet import defer
from zope.interface import implementer

from lp.app.errors import NotFoundError
from lp.buildmaster.enums import BuildBaseImageType
from lp.buildmaster.interfaces.builder import (
    BuildDaemonError,
    CannotBuild,
    )
from lp.buildmaster.interfaces.buildfarmjobbehaviour import (
    IBuildFarmJobBehaviour,
    )
from lp.buildmaster.model.buildfarmjobbehaviour import (
    BuildFarmJobBehaviourBase,
    )
from lp.registry.interfaces.series import SeriesStatus
from lp.services.librarian.utils import copy_and_close
from lp.snappy.model.snapbuildbehaviour import SnapProxyMixin
from lp.soyuz.adapters.archivedependencies import (
    get_sources_list_for_building,
    )


@implementer(IBuildFarmJobBehaviour)
class OCIRecipeBuildBehaviour(SnapProxyMixin, BuildFarmJobBehaviourBase):

    builder_type = "oci"
    image_types = [BuildBaseImageType.LXD, BuildBaseImageType.CHROOT]

    def getLogFileName(self):
        series = self.build.distro_series

        # Examples:
        #   buildlog_oci_ubuntu_wily_amd64_name_FULLYBUILT.txt
        return 'buildlog_oci_%s_%s_%s_%s_%s.txt' % (
            series.distribution.name, series.name,
            self.build.processor.name, self.build.recipe.name,
            self.build.status.name)

    def verifyBuildRequest(self, logger):
        """Assert some pre-build checks.

        The build request is checked:
         * Virtualized builds can't build on a non-virtual builder
         * Ensure that we have a chroot
        """
        build = self.build
        if build.virtualized and not self._builder.virtualized:
            raise AssertionError(
                "Attempt to build virtual item on a non-virtual builder.")

        chroot = build.distro_arch_series.getChroot(pocket=build.pocket)
        if chroot is None:
            raise CannotBuild(
                "Missing chroot for %s" % build.distro_arch_series.displayname)

    @defer.inlineCallbacks
    def extraBuildArgs(self, logger=None):
        """
        Return the extra arguments required by the slave for the given build.
        """
        build = self.build
        args = yield super(OCIRecipeBuildBehaviour, self).extraBuildArgs(
            logger=logger)
        yield self.addProxyArgs(args)
        # XXX twom 2020-02-17 This may need to be more complex, and involve
        # distribution name.
        args["name"] = build.recipe.name
        args["archives"], args["trusted_keys"] = (
            yield get_sources_list_for_building(
                build, build.distro_arch_series, None,
                tools_source=None, tools_fingerprint=None,
                logger=logger))

        args['build_file'] = build.recipe.build_file

        if build.recipe.git_ref is not None:
            args["git_repository"] = (
                build.recipe.git_repository.git_https_url)
        else:
            raise CannotBuild(
                "Source repository for ~%s/%s has been deleted." %
                (build.recipe.owner.name, build.recipe.name))

        if build.recipe.git_path != "HEAD":
            args["git_path"] = build.recipe.git_ref.name

        defer.returnValue(args)

    def _ensureFilePath(self, file_name, file_path, upload_path):
        # If the evaluated output file name is not within our
        # upload path, then we don't try to copy this or any
        # subsequent files.
        if not os.path.normpath(file_path).startswith(upload_path + '/'):
            raise BuildDaemonError(
                "Build returned a file named '%s'." % file_name)

    @defer.inlineCallbacks
    def _fetchIntermediaryFile(self, name, filemap, upload_path):
        file_hash = filemap[name]
        file_path = os.path.join(upload_path, name)
        self._ensureFilePath(name, file_path, upload_path)
        yield self._slave.getFile(file_hash, file_path)

        with open(file_path, 'r') as file_fp:
            contents = json.load(file_fp)
        defer.returnValue(contents)

    def _extractLayerFiles(self, upload_path, section, config, digests, files):
        # These are different sets of ids, in the same order
        # layer_id is the filename, diff_id is the internal (docker) id
        for diff_id in config['rootfs']['diff_ids']:
            for digests_section in digests:
                layer_id = digests_section[diff_id]['layer_id']
                # This is in the form '<id>/layer.tar', we only need the first
                layer_filename = "{}.tar.gz".format(layer_id.split('/')[0])
                digest = digests_section[diff_id]['digest']
                try:
                    _, librarian_file, _ = self.build.getLayerFileByDigest(
                        digest)
                except NotFoundError:
                    files.add(layer_filename)
                    continue
                layer_path = os.path.join(upload_path, layer_filename)
                librarian_file.open()
                copy_and_close(librarian_file, open(layer_path, 'wb'))

    def _convertToRetrievableFile(self, upload_path, file_name, filemap):
        file_path = os.path.join(upload_path, file_name)
        self._ensureFilePath(file_name, file_path, upload_path)
        return (filemap[file_name], file_path)

    @defer.inlineCallbacks
    def _downloadFiles(self, filemap, upload_path, logger):
        """Download required artifact files."""
        # We don't want to download all of the files that have been created,
        # just the ones that are mentioned in the manifest and config.

        manifest = yield self._fetchIntermediaryFile(
            'manifest.json', filemap, upload_path)
        digests = yield self._fetchIntermediaryFile(
            'digests.json', filemap, upload_path)

        files = set()
        for section in manifest:
            config = yield self._fetchIntermediaryFile(
                section['Config'], filemap, upload_path)
            self._extractLayerFiles(
                upload_path, section, config, digests, files)

        files_to_download = [
            self._convertToRetrievableFile(upload_path, filename, filemap)
            for filename in files]
        yield self._slave.getFiles(files_to_download, logger=logger)

    def verifySuccessfulBuild(self):
        """See `IBuildFarmJobBehaviour`."""
        # The implementation in BuildFarmJobBehaviourBase checks whether the
        # target suite is modifiable in the target archive.  However, an
        # `OCIRecipeBuild` does not use an archive in this manner.
        # We do, however, refuse to build for
        # obsolete series.
        assert self.build.distro_series.status != SeriesStatus.OBSOLETE
