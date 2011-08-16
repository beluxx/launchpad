# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the initialize_distroseries script machinery."""

__metaclass__ = type

import os
import subprocess
import sys

from testtools.content import Content
from testtools.content_type import UTF8_TEXT
import transaction
from zope.component import getUtility

from canonical.config import config
from canonical.launchpad.interfaces.lpstorm import IStore
from canonical.testing.layers import LaunchpadZopelessLayer
from lp.buildmaster.enums import BuildStatus
from lp.registry.interfaces.distroseriesdifference import (
    IDistroSeriesDifferenceSource,
    )
from lp.registry.interfaces.distroseriesparent import IDistroSeriesParentSet
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.services.features.testing import FeatureFixture
from lp.soyuz.enums import (
    ArchivePurpose,
    SourcePackageFormat,
    )
from lp.soyuz.interfaces.archivepermission import IArchivePermissionSet
from lp.soyuz.interfaces.component import IComponentSet
from lp.soyuz.interfaces.packageset import (
    IPackagesetSet,
    NoSuchPackageSet,
    )
from lp.soyuz.interfaces.processor import IProcessorFamilySet
from lp.soyuz.interfaces.publishing import PackagePublishingStatus
from lp.soyuz.interfaces.sourcepackageformat import (
    ISourcePackageFormatSelectionSet,
    )
from lp.soyuz.model.component import ComponentSelection
from lp.soyuz.model.distroarchseries import DistroArchSeries
from lp.soyuz.model.distroseriesdifferencejob import (
    FEATURE_FLAG_ENABLE_MODULE,
    find_waiting_jobs,
    )
from lp.soyuz.model.section import SectionSelection
from lp.soyuz.scripts.initialize_distroseries import (
    InitializationError,
    InitializeDistroSeries,
    )
from lp.testing import TestCaseWithFactory


class InitializationHelperTestCase(TestCaseWithFactory):
    # Helper class to:
    # - setup/populate parents with packages;
    # - initialize a child from parents.

    def setupParent(self, packages=None, format_selection=None,
                    distribution=None,
                    pocket=PackagePublishingPocket.RELEASE,
                    ):
        parent = self.factory.makeDistroSeries(distribution)
        pf = getUtility(IProcessorFamilySet).getByName('x86')
        parent_das = self.factory.makeDistroArchSeries(
            distroseries=parent, processorfamily=pf,
            architecturetag='i386')
        lf = self.factory.makeLibraryFileAlias()
        transaction.commit()
        parent_das.addOrUpdateChroot(lf)
        parent_das.supports_virtualized = True
        parent.nominatedarchindep = parent_das
        if format_selection is None:
            format_selection = SourcePackageFormat.FORMAT_1_0
        getUtility(ISourcePackageFormatSelectionSet).add(
            parent, format_selection)
        parent.backports_not_automatic = True
        self._populate_parent(parent, parent_das, packages, pocket)
        return parent, parent_das

    def _populate_parent(self, parent, parent_das, packages=None,
                         pocket=PackagePublishingPocket.RELEASE):
        if packages is None:
            packages = {'udev': '0.1-1', 'libc6': '2.8-1',
                'postgresql': '9.0-1', 'chromium': '3.6'}
        for package in packages.keys():
            spn = self.factory.getOrMakeSourcePackageName(package)
            spph = self.factory.makeSourcePackagePublishingHistory(
                sourcepackagename=spn, version=packages[package],
                distroseries=parent,
                pocket=pocket, status=PackagePublishingStatus.PUBLISHED)
            status = BuildStatus.FULLYBUILT
            if package is 'chromium':
                status = BuildStatus.FAILEDTOBUILD
            bpn = self.factory.getOrMakeBinaryPackageName(package)
            build = self.factory.makeBinaryPackageBuild(
                source_package_release=spph.sourcepackagerelease,
                distroarchseries=parent_das,
                status=status)
            bpr = self.factory.makeBinaryPackageRelease(
                binarypackagename=bpn, build=build,
                version=packages[package])
            if package is not 'chromium':
                self.factory.makeBinaryPackagePublishingHistory(
                    binarypackagerelease=bpr,
                    distroarchseries=parent_das,
                    pocket=pocket, status=PackagePublishingStatus.PUBLISHED)
                self.factory.makeBinaryPackageFile(binarypackagerelease=bpr)

    def _fullInitialize(self, parents, child=None, previous_series=None,
                        arches=(), packagesets=(), rebuild=False,
                        distribution=None, overlays=(),
                        overlay_pockets=(), overlay_components=()):
        if child is None:
            child = self.factory.makeDistroSeries(
                distribution=distribution, previous_series=previous_series)
        ids = InitializeDistroSeries(
            child, [parent.id for parent in parents], arches, packagesets,
            rebuild, overlays, overlay_pockets, overlay_components)
        ids.check()
        ids.initialize()
        return child


class TestInitializeDistroSeries(InitializationHelperTestCase):

    layer = LaunchpadZopelessLayer

    def test_failure_for_already_released_distroseries(self):
        # Initializing a distro series that has already been used will
        # error.
        self.parent, self.parent_das = self.setupParent()
        child = self.factory.makeDistroSeries()
        self.factory.makeDistroArchSeries(distroseries=child)
        ids = InitializeDistroSeries(child, [self.parent.id])
        self.assertRaisesWithContent(
            InitializationError,
            "Can not copy distroarchseries from parent, there are already "
            "distroarchseries(s) initialized for this series.", ids.check)

    def test_failure_when_previous_series_none(self):
        # Initialising a distroseries with no previous_series if the
        # distribution already has initialized series will error.
        self.parent, self.parent_das = self.setupParent()
        child = self.factory.makeDistroSeries(
            previous_series=None, name='series')
        another_distroseries = self.factory.makeDistroSeries(
            distribution=child.distribution)
        self.factory.makeSourcePackagePublishingHistory(
             distroseries=another_distroseries)
        self.factory.makeDistroArchSeries(distroseries=child)
        ids = InitializeDistroSeries(child, [self.parent.id])
        self.assertRaisesWithContent(
            InitializationError,
            ("DistroSeries series has no previous series and "
             "the distribution already has initialized series"
             ".").format(child=child),
             ids.check)

    def test_failure_with_pending_builds(self):
        # If the parent series has pending builds, and the child is a series
        # of the same distribution (which means they share an archive), we
        # can't initialize.
        self.parent, self.parent_das = self.setupParent()
        source = self.factory.makeSourcePackagePublishingHistory(
            distroseries=self.parent,
            pocket=PackagePublishingPocket.RELEASE)
        source.createMissingBuilds()
        child = self.factory.makeDistroSeries(
            distribution=self.parent.parent, previous_series=self.parent)
        ids = InitializeDistroSeries(child, [self.parent.id])
        self.assertRaisesWithContent(
            InitializationError, "Parent series has pending builds.",
            ids.check)

    def test_success_with_updates_packages(self):
        # Initialization copies all the package from the UPDATES pocket.
        self.parent, self.parent_das = self.setupParent(
            pocket=PackagePublishingPocket.UPDATES)
        child = self._fullInitialize([self.parent])
        self.assertDistroSeriesInitializedCorrectly(
            child, self.parent, self.parent_das)

    def test_success_with_security_packages(self):
        # Initialization copies all the package from the SECURITY pocket.
        self.parent, self.parent_das = self.setupParent(
            pocket=PackagePublishingPocket.SECURITY)
        child = self._fullInitialize([self.parent])
        self.assertDistroSeriesInitializedCorrectly(
            child, self.parent, self.parent_das)

    def test_success_with_pending_builds(self):
        # If the parent series has pending builds, and the child's
        # distribution is different, we can initialize.
        self.parent, self.parent_das = self.setupParent()
        source = self.factory.makeSourcePackagePublishingHistory(
            distroseries=self.parent,
            pocket=PackagePublishingPocket.RELEASE)
        source.createMissingBuilds()
        child = self._fullInitialize([self.parent])
        self.assertDistroSeriesInitializedCorrectly(
            child, self.parent, self.parent_das)

    def test_do_not_copy_superseded_sources(self):
        # Make sure we don't copy superseded sources from the parent,
        # we only want (pending, published).
        self.parent, self.parent_das = self.setupParent()
        # Add 2 more sources, pending and superseded.
        superseded = self.factory.makeSourcePackagePublishingHistory(
            distroseries=self.parent,
            pocket=PackagePublishingPocket.RELEASE,
            status=PackagePublishingStatus.SUPERSEDED)
        superseded_source_name = (
            superseded.sourcepackagerelease.sourcepackagename.name)
        pending = self.factory.makeSourcePackagePublishingHistory(
            distroseries=self.parent,
            pocket=PackagePublishingPocket.RELEASE,
            status=PackagePublishingStatus.PENDING)
        pending_source_name = (
            pending.sourcepackagerelease.sourcepackagename.name)
        child = self._fullInitialize([self.parent])

        # Check the superseded source is not copied.
        superseded_child_sources = child.main_archive.getPublishedSources(
            name=superseded_source_name, distroseries=child,
            exact_match=True)
        self.assertEqual(0, superseded_child_sources.count())

        # Check the pending source is copied.
        pending_child_sources = child.main_archive.getPublishedSources(
            name=pending_source_name, distroseries=child,
            exact_match=True)
        self.assertEqual(1, pending_child_sources.count())

    def test_failure_with_queue_items(self):
        # If the parent series has items in its queues, such as NEW and
        # UNAPPROVED, we can't initialize.
        self.parent, self.parent_das = self.setupParent()
        self.parent.createQueueEntry(
            PackagePublishingPocket.RELEASE, self.parent.main_archive,
            'foo.changes', 'bar')
        child = self.factory.makeDistroSeries()
        ids = InitializeDistroSeries(child, [self.parent.id])
        self.assertRaisesWithContent(
            InitializationError, "Parent series queues are not empty.",
            ids.check)

    def assertDistroSeriesInitializedCorrectly(self, child, parent,
                                               parent_das):
        # Check that 'udev' has been copied correctly.
        parent_udev_pubs = parent.main_archive.getPublishedSources(
            'udev', distroseries=parent)
        child_udev_pubs = child.main_archive.getPublishedSources(
            'udev', distroseries=child)
        self.assertEqual(
            parent_udev_pubs.count(), child_udev_pubs.count())
        parent_arch_udev_pubs = parent[
            parent_das.architecturetag].getReleasedPackages(
                'udev', include_pending=True)
        child_arch_udev_pubs = child[
            parent_das.architecturetag].getReleasedPackages(
                'udev', include_pending=True)
        self.assertEqual(
            len(parent_arch_udev_pubs), len(child_arch_udev_pubs))
        # And the binary package, and linked source package look fine too.
        udev_bin = child_arch_udev_pubs[0].binarypackagerelease
        self.assertEqual(udev_bin.title, u'udev-0.1-1')
        self.assertEqual(
            udev_bin.build.title,
            u'%s build of udev 0.1-1 in %s %s RELEASE' % (
                parent_das.architecturetag, parent.parent.name,
                parent.name))
        udev_src = udev_bin.build.source_package_release
        self.assertEqual(udev_src.title, u'udev - 0.1-1')
        # The build of udev 0.1-1 has been copied across.
        child_udev = udev_src.getBuildByArch(
            child[parent_das.architecturetag], child.main_archive)
        parent_udev = udev_src.getBuildByArch(
            parent[parent_das.architecturetag],
            parent.main_archive)
        self.assertEqual(parent_udev.id, child_udev.id)
        # We also inherit the permitted source formats from our parent.
        self.assertTrue(
            child.isSourcePackageFormatPermitted(
            SourcePackageFormat.FORMAT_1_0))
        # Other configuration bits are copied too.
        self.assertTrue(child.backports_not_automatic)

    def test_initialize(self):
        # Test a full initialize with no errors.
        self.parent, self.parent_das = self.setupParent()
        child = self._fullInitialize([self.parent])
        self.assertDistroSeriesInitializedCorrectly(
            child, self.parent, self.parent_das)

    def test_initialize_only_one_das(self):
        # Test a full initialize with no errors, but only copy i386 to
        # the child.
        self.parent, self.parent_das = self.setupParent()
        self.factory.makeDistroArchSeries(distroseries=self.parent)
        child = self._fullInitialize(
            [self.parent],
            arches=[self.parent_das.architecturetag])
        self.assertDistroSeriesInitializedCorrectly(
            child, self.parent, self.parent_das)
        das = list(IStore(DistroArchSeries).find(
            DistroArchSeries, distroseries=child))
        self.assertEqual(len(das), 1)
        self.assertEqual(
            das[0].architecturetag, self.parent_das.architecturetag)

    def test_copying_packagesets(self):
        # If a parent series has packagesets, we should copy them.
        self.parent, self.parent_das = self.setupParent()
        uploader = self.factory.makePerson()
        test1 = getUtility(IPackagesetSet).new(
            u'test1', u'test 1 packageset', self.parent.owner,
            distroseries=self.parent)
        test2 = getUtility(IPackagesetSet).new(
            u'test2', u'test 2 packageset', self.parent.owner,
            distroseries=self.parent)
        test3 = getUtility(IPackagesetSet).new(
            u'test3', u'test 3 packageset', self.parent.owner,
            distroseries=self.parent, related_set=test2)
        test1.addSources('udev')
        getUtility(IArchivePermissionSet).newPackagesetUploader(
            self.parent.main_archive, uploader, test1)
        child = self._fullInitialize([self.parent])
        # We can fetch the copied sets from the child.
        child_test1 = getUtility(IPackagesetSet).getByName(
            u'test1', distroseries=child)
        child_test2 = getUtility(IPackagesetSet).getByName(
            u'test2', distroseries=child)
        child_test3 = getUtility(IPackagesetSet).getByName(
            u'test3', distroseries=child)
        # And we can see they are exact copies, with the related_set for the
        # copies pointing to the packageset in the parent.
        self.assertEqual(test1.description, child_test1.description)
        self.assertEqual(test2.description, child_test2.description)
        self.assertEqual(test3.description, child_test3.description)
        self.assertEqual(child_test1.relatedSets().one(), test1)
        self.assertEqual(
            list(child_test2.relatedSets()),
            [test2, test3, child_test3])
        self.assertEqual(
            list(child_test3.relatedSets()),
            [test2, child_test2, test3])
        # The contents of the packagesets will have been copied.
        child_srcs = child_test1.getSourcesIncluded(
            direct_inclusion=True)
        parent_srcs = test1.getSourcesIncluded(direct_inclusion=True)
        self.assertEqual(parent_srcs, child_srcs)

    def test_copying_packagesets_multiple_parents(self):
        # When a packageset id is passed to the initialisation method,
        # only the packages in this packageset (and in the corresponding
        # distroseries) are copied.
        self.parent1, not_used = self.setupParent(
            packages={'udev': '0.1-1', 'firefox': '2.1'})
        self.parent2, not_used = self.setupParent(
            packages={'firefox': '3.1'})
        uploader = self.factory.makePerson()
        test1 = getUtility(IPackagesetSet).new(
            u'test1', u'test 1 packageset', self.parent1.owner,
            distroseries=self.parent1)
        test1.addSources('udev')
        test1.addSources('firefox')
        getUtility(IArchivePermissionSet).newPackagesetUploader(
            self.parent1.main_archive, uploader, test1)
        child = self._fullInitialize(
            [self.parent1, self.parent2], packagesets=(str(test1.id),))
        # Only the packages from the packageset test1 (from
        # self.parent1) are copied.
        published_sources = child.main_archive.getPublishedSources(
            distroseries=child)
        pub_sources = sorted(
            [(s.sourcepackagerelease.sourcepackagename.name,
              s.sourcepackagerelease.version)
                for s in published_sources])
        self.assertContentEqual(
            [(u'udev', u'0.1-1'), (u'firefox', u'2.1')],
            pub_sources)

    def test_intra_distro_perm_copying(self):
        # If child.distribution equals parent.distribution, we also
        # copy the archivepermissions.
        parent, unused = self.setupParent()
        uploader = self.factory.makePerson()
        test1 = self.factory.makePackageset(
            u'test1', u'test 1 packageset', parent.owner,
            distroseries=parent)
        #test1 = getUtility(IPackagesetSet).new(
        #    u'test1', u'test 1 packageset', self.parent.owner,
        #    distroseries=self.parent)
        test1.addSources('udev')
        archive_permset = getUtility(IArchivePermissionSet)
        archive_permset.newPackagesetUploader(
            parent.main_archive, uploader, test1)
        # Create child series in the same distribution.
        child = self.factory.makeDistroSeries(
            distribution=parent.distribution,
            previous_series=parent)
        self._fullInitialize([parent], child=child)

        # The uploader can upload to the new distroseries.
        self.assertTrue(archive_permset.isSourceUploadAllowed(
                parent.main_archive, 'udev', uploader,
                distroseries=parent))
        self.assertTrue(archive_permset.isSourceUploadAllowed(
                child.main_archive, 'udev', uploader,
                distroseries=child))

    def test_no_cross_distro_perm_copying(self):
        # No cross-distro archivepermissions copying should happen.
        self.parent, self.parent_das = self.setupParent()
        uploader = self.factory.makePerson()
        test1 = getUtility(IPackagesetSet).new(
            u'test1', u'test 1 packageset', self.parent.owner,
            distroseries=self.parent)
        test1.addSources('udev')
        getUtility(IArchivePermissionSet).newPackagesetUploader(
            self.parent.main_archive, uploader, test1)
        child = self._fullInitialize([self.parent])

        # The uploader cannot upload to the new distroseries.
        self.assertTrue(
            getUtility(IArchivePermissionSet).isSourceUploadAllowed(
                self.parent.main_archive, 'udev', uploader,
                distroseries=self.parent))
        self.assertFalse(
            getUtility(IArchivePermissionSet).isSourceUploadAllowed(
                child.main_archive, 'udev', uploader,
                distroseries=child))

    def test_packageset_owner_preserved_within_distro(self):
        # When initializing a new series within a distro, the copied
        # packagesets have ownership preserved.
        self.parent, self.parent_das = self.setupParent(packages={})
        ps_owner = self.factory.makePerson()
        getUtility(IPackagesetSet).new(
            u'ps', u'packageset', ps_owner, distroseries=self.parent)
        child = self._fullInitialize(
            [self.parent], distribution=self.parent.distribution)
        child_ps = getUtility(IPackagesetSet).getByName(
            u'ps', distroseries=child)
        self.assertEqual(ps_owner, child_ps.owner)

    def test_packageset_owner_not_preserved_cross_distro(self):
        # In the case of a cross-distro initialization, the new
        # packagesets are owned by the new distro owner.
        self.parent, self.parent_das = self.setupParent()
        getUtility(IPackagesetSet).new(
            u'ps', u'packageset', self.factory.makePerson(),
            distroseries=self.parent)
        child = self._fullInitialize([self.parent])
        child_ps = getUtility(IPackagesetSet).getByName(
            u'ps', distroseries=child)
        self.assertEqual(child.owner, child_ps.owner)

    def test_copy_limit_packagesets(self):
        # If a parent series has packagesets, we can decide which ones we
        # want to copy.
        self.parent, self.parent_das = self.setupParent()
        test1 = getUtility(IPackagesetSet).new(
            u'test1', u'test 1 packageset', self.parent.owner,
            distroseries=self.parent)
        getUtility(IPackagesetSet).new(
            u'test2', u'test 2 packageset', self.parent.owner,
            distroseries=self.parent)
        packages = ('udev', 'chromium', 'libc6')
        for pkg in packages:
            test1.addSources(pkg)
        packageset1 = getUtility(IPackagesetSet).getByName(
            u'test1', distroseries=self.parent)
        child = self._fullInitialize(
            [self.parent], packagesets=(str(packageset1.id),))
        child_test1 = getUtility(IPackagesetSet).getByName(
            u'test1', distroseries=child)
        self.assertEqual(test1.description, child_test1.description)
        self.assertRaises(
            NoSuchPackageSet, getUtility(IPackagesetSet).getByName,
                u'test2', distroseries=child)
        parent_srcs = test1.getSourcesIncluded(direct_inclusion=True)
        child_srcs = child_test1.getSourcesIncluded(
            direct_inclusion=True)
        self.assertEqual(parent_srcs, child_srcs)
        child.updatePackageCount()
        self.assertEqual(child.sourcecount, len(packages))
        self.assertEqual(child.binarycount, 2)  # Chromium is FTBFS

    def test_rebuild_flag(self):
        # No binaries will get copied if we specify rebuild=True.
        self.parent, self.parent_das = self.setupParent()
        self.parent.updatePackageCount()
        child = self._fullInitialize([self.parent], rebuild=True)
        child.updatePackageCount()
        builds = child.getBuildRecords(
            build_state=BuildStatus.NEEDSBUILD,
            pocket=PackagePublishingPocket.RELEASE)
        self.assertEqual(self.parent.sourcecount, child.sourcecount)
        self.assertEqual(child.binarycount, 0)
        self.assertEqual(builds.count(), self.parent.sourcecount)

    def test_limit_packagesets_rebuild_and_one_das(self):
        # We can limit the source packages copied, and only builds
        # for the copied source will be created.
        self.parent, self.parent_das = self.setupParent()
        test1 = getUtility(IPackagesetSet).new(
            u'test1', u'test 1 packageset', self.parent.owner,
            distroseries=self.parent)
        getUtility(IPackagesetSet).new(
            u'test2', u'test 2 packageset', self.parent.owner,
            distroseries=self.parent)
        packages = ('udev', 'chromium')
        for pkg in packages:
            test1.addSources(pkg)
        self.factory.makeDistroArchSeries(distroseries=self.parent)
        child = self._fullInitialize(
            [self.parent],
            arches=[self.parent_das.architecturetag],
            packagesets=(str(test1.id),), rebuild=True)
        child.updatePackageCount()
        builds = child.getBuildRecords(
            build_state=BuildStatus.NEEDSBUILD,
            pocket=PackagePublishingPocket.RELEASE)
        self.assertEqual(child.sourcecount, len(packages))
        self.assertEqual(child.binarycount, 0)
        self.assertEqual(builds.count(), len(packages))
        das = list(IStore(DistroArchSeries).find(
            DistroArchSeries, distroseries=child))
        self.assertEqual(len(das), 1)
        self.assertEqual(
            das[0].architecturetag, self.parent_das.architecturetag)

    def test_do_not_copy_disabled_dases(self):
        # DASes that are disabled in the parent will not be copied.
        self.parent, self.parent_das = self.setupParent()
        ppc_das = self.factory.makeDistroArchSeries(
            distroseries=self.parent)
        ppc_das.enabled = False
        child = self._fullInitialize([self.parent])
        das = list(IStore(DistroArchSeries).find(
            DistroArchSeries, distroseries=child))
        self.assertEqual(len(das), 1)
        self.assertEqual(
            das[0].architecturetag, self.parent_das.architecturetag)

    def test_script(self):
        # Do an end-to-end test using the command-line tool.
        self.parent, self.parent_das = self.setupParent()
        uploader = self.factory.makePerson()
        test1 = getUtility(IPackagesetSet).new(
            u'test1', u'test 1 packageset', self.parent.owner,
            distroseries=self.parent)
        test1.addSources('udev')
        getUtility(IArchivePermissionSet).newPackagesetUploader(
            self.parent.main_archive, uploader, test1)
        child = self.factory.makeDistroSeries(previous_series=self.parent)
        # Create an initialized series in the distribution.
        other_series = self.factory.makeDistroSeries(
            distribution=child.parent)
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=other_series)
        transaction.commit()
        ifp = os.path.join(
            config.root, 'scripts', 'ftpmaster-tools',
            'initialize-from-parent.py')
        process = subprocess.Popen(
            [sys.executable, ifp, "-vv", "-d", child.parent.name,
            child.name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        self.addDetail("stdout", Content(UTF8_TEXT, lambda: stdout))
        self.addDetail("stderr", Content(UTF8_TEXT, lambda: stderr))
        self.assertEqual(process.returncode, 0)
        self.assertTrue(
            "DEBUG   Committing transaction." in stderr.split('\n'))
        transaction.commit()
        self.assertDistroSeriesInitializedCorrectly(
            child, self.parent, self.parent_das)

    def test_is_initialized(self):
        # At the end of the initialization, the distroseriesparent is marked
        # as 'initialized'.
        self.parent, self.parent_das = self.setupParent()
        child = self._fullInitialize([self.parent], rebuild=True, overlays=())
        dsp_set = getUtility(IDistroSeriesParentSet)
        distroseriesparent = dsp_set.getByDerivedAndParentSeries(
            child, self.parent)

        self.assertTrue(distroseriesparent.initialized)

    def test_no_overlays(self):
        # Without the overlay parameter, no overlays are created.
        self.parent, self.parent_das = self.setupParent()
        child = self._fullInitialize([self.parent], rebuild=True, overlays=[])
        dsp_set = getUtility(IDistroSeriesParentSet)
        distroseriesparent = dsp_set.getByDerivedAndParentSeries(
            child, self.parent)

        self.assertFalse(distroseriesparent.is_overlay)

    def test_setup_overlays(self):
        # If the overlay parameter is passed, overlays are properly setup.
        self.parent1, notused = self.setupParent(
            packages={'udev': '0.1-1'})
        self.parent2, notused = self.setupParent(
            packages={'udev': '0.1-3'})

        overlays = [False, True]
        overlay_pockets = [None, 'Updates']
        overlay_components = [None, 'universe']
        child = self._fullInitialize(
            [self.parent1, self.parent2], rebuild=True,
            overlays=overlays,
            overlay_pockets=overlay_pockets,
            overlay_components=overlay_components)
        dsp_set = getUtility(IDistroSeriesParentSet)
        distroseriesparent1 = dsp_set.getByDerivedAndParentSeries(
            child, self.parent1)
        distroseriesparent2 = dsp_set.getByDerivedAndParentSeries(
            child, self.parent2)

        self.assertFalse(distroseriesparent1.is_overlay)
        self.assertTrue(distroseriesparent2.is_overlay)
        self.assertEqual(
            getUtility(IComponentSet)['universe'],
            distroseriesparent2.component)
        self.assertEqual(
            PackagePublishingPocket.UPDATES, distroseriesparent2.pocket)

    def test_multiple_parents_initialize(self):
        self.parent, self.parent_das = self.setupParent()
        self.parent2, self.parent_das2 = self.setupParent(
            packages={'alpha': '0.1-1'})
        child = self._fullInitialize([self.parent, self.parent2])
        self.assertDistroSeriesInitializedCorrectly(
            child, self.parent, self.parent_das)

    def test_multiple_parents_ordering(self):
        # The parents' order is stored.
        self.parent1, notused = self.setupParent(
            packages={'udev': '0.1-1'})
        self.parent2, notused = self.setupParent(
            packages={'udev': '0.1-3'})
        self.parent3, notused = self.setupParent(
            packages={'udev': '0.1-2'})
        child = self._fullInitialize(
            [self.parent1, self.parent3, self.parent2])
        dsp_set = getUtility(IDistroSeriesParentSet)
        distroseriesparent1 = dsp_set.getByDerivedAndParentSeries(
            child, self.parent1)
        distroseriesparent2 = dsp_set.getByDerivedAndParentSeries(
            child, self.parent2)
        distroseriesparent3 = dsp_set.getByDerivedAndParentSeries(
            child, self.parent3)

        self.assertContentEqual(
            [self.parent1, self.parent3, self.parent2],
            child.getParentSeries())
        self.assertEqual(0, distroseriesparent1.ordering)
        self.assertEqual(1, distroseriesparent3.ordering)
        self.assertEqual(2, distroseriesparent2.ordering)

    def test_multiple_parent_packagesets_merge(self):
        # Identical packagesets from the parents are merged as one
        # packageset in the child.
        self.parent1, self.parent_das1 = self.setupParent(
            packages={'udev': '0.1-1', 'libc6': '2.8-1',
                'postgresql': '9.0-1', 'chromium': '3.6'})
        self.parent2, self.parent_das2 = self.setupParent(
            packages={'udev': '0.1-2', 'libc6': '2.8-2',
                'postgresql': '9.0-2', 'chromium': '3.7'})
        uploader1 = self.factory.makePerson()
        uploader2 = self.factory.makePerson()
        test1_parent1 = getUtility(IPackagesetSet).new(
            u'test1', u'test 1 packageset', self.parent1.owner,
            distroseries=self.parent1)
        test1_parent2 = getUtility(IPackagesetSet).new(
            u'test1', u'test 1 packageset', self.parent2.owner,
            distroseries=self.parent2)
        test1_parent1.addSources('chromium')
        test1_parent1.addSources('udev')
        test1_parent2.addSources('udev')
        test1_parent2.addSources('libc6')
        getUtility(IArchivePermissionSet).newPackagesetUploader(
            self.parent1.main_archive, uploader1, test1_parent1)
        getUtility(IArchivePermissionSet).newPackagesetUploader(
            self.parent2.main_archive, uploader2, test1_parent2)
        child = self._fullInitialize([self.parent1, self.parent2])

        # In the child, the identical packagesets are merged into one.
        child_test1 = getUtility(IPackagesetSet).getByName(
            u'test1', distroseries=child)
        child_srcs = child_test1.getSourcesIncluded(
            direct_inclusion=True)
        parent1_srcs = test1_parent1.getSourcesIncluded(direct_inclusion=True)
        parent2_srcs = test1_parent2.getSourcesIncluded(direct_inclusion=True)
        self.assertContentEqual(
            set(parent1_srcs).union(set(parent2_srcs)),
            child_srcs)

    def test_multiple_parents_format_selection_union(self):
        # The format selection for the derived series is the union of
        # the format selections of the parents.
        format1 = SourcePackageFormat.FORMAT_1_0
        format2 = SourcePackageFormat.FORMAT_3_0_QUILT
        self.parent1, notused = self.setupParent(
            format_selection=format1, packages={'udev': '0.1-1'})
        self.parent2, notused = self.setupParent(
            format_selection=format2, packages={'udev': '0.1-2'})
        child = self._fullInitialize([self.parent1, self.parent2])

        self.assertTrue(child.isSourcePackageFormatPermitted(format1))
        self.assertTrue(child.isSourcePackageFormatPermitted(format2))

    def test_multiple_parents_component_merge(self):
        # The components from the parents are merged to create the
        # child's components.
        self.comp1 = self.factory.makeComponent()
        self.comp2 = self.factory.makeComponent()
        self.parent1, unused = self.setupParent(
            packages={'udev': '0.1-1'})
        self.parent2, unused = self.setupParent(
            packages={'udev': '0.1-2'})
        ComponentSelection(distroseries=self.parent1, component=self.comp1)
        ComponentSelection(distroseries=self.parent2, component=self.comp1)
        ComponentSelection(distroseries=self.parent2, component=self.comp2)
        child = self._fullInitialize([self.parent1, self.parent2])

        self.assertContentEqual(
            [self.comp1, self.comp2],
            child.components)

    def test_multiple_parents_section_merge(self):
        # The sections from the parents are merged to create the child's
        # sections.
        self.section1 = self.factory.makeSection()
        self.section2 = self.factory.makeSection()
        self.parent1, unused = self.setupParent(
            packages={'udev': '0.1-1'})
        self.parent2, unused = self.setupParent(
            packages={'udev': '0.1-2'})
        SectionSelection(distroseries=self.parent1, section=self.section1)
        SectionSelection(distroseries=self.parent2, section=self.section1)
        SectionSelection(distroseries=self.parent2, section=self.section2)
        child = self._fullInitialize([self.parent1, self.parent2])

        self.assertContentEqual(
            [self.section1, self.section2],
            child.sections)

    def test_multiple_parents_same_package(self):
        # If the same package (i.e. same packagename and version) is
        # published in different parents the initialization will error.
        self.parent1, self.parent_das1 = self.setupParent(
            packages={'package': '0.1-1'})
        self.parent2, self.parent_das2 = self.setupParent(
            packages={'package': '0.1-1'})

        self.assertRaises(
            InitializationError, self._fullInitialize,
            [self.parent1, self.parent2])

    def setUpSeriesWithPreviousSeries(self, previous_parents=(),
                                      publish_in_distribution=True,
                                      same_distribution=True):
        # Helper method to create a series within an initialized
        # distribution (i.e. that has an initialized series) with a
        # 'previous_series' with parents.

        # Create a previous_series derived from 2 parents.
        previous_series = self._fullInitialize(previous_parents)

        if same_distribution:
            child = self.factory.makeDistroSeries(
                previous_series=previous_series,
                distribution=previous_series.distribution)
        else:
            child = self.factory.makeDistroSeries(
                previous_series=previous_series)

        # Add a publishing in another series from this distro.
        other_series = self.factory.makeDistroSeries(
            distribution=child.distribution)
        if publish_in_distribution:
            self.factory.makeSourcePackagePublishingHistory(
                distroseries=other_series)

        return child

    def test_derive_from_previous_parents(self):
        # If the series to be initialized is in a distribution with
        # initialized series, the series is *derived* from
        # the previous_series' parents.
        previous_parent1, unused = self.setupParent(packages={u'p1': u'1.2'})
        previous_parent2, unused = self.setupParent(packages={u'p2': u'1.5'})
        child = self.setUpSeriesWithPreviousSeries(
            previous_parents=[previous_parent1, previous_parent2])
        parent, unused = self.setupParent()
        self._fullInitialize([parent], child=child)

        # The parent for the derived series is the distroseries given as
        # argument to InitializeSeries.
        self.assertContentEqual(
            [parent],
            child.getParentSeries())

        # The new series has been derived from previous_series.
        published_sources = child.main_archive.getPublishedSources(
            distroseries=child)
        self.assertEquals(2, published_sources.count())
        pub_sources = sorted(
            [(s.sourcepackagerelease.sourcepackagename.name,
              s.sourcepackagerelease.version)
                for s in published_sources])
        self.assertEquals(
            [(u'p1', u'1.2'), (u'p2', u'1.5')],
            pub_sources)

    def test_derive_from_previous_parents_empty_parents(self):
        # If an empty list is passed to InitializeDistroSeries, the
        # parents of the previous series are used as parents.
        previous_parent1, unused = self.setupParent(packages={u'p1': u'1.2'})
        previous_parent2, unused = self.setupParent(packages={u'p2': u'1.5'})
        child = self.setUpSeriesWithPreviousSeries(
            previous_parents=[previous_parent1, previous_parent2])
        # Initialize from an empty list of parents.
        self._fullInitialize([], child=child)

        self.assertContentEqual(
            [previous_parent1, previous_parent2],
            child.getParentSeries())

    def test_derive_empty_parents_distribution_not_initialized(self):
        # Initializing a series with an empty parent list if the series'
        # distribution has no initialized series triggers an error.
        previous_parent1, unused = self.setupParent(packages={u'p1': u'1.2'})
        child = self.setUpSeriesWithPreviousSeries(
            previous_parents=[previous_parent1],
            publish_in_distribution=False,
            same_distribution=False)

        # Initialize from an empty list of parents.
        ids = InitializeDistroSeries(child, [])
        self.assertRaisesWithContent(
            InitializationError,
            ("Distroseries {child.name} cannot be initialized: "
             "No other series in the distribution is initialized "
             "and no parent was passed to the initilization method"
             ".").format(child=child),
             ids.check)

    def createDistroSeriesWithPublication(self, distribution=None):
        # Create a distroseries with a publication in the DEBUG archive.
        distroseries = self.factory.makeDistroSeries(
            distribution=distribution)
        # Publish a package in another archive in distroseries' distribution.
        debug_archive = self.factory.makeArchive(
            distribution=distroseries.distribution,
            purpose=ArchivePurpose.DEBUG)

        self.factory.makeSourcePackagePublishingHistory(
            distroseries=distroseries, archive=debug_archive)
        return distroseries

    def test_copy_method_diff_archive_empty_target(self):
        # If the archives are different and the target archive is
        # empty: use the cloner.
        distroseries = self.createDistroSeriesWithPublication()
        parent = self.factory.makeDistroSeries()
        target_archive = distroseries.main_archive

        ids = InitializeDistroSeries(distroseries, [parent.id])
        self.assertTrue(
            ids._use_cloner(
                target_archive, parent.main_archive))

    def test_copy_method_first_derivation(self):
        # If this is a first derivation: do not use the copier.
        parent = self.factory.makeDistroSeries()
        distroseries = self.factory.makeDistroSeries()
        target_archive = distroseries.main_archive
        ids = InitializeDistroSeries(distroseries, [parent.id])

        self.assertFalse(
            ids._use_cloner(target_archive, target_archive))

    def test_copy_method_same_archive_empty_series_non_empty_archive(self):
        # In a post-first derivation, if the archives are the same and the
        # target series is empty (another series in the same distribution
        # might not be empty): use the cloner.
        parent = self.factory.makeDistroSeries()
        distroseries = self.createDistroSeriesWithPublication()
        other_distroseries = self.factory.makeDistroSeries(
            distribution=distroseries.distribution)
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=other_distroseries)
        target_archive = distroseries.main_archive
        ids = InitializeDistroSeries(distroseries, [parent.id])

        self.assertTrue(
            ids._use_cloner(target_archive, target_archive))

    def test_copy_method_diff_archive_non_empty_target(self):
        # In a post-first derivation, if the archives are different and the
        # target archive is *not* empty: don't use the cloner.
        parent = self.factory.makeDistroSeries()
        distroseries = self.factory.makeDistroSeries()
        target_archive = distroseries.main_archive
        other_distroseries = self.factory.makeDistroSeries(
            distribution=distroseries.distribution)
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=other_distroseries)
        ids = InitializeDistroSeries(distroseries, [parent.id])

        self.assertFalse(
            ids._use_cloner(target_archive, parent.main_archive))

    def test_copy_method_same_archive_non_empty_series(self):
        # In a post-first derivation, if the archives are the same and the
        # target series is *not* empty: don't use the cloner.
        parent = self.factory.makeDistroSeries()
        distroseries = self.factory.makeDistroSeries()
        self.factory.makeSourcePackagePublishingHistory(
            distroseries=distroseries)
        target_archive = distroseries.main_archive

        ids = InitializeDistroSeries(distroseries, [parent.id])
        self.assertFalse(
            ids._use_cloner(target_archive, target_archive))

    def test__has_same_parents_as_previous_series_explicit(self):
        # IDS._has_same_parents_as_previous_series returns True if the
        # parents for the series to be initialized are the same as
        # previous_series' parents.
        prev_parent1, unused = self.setupParent(packages={u'p1': u'1.2'})
        prev_parent2, unused = self.setupParent(packages={u'p2': u'1.5'})
        child = self.setUpSeriesWithPreviousSeries(
            previous_parents=[prev_parent1, prev_parent2])
        # The same parents can be explicitely set.
        ids = InitializeDistroSeries(
            child, [prev_parent2.id, prev_parent1.id])

        self.assertTrue(ids._has_same_parents_as_previous_series())

    def test__has_same_parents_as_previous_series_implicit(self):
        # IDS._has_same_parents_as_previous_series returns True if the
        # parents for the series to be initialized are the same as
        # previous_series' parents.
        prev_parent1, unused = self.setupParent(packages={u'p1': u'1.2'})
        prev_parent2, unused = self.setupParent(packages={u'p2': u'1.5'})
        child = self.setUpSeriesWithPreviousSeries(
            previous_parents=[prev_parent1, prev_parent2])
        # If no parents are provided, the parents from previous_series
        # will be used.
        ids = InitializeDistroSeries(child)

        self.assertTrue(ids._has_same_parents_as_previous_series())

    def test_not__has_same_parents_as_previous_series(self):
        # IDS._has_same_parents_as_previous_series returns False if the
        # parents for the series to be initialized are *not* the same as
        # previous_series' parents.
        prev_parent1, unused = self.setupParent(packages={u'p1': u'1.2'})
        prev_parent2, unused = self.setupParent(packages={u'p2': u'1.5'})
        child = self.setUpSeriesWithPreviousSeries(
            previous_parents=[prev_parent1, prev_parent2])
        parent3 = self.factory.makeDistroSeries()
        ids = InitializeDistroSeries(
            child, [prev_parent2.id, prev_parent1.id, parent3.id])

        self.assertFalse(ids._has_same_parents_as_previous_series())

    def test_initialization_post_first_deriv_copy_dsds(self):
        # Post-first initialization of a series with the same parents
        # than those of the previous_series causes a copy of
        # previous_series' DSDs.
        prev_parent1, unused = self.setupParent(packages={u'p1': u'1.2'})
        prev_parent2, unused = self.setupParent(packages={u'p2': u'1.5'})
        child = self.setUpSeriesWithPreviousSeries(
            previous_parents=[prev_parent1, prev_parent2])
        self.factory.makeDistroSeriesDifference()
        self.factory.makeDistroSeriesDifference(
            derived_series=child.previous_series,
            source_package_name_str=u'p1')
        self.factory.makeDistroSeriesDifference(
            derived_series=child.previous_series,
            source_package_name_str=u'p2')
        dsd_source = getUtility(IDistroSeriesDifferenceSource)
        # No DSDs for the child yet.
        self.assertEquals(0, dsd_source.getForDistroSeries(child).count())
        self._fullInitialize([], child=child)

        self.assertContentEqual(
            [u'p1', u'p2'],
            [
                diff.source_package_name.name
                for diff in dsd_source.getForDistroSeries(child)])

    def getWaitingJobs(self, derived_series, package_name, parent_series):
        """Get waiting jobs for given derived/parent series and package.

        :return: A list (not a result set or any old iterable, but a list)
            of `DistroSeriesDifferenceJob`.
        """
        sourcepackagename = self.factory.getOrMakeSourcePackageName(
            package_name)
        return list(find_waiting_jobs(
            derived_series, sourcepackagename, parent_series))

    def test_initialization_first_deriv_create_dsdjs(self):
        # A first initialization of a series creates the creation
        # of the DSDJs with all the parents.
        parent1, unused = self.setupParent(packages={u'p1': u'1.2'})
        parent2, unused = self.setupParent(packages={u'p2': u'1.5'})
        self.useFixture(FeatureFixture({FEATURE_FLAG_ENABLE_MODULE: 'on'}))
        child = self._fullInitialize([parent1, parent2])

        self.assertNotEqual([], self.getWaitingJobs(child, 'p1', parent1))
        self.assertNotEqual([], self.getWaitingJobs(child, 'p2', parent1))

    def test_initialization_post_first_deriv_create_dsdjs(self):
        # Post-first initialization of a series with different parents
        # than those of the previous_series creates the DSDJs to
        # compute the DSDs with the parents.
        prev_parent1, unused = self.setupParent(packages={u'p1': u'1.2'})
        prev_parent2, unused = self.setupParent(packages={u'p2': u'1.5'})
        child = self.setUpSeriesWithPreviousSeries(
            previous_parents=[prev_parent1, prev_parent2])
        parent3, unused = self.setupParent(
            packages={u'p2': u'2.5', u'p3': u'1.1'})
        self.useFixture(FeatureFixture({FEATURE_FLAG_ENABLE_MODULE: 'on'}))
        self._fullInitialize(
            [prev_parent1, prev_parent2, parent3], child=child)

        self.assertNotEqual(
            [], self.getWaitingJobs(child, 'p1', prev_parent1))
        self.assertNotEqual(
            [], self.getWaitingJobs(child, 'p2', prev_parent2))
        self.assertNotEqual([], self.getWaitingJobs(child, 'p2', parent3))
        self.assertEqual([], self.getWaitingJobs(child, 'p3', parent3))

    def test_initialization_compute_dsds_specific_packagesets(self):
        # Post-first initialization of a series with specific
        # packagesets creates the DSDJs for the packages inside these
        # packagesets.
        prev_parent1, unused = self.setupParent(
            packages={u'p1': u'1.2', u'p11': u'3.1'})
        prev_parent2, unused = self.setupParent(packages={u'p2': u'1.5'})
        child = self.setUpSeriesWithPreviousSeries(
            previous_parents=[prev_parent1, prev_parent2])
        test1 = getUtility(IPackagesetSet).new(
            u'test1', u'test 1 packageset', child.previous_series.owner,
            distroseries=child.previous_series)
        test1.addSources('p1')
        parent3, unused = self.setupParent(
            packages={u'p1': u'2.5', u'p3': u'4.4'})
        self.useFixture(FeatureFixture({FEATURE_FLAG_ENABLE_MODULE: 'on'}))
        self._fullInitialize(
            [prev_parent1, prev_parent2, parent3], child=child,
            packagesets=(str(test1.id),))

        self.assertNotEqual(
            [], self.getWaitingJobs(child, 'p1', prev_parent1))
        self.assertEqual([], self.getWaitingJobs(child, 'p11', prev_parent1))
        self.assertEqual([], self.getWaitingJobs(child, 'p2', prev_parent2))
        self.assertNotEqual([], self.getWaitingJobs(child, 'p1', parent3))
        self.assertEqual([], self.getWaitingJobs(child, 'p3', parent3))
