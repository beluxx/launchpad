# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the lp.soyuz.browser.builder module."""

__metaclass__ = type

from testtools.matchers import LessThan
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.buildmaster.interfaces.builder import IBuilderSet
from lp.buildmaster.interfaces.buildqueue import IBuildQueueSet
from lp.services.webapp import canonical_url
from lp.soyuz.browser.tests.test_builder_views import BuildCreationMixin
from lp.testing import (
    record_two_runs,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )
from lp.testing.matchers import HasQueryCount
from lp.testing.publication import test_traverse
from lp.testing.views import create_initialized_view
from lp.translations.interfaces.translationtemplatesbuildjob import (
    ITranslationTemplatesBuildJobSource,
    )


class TestBuildersNavigation(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_buildjob_redirects_for_recipe_build(self):
        # /builders/+buildjob/<job id> redirects to the build page.
        build = self.factory.makeSourcePackageRecipeBuild()
        url = 'http://launchpad.dev/builders/+buildjob/%s' % (
            build.build_farm_job.id)
        context, view, request = test_traverse(url)
        view()
        self.assertEqual(301, request.response.getStatus())
        self.assertEqual(
            canonical_url(build),
            request.response.getHeader('location'))

    def test_buildjob_redirects_for_binary_build(self):
        # /builders/+buildjob/<job id> redirects to the build page.
        build = self.factory.makeBinaryPackageBuild()
        url = 'http://launchpad.dev/builders/+buildjob/%s' % (
            build.build_farm_job.id)
        context, view, request = test_traverse(url)
        view()
        self.assertEqual(301, request.response.getStatus())
        self.assertEqual(
            canonical_url(build),
            request.response.getHeader('location'))


def builders_homepage_render():
    builders = getUtility(IBuilderSet)
    create_initialized_view(builders, "+index").render()


class TestBuildersHomepage(TestCaseWithFactory, BuildCreationMixin):

    layer = LaunchpadFunctionalLayer

    # XXX rvb: the query issued per build is the result of the call to
    # build.buildqueue_record.  It was decided not to make it a cachedproperty
    # because the code relies on the fact that this property always returns
    # the current record.

    def test_builders_binary_package_build_query_count(self):
        def create_build():
            build = self.createBinaryPackageBuild()
            queue = build.queueBuild()
            queue.markAsBuilding(build.builder)

        nb_objects = 2
        recorder1, recorder2 = record_two_runs(
            builders_homepage_render, create_build, nb_objects)

        self.assertThat(
            recorder2,
            HasQueryCount(LessThan(recorder1.count + 1 * nb_objects + 1)))

    def test_builders_recipe_build_query_count(self):
        def create_build():
            build = self.createRecipeBuildWithBuilder()
            queue = build.queueBuild()
            queue.markAsBuilding(build.builder)

        nb_objects = 2
        recorder1, recorder2 = record_two_runs(
            builders_homepage_render, create_build, nb_objects)

        self.assertThat(
            recorder2,
            HasQueryCount(LessThan(recorder1.count + 1 * nb_objects + 1)))

    def test_builders_translation_template_build_query_count(self):
        def create_build():
            jobset = getUtility(ITranslationTemplatesBuildJobSource)
            branch = self.factory.makeBranch()
            specific_job = jobset.create(branch)
            queueset = getUtility(IBuildQueueSet)
            # Using rSP is required to get the job id.
            naked_job = removeSecurityProxy(specific_job.job)
            job_id = naked_job.id
            queue = queueset.get(job_id)
            queue.markAsBuilding(self.factory.makeBuilder())

        nb_objects = 2
        recorder1, recorder2 = record_two_runs(
            builders_homepage_render, create_build, nb_objects)

        self.assertThat(
            recorder2,
            HasQueryCount(LessThan(recorder1.count + 1 * nb_objects + 1)))
