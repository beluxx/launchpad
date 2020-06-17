# -*- coding: utf-8 -*-
# Copyright 2019-2020 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test OCI project views."""

from __future__ import absolute_import, print_function, unicode_literals

__metaclass__ = type
__all__ = []

from datetime import datetime

import pytz
from zope.security.proxy import removeSecurityProxy

from lp.oci.interfaces.ocirecipe import OCI_RECIPE_ALLOW_CREATE
from lp.registry.interfaces.ociproject import (
    OCI_PROJECT_ALLOW_CREATE,
    OCIProjectCreateFeatureDisabled,
    )
from lp.services.database.constants import UTC_NOW
from lp.services.features.testing import FeatureFixture
from lp.services.webapp import canonical_url
from lp.services.webapp.escaping import structured
from lp.testing import (
    admin_logged_in,
    BrowserTestCase,
    login_person,
    person_logged_in,
    record_two_runs,
    test_tales,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.matchers import MatchesTagText
from lp.testing.pages import (
    extract_text,
    find_main_content,
    find_tag_by_id,
    find_tags_by_class,
    )
from lp.testing.publication import test_traverse
from lp.testing.views import create_initialized_view


class TestOCIProjectFormatterAPI(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_link(self):
        oci_project = self.factory.makeOCIProject()
        markup = structured(
            '<a href="/%s/+oci/%s">%s</a>',
            oci_project.pillar.name, oci_project.name,
            oci_project.display_name).escapedtext
        self.assertEqual(
            markup,
            test_tales('oci_project/fmt:link', oci_project=oci_project))


class TestOCIProjectNavigation(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_canonical_url(self):
        distribution = self.factory.makeDistribution(name="mydistro")
        oci_project = self.factory.makeOCIProject(
            pillar=distribution, ociprojectname="myociproject")
        self.assertEqual(
            "http://launchpad.test/mydistro/+oci/myociproject",
            canonical_url(oci_project))

    def test_traversal(self):
        oci_project = self.factory.makeOCIProject()
        obj, _, _ = test_traverse(
            "http://launchpad.test/%s/+oci/%s" %
            (oci_project.pillar.name, oci_project.name))
        self.assertEqual(oci_project, obj)


class TestOCIProjectView(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def test_index_distribution_pillar(self):
        distribution = self.factory.makeDistribution(displayname="My Distro")
        oci_project = self.factory.makeOCIProject(
            pillar=distribution, ociprojectname="oci-name")
        self.assertTextMatchesExpressionIgnoreWhitespace("""\
            OCI project oci-name for My Distro
            .*
            OCI project information
            Distribution: My Distro
            Name: oci-name
            """, self.getMainText(oci_project))

    def test_index_project_pillar(self):
        product = self.factory.makeProduct(displayname="My Project")
        oci_project = self.factory.makeOCIProject(
            pillar=product, ociprojectname="oci-name")
        self.assertTextMatchesExpressionIgnoreWhitespace("""\
            OCI project oci-name for My Project
            .*
            OCI project information
            Project: My Project
            Name: oci-name
            """, self.getMainText(oci_project))


class TestOCIProjectEditView(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def submitEditForm(self, browser, name, official_recipe=''):
        browser.getLink("Edit OCI project").click()
        browser.getControl(name="field.name").value = name
        browser.getControl(name="field.official_recipe").value = (
            official_recipe)
        browser.getControl("Update OCI project").click()

    def test_edit_oci_project(self):
        oci_project = self.factory.makeOCIProject()
        new_distribution = self.factory.makeDistribution(
            owner=oci_project.pillar.owner)

        browser = self.getViewBrowser(
            oci_project, user=oci_project.pillar.owner)
        browser.getLink("Edit OCI project").click()
        browser.getControl(name="field.distribution").value = [
            new_distribution.name]
        browser.getControl(name="field.name").value = "new-name"
        browser.getControl("Update OCI project").click()

        content = find_main_content(browser.contents)
        self.assertEqual(
            "OCI project new-name for %s" % new_distribution.display_name,
            extract_text(content.h1))
        self.assertThat(
            "Distribution:\n%s\nEdit OCI project" % (
                new_distribution.display_name),
            MatchesTagText(content, "pillar"))
        self.assertThat(
            "Name:\nnew-name\nEdit OCI project",
            MatchesTagText(content, "name"))

    def test_edit_oci_project_change_project_pillar(self):
        with admin_logged_in():
            owner = self.factory.makePerson()
            project = self.factory.makeProduct(owner=owner)
            new_project = self.factory.makeProduct(owner=owner)
            oci_project = self.factory.makeOCIProject(pillar=project)
            new_project_name = new_project.name

        browser = self.getViewBrowser(
            oci_project, user=oci_project.pillar.owner)
        browser.getLink("Edit OCI project").click()
        browser.getControl(name="field.project").value = [new_project_name]
        browser.getControl(name="field.name").value = "new-name"
        browser.getControl("Update OCI project").click()

        content = find_main_content(browser.contents)
        with person_logged_in(owner):
            self.assertEqual(
                "OCI project new-name for %s" % new_project.display_name,
                extract_text(content.h1))
            self.assertThat(
                "Project:\n%s\nEdit OCI project" % (
                    new_project.display_name),
                MatchesTagText(content, "pillar"))
            self.assertThat(
                "Name:\nnew-name\nEdit OCI project",
                MatchesTagText(content, "name"))

    def test_edit_oci_project_ad_oci_project_admin(self):
        admin_person = self.factory.makePerson()
        admin_team = self.factory.makeTeam(members=[admin_person])
        original_distribution = self.factory.makeDistribution(
            oci_project_admin=admin_team)
        oci_project = self.factory.makeOCIProject(
            pillar=original_distribution)
        new_distribution = self.factory.makeDistribution(
            oci_project_admin=admin_team)

        browser = self.getViewBrowser(
            oci_project, user=admin_person)
        browser.getLink("Edit OCI project").click()
        browser.getControl(name="field.distribution").value = [
            new_distribution.name]
        browser.getControl(name="field.name").value = "new-name"
        browser.getControl("Update OCI project").click()

        content = find_main_content(browser.contents)
        self.assertEqual(
            "OCI project new-name for %s" % new_distribution.display_name,
            extract_text(content.h1))
        self.assertThat(
            "Distribution:\n%s\nEdit OCI project" % (
                new_distribution.display_name),
            MatchesTagText(content, "pillar"))
        self.assertThat(
            "Name:\nnew-name\nEdit OCI project",
            MatchesTagText(content, "name"))

    def test_edit_oci_project_sets_date_last_modified(self):
        # Editing an OCI project sets the date_last_modified property.
        date_created = datetime(2000, 1, 1, tzinfo=pytz.UTC)
        oci_project = self.factory.makeOCIProject(date_created=date_created)
        self.assertEqual(date_created, oci_project.date_last_modified)
        with person_logged_in(oci_project.pillar.owner):
            view = create_initialized_view(
                oci_project, name="+edit", principal=oci_project.pillar.owner)
            view.update_action.success(
                {"name": "changed", "official_recipe": None})
        self.assertSqlAttributeEqualsDate(
            oci_project, "date_last_modified", UTC_NOW)

    def test_edit_oci_project_already_exists(self):
        oci_project = self.factory.makeOCIProject(ociprojectname="one")
        self.factory.makeOCIProject(
            pillar=oci_project.pillar, ociprojectname="two")
        pillar_display_name = oci_project.pillar.display_name
        browser = self.getViewBrowser(
            oci_project, user=oci_project.pillar.owner)
        self.submitEditForm(browser, "two")
        self.assertEqual(
            "There is already an OCI project in distribution %s with this "
            "name." % (pillar_display_name),
            extract_text(find_tags_by_class(browser.contents, "message")[1]))

    def test_edit_oci_project_invalid_name(self):
        oci_project = self.factory.makeOCIProject()
        browser = self.getViewBrowser(
            oci_project, user=oci_project.pillar.owner)
        self.submitEditForm(browser, "invalid name")

        self.assertStartsWith(
            extract_text(find_tags_by_class(browser.contents, "message")[1]),
            "Invalid name 'invalid name'.")

    def test_edit_oci_project_setting_official_recipe(self):
        self.useFixture(FeatureFixture({OCI_RECIPE_ALLOW_CREATE: 'on'}))

        with admin_logged_in():
            oci_project = self.factory.makeOCIProject()
            user = oci_project.pillar.owner
            recipe1 = self.factory.makeOCIRecipe(
                registrant=user, owner=user, oci_project=oci_project)
            recipe2 = self.factory.makeOCIRecipe(
                registrant=user, owner=user, oci_project=oci_project)

            name_value = oci_project.name
            recipe_value = "%s/%s" % (user.name, recipe1.name)

        browser = self.getViewBrowser(oci_project, user=user)
        self.submitEditForm(browser, name_value, recipe_value)

        with admin_logged_in():
            self.assertEqual(recipe1, oci_project.getOfficialRecipe())
            self.assertTrue(recipe1.official)
            self.assertFalse(recipe2.official)

    def test_edit_oci_project_overriding_official_recipe(self):
        self.useFixture(FeatureFixture({OCI_RECIPE_ALLOW_CREATE: 'on'}))
        with admin_logged_in():
            oci_project = self.factory.makeOCIProject()
            user = oci_project.pillar.owner
            recipe1 = self.factory.makeOCIRecipe(
                registrant=user, owner=user, oci_project=oci_project)
            recipe2 = self.factory.makeOCIRecipe(
                registrant=user, owner=user, oci_project=oci_project)

            # Sets recipe1 as the current official one
            oci_project.setOfficialRecipe(recipe1)

            # And we will try to set recipe2 as the new official.
            name_value = oci_project.name
            recipe_value = "%s/%s" % (user.name, recipe2.name)

        browser = self.getViewBrowser(oci_project, user=user)
        self.submitEditForm(browser, name_value, recipe_value)

        with admin_logged_in():
            self.assertEqual(recipe2, oci_project.getOfficialRecipe())
            self.assertFalse(recipe1.official)
            self.assertTrue(recipe2.official)

    def test_edit_oci_project_unsetting_official_recipe(self):
        self.useFixture(FeatureFixture({OCI_RECIPE_ALLOW_CREATE: 'on'}))
        with admin_logged_in():
            oci_project = self.factory.makeOCIProject()
            user = oci_project.pillar.owner
            recipe = self.factory.makeOCIRecipe(
                registrant=user, owner=user, oci_project=oci_project)
            oci_project.setOfficialRecipe(recipe)
            name_value = oci_project.name

        browser = self.getViewBrowser(oci_project, user=user)
        self.submitEditForm(browser, name_value, '')

        with admin_logged_in():
            self.assertEqual(None, oci_project.getOfficialRecipe())
            self.assertFalse(recipe.official)


class TestOCIProjectAddView(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def test_create_oci_project(self):
        oci_project = self.factory.makeOCIProject()
        user = oci_project.pillar.owner
        new_distribution = self.factory.makeDistribution(
            owner=user, oci_project_admin=user)
        browser = self.getViewBrowser(
            new_distribution, user=user, view_name='+new-oci-project')
        browser.getControl(name="field.name").value = "new-name"
        browser.getControl("Create OCI Project").click()

        content = find_main_content(browser.contents)
        self.assertEqual(
            "OCI project new-name for %s" % new_distribution.display_name,
            extract_text(content.h1))
        self.assertThat(
            "Distribution:\n%s\nEdit OCI project" % (
                new_distribution.display_name),
            MatchesTagText(content, "pillar"))
        self.assertThat(
             "Name:\nnew-name\nEdit OCI project",
             MatchesTagText(content, "name"))

    def test_create_oci_project_for_project(self):
        oci_project = self.factory.makeOCIProject()
        user = oci_project.pillar.owner
        project = self.factory.makeProduct(owner=user)
        browser = self.getViewBrowser(
            project, user=user, view_name='+new-oci-project')
        browser.getControl(name="field.name").value = "new-name"
        browser.getControl("Create OCI Project").click()

        content = find_main_content(browser.contents)
        with person_logged_in(user):
            self.assertEqual(
                "OCI project new-name for %s" % project.display_name,
                extract_text(content.h1))
            self.assertThat(
                "Project:\n%s\nEdit OCI project" % (
                    project.display_name),
                MatchesTagText(content, "pillar"))
            self.assertThat(
                 "Name:\nnew-name\nEdit OCI project",
                 MatchesTagText(content, "name"))

    def test_create_oci_project_already_exists(self):
        person = self.factory.makePerson()
        distribution = self.factory.makeDistribution(oci_project_admin=person)
        self.factory.makeOCIProject(ociprojectname="new-name",
                                    pillar=distribution,
                                    registrant=person)

        browser = self.getViewBrowser(
            distribution, user=person, view_name='+new-oci-project')
        browser.getControl(name="field.name").value = "new-name"
        browser.getControl("Create OCI Project").click()

        expected_msg = (
            "There is already an OCI project in distribution %s with this "
            "name." % distribution.display_name)
        self.assertEqual(
            expected_msg,
            extract_text(find_tags_by_class(browser.contents, "message")[1]))

    def test_create_oci_project_no_permission(self):
        self.useFixture(FeatureFixture({OCI_PROJECT_ALLOW_CREATE: ''}))
        another_person = self.factory.makePerson()
        new_distribution = self.factory.makeDistribution()
        self.assertRaises(
            OCIProjectCreateFeatureDisabled,
            self.getViewBrowser,
            new_distribution,
            user=another_person,
            view_name='+new-oci-project')


class TestOCIProjectSearchView(BrowserTestCase):

    layer = DatabaseFunctionalLayer

    def assertPaginationIsPresent(
            self, browser, results_in_page, total_result):
        """Checks that pagination is shown at the browser."""
        nav_index = find_tags_by_class(
            browser.contents, "batch-navigation-index")[0]
        nav_index_text = extract_text(nav_index).replace('\n', ' ')
        self.assertIn(
            "1 → %s of %s results" % (results_in_page, total_result),
            nav_index_text)

        nav_links = find_tags_by_class(
            browser.contents, "batch-navigation-links")[0]
        nav_links_text = extract_text(nav_links).replace('\n', ' ')
        self.assertIn("First • Previous • Next • Last", nav_links_text)

    def assertOCIProjectsArePresent(self, browser, oci_projects):
        table = find_tag_by_id(browser.contents, "projects_list")
        with admin_logged_in():
            for oci_project in oci_projects:
                url = canonical_url(oci_project, force_local_path=True)
                self.assertIn(url, str(table))
                self.assertIn(oci_project.name, str(table))

    def assertOCIProjectsAreNotPresent(self, browser, oci_projects):
        table = find_tag_by_id(browser.contents, "projects_list")
        with admin_logged_in():
            for oci_project in oci_projects:
                url = canonical_url(oci_project, force_local_path=True)
                self.assertNotIn(url, str(table))
                self.assertNotIn(oci_project.name, str(table))

    def check_search_no_oci_projects(self, pillar):
        pillar = removeSecurityProxy(pillar)
        person = self.factory.makePerson()

        browser = self.getViewBrowser(
            pillar, user=person, view_name='+search-oci-project')

        main_portlet = find_tags_by_class(browser.contents, "main-portlet")[0]
        self.assertIn(
            "There are no OCI projects registered for %s" % pillar.name,
            extract_text(main_portlet).replace("\n", " "))

    def test_search_no_oci_projects_distribution_pillar(self):
        return self.check_search_no_oci_projects(
            self.factory.makeDistribution())

    def test_search_no_oci_projects_project_pillar(self):
        return self.check_search_no_oci_projects(self.factory.makeProduct())

    def check_oci_projects_no_search_keyword(self, pillar):
        pillar = removeSecurityProxy(pillar)
        person = pillar.owner

        # Creates 3 OCI Projects
        oci_projects = [
            self.factory.makeOCIProject(
                ociprojectname="test-project-%s" % i,
                registrant=person, pillar=pillar) for i in range(3)]

        browser = self.getViewBrowser(
            pillar, user=person, view_name='+search-oci-project')

        # Check top message.
        main_portlet = find_tags_by_class(browser.contents, "main-portlet")[0]
        self.assertIn(
            "There are 3 OCI projects registered for %s" % pillar.name,
            extract_text(main_portlet).replace("\n", " "))

        self.assertOCIProjectsArePresent(browser, oci_projects)
        self.assertPaginationIsPresent(browser, 3, 3)

    def test_oci_projects_no_search_keyword_for_distribution(self):
        return self.check_oci_projects_no_search_keyword(
            self.factory.makeDistribution())

    def test_oci_projects_no_search_keyword_for_project(self):
        return self.check_oci_projects_no_search_keyword(
            self.factory.makeProduct())

    def check_oci_projects_with_search_keyword(self, pillar):
        pillar = removeSecurityProxy(pillar)
        person = pillar.owner

        # And 2 OCI projects that will match the name
        oci_projects = [
            self.factory.makeOCIProject(
                ociprojectname="find-me-%s" % i,
                registrant=person, pillar=pillar) for i in range(2)]

        # Creates 2 OCI Projects that will not match search
        other_oci_projects = [
            self.factory.makeOCIProject(
                ociprojectname="something-%s" % i,
                registrant=person, pillar=pillar) for i in range(2)]

        browser = self.getViewBrowser(
            pillar, user=person, view_name='+search-oci-project')
        browser.getControl(name="text").value = "find-me"
        browser.getControl("Search").click()

        # Check top message.
        main_portlet = find_tags_by_class(browser.contents, "main-portlet")[0]
        self.assertIn(
            'There are 2 OCI projects registered for %s matching "%s"' %
            (pillar.name, "find-me"),
            extract_text(main_portlet).replace("\n", " "))

        self.assertOCIProjectsArePresent(browser, oci_projects)
        self.assertOCIProjectsAreNotPresent(browser, other_oci_projects)
        self.assertPaginationIsPresent(browser, 2, 2)

    def test_oci_projects_with_search_keyword_for_distribution(self):
        self.check_oci_projects_with_search_keyword(
            self.factory.makeDistribution())

    def test_oci_projects_with_search_keyword_for_project(self):
        self.check_oci_projects_with_search_keyword(self.factory.makeProduct())

    def check_query_count_is_constant(self, pillar):
        batch_size = 3
        self.pushConfig("launchpad", default_batch_size=batch_size)

        person = self.factory.makePerson()
        distro = self.factory.makeDistribution(owner=person)
        name_pattern = "find-me-"

        def createOCIProject():
            self.factory.makeOCIProject(
                ociprojectname=self.factory.getUniqueString(name_pattern),
                pillar=distro)

        viewer = self.factory.makePerson()

        def getView():
            browser = self.getViewBrowser(
                distro, user=viewer, view_name='+search-oci-project')
            browser.getControl(name="text").value = name_pattern
            browser.getControl("Search").click()
            return browser

        def do_login():
            login_person(person)

        recorder1, recorder2 = record_two_runs(
            getView, createOCIProject, 1, 10, login_method=do_login)
        self.assertEqual(recorder1.count, recorder2.count)

    def test_query_count_is_constant_for_distribution(self):
        self.check_query_count_is_constant(self.factory.makeDistribution())

    def test_query_count_is_constant_for_project(self):
        self.check_query_count_is_constant(self.factory.makeProduct())
