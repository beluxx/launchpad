# Copyright 2019-2020 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `OCIProject` and `OCIProjectSet`."""

from __future__ import absolute_import, print_function, unicode_literals

__metaclass__ = type

import json

from six import string_types
from storm.store import Store
from testtools.matchers import (
    ContainsDict,
    Equals,
    )
from testtools.testcase import ExpectedException
from zope.component import getUtility
from zope.security.interfaces import Unauthorized
from zope.security.proxy import removeSecurityProxy

from lp.registry.interfaces.ociproject import (
    IOCIProject,
    IOCIProjectSet,
    )
from lp.registry.interfaces.ociprojectseries import IOCIProjectSeries
from lp.registry.model.ociproject import (
    OCI_PROJECT_ALLOW_CREATE,
    OCIProject,
    )
from lp.services.features.testing import FeatureFixture
from lp.services.macaroons.testing import MatchesStructure
from lp.services.webapp.interfaces import OAuthPermission
from lp.testing import (
    admin_logged_in,
    api_url,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.pages import webservice_for_person


class TestOCIProject(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_implements_interface(self):
        oci_project = self.factory.makeOCIProject()
        with admin_logged_in():
            self.assertProvides(oci_project, IOCIProject)

    def test_newSeries(self):
        driver = self.factory.makePerson()
        distribution = self.factory.makeDistribution(driver=driver)
        registrant = self.factory.makePerson()
        oci_project = self.factory.makeOCIProject(pillar=distribution)
        with person_logged_in(driver):
            series = oci_project.newSeries(
                'test-series',
                'test-summary',
                registrant)
            self.assertProvides(series, IOCIProjectSeries)

    def test_newSeries_bad_permissions(self):
        distribution = self.factory.makeDistribution()
        registrant = self.factory.makePerson()
        oci_project = self.factory.makeOCIProject(pillar=distribution)
        with ExpectedException(Unauthorized):
            oci_project.newSeries(
                'test-series',
                'test-summary',
                registrant)

    def test_series(self):
        driver = self.factory.makePerson()
        distribution = self.factory.makeDistribution(driver=driver)
        first_oci_project = self.factory.makeOCIProject(pillar=distribution)
        second_oci_project = self.factory.makeOCIProject(pillar=distribution)
        with person_logged_in(driver):
            first_series = self.factory.makeOCIProjectSeries(
                oci_project=first_oci_project)
            self.factory.makeOCIProjectSeries(
                oci_project=second_oci_project)
            self.assertContentEqual([first_series], first_oci_project.series)

    def test_name(self):
        oci_project_name = self.factory.makeOCIProjectName(name='test-name')
        oci_project = self.factory.makeOCIProject(
            ociprojectname=oci_project_name)
        self.assertEqual('test-name', oci_project.name)

    def test_display_name(self):
        oci_project_name = self.factory.makeOCIProjectName(name='test-name')
        oci_project = self.factory.makeOCIProject(
            ociprojectname=oci_project_name)
        self.assertEqual(
            'OCI project test-name for %s' % oci_project.pillar.display_name,
            oci_project.display_name)


class TestOCIProjectSet(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_implements_interface(self):
        target_set = getUtility(IOCIProjectSet)
        with admin_logged_in():
            self.assertProvides(target_set, IOCIProjectSet)

    def test_new_oci_project(self):
        registrant = self.factory.makePerson()
        distribution = self.factory.makeDistribution(owner=registrant)
        oci_project_name = self.factory.makeOCIProjectName()
        target = getUtility(IOCIProjectSet).new(
            registrant,
            distribution,
            oci_project_name)
        with person_logged_in(registrant):
            self.assertEqual(target.registrant, registrant)
            self.assertEqual(target.distribution, distribution)
            self.assertEqual(target.pillar, distribution)
            self.assertEqual(target.ociprojectname, oci_project_name)

    def test_getByDistributionAndName(self):
        registrant = self.factory.makePerson()
        distribution = self.factory.makeDistribution(owner=registrant)
        oci_project = self.factory.makeOCIProject(
            registrant=registrant, pillar=distribution)

        # Make sure there's more than one to get the result from
        self.factory.makeOCIProject(
            pillar=self.factory.makeDistribution())

        with person_logged_in(registrant):
            fetched_result = getUtility(
                IOCIProjectSet).getByDistributionAndName(
                    distribution, oci_project.ociprojectname.name)
            self.assertEqual(oci_project, fetched_result)


class TestOCIProjectWebservice(TestCaseWithFactory):
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestOCIProjectWebservice, self).setUp()
        self.person = self.factory.makePerson(displayname="Test Person")
        self.webservice = webservice_for_person(
            self.person, permission=OAuthPermission.WRITE_PUBLIC,
            default_api_version="devel")
        self.useFixture(FeatureFixture({OCI_PROJECT_ALLOW_CREATE: 'on'}))

    def getAbsoluteURL(self, target):
        """Get the webservice absolute URL of the given object or relative
        path."""
        if not isinstance(target, string_types):
            target = api_url(target)
        return self.webservice.getAbsoluteUrl(target)

    def load_from_api(self, url):
        response = self.webservice.get(url)
        self.assertEqual(200, response.status, response.body)
        return response.jsonBody()

    def test_api_get_oci_project(self):
        with person_logged_in(self.person):
            person = removeSecurityProxy(self.person)
            project = removeSecurityProxy(self.factory.makeOCIProject(
                registrant=self.person))
            self.factory.makeOCIProjectSeries(
                oci_project=project, registrant=self.person)
            url = api_url(project)

        ws_project = self.load_from_api(url)

        series_url = "{project_path}/series".format(
            project_path=self.getAbsoluteURL(project))

        self.assertThat(ws_project, ContainsDict(dict(
            date_created=Equals(project.date_created.isoformat()),
            date_last_modified=Equals(project.date_last_modified.isoformat()),
            display_name=Equals(project.display_name),
            registrant_link=Equals(self.getAbsoluteURL(person)),
            series_collection_link=Equals(series_url)
            )))

    def test_api_save_oci_project(self):
        with person_logged_in(self.person):
            # Only the owner of the distribution (which is the pillar of the
            # OCIProject) is allowed to update its attributes.
            distro = self.factory.makeDistribution(owner=self.person)
            project = removeSecurityProxy(self.factory.makeOCIProject(
                registrant=self.person, pillar=distro))
            url = api_url(project)

        new_description = 'Some other description'
        resp = self.webservice.patch(
            url, 'application/json',
            json.dumps({'description': new_description}))
        self.assertEqual(209, resp.status, resp.body)

        ws_project = self.load_from_api(url)
        self.assertEqual(new_description, ws_project['description'])

    def test_api_save_oci_project_prevents_updates_from_others(self):
        with admin_logged_in():
            other_person = self.factory.makePerson()
        with person_logged_in(other_person):
            # Only the owner of the distribution (which is the pillar of the
            # OCIProject) is allowed to update its attributes.
            distro = self.factory.makeDistribution(owner=other_person)
            project = removeSecurityProxy(self.factory.makeOCIProject(
                registrant=other_person, pillar=distro,
                description="old description"))
            url = api_url(project)

        new_description = 'Some other description'
        resp = self.webservice.patch(
            url, 'application/json',
            json.dumps({'description': new_description}))
        self.assertEqual(401, resp.status, resp.body)

        ws_project = self.load_from_api(url)
        self.assertEqual("old description", ws_project['description'])

    def test_create_oci_project(self):
        with person_logged_in(self.person):
            distro = removeSecurityProxy(self.factory.makeDistribution(
                owner=self.person))
            url = api_url(distro)

        obj = {
            "ociprojectname": "someprojectname",
            "description": "My OCI project",
            "bug_reporting_guidelines": "Bug reporting guide",
            "bug_reported_acknowledgement": "Bug reporting ack",
            "bugfiling_duplicate_search": True,
        }
        resp = self.webservice.named_post(url, "newOCIProject", **obj)
        self.assertEqual(201, resp.status, resp.body)

        store = Store.of(distro)
        result_set = [i for i in store.find(OCIProject)]

        self.assertEqual(1, len(result_set))
        self.assertThat(result_set[0], MatchesStructure(
            ociprojectname=MatchesStructure(
                name=Equals(obj["ociprojectname"])),
            description=Equals(obj["description"]),
            bug_reporting_guidelines=Equals(obj["bug_reporting_guidelines"]),
            bug_reported_acknowledgement=Equals(
                obj["bug_reported_acknowledgement"]),
            enable_bugfiling_duplicate_search=Equals(
                obj["bugfiling_duplicate_search"])
            ))

    def test_api_create_oci_project_is_disabled_by_feature_flag(self):
        self.useFixture(FeatureFixture({OCI_PROJECT_ALLOW_CREATE: ''}))
        with person_logged_in(self.person):
            distro = removeSecurityProxy(self.factory.makeDistribution(
                owner=self.person))
            url = api_url(distro)

        obj = {
            "ociprojectname": "someprojectname",
            "description": "My OCI project",
            "bug_reporting_guidelines": "Bug reporting guide",
            "bug_reported_acknowledgement": "Bug reporting ack",
            "bugfiling_duplicate_search": True,
        }
        resp = self.webservice.named_post(url, "newOCIProject", **obj)
        self.assertEqual(401, resp.status, resp.body)
