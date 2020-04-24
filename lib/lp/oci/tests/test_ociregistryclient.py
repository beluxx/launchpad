# Copyright 2020 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the OCI Registry client."""

from __future__ import absolute_import, print_function, unicode_literals

__metaclass__ = type

import json

from fixtures import MockPatch
from requests.exceptions import (
    ConnectionError,
    HTTPError,
    )
import responses
from tenacity import (
    stop_after_attempt,
    wait_fixed,
    RetryError,
    )
from testtools.matchers import (
    Equals,
    MatchesDict,
    MatchesListwise,
    )
import transaction

from lp.oci.model.ociregistryclient import OCIRegistryClient
from lp.oci.tests.helpers import OCIConfigHelperMixin
from lp.testing import TestCaseWithFactory
from lp.testing.layers import LaunchpadZopelessLayer


class TestOCIRegistryClient(OCIConfigHelperMixin, TestCaseWithFactory):

    layer = LaunchpadZopelessLayer
    retry_count = 0

    def setUp(self):
        super(TestOCIRegistryClient, self).setUp()
        self.setConfig()
        self.manifest = [{
            "Config": "config_file_1.json",
            "Layers": ["layer_1/layer.tar", "layer_2/layer.tar"]}]
        self.digests = [{
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
        self.config = {"rootfs": {"diff_ids": ["diff_id_1", "diff_id_2"]}}
        self.build = self.factory.makeOCIRecipeBuild()
        self.push_rule = self.factory.makeOCIPushRule(recipe=self.build.recipe)
        self.client = OCIRegistryClient()

    def _makeFiles(self):
        self.factory.makeOCIFile(
            build=self.build,
            content=json.dumps(self.manifest),
            filename='manifest.json',
        )
        self.factory.makeOCIFile(
            build=self.build,
            content=json.dumps(self.digests),
            filename='digests.json',
        )
        self.factory.makeOCIFile(
            build=self.build,
            content=json.dumps(self.config),
            filename='config_file_1.json'
        )

        # make layer files
        self.layer_1_file = self.factory.makeOCIFile(
            build=self.build,
            content="digest_1",
            filename="digest_1_filename",
            layer_file_digest="digest_1"
        )
        self.layer_2_file = self.factory.makeOCIFile(
            build=self.build,
            content="digest_2",
            filename="digest_2_filename",
            layer_file_digest="digest_2"
        )

        transaction.commit()

    @responses.activate
    def test_upload(self):
        self._makeFiles()
        self.useFixture(MockPatch(
            "lp.oci.model.ociregistryclient.OCIRegistryClient._upload"))
        self.useFixture(MockPatch(
            "lp.oci.model.ociregistryclient.OCIRegistryClient._upload_layer"))

        manifests_url = "{}/v2/{}/manifests/edge".format(
            self.build.recipe.push_rules[0].registry_credentials.url,
            self.build.recipe.push_rules[0].image_name
        )
        responses.add("PUT", manifests_url, status=201)
        self.client.upload(self.build)

        request = json.loads(responses.calls[0].request.body)

        self.assertThat(request, MatchesDict({
            "layers": MatchesListwise([
                MatchesDict({
                    "mediaType": Equals(
                        "application/vnd.docker.image.rootfs.diff.tar.gzip"),
                    "digest": Equals("diff_id_1"),
                    "size": Equals(8)}),
                MatchesDict({
                    "mediaType": Equals(
                        "application/vnd.docker.image.rootfs.diff.tar.gzip"),
                    "digest": Equals("diff_id_2"),
                    "size": Equals(8)})
            ]),
            "schemaVersion": Equals(2),
            "config": MatchesDict({
                "mediaType": Equals(
                    "application/vnd.docker.container.image.v1+json"),
                "digest": Equals(
                    "sha256:33b69b4b6e106f9fc7a8b93409"
                    "36c85cf7f84b2d017e7b55bee6ab214761f6ab"),
                "size": Equals(52)
            }),
            "mediaType": Equals(
                "application/vnd.docker.distribution.manifest.v2+json")
        }))

    @responses.activate
    def test_upload_formats_credentials(self):
        self._makeFiles()
        _upload_fixture = self.useFixture(MockPatch(
            "lp.oci.model.ociregistryclient.OCIRegistryClient._upload"))
        self.useFixture(MockPatch(
            "lp.oci.model.ociregistryclient.OCIRegistryClient._upload_layer"))

        self.push_rule.registry_credentials.setCredentials({
            "username": "test-username",
            "password": "test-password"
        })

        manifests_url = "{}/v2/{}/manifests/edge".format(
            self.build.recipe.push_rules[0].registry_credentials.url,
            self.build.recipe.push_rules[0].image_name
        )
        responses.add("PUT", manifests_url, status=201)
        self.client.upload(self.build)

        self.assertIn(
            ('test-username', 'test-password'),
            _upload_fixture.mock.call_args_list[0][0])

    def test_preloadFiles(self):
        self._makeFiles()
        files = self.client._preloadFiles(
            self.build, self.manifest, self.digests[0])

        self.assertThat(files, MatchesDict({
            'config_file_1.json': MatchesDict({
                'config_file': Equals(self.config),
                'diff_id_1': Equals(self.layer_1_file.library_file),
                'diff_id_2': Equals(self.layer_2_file.library_file)})}))

    def test_calculateTag(self):
        result = self.client._calculateTag(
            self.build, self.build.recipe.push_rules[0])
        self.assertEqual("edge", result)

    def test_build_registry_manifest(self):
        self._makeFiles()
        preloaded_data = self.client._preloadFiles(
            self.build, self.manifest, self.digests[0])
        manifest = self.client._build_registry_manifest(
            self.digests[0],
            self.config,
            json.dumps(self.config),
            "config-sha",
            preloaded_data["config_file_1.json"])
        self.assertThat(manifest, MatchesDict({
            "layers": MatchesListwise([
                MatchesDict({
                    "mediaType": Equals(
                        "application/vnd.docker.image.rootfs.diff.tar.gzip"),
                    "digest": Equals("diff_id_1"),
                    "size": Equals(8)}),
                MatchesDict({
                    "mediaType": Equals(
                        "application/vnd.docker.image.rootfs.diff.tar.gzip"),
                    "digest": Equals("diff_id_2"),
                    "size": Equals(8)})
            ]),
            "schemaVersion": Equals(2),
            "config": MatchesDict({
                "mediaType": Equals(
                    "application/vnd.docker.container.image.v1+json"),
                "digest": Equals("sha256:config-sha"),
                "size": Equals(52)
            }),
            "mediaType": Equals(
                "application/vnd.docker.distribution.manifest.v2+json")
        }))

    @responses.activate
    def test_upload_handles_existing(self):
        blobs_url = "{}/v2/{}/blobs/{}".format(
            self.build.recipe.push_rules[0].registry_credentials.url,
            "test-name",
            "test-digest")
        responses.add("HEAD", blobs_url, status=200)
        self.client._upload(
            "test-digest", self.build.recipe.push_rules[0],
            "test-name", None, None)
        # There should be no auth headers for these calls
        for call in responses.calls:
            self.assertNotIn('Authorization', call.request.headers.keys())

    @responses.activate
    def test_upload_raises_non_404(self):
        blobs_url = "{}/v2/{}/blobs/{}".format(
            self.build.recipe.push_rules[0].registry_credentials.url,
            "test-name",
            "test-digest")
        responses.add("HEAD", blobs_url, status=500)
        self.assertRaises(
            HTTPError,
            self.client._upload,
            "test-digest",
            self.build.recipe.push_rules[0],
            "test-name",
            None,
            None)

    @responses.activate
    def test_upload_passes_basic_auth(self):
        blobs_url = "{}/v2/{}/blobs/{}".format(
            self.build.recipe.push_rules[0].registry_credentials.url,
            "test-name",
            "test-digest")
        responses.add("HEAD", blobs_url, status=200)
        self.client._upload(
            "test-digest", self.build.recipe.push_rules[0],
            "test-name", None, ('user', 'password'))

        for call in responses.calls:
            self.assertEqual(
                'Basic dXNlcjpwYXNzd29yZA==',
                call.request.headers['Authorization'])

    def test_upload_retries_exception(self):
        # Use a separate counting mechanism so we're not entirely relying
        # on tenacity to tell us that it has retried.
        def count_retries(*args, **kwargs):
            self.retry_count += 1
            raise ConnectionError

        self.useFixture(MockPatch(
            'lp.oci.model.ociregistryclient.urlfetch',
            side_effect=count_retries
        ))
        # Patch sleep so we don't need to change our arguments and the
        # test is instant
        self.client._upload.retry.sleep = lambda x: None

        try:
            self.client._upload(
                "test-digest", self.build.recipe.push_rules[0],
                "test-name", None, ('user', 'password'))
        except RetryError:
            pass
        # Check that tenacity and our counting agree
        self.assertEqual(
            5, self.client._upload.retry.statistics["attempt_number"])
        self.assertEqual(5, self.retry_count)
