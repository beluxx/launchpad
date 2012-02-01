# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test model and set utilities used for publishing."""

from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.errors import NotFoundError
from lp.buildmaster.enums import BuildStatus
from lp.services.database.constants import UTC_NOW
from lp.services.librarian.browser import ProxiedLibraryFileAlias
from lp.services.webapp.publisher import canonical_url
from lp.soyuz.enums import BinaryPackageFileType
from lp.soyuz.interfaces.publishing import (
    IPublishingSet,
    PackagePublishingStatus,
    )
from lp.soyuz.tests.test_binarypackagebuild import BaseTestCaseWithThreeBuilds
from lp.testing import TestCaseWithFactory
from lp.testing.layers import (
    LaunchpadFunctionalLayer,
    LaunchpadZopelessLayer,
    )


class TestPublishingSet(BaseTestCaseWithThreeBuilds):
    """Tests the IPublishingSet utility implementation."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        """Use `SoyuzTestPublisher` to publish some sources in archives."""
        super(TestPublishingSet, self).setUp()

        # Ensure all the builds have been built.
        for build in self.builds:
            removeSecurityProxy(build).status = BuildStatus.FULLYBUILT
        self.publishing_set = getUtility(IPublishingSet)

    def _getBuildsForResults(self, results):
        # The method returns (SPPH, Build) tuples, we just want the build.
        return [result[1] for result in results]

    def test_getUnpublishedBuildsForSources_none_published(self):
        # If no binaries have been published then all builds are.
        results = self.publishing_set.getUnpublishedBuildsForSources(
            self.sources)
        unpublished_builds = self._getBuildsForResults(results)

        self.assertContentEqual(self.builds, unpublished_builds)

    def test_getUnpublishedBuildsForSources_one_published(self):
        # If we publish a binary for a build, it is no longer returned.
        bpr = self.publisher.uploadBinaryForBuild(self.builds[0], 'gedit')
        self.publisher.publishBinaryInArchive(
            bpr, self.sources[0].archive,
            status=PackagePublishingStatus.PUBLISHED)

        results = self.publishing_set.getUnpublishedBuildsForSources(
            self.sources)
        unpublished_builds = self._getBuildsForResults(results)

        self.assertContentEqual(self.builds[1:3], unpublished_builds)

    def test_getUnpublishedBuildsForSources_with_cruft(self):
        # SourcePackages that has a superseded binary are still considered
        # 'published'.

        # Publish the binaries for gedit as superseded, explicitly setting
        # the date published.
        bpr = self.publisher.uploadBinaryForBuild(self.builds[0], 'gedit')
        bpphs = self.publisher.publishBinaryInArchive(
            bpr, self.sources[0].archive,
            status=PackagePublishingStatus.SUPERSEDED)
        for bpph in bpphs:
            bpph.datepublished = UTC_NOW

        results = self.publishing_set.getUnpublishedBuildsForSources(
            self.sources)
        unpublished_builds = self._getBuildsForResults(results)

        # The original gedit build should not be included in the results as,
        # even though it is no longer published.
        self.assertContentEqual(self.builds[1:3], unpublished_builds)

    def test_getChangesFileLFA(self):
        # The getChangesFileLFA() method finds the right LFAs.
        lfas = (
            self.publishing_set.getChangesFileLFA(hist.sourcepackagerelease)
            for hist in self.sources)
        urls = [lfa.http_url for lfa in lfas]
        self.assert_(urls[0].endswith('/94/gedit_666_source.changes'))
        self.assert_(urls[1].endswith('/96/firefox_666_source.changes'))
        self.assert_(urls[2].endswith(
            '/98/getting-things-gnome_666_source.changes'))


class TestSourcePackagePublishingHistory(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def test_ancestry(self):
        """Ancestry can be traversed."""
        ancestor = self.factory.makeSourcePackagePublishingHistory()
        spph = self.factory.makeSourcePackagePublishingHistory(
            ancestor=ancestor)
        self.assertEquals(spph.ancestor.displayname, ancestor.displayname)

    def test_changelogUrl_missing(self):
        spr = self.factory.makeSourcePackageRelease(changelog=None)
        spph = self.factory.makeSourcePackagePublishingHistory(
            sourcepackagerelease=spr)
        self.assertEqual(None, spph.changelogUrl())

    def test_changelogUrl(self):
        spr = self.factory.makeSourcePackageRelease(
            changelog=self.factory.makeChangelog('foo', ['1.0']))
        spph = self.factory.makeSourcePackagePublishingHistory(
            sourcepackagerelease=spr)
        self.assertEqual(
            canonical_url(spph) + '/+files/%s' % spr.changelog.filename,
            spph.changelogUrl())

    def test_getFileByName_changelog(self):
        spr = self.factory.makeSourcePackageRelease(
            changelog=self.factory.makeLibraryFileAlias(filename='changelog'))
        spph = self.factory.makeSourcePackagePublishingHistory(
            sourcepackagerelease=spr)
        self.assertEqual(spr.changelog, spph.getFileByName('changelog'))

    def test_getFileByName_changelog_absent(self):
        spr = self.factory.makeSourcePackageRelease(changelog=None)
        spph = self.factory.makeSourcePackagePublishingHistory(
            sourcepackagerelease=spr)
        self.assertRaises(NotFoundError, spph.getFileByName, 'changelog')

    def test_getFileByName_unhandled_name(self):
        spph = self.factory.makeSourcePackagePublishingHistory()
        self.assertRaises(NotFoundError, spph.getFileByName, 'not-changelog')


class TestBinaryPackagePublishingHistory(TestCaseWithFactory):

    layer = LaunchpadFunctionalLayer

    def test_binaryFileUrls_no_binaries(self):
        bpr = self.factory.makeBinaryPackageRelease()
        bpph = self.factory.makeBinaryPackagePublishingHistory(
            binarypackagerelease=bpr)
        expected_urls = []
        self.assertContentEqual(expected_urls, bpph.binaryFileUrls())

    def get_urls_for_binarypackagerelease(self, bpr, archive):
        return [ProxiedLibraryFileAlias(f.libraryfile, archive).http_url
            for f in bpr.files]

    def test_binaryFileUrls_one_binary(self):
        archive = self.factory.makeArchive(private=False)
        bpr = self.factory.makeBinaryPackageRelease()
        self.factory.makeBinaryPackageFile(binarypackagerelease=bpr)
        bpph = self.factory.makeBinaryPackagePublishingHistory(
            binarypackagerelease=bpr, archive=archive)
        expected_urls = self.get_urls_for_binarypackagerelease(bpr, archive)
        self.assertContentEqual(expected_urls, bpph.binaryFileUrls())

    def test_binaryFileUrls_two_binaries(self):
        archive = self.factory.makeArchive(private=False)
        bpr = self.factory.makeBinaryPackageRelease()
        self.factory.makeBinaryPackageFile(
            binarypackagerelease=bpr, filetype=BinaryPackageFileType.DEB)
        self.factory.makeBinaryPackageFile(
            binarypackagerelease=bpr, filetype=BinaryPackageFileType.DDEB)
        bpph = self.factory.makeBinaryPackagePublishingHistory(
            binarypackagerelease=bpr, archive=archive)
        expected_urls = self.get_urls_for_binarypackagerelease(bpr, archive)
        self.assertContentEqual(expected_urls, bpph.binaryFileUrls())
