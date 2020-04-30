# Copyright 2015-2020 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `OCIRecipeBuildBehaviour`."""

from __future__ import absolute_import, print_function, unicode_literals

__metaclass__ = type

import base64
from datetime import datetime
import json
import os
import shutil
import tempfile
import time
import uuid

import fixtures
from fixtures import MockPatch
from six.moves.urllib_parse import urlsplit
from testtools import ExpectedException
from testtools.matchers import (
    AfterPreprocessing,
    ContainsDict,
    Equals,
    Is,
    IsInstance,
    MatchesDict,
    MatchesListwise,
    StartsWith,
    )
from testtools.twistedsupport import (
    AsynchronousDeferredRunTestForBrokenTwisted,
    )
from twisted.internet import defer
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.buildmaster.enums import (
    BuildBaseImageType,
    BuildStatus,
    )
from lp.buildmaster.interactor import BuilderInteractor
from lp.buildmaster.interfaces.builder import (
    BuildDaemonError,
    CannotBuild,
    )
from lp.buildmaster.interfaces.buildfarmjobbehaviour import (
    IBuildFarmJobBehaviour,
    )
from lp.buildmaster.interfaces.processor import IProcessorSet
from lp.buildmaster.tests.mock_slaves import (
    MockBuilder,
    OkSlave,
    SlaveTestHelpers,
    WaitingSlave,
    )
from lp.buildmaster.tests.snapbuildproxy import (
    InProcessProxyAuthAPIFixture,
    ProxyURLMatcher,
    RevocationEndpointMatcher,
    )
from lp.buildmaster.tests.test_buildfarmjobbehaviour import (
    TestGetUploadMethodsMixin,
    )
from lp.oci.interfaces.ocirecipe import OCI_RECIPE_ALLOW_CREATE
from lp.oci.model.ocirecipebuildbehaviour import OCIRecipeBuildBehaviour
from lp.registry.interfaces.series import SeriesStatus
from lp.services.config import config
from lp.services.features.testing import FeatureFixture
from lp.services.log.logger import DevNullLogger
from lp.services.webapp import canonical_url
from lp.soyuz.adapters.archivedependencies import (
    get_sources_list_for_building,
    )
from lp.testing import TestCaseWithFactory
from lp.testing.dbuser import dbuser
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import LaunchpadZopelessLayer
from lp.testing.mail_helpers import pop_notifications


class MakeOCIBuildMixin:

    def makeBuild(self):
        build = self.factory.makeOCIRecipeBuild()
        self.factory.makeDistroSeries(
            distribution=build.recipe.oci_project.distribution,
            status=SeriesStatus.CURRENT)
        build.queueBuild()
        return build

    def makeUnmodifiableBuild(self):
        build = self.factory.makeOCIRecipeBuild()
        build.distro_arch_series = 'failed'
        build.queueBuild()
        return build

    def makeJob(self, git_ref, recipe=None, build=None):
        """Create a sample `IOCIRecipeBuildBehaviour`."""
        if build is None:
            if recipe is None:
                build = self.factory.makeOCIRecipeBuild()
            else:
                build = self.factory.makeOCIRecipeBuild(recipe=recipe)
        build.recipe.git_ref = git_ref

        job = IBuildFarmJobBehaviour(build)
        builder = MockBuilder()
        builder.processor = job.build.processor
        slave = self.useFixture(SlaveTestHelpers()).getClientSlave()
        job.setBuilder(builder, slave)
        self.addCleanup(slave.pool.closeCachedConnections)

        # Taken from test_archivedependencies.py
        for component_name in ("main", "universe"):
            self.factory.makeComponentSelection(
                build.distro_arch_series.distroseries, component_name)

        return job


class TestOCIBuildBehaviour(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestOCIBuildBehaviour, self).setUp()
        self.useFixture(FeatureFixture({OCI_RECIPE_ALLOW_CREATE: 'on'}))

    def test_provides_interface(self):
        # OCIRecipeBuildBehaviour provides IBuildFarmJobBehaviour.
        job = OCIRecipeBuildBehaviour(self.factory.makeOCIRecipeBuild())
        self.assertProvides(job, IBuildFarmJobBehaviour)

    def test_adapts_IOCIRecipeBuild(self):
        # IBuildFarmJobBehaviour adapts an IOCIRecipeBuild.
        build = self.factory.makeOCIRecipeBuild()
        job = IBuildFarmJobBehaviour(build)
        self.assertProvides(job, IBuildFarmJobBehaviour)


class TestAsyncOCIRecipeBuildBehaviour(MakeOCIBuildMixin, TestCaseWithFactory):

    run_tests_with = AsynchronousDeferredRunTestForBrokenTwisted.make_factory(
        timeout=10)
    layer = LaunchpadZopelessLayer

    @defer.inlineCallbacks
    def setUp(self):
        super(TestAsyncOCIRecipeBuildBehaviour, self).setUp()
        build_username = 'OCIBUILD-1'
        self.token = {'secret': uuid.uuid4().get_hex(),
                      'username': build_username,
                      'timestamp': datetime.utcnow().isoformat()}
        self.proxy_url = ("http://{username}:{password}"
                          "@{host}:{port}".format(
                            username=self.token['username'],
                            password=self.token['secret'],
                            host=config.snappy.builder_proxy_host,
                            port=config.snappy.builder_proxy_port))
        self.proxy_api = self.useFixture(InProcessProxyAuthAPIFixture())
        yield self.proxy_api.start()
        self.now = time.time()
        self.useFixture(fixtures.MockPatch(
            "time.time", return_value=self.now))
        self.useFixture(FeatureFixture({OCI_RECIPE_ALLOW_CREATE: 'on'}))

    @defer.inlineCallbacks
    def test_composeBuildRequest(self):
        [ref] = self.factory.makeGitRefs()
        job = self.makeJob(git_ref=ref)
        lfa = self.factory.makeLibraryFileAlias(db_only=True)
        job.build.distro_arch_series.addOrUpdateChroot(lfa)
        build_request = yield job.composeBuildRequest(None)
        self.assertThat(build_request, MatchesListwise([
            Equals('oci'),
            Equals(job.build.distro_arch_series),
            Equals(job.build.pocket),
            Equals({}),
            IsInstance(dict),
            ]))

    @defer.inlineCallbacks
    def test_requestProxyToken_unconfigured(self):
        self.pushConfig("snappy", builder_proxy_auth_api_admin_secret=None)
        [ref] = self.factory.makeGitRefs()
        job = self.makeJob(git_ref=ref)
        expected_exception_msg = (
            "builder_proxy_auth_api_admin_secret is not configured.")
        with ExpectedException(CannotBuild, expected_exception_msg):
            yield job.extraBuildArgs()

    @defer.inlineCallbacks
    def test_requestProxyToken(self):
        [ref] = self.factory.makeGitRefs()
        job = self.makeJob(git_ref=ref)
        yield job.extraBuildArgs()
        self.assertThat(self.proxy_api.tokens.requests, MatchesListwise([
            MatchesDict({
                "method": Equals("POST"),
                "uri": Equals(urlsplit(
                    config.snappy.builder_proxy_auth_api_endpoint).path),
                "headers": ContainsDict({
                    b"Authorization": MatchesListwise([
                        Equals(b"Basic " + base64.b64encode(
                            b"admin-launchpad.test:admin-secret"))]),
                    b"Content-Type": MatchesListwise([
                        Equals(b"application/json; charset=UTF-8"),
                        ]),
                    }),
                "content": AfterPreprocessing(json.loads, MatchesDict({
                    "username": StartsWith(job.build.build_cookie + "-"),
                    })),
                }),
            ]))

    @defer.inlineCallbacks
    def test_extraBuildArgs_git(self):
        # extraBuildArgs returns appropriate arguments if asked to build a
        # job for a Git branch.
        [ref] = self.factory.makeGitRefs()
        job = self.makeJob(git_ref=ref)
        expected_archives, expected_trusted_keys = (
            yield get_sources_list_for_building(
                job.build, job.build.distro_arch_series, None))
        for archive_line in expected_archives:
            self.assertIn('universe', archive_line)
        with dbuser(config.builddmaster.dbuser):
            args = yield job.extraBuildArgs()
        self.assertThat(args, MatchesDict({
            "archive_private": Is(False),
            "archives": Equals(expected_archives),
            "arch_tag": Equals("i386"),
            "build_file": Equals(job.build.recipe.build_file),
            "build_url": Equals(canonical_url(job.build)),
            "fast_cleanup": Is(True),
            "git_repository": Equals(ref.repository.git_https_url),
            "git_path": Equals(ref.name),
            "name": Equals(job.build.recipe.name),
            "proxy_url": ProxyURLMatcher(job, self.now),
            "revocation_endpoint":  RevocationEndpointMatcher(job, self.now),
            "series": Equals(job.build.distro_arch_series.distroseries.name),
            "trusted_keys": Equals(expected_trusted_keys),
            }))

    @defer.inlineCallbacks
    def test_extraBuildArgs_git_HEAD(self):
        # extraBuildArgs returns appropriate arguments if asked to build a
        # job for the default branch in a Launchpad-hosted Git repository.
        [ref] = self.factory.makeGitRefs()
        removeSecurityProxy(ref.repository)._default_branch = ref.path
        job = self.makeJob(git_ref=ref.repository.getRefByPath("HEAD"))
        expected_archives, expected_trusted_keys = (
            yield get_sources_list_for_building(
                job.build, job.build.distro_arch_series, None))
        for archive_line in expected_archives:
            self.assertIn('universe', archive_line)
        with dbuser(config.builddmaster.dbuser):
            args = yield job.extraBuildArgs()
        self.assertThat(args, MatchesDict({
            "archive_private": Is(False),
            "archives": Equals(expected_archives),
            "arch_tag": Equals("i386"),
            "build_file": Equals(job.build.recipe.build_file),
            "build_url": Equals(canonical_url(job.build)),
            "fast_cleanup": Is(True),
            "git_repository": Equals(ref.repository.git_https_url),
            "name": Equals(job.build.recipe.name),
            "proxy_url": ProxyURLMatcher(job, self.now),
            "revocation_endpoint":  RevocationEndpointMatcher(job, self.now),
            "series": Equals(job.build.distro_arch_series.distroseries.name),
            "trusted_keys": Equals(expected_trusted_keys),
            }))

    @defer.inlineCallbacks
    def test_composeBuildRequest_proxy_url_set(self):
        [ref] = self.factory.makeGitRefs()
        job = self.makeJob(git_ref=ref)
        build_request = yield job.composeBuildRequest(None)
        self.assertThat(
            build_request[4]["proxy_url"], ProxyURLMatcher(job, self.now))

    @defer.inlineCallbacks
    def test_composeBuildRequest_git_ref_deleted(self):
        # If the source Git reference has been deleted, composeBuildRequest
        # raises CannotBuild.
        repository = self.factory.makeGitRepository()
        [ref] = self.factory.makeGitRefs(repository=repository)
        owner = self.factory.makePerson(name="oci-owner")

        distribution = self.factory.makeDistribution()
        distroseries = self.factory.makeDistroSeries(
            distribution=distribution, status=SeriesStatus.CURRENT)
        processor = getUtility(IProcessorSet).getByName("386")
        self.factory.makeDistroArchSeries(
            distroseries=distroseries, architecturetag="i386",
            processor=processor)

        oci_project = self.factory.makeOCIProject(
            pillar=distribution, registrant=owner)
        recipe = self.factory.makeOCIRecipe(
            oci_project=oci_project, registrant=owner, owner=owner,
            git_ref=ref)
        job = self.makeJob(ref, recipe=recipe)
        repository.removeRefs([ref.path])
        # Clean the git_ref cache
        removeSecurityProxy(job.build.recipe)._git_ref = None

        self.assertIsNone(job.build.recipe.git_ref)
        expected_exception_msg = ("Source repository for "
                                  "~oci-owner/{} has been deleted.".format(
                                      recipe.name))
        with ExpectedException(CannotBuild, expected_exception_msg):
            yield job.composeBuildRequest(None)

    @defer.inlineCallbacks
    def test_dispatchBuildToSlave_prefers_lxd(self):
        self.pushConfig("snappy", builder_proxy_host=None)
        [ref] = self.factory.makeGitRefs()
        job = self.makeJob(git_ref=ref)
        builder = MockBuilder()
        builder.processor = job.build.processor
        slave = OkSlave()
        job.setBuilder(builder, slave)
        chroot_lfa = self.factory.makeLibraryFileAlias(db_only=True)
        job.build.distro_arch_series.addOrUpdateChroot(
            chroot_lfa, image_type=BuildBaseImageType.CHROOT)
        lxd_lfa = self.factory.makeLibraryFileAlias(db_only=True)
        job.build.distro_arch_series.addOrUpdateChroot(
            lxd_lfa, image_type=BuildBaseImageType.LXD)
        yield job.dispatchBuildToSlave(DevNullLogger())
        self.assertEqual(
            ('ensurepresent', lxd_lfa.http_url, '', ''), slave.call_log[0])

    @defer.inlineCallbacks
    def test_dispatchBuildToSlave_falls_back_to_chroot(self):
        self.pushConfig("snappy", builder_proxy_host=None)
        [ref] = self.factory.makeGitRefs()
        job = self.makeJob(git_ref=ref)
        builder = MockBuilder()
        builder.processor = job.build.processor
        slave = OkSlave()
        job.setBuilder(builder, slave)
        chroot_lfa = self.factory.makeLibraryFileAlias(db_only=True)
        job.build.distro_arch_series.addOrUpdateChroot(
            chroot_lfa, image_type=BuildBaseImageType.CHROOT)
        yield job.dispatchBuildToSlave(DevNullLogger())
        self.assertEqual(
            ('ensurepresent', chroot_lfa.http_url, '', ''), slave.call_log[0])

    @defer.inlineCallbacks
    def test_dispatchBuildToSlave_oci_feature_flag_enabled(self):
        self.pushConfig("snappy", builder_proxy_host=None)
        [ref] = self.factory.makeGitRefs()

        distribution = self.factory.makeDistribution()
        distroseries = self.factory.makeDistroSeries(
            distribution=distribution, status=SeriesStatus.CURRENT)
        processor = getUtility(IProcessorSet).getByName("386")
        self.useFixture(FeatureFixture({
            "oci.build_series.%s" % distribution.name: distroseries.name,
            OCI_RECIPE_ALLOW_CREATE: 'on'}))
        distro_arch_series = self.factory.makeDistroArchSeries(
            distroseries=distroseries, architecturetag="i386",
            processor=processor)

        build = self.factory.makeOCIRecipeBuild(
            distro_arch_series=distro_arch_series)
        job = self.makeJob(git_ref=ref, build=build)
        builder = MockBuilder()
        builder.processor = job.build.processor
        slave = OkSlave()
        job.setBuilder(builder, slave)
        chroot_lfa = self.factory.makeLibraryFileAlias(db_only=True)

        job.build.distro_arch_series.addOrUpdateChroot(
            chroot_lfa, image_type=BuildBaseImageType.CHROOT)
        lxd_lfa = self.factory.makeLibraryFileAlias(db_only=True)
        job.build.distro_arch_series.addOrUpdateChroot(
            lxd_lfa, image_type=BuildBaseImageType.LXD)
        yield job.dispatchBuildToSlave(DevNullLogger())
        self.assertEqual(distroseries.name,
            job.build.distro_arch_series.distroseries.name)
        self.assertEqual(
            ('ensurepresent', lxd_lfa.http_url, '', ''), slave.call_log[0])
        # grab the build method log from the OKMockSlave
        # and check inside the arguments dict that we build
        # for Distro series
        self.assertEqual(distroseries.name, slave.call_log[1][5]['series'])


class TestHandleStatusForOCIRecipeBuild(MakeOCIBuildMixin,
                                        TestCaseWithFactory):
    # This is mostly copied from TestHandleStatusMixin, however
    # we can't use all of those tests, due to the way OCIRecipeBuildBehaviour
    # parses the file contents, rather than just retrieving all that are
    # available. There's also some differences in the filemap handling, as
    # we need a much more complex filemap here.

    layer = LaunchpadZopelessLayer
    run_tests_with = AsynchronousDeferredRunTestForBrokenTwisted.make_factory(
        timeout=20)

    def _createTestFile(self, name, content, hash):
        path = os.path.join(self.test_files_dir, name)
        with open(path, 'wb') as fp:
            fp.write(content)
        self.slave.valid_files[hash] = path

    def setUp(self):
        super(TestHandleStatusForOCIRecipeBuild, self).setUp()
        self.useFixture(fixtures.FakeLogger())
        self.useFixture(FeatureFixture({OCI_RECIPE_ALLOW_CREATE: 'on'}))
        self.build = self.makeBuild()
        # For the moment, we require a builder for the build so that
        # handleStatus_OK can get a reference to the slave.
        self.builder = self.factory.makeBuilder()
        self.build.buildqueue_record.markAsBuilding(self.builder)
        self.slave = WaitingSlave('BuildStatus.OK')
        self.slave.valid_files['test_file_hash'] = ''
        self.interactor = BuilderInteractor()
        self.behaviour = self.interactor.getBuildBehaviour(
            self.build.buildqueue_record, self.builder, self.slave)

        # We overwrite the buildmaster root to use a temp directory.
        tempdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tempdir)
        self.upload_root = tempdir
        self.pushConfig('builddmaster', root=self.upload_root)

        # We stub out our build's getUploaderCommand() method so
        # we can check whether it was called as well as
        # verifySuccessfulUpload().
        removeSecurityProxy(self.build).verifySuccessfulUpload = FakeMethod(
            result=True)

        digests = [{
            "diff_id_1": {
                "digest": "digest_1",
                "source": "test/base_1",
                "layer_id": "layer_1"
            },
            "diff_id_2": {
                "digest": "digest_2",
                "source": "",
                "layer_id": "layer_2"
            }
        }]

        self.test_files_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.test_files_dir)
        self._createTestFile('buildlog', '', 'buildlog')
        self._createTestFile(
            'manifest.json',
            '[{"Config": "config_file_1.json", '
            '"Layers": ["layer_1/layer.tar", "layer_2/layer.tar"]}]',
            'manifest_hash')
        self._createTestFile(
            'digests.json',
            json.dumps(digests),
            'digests_hash')
        self._createTestFile(
            'config_file_1.json',
            '{"rootfs": {"diff_ids": ["diff_id_1", "diff_id_2"]}}',
            'config_1_hash')
        self._createTestFile(
            'layer_2.tar.gz',
            '',
            'layer_2_hash'
        )

        self.filemap = {
            'manifest.json': 'manifest_hash',
            'digests.json': 'digests_hash',
            'config_file_1.json': 'config_1_hash',
            'layer_1.tar.gz': 'layer_1_hash',
            'layer_2.tar.gz': 'layer_2_hash'
        }
        self.factory.makeOCIFile(
            build=self.build, layer_file_digest=u'digest_1',
            content="retrieved from librarian")

    def assertResultCount(self, count, result):
        self.assertEqual(
            1, len(os.listdir(os.path.join(self.upload_root, result))))

    @defer.inlineCallbacks
    def test_handleStatus_OK_normal_image(self):
        now = datetime.now()
        mock_datetime = self.useFixture(MockPatch(
            'lp.buildmaster.model.buildfarmjobbehaviour.datetime')).mock
        mock_datetime.now = lambda: now
        with dbuser(config.builddmaster.dbuser):
            yield self.behaviour.handleStatus(
                self.build.buildqueue_record, 'OK',
                {'filemap': self.filemap})
        self.assertEqual(
            ['buildlog', 'manifest_hash', 'digests_hash', 'config_1_hash',
             'layer_2_hash'],
            self.slave._got_file_record)
        # This hash should not appear as it is already in the librarian
        self.assertNotIn('layer_1_hash', self.slave._got_file_record)
        self.assertEqual(BuildStatus.UPLOADING, self.build.status)
        self.assertResultCount(1, "incoming")

        # layer_1 should have been retrieved from the librarian
        layer_1_path = os.path.join(
            self.upload_root,
            "incoming",
            self.behaviour.getUploadDirLeaf(self.build.build_cookie),
            str(self.build.archive.id),
            self.build.distribution.name,
            "layer_1.tar.gz"
        )
        with open(layer_1_path, 'rb') as layer_1_fp:
            contents = layer_1_fp.read()
            self.assertEqual(contents, b'retrieved from librarian')

    @defer.inlineCallbacks
    def test_handleStatus_OK_absolute_filepath(self):

        self._createTestFile(
            'manifest.json',
            '[{"Config": "/notvalid/config_file_1.json", '
            '"Layers": ["layer_1/layer.tar", "layer_2/layer.tar"]}]',
            'manifest_hash')

        self.filemap['/notvalid/config_file_1.json'] = 'config_1_hash'

        # A filemap that tries to write to files outside of the upload
        # directory will not be collected.
        with ExpectedException(
                BuildDaemonError,
                "Build returned a file named "
                "'/notvalid/config_file_1.json'."):
            with dbuser(config.builddmaster.dbuser):
                yield self.behaviour.handleStatus(
                    self.build.buildqueue_record, 'OK',
                    {'filemap': self.filemap})

    @defer.inlineCallbacks
    def test_handleStatus_OK_relative_filepath(self):

        self._createTestFile(
            'manifest.json',
            '[{"Config": "../config_file_1.json", '
            '"Layers": ["layer_1/layer.tar", "layer_2/layer.tar"]}]',
            'manifest_hash')

        self.filemap['../config_file_1.json'] = 'config_1_hash'
        # A filemap that tries to write to files outside of
        # the upload directory will not be collected.
        with ExpectedException(
                BuildDaemonError,
                "Build returned a file named '../config_file_1.json'."):
            with dbuser(config.builddmaster.dbuser):
                yield self.behaviour.handleStatus(
                    self.build.buildqueue_record, 'OK',
                    {'filemap': self.filemap})

    @defer.inlineCallbacks
    def test_handleStatus_OK_sets_build_log(self):
        # The build log is set during handleStatus.
        self.assertEqual(None, self.build.log)
        with dbuser(config.builddmaster.dbuser):
            yield self.behaviour.handleStatus(
                self.build.buildqueue_record, 'OK',
                {'filemap': self.filemap})
        self.assertNotEqual(None, self.build.log)

    @defer.inlineCallbacks
    def test_handleStatus_ABORTED_cancels_cancelling(self):
        with dbuser(config.builddmaster.dbuser):
            self.build.updateStatus(BuildStatus.CANCELLING)
            yield self.behaviour.handleStatus(
                self.build.buildqueue_record, "ABORTED", {})
        self.assertEqual(0, len(pop_notifications()), "Notifications received")
        self.assertEqual(BuildStatus.CANCELLED, self.build.status)

    @defer.inlineCallbacks
    def test_handleStatus_ABORTED_illegal_when_building(self):
        self.builder.vm_host = "fake_vm_host"
        self.behaviour = self.interactor.getBuildBehaviour(
            self.build.buildqueue_record, self.builder, self.slave)
        with dbuser(config.builddmaster.dbuser):
            self.build.updateStatus(BuildStatus.BUILDING)
            with ExpectedException(
                    BuildDaemonError,
                    "Build returned unexpected status: u'ABORTED'"):
                yield self.behaviour.handleStatus(
                    self.build.buildqueue_record, "ABORTED", {})

    @defer.inlineCallbacks
    def test_handleStatus_ABORTED_cancelling_sets_build_log(self):
        # If a build is intentionally cancelled, the build log is set.
        self.assertEqual(None, self.build.log)
        with dbuser(config.builddmaster.dbuser):
            self.build.updateStatus(BuildStatus.CANCELLING)
            yield self.behaviour.handleStatus(
                self.build.buildqueue_record, "ABORTED", {})
        self.assertNotEqual(None, self.build.log)

    @defer.inlineCallbacks
    def test_date_finished_set(self):
        # The date finished is updated during handleStatus_OK.
        self.assertEqual(None, self.build.date_finished)
        with dbuser(config.builddmaster.dbuser):
            yield self.behaviour.handleStatus(
                self.build.buildqueue_record, 'OK',
                {'filemap': self.filemap})
        self.assertNotEqual(None, self.build.date_finished)

    @defer.inlineCallbacks
    def test_givenback_collection(self):
        with ExpectedException(
                BuildDaemonError,
                "Build returned unexpected status: u'GIVENBACK'"):
            with dbuser(config.builddmaster.dbuser):
                yield self.behaviour.handleStatus(
                    self.build.buildqueue_record, "GIVENBACK", {})

    @defer.inlineCallbacks
    def test_builderfail_collection(self):
        with ExpectedException(
                BuildDaemonError,
                "Build returned unexpected status: u'BUILDERFAIL'"):
            with dbuser(config.builddmaster.dbuser):
                yield self.behaviour.handleStatus(
                    self.build.buildqueue_record, "BUILDERFAIL", {})

    @defer.inlineCallbacks
    def test_invalid_status_collection(self):
        with ExpectedException(
                BuildDaemonError,
                "Build returned unexpected status: u'BORKED'"):
            with dbuser(config.builddmaster.dbuser):
                yield self.behaviour.handleStatus(
                    self.build.buildqueue_record, "BORKED", {})


class TestGetUploadMethodsForOCIRecipeBuild(
    MakeOCIBuildMixin, TestGetUploadMethodsMixin, TestCaseWithFactory):
    """IPackageBuild.getUpload-related methods work with OCI recipe builds."""
    def setUp(self):
        self.useFixture(FeatureFixture({OCI_RECIPE_ALLOW_CREATE: 'on'}))
        super(TestGetUploadMethodsForOCIRecipeBuild, self).setUp()
