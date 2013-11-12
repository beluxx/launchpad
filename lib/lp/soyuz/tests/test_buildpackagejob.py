# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test BuildQueue features."""

from datetime import timedelta

from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.buildmaster.enums import BuildStatus
from lp.buildmaster.interfaces.builder import IBuilderSet
from lp.services.database.interfaces import IStore
from lp.soyuz.enums import (
    ArchivePurpose,
    PackagePublishingStatus,
    )
from lp.soyuz.interfaces.buildfarmbuildjob import IBuildFarmBuildJob
from lp.soyuz.interfaces.buildpackagejob import IBuildPackageJob
from lp.soyuz.interfaces.processor import IProcessorSet
from lp.soyuz.model.binarypackagebuild import BinaryPackageBuild
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
from lp.testing import TestCaseWithFactory
from lp.testing.layers import LaunchpadZopelessLayer


def find_job(test, name, processor='386'):
    """Find build and queue instance for the given source and processor."""
    for build in test.builds:
        if (build.source_package_release.name == name
            and build.processor.name == processor):
            return (build, build.buildqueue_record)
    return (None, None)


def builder_key(build):
    """Return processor and virtualization for the given build."""
    return (build.processor.id, build.is_virtualized)


def assign_to_builder(test, job_name, builder_number, processor='386'):
    """Simulate assigning a build to a builder."""
    def nth_builder(test, build, n):
        """Get builder #n for the given build processor and virtualization."""
        builder = None
        builders = test.builders.get(builder_key(build), [])
        try:
            builder = builders[n - 1]
        except IndexError:
            pass
        return builder

    build, bq = find_job(test, job_name, processor)
    builder = nth_builder(test, build, builder_number)
    bq.markAsBuilding(builder)


class TestBuildJobBase(TestCaseWithFactory):
    """Setup the test publisher and some builders."""

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestBuildJobBase, self).setUp()
        self.publisher = SoyuzTestPublisher()
        self.publisher.prepareBreezyAutotest()

        self.i8 = self.factory.makeBuilder(name='i386-n-8', virtualized=False)
        self.i9 = self.factory.makeBuilder(name='i386-n-9', virtualized=False)

        processor = getUtility(IProcessorSet).getByName('hppa')
        self.h6 = self.factory.makeBuilder(
            name='hppa-n-6', processor=processor, virtualized=False)
        self.h7 = self.factory.makeBuilder(
            name='hppa-n-7', processor=processor, virtualized=False)

        self.builders = dict()
        # x86 native
        self.builders[(1, False)] = [self.i8, self.i9]

        # hppa native
        self.builders[(3, True)] = [self.h6, self.h7]

        # Ensure all builders are operational.
        for builders in self.builders.values():
            for builder in builders:
                builder.builderok = True
                builder.manual = False

        # Disable the sample data builders.
        getUtility(IBuilderSet)['bob'].builderok = False
        getUtility(IBuilderSet)['frog'].builderok = False


class TestBuildPackageJob(TestBuildJobBase):
    """Test dispatch time estimates for binary builds (i.e. single build
    farm job type) targetting a single processor architecture and the primary
    archive.
    """

    def setUp(self):
        """Set up some native x86 builds for the test archive."""
        super(TestBuildPackageJob, self).setUp()
        # The builds will be set up as follows:
        #
        # j: 3        gedit p: hppa v:False e:0:01:00 *** s: 1001
        # j: 4        gedit p:  386 v:False e:0:02:00 *** s: 1002
        # j: 5      firefox p: hppa v:False e:0:03:00 *** s: 1003
        # j: 6      firefox p:  386 v:False e:0:04:00 *** s: 1004
        # j: 7     cobblers p: hppa v:False e:0:05:00 *** s: 1005
        # j: 8     cobblers p:  386 v:False e:0:06:00 *** s: 1006
        # j: 9 thunderpants p: hppa v:False e:0:07:00 *** s: 1007
        # j:10 thunderpants p:  386 v:False e:0:08:00 *** s: 1008
        # j:11          apg p: hppa v:False e:0:09:00 *** s: 1009
        # j:12          apg p:  386 v:False e:0:10:00 *** s: 1010
        # j:13          vim p: hppa v:False e:0:11:00 *** s: 1011
        # j:14          vim p:  386 v:False e:0:12:00 *** s: 1012
        # j:15          gcc p: hppa v:False e:0:13:00 *** s: 1013
        # j:16          gcc p:  386 v:False e:0:14:00 *** s: 1014
        # j:17        bison p: hppa v:False e:0:15:00 *** s: 1015
        # j:18        bison p:  386 v:False e:0:16:00 *** s: 1016
        # j:19         flex p: hppa v:False e:0:17:00 *** s: 1017
        # j:20         flex p:  386 v:False e:0:18:00 *** s: 1018
        # j:21     postgres p: hppa v:False e:0:19:00 *** s: 1019
        # j:22     postgres p:  386 v:False e:0:20:00 *** s: 1020
        #
        # j=job, p=processor, v=virtualized, e=estimated_duration, s=score

        # First mark all builds in the sample data as already built.
        store = IStore(BinaryPackageBuild)
        sample_data = store.find(BinaryPackageBuild)
        for build in sample_data:
            build.buildstate = BuildStatus.FULLYBUILT
        store.flush()

        # We test builds that target a primary archive.
        self.non_ppa = self.factory.makeArchive(
            name="primary", purpose=ArchivePurpose.PRIMARY)
        self.non_ppa.require_virtualized = False

        self.builds = []
        sourcenames = [
            "gedit",
            "firefox",
            "cobblers",
            "thunderpants",
            "apg",
            "vim",
            "gcc",
            "bison",
            "flex",
            "postgres",
            ]
        for sourcename in sourcenames:
            self.builds.extend(
                self.publisher.getPubSource(
                    sourcename=sourcename,
                    status=PackagePublishingStatus.PUBLISHED,
                    archive=self.non_ppa,
                    architecturehintlist='any').createMissingBuilds())

        # We want the builds to have a lot of variety when it comes to score
        # and estimated duration etc. so that the queries under test get
        # exercised properly.
        score = 1000
        duration = 0
        for build in self.builds:
            score += 1
            duration += 60
            bq = build.buildqueue_record
            bq.lastscore = score
            removeSecurityProxy(bq).estimated_duration = timedelta(
                seconds=duration)

    def test_providesInterfaces(self):
        # Ensure that a BuildPackageJob generates an appropriate cookie.
        build, bq = find_job(self, 'gcc', '386')
        build_farm_job = bq.specific_job
        self.assertProvides(build_farm_job, IBuildPackageJob)
        self.assertProvides(build_farm_job, IBuildFarmBuildJob)
