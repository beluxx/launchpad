# Copyright 2020 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the OCI Registry client."""

from __future__ import absolute_import, print_function, unicode_literals

__metaclass__ = type

import json

from fixtures import MockPatch
import responses
import transaction

from lp.oci.model.ociregistryclient import OCIRegistryClient
from lp.oci.tests.helpers import OCIConfigHelperMixin

from lp.testing import TestCaseWithFactory
from lp.testing.layers import LaunchpadZopelessLayer
from testtools.matchers import Equals, MatchesDict, MatchesListwise


class TestOCIRegistryClient(OCIConfigHelperMixin, TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

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
        self.factory.makeOCIPushRule(recipe=self.build.recipe)

    @responses.activate
    def test_upload(self):
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
        self.factory.makeOCIFile(
            build=self.build,
            content="digest_1",
            filename="digest_1_filename",
            layer_file_digest="digest_1"
        )
        self.factory.makeOCIFile(
            build=self.build,
            content="digest_2",
            filename="digest_2_filename",
            layer_file_digest="digest_2"
        )

        transaction.commit()
        client = OCIRegistryClient()
        self.useFixture(MockPatch(
            "lp.oci.model.ociregistryclient.OCIRegistryClient._upload"))
        self.useFixture(MockPatch(
            "lp.oci.model.ociregistryclient.OCIRegistryClient._upload_layer"))

        manifests_url = "{}/v2/{}/{}/manifests/edge".format(
            self.build.recipe.push_rules[0].registry_credentials.url,
            self.build.recipe.oci_project.pillar.name,
            self.build.recipe.push_rules[0].image_name
        )
        responses.add("PUT", manifests_url, status=201)
        client.upload(self.build)

        request = json.loads(responses.calls[0].request.body)

        self.assertThat(request, MatchesDict({
            "layers": MatchesListwise([
                MatchesDict({
                    "mediaType": Equals(
                        "application/vnd.docker.image.rootfs.diff.tar.gzip"),
                    "digest": Equals("diff_id_1"),
                    "size": Equals(0)}),
                MatchesDict({
                    "mediaType": Equals(
                        "application/vnd.docker.image.rootfs.diff.tar.gzip"),
                    "digest": Equals("diff_id_2"),
                    "size": Equals(0)})
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

