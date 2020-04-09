# Copyright 2020 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test OCI recipe build views."""

from __future__ import absolute_import, print_function, unicode_literals

__metaclass__ = type

import re

from storm.locals import Store
from testtools.matchers import StartsWith

from lp.buildmaster.enums import BuildStatus
from lp.oci.interfaces.ocirecipe import OCI_RECIPE_ALLOW_CREATE
from lp.services.features.testing import FeatureFixture
from lp.services.webapp import canonical_url
from lp.testing import (
    BrowserTestCase,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )
from lp.testing.pages import (
    extract_text,
    find_main_content,
    )


class TestCanonicalUrlForOCIRecipeBuild(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestCanonicalUrlForOCIRecipeBuild, self).setUp()
        self.useFixture(FeatureFixture({OCI_RECIPE_ALLOW_CREATE: 'on'}))

    def test_canonical_url(self):
        owner = self.factory.makePerson(name="person")
        distribution = self.factory.makeDistribution(name="distro")
        oci_project = self.factory.makeOCIProject(
            pillar=distribution, ociprojectname="oci-project")
        recipe = self.factory.makeOCIRecipe(
            name="recipe", registrant=owner, owner=owner,
            oci_project=oci_project)
        build = self.factory.makeOCIRecipeBuild(requester=owner, recipe=recipe)
        self.assertThat(
            canonical_url(build),
            StartsWith(
                "http://launchpad.test/~person/distro/+oci/oci-project/"
                "+recipe/recipe/+build/"))


class TestOCIRecipeBuildView(BrowserTestCase):

    layer = LaunchpadFunctionalLayer

    def setUp(self):
        super(TestOCIRecipeBuildView, self).setUp()
        self.useFixture(FeatureFixture({OCI_RECIPE_ALLOW_CREATE: 'on'}))

    def test_index(self):
        build = self.factory.makeOCIRecipeBuild()
        recipe = build.recipe
        oci_project = recipe.oci_project
        self.assertTextMatchesExpressionIgnoreWhitespace("""\
            386 build of .*
            created .*
            Build status
            Needs building
            Build details
            Recipe: OCI recipe %s/%s/%s for %s
            Architecture: i386
            """ % (
                oci_project.pillar.name, oci_project.name, recipe.name,
                recipe.owner.display_name),
            self.getMainText(build))


class TestOCIRecipeBuildOperations(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestOCIRecipeBuildOperations, self).setUp()
        self.useFixture(FeatureFixture({OCI_RECIPE_ALLOW_CREATE: 'on'}))
        self.build = self.factory.makeOCIRecipeBuild()
        self.build_url = canonical_url(self.build)

    def test_builder_history(self):
        Store.of(self.build).flush()
        self.build.updateStatus(
            BuildStatus.FULLYBUILT, builder=self.factory.makeBuilder())
        title = self.build.title
        browser = self.getViewBrowser(self.build.builder, "+history")
        self.assertTextMatchesExpressionIgnoreWhitespace(
            "Build history.*%s" % re.escape(title),
            extract_text(find_main_content(browser.contents)))
        self.assertEqual(self.build_url, browser.getLink(title).url)

    def makeBuildingOCIRecipe(self):
        builder = self.factory.makeBuilder()
        build = self.factory.makeOCIRecipeBuild()
        build.updateStatus(BuildStatus.BUILDING, builder=builder)
        build.queueBuild()
        build.buildqueue_record.builder = builder
        build.buildqueue_record.logtail = "tail of the log"
        return build

    def test_builder_index(self):
        build = self.makeBuildingOCIRecipe()
        browser = self.getViewBrowser(build.builder, no_login=True)
        self.assertIn("tail of the log", browser.contents)
