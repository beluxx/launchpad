# Copyright 2009-2015 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from storm.store import Store
from testtools.matchers import Equals
from zope.component import getUtility
from zope.security.management import endInteraction
from zope.security.proxy import removeSecurityProxy

from lp.registry.interfaces.person import (
    IPersonSet,
    TeamMembershipStatus,
    )
from lp.registry.interfaces.teammembership import ITeamMembershipSet
from lp.services.identity.interfaces.account import AccountStatus
from lp.services.openid.model.openididentifier import OpenIdIdentifier
from lp.services.webapp.interfaces import OAuthPermission
from lp.testing import (
    admin_logged_in,
    api_url,
    launchpadlib_for,
    login,
    logout,
    record_two_runs,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.matchers import HasQueryCount
from lp.testing.pages import (
    LaunchpadWebServiceCaller,
    webservice_for_person,
    )


class TestPersonEmailSecurity(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestPersonEmailSecurity, self).setUp()
        self.target = self.factory.makePerson(name='target')
        self.email_one = self.factory.makeEmail(
                'test1@example.com', self.target)
        self.email_two = self.factory.makeEmail(
                'test2@example.com', self.target)

    def test_logged_in_can_access(self):
        # A logged in launchpadlib connection can see confirmed email
        # addresses.
        accessor = self.factory.makePerson()
        lp = launchpadlib_for("test", accessor.name)
        person = lp.people['target']
        emails = sorted(list(person.confirmed_email_addresses))
        self.assertNotEqual(
                sorted([self.email_one, self.email_two]),
                len(emails))

    def test_anonymous_cannot_access(self):
        # An anonymous launchpadlib connection cannot see email addresses.

        # Need to endInteraction() because launchpadlib_for() will
        # setup a new one.
        endInteraction()
        lp = launchpadlib_for('test', person=None, version='devel')
        person = lp.people['target']
        emails = list(person.confirmed_email_addresses)
        self.assertEqual([], emails)


class TestPersonAccountStatus(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_account_status_history_restricted(self):
        person = self.factory.makePerson()
        registrar = self.factory.makePerson(
            member_of=[getUtility(IPersonSet).getByName('registry')])
        removeSecurityProxy(person.account).status_history = u'Test'
        person_url = api_url(person)

        # A normal user cannot read account_status_history. Not even
        # their own.
        body = webservice_for_person(
                person, permission=OAuthPermission.WRITE_PRIVATE).get(
            person_url, api_version='devel').jsonBody()
        self.assertEqual('Active', body['account_status'])
        self.assertEqual(
            'tag:launchpad.net:2008:redacted', body['account_status_history'])

        # A member of ~registry can see it all.
        body = webservice_for_person(
                registrar, permission=OAuthPermission.WRITE_PRIVATE).get(
            person_url, api_version='devel').jsonBody()
        self.assertEqual('Active', body['account_status'])
        self.assertEqual('Test', body['account_status_history'])

    def test_setAccountStatus(self):
        person = self.factory.makePerson()
        registrar = self.factory.makePerson(
            name='registrar',
            member_of=[getUtility(IPersonSet).getByName('registry')])
        person_url = api_url(person)

        # A normal user cannot set even their own account status.
        webservice = webservice_for_person(
            person, permission=OAuthPermission.WRITE_PRIVATE)
        response = webservice.named_post(
            person_url, 'setAccountStatus', status='Suspended',
            comment='Go away', api_version='devel')
        self.assertEqual(401, response.status)

        # A member of ~registry can do what they wish.
        webservice = webservice_for_person(
            registrar, permission=OAuthPermission.WRITE_PRIVATE)
        response = webservice.named_post(
            person_url, 'setAccountStatus', status='Suspended',
            comment='Go away', api_version='devel')
        self.assertEqual(200, response.status)
        with admin_logged_in():
            self.assertEqual(AccountStatus.SUSPENDED, person.account_status)
            self.assertEndsWith(
                person.account_status_history,
                'registrar: Active -> Suspended: Go away\n')


class TestPersonRepresentation(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        login('guilherme.salgado@canonical.com ')
        self.person = self.factory.makePerson(
            name='test-person', displayname='Test Person')
        self.webservice = LaunchpadWebServiceCaller(
            'launchpad-library', 'salgado-change-anything')

    def test_GET_xhtml_representation(self):
        # Remove the security proxy because IPerson.name is protected.
        person_name = removeSecurityProxy(self.person).name
        response = self.webservice.get(
            '/~%s' % person_name, 'application/xhtml+xml')

        self.assertEqual(response.status, 200)

        rendered_comment = response.body
        self.assertEquals(
            rendered_comment,
            '<a href="/~test-person" class="sprite person">Test Person</a>')


class PersonWebServiceTests(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_deactivated_members_query_count(self):
        with admin_logged_in():
            team = self.factory.makeTeam()
            owner = team.teamowner
            name = team.name
        ws = webservice_for_person(owner)

        def create_member():
            with admin_logged_in():
                person = self.factory.makePerson()
                team.addMember(person, owner)
                getUtility(ITeamMembershipSet).getByPersonAndTeam(
                    person, team).setStatus(
                        TeamMembershipStatus.DEACTIVATED, owner, u"Go away.")

        def get_members():
            ws.get('/~%s/deactivated_members' % name).jsonBody()

        # Ensure that we're already in a stable cache state.
        get_members()
        recorder1, recorder2 = record_two_runs(
            get_members, create_member, 2)
        self.assertThat(recorder2, HasQueryCount(Equals(recorder1.count)))


class PersonSetWebServiceTests(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(PersonSetWebServiceTests, self).setUp()
        self.webservice = LaunchpadWebServiceCaller('test', None)
        logout()

    def assertReturnsPeople(self, expected_names, path):
        self.assertEqual(
            expected_names,
            [person['name'] for person in
             self.webservice.get(path).jsonBody()['entries']])

    def test_default_content(self):
        # /people lists the 50 people with the most karma, excluding
        # those with no karma at all.
        self.assertEqual(
            4, len(self.webservice.get('/people').jsonBody()['entries']))

    def test_find(self):
        # It's possible to find people by name.
        with admin_logged_in():
            person_name = self.factory.makePerson().name
        self.assertReturnsPeople(
            [person_name], '/people?ws.op=find&text=%s' % person_name)

    def test_findTeam(self):
        # The search can be restricted to teams.
        with admin_logged_in():
            person_name = self.factory.makePerson().name
            team_name = self.factory.makeTeam(
                name='%s-team' % person_name).name
        self.assertReturnsPeople(
            [team_name], '/people?ws.op=findTeam&text=%s' % person_name)

    def test_findTeam_query_count(self):
        with admin_logged_in():
            ws = webservice_for_person(self.factory.makePerson())

        def create_match():
            with admin_logged_in():
                self.factory.makeTeam(displayname='foobar')

        def find_teams():
            ws.named_get('/people', 'findTeam', text="foobar").jsonBody()

        # Ensure that we're already in a stable cache state.
        find_teams()
        recorder1, recorder2 = record_two_runs(
            find_teams, create_match, 2)
        self.assertThat(recorder2, HasQueryCount(Equals(recorder1.count)))

    def test_findPerson(self):
        # The search can be restricted to people.
        with admin_logged_in():
            person_name = self.factory.makePerson().name
            self.factory.makeTeam(name='%s-team' % person_name)
        self.assertReturnsPeople(
            [person_name], '/people?ws.op=findPerson&text=%s' % person_name)

    def test_find_by_date(self):
        # Creation date filtering is supported.
        self.assertReturnsPeople(
            [u'bac'],
            '/people?ws.op=findPerson&text='
            '&created_after=2008-06-27&created_before=2008-07-01')

    def test_getByEmail(self):
        # You can get a person by their email address.
        with admin_logged_in():
            person = self.factory.makePerson()
            person_name = person.name
            person_email = person.preferredemail.email
        self.assertEqual(
            person_name,
            self.webservice.get(
                '/people?ws.op=getByEmail&email=%s' % person_email
                ).jsonBody()['name'])

    def test_getByEmail_checks_format(self):
        # A malformed email address is rejected.
        e = self.assertRaises(
            ValueError,
            self.webservice.get(
                '/people?ws.op=getByEmail&email=foo@').jsonBody)
        # XXX wgrant bug=1088358: This escaping shouldn't be here; it's
        # not HTML.
        self.assertEqual("email: Invalid email &#x27;foo@&#x27;.", e[0])

    def test_getByOpenIDIdentifier(self):
        # You can get a person by their OpenID identifier URL.
        with admin_logged_in():
            person = self.factory.makePerson()
            person_name = person.name
            person_openid = person.account.openid_identifiers.one().identifier
        self.assertEqual(
            person_name,
            self.webservice.get(
                '/people?ws.op=getByOpenIDIdentifier&'
                'identifier=http://login1.dev/%%2Bid/%s'
                % person_openid,
                api_version='devel').jsonBody()['name'])

    def getOrCreateSoftwareCenterCustomer(self, user):
        webservice = webservice_for_person(
            user, permission=OAuthPermission.WRITE_PRIVATE)
        response = webservice.named_post(
            '/people', 'getOrCreateSoftwareCenterCustomer',
            openid_identifier='somebody',
            email_address='somebody@example.com', display_name='Somebody',
            api_version='devel')
        return response

    def test_getOrCreateSoftwareCenterCustomer(self):
        # Software Center Agent (SCA) can get or create people by OpenID
        # identifier.
        with admin_logged_in():
            sca = getUtility(IPersonSet).getByName('software-center-agent')
        response = self.getOrCreateSoftwareCenterCustomer(sca)
        self.assertEqual('Somebody', response.jsonBody()['display_name'])
        with admin_logged_in():
            person = getUtility(IPersonSet).getByEmail('somebody@example.com')
            self.assertEqual('Somebody', person.displayname)
            self.assertEqual(
                ['somebody'],
                [oid.identifier for oid in person.account.openid_identifiers])
            self.assertEqual(
                'somebody@example.com', person.preferredemail.email)

    def test_getOrCreateSoftwareCenterCustomer_is_restricted(self):
        # The method may only be invoked by the ~software-center-agent
        # celebrity user, as it is security-sensitive.
        with admin_logged_in():
            random = self.factory.makePerson()
        response = self.getOrCreateSoftwareCenterCustomer(random)
        self.assertEqual(401, response.status)

    def test_getOrCreateSoftwareCenterCustomer_rejects_email_conflicts(self):
        # An unknown OpenID identifier with a known email address causes
        # the request to fail with 409 Conflict, as we'd otherwise end
        # up linking the OpenID identifier to an existing account.
        with admin_logged_in():
            self.factory.makePerson(email='somebody@example.com')
            sca = getUtility(IPersonSet).getByName('software-center-agent')
        response = self.getOrCreateSoftwareCenterCustomer(sca)
        self.assertEqual(409, response.status)

    def test_getOrCreateSoftwareCenterCustomer_rejects_suspended(self):
        # Suspended accounts are not returned.
        with admin_logged_in():
            existing = self.factory.makePerson(
                email='somebody@example.com',
                account_status=AccountStatus.SUSPENDED)
            oid = OpenIdIdentifier()
            oid.account = existing.account
            oid.identifier = u'somebody'
            Store.of(existing).add(oid)
            sca = getUtility(IPersonSet).getByName('software-center-agent')
        response = self.getOrCreateSoftwareCenterCustomer(sca)
        self.assertEqual(400, response.status)
