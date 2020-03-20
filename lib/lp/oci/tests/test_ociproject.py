# Copyright 2020 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests OCI project."""

from __future__ import absolute_import, print_function, unicode_literals

import json

from testtools.matchers import (
    ContainsDict,
    Equals,
    )
from zope.security.proxy import removeSecurityProxy

from lp.services.webapp.interfaces import OAuthPermission
from lp.services.webhooks.testing import StartsWith
from lp.testing import (
    admin_logged_in,
    api_url,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.pages import webservice_for_person


class TestOCIProjectWebservice(TestCaseWithFactory):
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestOCIProjectWebservice, self).setUp()
        self.person = self.factory.makePerson(displayname="Test Person")
        self.webservice = webservice_for_person(
            self.person, permission=OAuthPermission.WRITE_PUBLIC,
            default_api_version="devel")

    def load_from_api(self, url):
        response = self.webservice.get(url)
        self.assertEqual(200, response.status, response.body)
        return response.jsonBody()

    def test_api_get_oci_project(self):
        with person_logged_in(self.person):
            project = removeSecurityProxy(self.factory.makeOCIProject(
                registrant=self.person))
            self.factory.makeOCIProjectSeries(
                oci_project=project, registrant=self.person)
            url = api_url(project)

        ws_project = self.load_from_api(url)

        self.assertThat(ws_project, ContainsDict(dict(
            date_created=Equals(project.date_created.isoformat()),
            date_last_modified=Equals(project.date_last_modified.isoformat()),
            display_name=Equals(project.display_name),
            registrant_link=StartsWith("http"),
            series_collection_link=StartsWith("http"))
            ))

    def test_api_save_oci_project(self):
        with person_logged_in(self.person):
            # Only the owner of the distribution (which is the pillar of the
            # OCIProject) is allowed to update it's attributed.
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
            # OCIProject) is allowed to update it's attributed.
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
