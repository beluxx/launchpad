# Copyright 2009-2017 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from lp.registry.scripts import listteammembers
from lp.testing import TestCaseWithFactory
from lp.testing.layers import LaunchpadZopelessLayer


ubuntuteam_default = sorted([
    u'cprov, celso.providelo@canonical.com',
    u'edgar, edgar@monteparadiso.hr',
    u'jdub, jeff.waugh@ubuntulinux.com',
    u'kamion, colin.watson@ubuntulinux.com',
    u'kinnison, daniel.silverstone@canonical.com',
    u'limi, limi@plone.org',
    u'name16, foo.bar@canonical.com',
    u'mark, mark@example.com',
    u'stevea, steve.alexander@ubuntulinux.com',
    u'warty-gnome, --none--',
    ])

ubuntuteam_email = sorted([
    u'admin@canonical.com',
    u'celso.providelo@canonical.com',
    u'colin.watson@ubuntulinux.com',
    u'cprov@ubuntu.com',
    u'daniel.silverstone@canonical.com',
    u'edgar@monteparadiso.hr',
    u'foo.bar@canonical.com',
    u'jeff.waugh@ubuntulinux.com',
    u'limi@plone.org',
    u'mark@example.com',
    u'steve.alexander@ubuntulinux.com',
    ])

ubuntuteam_full = sorted([
    u'ubuntu-team|10|limi|limi@plone.org|Alexander Limi|no',
    u'ubuntu-team|11|stevea|steve.alexander@ubuntulinux.com'
        u'|Steve Alexander|no',
    u'ubuntu-team|16|name16|foo.bar@canonical.com|Foo Bar|yes',
    u'ubuntu-team|19|warty-gnome|--none--|Warty Gnome Team|no',
    u'ubuntu-team|1|mark|mark@example.com|Mark Shuttleworth|no',
    u'ubuntu-team|26|kinnison|daniel.silverstone@canonical.com'
        u'|Daniel Silverstone|no',
    u'ubuntu-team|28|cprov|celso.providelo@canonical.com|Celso Providelo|no',
    u'ubuntu-team|33|edgar|edgar@monteparadiso.hr|Edgar Bursic|no',
    u'ubuntu-team|4|kamion|colin.watson@ubuntulinux.com|Colin Watson|no',
    u'ubuntu-team|6|jdub|jeff.waugh@ubuntulinux.com|Jeff Waugh|no',
    ])

ubuntuteam_sshkeys = [
    u'mark: ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAAgQCeP6iOLFdRSJ/CwuUjj0dE3+bJi'
    u'ZUn2AsappUcjCZN75CBKvqPkpGDIU/ZlOddAdj1rif6dl9rqEBuoliduIZ1bmPaGs1jmpME'
    u'7HPctLhCmzy1oC8wkdVNkZnmoTW34j5Y8mKWuy32hVWvp3OdfIo+dxW576ny52VkTbST+t4'
    u'KlQ== Private key in lib/lp/codehosting/tests/id_rsa',
    ]


class ListTeamMembersTestCase(TestCaseWithFactory):
    """Test listing team members."""
    layer = LaunchpadZopelessLayer

    def test_listteammembers_default_list(self):
        """Test the default option."""
        self.assertEqual(
            ubuntuteam_default, listteammembers.process_team('ubuntu-team'))

    def test_listteammembers_email_only(self):
        """Test the email only option."""
        self.assertEqual(
            ubuntuteam_email,
            listteammembers.process_team('ubuntu-team', 'email'))

    def test_listteammembers_full_details(self):
        """Test the full details option."""
        self.assertEqual(
            ubuntuteam_full,
            listteammembers.process_team('ubuntu-team', 'full'))

    def test_listteammembers_sshkeys(self):
        """Test the ssh keys option."""
        self.assertEqual(
            ubuntuteam_sshkeys,
            listteammembers.process_team('ubuntu-team', 'sshkeys'))

    def test_make_sshkey_params(self):
        """Test that ssh keys are rendered as a single line."""
        member = self.factory.makePerson(name='biggles')
        team = self.factory.makeTeam(name='squadron')
        team.addMember(member, reviewer=team.teamowner)
        sshkey = self.factory.makeSSHKey(member)
        sshkey.keytext = u'123badKeysMight\r\nContain\fBadCharacters'
        sshkey.comment = 'co\rmm\ne\f\fnt'
        expected = dict(
            name=u'biggles',
            sshkey=u'ssh-rsa 123badKeysMightContainBadCharacters comment')
        result = listteammembers.make_sshkey_params(member, sshkey)
        self.assertEqual(expected, result)

    def test_listteammembers_unknown_team(self):
        """Test unknown team."""
        self.assertRaises(
            listteammembers.NoSuchTeamError, listteammembers.process_team,
            'nosuchteam-matey')
