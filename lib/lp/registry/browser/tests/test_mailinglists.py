
# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from __future__ import with_statement

"""Test harness for mailinglist views unit tests."""

__metaclass__ = type


from canonical.testing.layers import DatabaseFunctionalLayer
from canonical.launchpad.ftests import login_person
from lp.testing import TestCaseWithFactory, person_logged_in
from lp.testing.views import create_view


class MailingListSubscriptionControlsTestCase(TestCaseWithFactory):
    """Tests to ensure the rendering of subscribe and unsubscribe
    controls on the team page."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(MailingListSubscriptionControlsTestCase, self).setUp()
        self.a_team = self.factory.makeTeam(name='a')
        self.b_team = self.factory.makeTeam(name='b', owner=self.a_team)
        self.b_team_list = self.factory.makeMailingList(team=self.b_team,
            owner=self.b_team.teamowner)
        self.user = self.factory.makePerson()
        with person_logged_in(self.a_team.teamowner):
            self.a_team.addMember(self.user, self.a_team.teamowner)

    def test_subscribe_control_renders(self):
        login_person(self.user)
        view = create_view(self.b_team, name='+index',
            principal=self.user, server_url='http://launchpad.dev',
            path_info='/~%s' % self.b_team.name)
        content = view.render()
        self.assertTrue('id="link.list.subscribe"' in content)

    def test_subscribe_control_doesnt_render_for_anon(self):
        other_person = self.factory.makePerson()
        login_person(other_person)
        view = create_view(self.b_team, name='+index',
            principal=other_person, server_url='http://launchpad.dev',
            path_info='/~%s' % self.b_team.name)
        content = view.render()
        self.assertNotEqual('', content)
        self.assertFalse('id="link.list.subscribe"' in content)
