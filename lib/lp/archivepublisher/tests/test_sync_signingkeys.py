# Copyright 2020 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test cases for the script that injects signing keys into signing service."""

from __future__ import absolute_import, print_function, unicode_literals

__metaclass__ = type


__all__ = [
    'SyncSigningKeysScript',
    ]

from datetime import datetime
import os

from fixtures import (
    MockPatch,
    TempDir,
    )
from pytz import utc
from testtools.matchers import (
    Equals,
    MatchesDict,
    MatchesStructure,
    )

from lp.archivepublisher.scripts.sync_signingkeys import SyncSigningKeysScript
from lp.services.compat import mock
from lp.services.database.interfaces import IStore
from lp.services.log.logger import BufferLogger
from lp.services.signing.enums import SigningKeyType
from lp.services.signing.tests.helpers import SigningServiceClientFixture
from lp.soyuz.model.archive import Archive
from lp.testing import TestCaseWithFactory
from lp.testing.layers import ZopelessDatabaseLayer


class TestSyncSigningKeysScript(TestCaseWithFactory):
    layer = ZopelessDatabaseLayer

    def setUp(self):
        super(TestSyncSigningKeysScript, self).setUp()
        self.signing_root_dir = self.useFixture(TempDir()).path
        self.pushConfig(
            "personalpackagearchive", signing_keys_root=self.signing_root_dir)

    def makeScript(self, test_args):
        script = SyncSigningKeysScript("test-sync", test_args=test_args)
        script.logger = BufferLogger()
        return script

    def makeArchives(self):
        for i in range(10):
            self.factory.makeArchive()
        return IStore(Archive).find(Archive).order_by(Archive.id)

    def makeArchiveSigningDir(self, ppa, series=None):
        """Creates the directory tree to hold signing keys for the PPA
        and specific list of DistroSeries provided.

        :param archive: The Archive that will hold the keys (should be PPA)
        :param series: A list of DistroSeries
        :return: A dict with series as keys (and None for the root archive)
                 and the values being the directory where the keys should be.
        """
        archive_root = os.path.join(
            self.signing_root_dir, "signing", ppa.owner.name, ppa.name)
        os.makedirs(archive_root)

        ret = {None: archive_root}
        for series in (series or []):
            path = os.path.join(archive_root, series.name)
            ret[series] = path
            os.makedirs(path)
        return ret

    def makeArchive(self, *args, **kwargs):
        """Creates an archive and its signing keys directories."""

    def test_fetch_archives_without_limit_and_offset(self):
        script = self.makeScript([])
        all_archives = list(self.makeArchives())
        archives = list(script.getArchives())
        self.assertEqual(all_archives, archives)

    def test_fetch_archives_with_limit_and_offset(self):
        script = self.makeScript([
            "--limit", "3",
            "--offset", "2"
        ])
        all_archives = list(self.makeArchives())
        archives = list(script.getArchives())
        self.assertEqual(all_archives[2:5], archives)

    def test_get_keys_per_type(self):
        keys_dir = self.signing_root_dir

        # Create fake uefi keys, and missing opal pem
        for filename in ["uefi.key", "uefi.crt", "opal.x509"]:
            with open(os.path.join(keys_dir, filename), 'wb') as fd:
                fd.write(b"something something")

        script = self.makeScript([])
        self.assertThat(script.getKeysPerType(keys_dir), MatchesDict({
            SigningKeyType.UEFI: Equals(("uefi.key", "uefi.crt"))
        }))

    def test_get_series_paths(self):
        distro = self.factory.makeDistribution()
        series1 = self.factory.makeDistroSeries(distribution=distro)
        series2 = self.factory.makeDistroSeries(distribution=distro)
        # For this series, we will not create the keys directory.
        self.factory.makeDistroSeries(distribution=distro)

        archive = self.factory.makeArchive(distribution=distro)
        key_dirs = self.makeArchiveSigningDir(archive, [series1, series2])
        archive_root = key_dirs[None]

        script = self.makeScript([])
        self.assertThat(script.getSeriesPaths(archive), MatchesDict({
            series1: Equals(os.path.join(archive_root, series1.name)),
            series2: Equals(os.path.join(archive_root, series2.name)),
            None: Equals(archive_root)
        }))

    def test_process_archive(self):
        distro = self.factory.makeDistribution()
        series1 = self.factory.makeDistroSeries(distribution=distro)
        series2 = self.factory.makeDistroSeries(distribution=distro)

        archive = self.factory.makeArchive(distribution=distro)
        key_dirs = self.makeArchiveSigningDir(archive, [series1, series2])

        archive_root = key_dirs[None]

        # Create fake uefi keys for the root
        for filename in ["uefi.key", "uefi.crt"]:
            with open(os.path.join(archive_root, filename), 'wb') as fd:
                fd.write(b"Root %s" % filename)

        # Create fake opal keys for series1
        for filename in ["opal.pem", "opal.x509", "kmod.pem", "kmod.x509"]:
            with open(os.path.join(key_dirs[series1], filename), 'wb') as fd:
                fd.write(b"Series 1 %s" % filename)

        script = self.makeScript([])
        script.getArchives = mock.Mock(return_value=[archive])
        script.inject = mock.Mock()
        script.main()

        self.assertItemsEqual([
            mock.call(archive, SigningKeyType.KMOD, series1, "kmod.pem",
                      "kmod.x509"),
            mock.call(archive, SigningKeyType.OPAL, series1, "opal.pem",
                      "opal.x509"),
            mock.call(archive, SigningKeyType.UEFI, None, "uefi.key",
                      "uefi.crt")],
            script.inject.call_args_list)

        # Check the log messages.
        content = script.logger.content.as_text()
        self.assertIn(
            "INFO #0 - Processing keys for archive %s." % archive.reference,
            content)

        tpl = "INFO Found key files %s / %s (type=%s, series=%s)."
        self.assertIn(
            tpl % ("kmod.pem", "kmod.x509", SigningKeyType.KMOD, series1.name),
            content)
        self.assertIn(
            tpl % ("opal.pem", "opal.x509", SigningKeyType.OPAL, series1.name),
            content)
        self.assertIn(
            tpl % ("uefi.key", "uefi.crt", SigningKeyType.UEFI, None),
            content)

    def test_inject(self):
        signing_service_client = self.useFixture(
            SigningServiceClientFixture(self.factory))

        now = datetime.now()
        mock_datetime = self.useFixture(MockPatch(
            'lp.archivepublisher.scripts.sync_signingkeys.datetime')).mock
        mock_datetime.now = lambda: now

        tmpdir = self.useFixture(TempDir()).path
        priv_key_path = os.path.join(tmpdir, "priv.key")
        pub_key_path = os.path.join(tmpdir, "pub.crt")

        with open(priv_key_path, 'wb') as fd:
            fd.write(b"Private key content")
        with open(pub_key_path, 'wb') as fd:
            fd.write(b"Public key content")

        distro = self.factory.makeDistribution()
        series = self.factory.makeDistroSeries(distribution=distro)
        archive = self.factory.makeArchive(distribution=distro)

        script = self.makeScript([])

        result_with_series = script.inject(
            archive, SigningKeyType.UEFI, series, priv_key_path, pub_key_path)

        self.assertThat(result_with_series, MatchesStructure.byEquality(
            archive=archive,
            earliest_distro_series=series,
            key_type=SigningKeyType.UEFI))
        self.assertThat(
            result_with_series.signing_key, MatchesStructure.byEquality(
                key_type=SigningKeyType.UEFI,
                public_key=b"Public key content"))

        # Check if we called lp-signing's /inject endpoint correctly
        self.assertEqual(1, signing_service_client.inject.call_count)
        self.assertEqual(
            (SigningKeyType.UEFI, b"Private key content",
             b"Public key content",
             u"UEFI key for %s" % archive.reference, now.replace(tzinfo=utc)),
            signing_service_client.inject.call_args[0])

        result_no_series = script.inject(
            archive, SigningKeyType.UEFI, None, priv_key_path, pub_key_path)

        self.assertThat(result_no_series, MatchesStructure.byEquality(
            archive=archive,
            earliest_distro_series=None,
            key_type=SigningKeyType.UEFI))
        self.assertThat(
            result_no_series.signing_key, MatchesStructure.byEquality(
                key_type=SigningKeyType.UEFI,
                public_key=b"Public key content"))

        # Check again lp-signing's /inject endpoint call
        self.assertEqual(2, signing_service_client.inject.call_count)
        self.assertEqual(
            (SigningKeyType.UEFI, b"Private key content",
             b"Public key content",
             u"UEFI key for %s" % archive.reference, now.replace(tzinfo=utc)),
            signing_service_client.inject.call_args[0])
