# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from datetime import datetime

import pytz

from storm.store import Store

from testtools.matchers import (
    Equals,
    LessThan,
    )

from zope.component import getUtility
from zope.interface import providedBy
from zope.security.interfaces import Unauthorized
from zope.security.proxy import removeSecurityProxy

from lazr.lifecycle.snapshot import Snapshot

from lp.answers.model.answercontact import AnswerContact
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.blueprints.model.specification import Specification
from lp.bugs.interfaces.bugtask import IllegalRelatedBugTasksParams
from lp.bugs.model.bug import Bug
from lp.bugs.model.bugtask import get_related_bugtasks_search_params
from lp.registry.errors import (
    PrivatePersonLinkageError,
    )
from lp.registry.interfaces.karma import IKarmaCacheManager
from lp.registry.interfaces.person import (
    ImmutableVisibilityError,
    IPersonSet,
    PersonVisibility,
    )
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.registry.interfaces.product import IProductSet
from lp.registry.model.karma import (
    KarmaCategory,
    KarmaTotalCache,
    )
from lp.registry.model.person import (
    get_recipients,
    Person,
    )
from lp.services.identity.interfaces.account import (
    AccountStatus,
    )
from lp.services.identity.interfaces.emailaddress import (
    EmailAddressStatus,
    )
from lp.services.propertycache import clear_property_cache
from lp.soyuz.enums import (
    ArchivePurpose,
    )
from lp.testing import (
    celebrity_logged_in,
    login,
    login_person,
    logout,
    person_logged_in,
    StormStatementRecorder,
    TestCaseWithFactory,
    )
from lp.testing._webservice import QueryCollector
from lp.testing.dbuser import dbuser
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.matchers import HasQueryCount
from lp.testing.pages import LaunchpadWebServiceCaller
from lp.testing.views import create_initialized_view


class TestPersonTeams(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestPersonTeams, self).setUp()
        self.user = self.factory.makePerson(name="test-member")
        self.a_team = self.factory.makeTeam(name='a')
        self.b_team = self.factory.makeTeam(name='b', owner=self.a_team)
        self.c_team = self.factory.makeTeam(name='c', owner=self.b_team)
        login_person(self.a_team.teamowner)
        self.a_team.addMember(self.user, self.a_team.teamowner)

    def test_teams_indirectly_participated_in(self):
        indirect_teams = self.user.teams_indirectly_participated_in
        expected_teams = [self.b_team, self.c_team]
        test_teams = sorted(indirect_teams,
            key=lambda team: team.displayname)
        self.assertEqual(expected_teams, test_teams)

    def test_team_memberships(self):
        memberships = self.user.team_memberships
        memberships = [(m.person, m.team) for m in memberships]
        self.assertEqual([(self.user, self.a_team)], memberships)

    def test_path_to_team(self):
        path_to_a = self.user.findPathToTeam(self.a_team)
        path_to_b = self.user.findPathToTeam(self.b_team)
        path_to_c = self.user.findPathToTeam(self.c_team)

        self.assertEqual([self.a_team], path_to_a)
        self.assertEqual([self.a_team, self.b_team], path_to_b)
        self.assertEqual([self.a_team, self.b_team, self.c_team], path_to_c)

    def test_teams_participated_in(self):
        teams = self.user.teams_participated_in
        teams = sorted(list(teams), key=lambda x: x.displayname)
        expected_teams = [self.a_team, self.b_team, self.c_team]
        self.assertEqual(expected_teams, teams)

    def test_getPathsToTeams(self):
        paths, memberships = self.user.getPathsToTeams()
        expected_paths = {self.a_team: [self.a_team, self.user],
            self.b_team: [self.b_team, self.a_team, self.user],
            self.c_team: [self.c_team, self.b_team, self.a_team, self.user]}
        self.assertEqual(expected_paths, paths)

        expected_memberships = [(self.a_team, self.user)]
        memberships = [
            (membership.team, membership.person) for membership
            in memberships]
        self.assertEqual(expected_memberships, memberships)

    def test_getPathsToTeams_complicated(self):
        d_team = self.factory.makeTeam(name='d', owner=self.b_team)
        e_team = self.factory.makeTeam(name='e')
        f_team = self.factory.makeTeam(name='f', owner=e_team)
        self.factory.makeTeam(name='unrelated')
        login_person(self.a_team.teamowner)
        d_team.addMember(self.user, d_team.teamowner)
        login_person(e_team.teamowner)
        e_team.addMember(self.user, e_team.teamowner)

        paths, memberships = self.user.getPathsToTeams()
        expected_paths = {
            self.a_team: [self.a_team, self.user],
            self.b_team: [self.b_team, self.a_team, self.user],
            self.c_team: [self.c_team, self.b_team, self.a_team, self.user],
            d_team: [d_team, self.b_team, self.a_team, self.user],
            e_team: [e_team, self.user],
            f_team: [f_team, e_team, self.user]}
        self.assertEqual(expected_paths, paths)

        expected_memberships = [
            (e_team, self.user),
            (d_team, self.user),
            (self.a_team, self.user),
            ]
        memberships = [
            (membership.team, membership.person) for membership
            in memberships]
        self.assertEqual(expected_memberships, memberships)

    def test_getPathsToTeams_multiple_paths(self):
        d_team = self.factory.makeTeam(name='d', owner=self.b_team)
        login_person(self.a_team.teamowner)
        self.c_team.addMember(d_team, self.c_team.teamowner)

        paths, memberships = self.user.getPathsToTeams()
        # getPathsToTeams should not randomly pick one path or another
        # when multiples exist; it sorts to use the oldest path, so
        # the expected paths below should be the returned result.
        expected_paths = {
            self.a_team: [self.a_team, self.user],
            self.b_team: [self.b_team, self.a_team, self.user],
            self.c_team: [self.c_team, self.b_team, self.a_team, self.user],
            d_team: [d_team, self.b_team, self.a_team, self.user]}
        self.assertEqual(expected_paths, paths)

        expected_memberships = [(self.a_team, self.user)]
        memberships = [
            (membership.team, membership.person) for membership
            in memberships]
        self.assertEqual(expected_memberships, memberships)

    def test_inTeam_direct_team(self):
        # Verify direct membeship is True and the cache is populated.
        self.assertTrue(self.user.inTeam(self.a_team))
        self.assertEqual(
            {self.a_team.id: True},
            removeSecurityProxy(self.user)._inTeam_cache)

    def test_inTeam_indirect_team(self):
        # Verify indirect membeship is True and the cache is populated.
        self.assertTrue(self.user.inTeam(self.b_team))
        self.assertEqual(
            {self.b_team.id: True},
            removeSecurityProxy(self.user)._inTeam_cache)

    def test_inTeam_cache_cleared_by_membership_change(self):
        # Verify a change in membership clears the team cache.
        self.user.inTeam(self.a_team)
        with person_logged_in(self.b_team.teamowner):
            self.b_team.addMember(self.user, self.b_team.teamowner)
        self.assertEqual(
            {},
            removeSecurityProxy(self.user)._inTeam_cache)

    def test_inTeam_person_is_false(self):
        # Verify a user cannot be a member of another user.
        other_user = self.factory.makePerson()
        self.assertFalse(self.user.inTeam(other_user))

    def test_inTeam_person_does_not_build_TeamParticipation_cache(self):
        # Verify when a user is the argument, a DB call to TeamParticipation
        # was not made to learn this.
        other_user = self.factory.makePerson()
        Store.of(self.user).invalidate()
        # Load the two person objects only by reading a non-id attribute
        # unrelated to team/person or teamparticipation.
        other_user.name
        self.user.name
        self.assertFalse(
            self.assertStatementCount(0, self.user.inTeam, other_user))
        self.assertEqual(
            {},
            removeSecurityProxy(self.user)._inTeam_cache)

    def test_inTeam_person_string_missing_team(self):
        # If a check against a string is done, the team lookup is implicit:
        # treat a missing team as an empty team so that any pages that choose
        # to do this don't blow up unnecessarily. Similarly feature flags
        # team: scopes depend on this.
        self.assertFalse(self.user.inTeam('does-not-exist'))

    def test_inTeam_person_incorrect_archive(self):
        # If a person has an archive marked incorrectly that person should
        # still be retrieved by 'all_members_prepopulated'.  See bug #680461.
        self.factory.makeArchive(
            owner=self.user, purpose=ArchivePurpose.PARTNER)
        expected_members = sorted([self.user, self.a_team.teamowner])
        retrieved_members = sorted(list(self.a_team.all_members_prepopulated))
        self.assertEqual(expected_members, retrieved_members)

    def test_inTeam_person_no_archive(self):
        # If a person has no archive that person should still be retrieved by
        # 'all_members_prepopulated'.
        expected_members = sorted([self.user, self.a_team.teamowner])
        retrieved_members = sorted(list(self.a_team.all_members_prepopulated))
        self.assertEqual(expected_members, retrieved_members)

    def test_inTeam_person_ppa_archive(self):
        # If a person has a PPA that person should still be retrieved by
        # 'all_members_prepopulated'.
        self.factory.makeArchive(
            owner=self.user, purpose=ArchivePurpose.PPA)
        expected_members = sorted([self.user, self.a_team.teamowner])
        retrieved_members = sorted(list(self.a_team.all_members_prepopulated))
        self.assertEqual(expected_members, retrieved_members)

    def test_administrated_teams(self):
        # The property Person.administrated_teams is a cached copy of
        # the result of Person.getAdministratedTeams().
        expected = [self.b_team, self.c_team]
        self.assertEqual(expected, list(self.user.getAdministratedTeams()))
        with StormStatementRecorder() as recorder:
            self.assertEqual(expected, self.user.administrated_teams)
            self.user.administrated_teams
        # The second access of administrated_teams did not require an
        # SQL query, hence the total number of SQL queries is 1.
        self.assertEqual(1, len(recorder.queries))


class TestPerson(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_getOwnedOrDrivenPillars(self):
        user = self.factory.makePerson()
        active_project = self.factory.makeProject(owner=user)
        inactive_project = self.factory.makeProject(owner=user)
        with celebrity_logged_in('admin'):
            inactive_project.active = False
        expected_pillars = [active_project.name]
        received_pillars = [pillar.name for pillar in
            user.getOwnedOrDrivenPillars()]
        self.assertEqual(expected_pillars, received_pillars)

    def test_no_merge_pending(self):
        # is_merge_pending returns False when this person is not the "from"
        # person of an active merge job.
        person = self.factory.makePerson()
        self.assertFalse(person.is_merge_pending)

    def test_is_merge_pending(self):
        # is_merge_pending returns True when this person is being merged with
        # another person in an active merge job.
        from_person = self.factory.makePerson()
        to_person = self.factory.makePerson()
        getUtility(IPersonSet).mergeAsync(from_person, to_person)
        self.assertTrue(from_person.is_merge_pending)
        self.assertFalse(to_person.is_merge_pending)

    def test_mergeAsync_success(self):
        # mergeAsync returns a job with the from and to persons.
        from_person = self.factory.makePerson()
        to_person = self.factory.makePerson()
        job = getUtility(IPersonSet).mergeAsync(from_person, to_person)
        self.assertEqual(from_person, job.from_person)
        self.assertEqual(to_person, job.to_person)

    def test_selfgenerated_bugnotifications_none_by_default(self):
        # Default for new accounts is to not get any
        # self-generated bug notifications by default.
        user = self.factory.makePerson()
        self.assertFalse(user.selfgenerated_bugnotifications)

    def test_canAccess__anonymous(self):
        # Anonymous users cannot call Person.canAccess()
        person = self.factory.makePerson()
        self.assertRaises(Unauthorized, getattr, person, 'canAccess')

    def test_canAccess__checking_own_permissions(self):
        # Logged in users can call Person.canAccess() on their own
        # Person object.
        person = self.factory.makePerson()
        product = self.factory.makeProduct()
        with person_logged_in(person):
            self.assertTrue(person.canAccess(product, 'licenses'))
            self.assertFalse(person.canAccess(product, 'newSeries'))

    def test_canAccess__checking_permissions_of_others(self):
        # Logged in users cannot call Person.canAccess() on Person
        # object for other people.
        person = self.factory.makePerson()
        other = self.factory.makePerson()
        with person_logged_in(person):
            self.assertRaises(Unauthorized, getattr, other, 'canAccess')

    def test_canWrite__anonymous(self):
        # Anonymous users cannot call Person.canWrite()
        person = self.factory.makePerson()
        self.assertRaises(Unauthorized, getattr, person, 'canWrite')

    def test_canWrite__checking_own_permissions(self):
        # Logged in users can call Person.canWrite() on their own
        # Person object.
        person = self.factory.makePerson()
        product = self.factory.makeProduct()
        with person_logged_in(person):
            self.assertFalse(person.canWrite(product, 'displayname'))
        with person_logged_in(product.owner):
            self.assertTrue(product.owner.canWrite(product, 'displayname'))

    def test_canWrite__checking_permissions_of_others(self):
        # Logged in users cannot call Person.canWrite() on Person
        # object for other people.
        person = self.factory.makePerson()
        other = self.factory.makePerson()
        with person_logged_in(person):
            self.assertRaises(Unauthorized, getattr, other, 'canWrite')

    def makeSubscribedDistroSourcePackages(self):
        # Create a person, a distribution and four
        # DistributionSourcePacakage. Subscribe the person to two
        # DSPs, and subscribe another person to another DSP.
        user = self.factory.makePerson()
        distribution = self.factory.makeDistribution()
        dsp1 = self.factory.makeDistributionSourcePackage(
            sourcepackagename='sp-b', distribution=distribution)
        distribution = self.factory.makeDistribution()
        dsp2 = self.factory.makeDistributionSourcePackage(
            sourcepackagename='sp-a', distribution=distribution)
        # We don't reference dsp3 so it gets no name:
        self.factory.makeDistributionSourcePackage(
            sourcepackagename='sp-c', distribution=distribution)
        with person_logged_in(user):
            dsp1.addSubscription(user, subscribed_by=user)
            dsp2.addSubscription(user, subscribed_by=user)
        dsp4 = self.factory.makeDistributionSourcePackage(
            sourcepackagename='sp-d', distribution=distribution)
        other_user = self.factory.makePerson()
        with person_logged_in(other_user):
            dsp4.addSubscription(other_user, subscribed_by=other_user)
        return user, dsp1, dsp2

    def test_getBugSubscriberPackages(self):
        # getBugSubscriberPackages() returns the DistributionSourcePackages
        # to which a user is subscribed.
        user, dsp1, dsp2 = self.makeSubscribedDistroSourcePackages()

        # We cannot directly compare the objects returned by
        # getBugSubscriberPackages() with the expected DSPs:
        # These are different objects and the class does not have
        # an __eq__ operator. So we compare the attributes distribution
        # and sourcepackagename.

        def get_distribution(dsp):
            return dsp.distribution

        def get_spn(dsp):
            return dsp.sourcepackagename

        result = user.getBugSubscriberPackages()
        self.assertEqual(
            [get_distribution(dsp) for dsp in (dsp2, dsp1)],
            [get_distribution(dsp) for dsp in result])
        self.assertEqual(
            [get_spn(dsp) for dsp in (dsp2, dsp1)],
            [get_spn(dsp) for dsp in result])

    def test_getBugSubscriberPackages__one_query(self):
        # getBugSubscriberPackages() retrieves all objects
        # needed to build the DistributionSourcePackages in
        # one SQL query.
        user, dsp1, dsp2 = self.makeSubscribedDistroSourcePackages()
        Store.of(user).invalidate()
        with StormStatementRecorder() as recorder:
            list(user.getBugSubscriberPackages())
        self.assertThat(recorder, HasQueryCount(Equals(1)))

    def createCopiedPackage(self, spph, copier, dest_distroseries=None,
                            dest_archive=None):
        if dest_distroseries is None:
            dest_distroseries = self.factory.makeDistroSeries()
        if dest_archive is None:
            dest_archive = dest_distroseries.main_archive
        return spph.copyTo(
            dest_distroseries, creator=copier,
            pocket=PackagePublishingPocket.UPDATES,
            archive=dest_archive)

    def test_getLatestSynchronisedPublishings_most_recent_first(self):
        # getLatestSynchronisedPublishings returns the latest copies sorted
        # by most recent first.
        spph = self.factory.makeSourcePackagePublishingHistory()
        copier = self.factory.makePerson()
        copied_spph1 = self.createCopiedPackage(spph, copier)
        copied_spph2 = self.createCopiedPackage(spph, copier)
        synchronised_spphs = copier.getLatestSynchronisedPublishings()

        self.assertContentEqual(
            [copied_spph2, copied_spph1],
            synchronised_spphs)

    def test_getLatestSynchronisedPublishings_other_creator(self):
        spph = self.factory.makeSourcePackagePublishingHistory()
        copier = self.factory.makePerson()
        self.createCopiedPackage(spph, copier)
        someone_else = self.factory.makePerson()
        synchronised_spphs = someone_else.getLatestSynchronisedPublishings()

        self.assertEqual(
            0,
            synchronised_spphs.count())

    def test_getLatestSynchronisedPublishings_latest(self):
        # getLatestSynchronisedPublishings returns only the latest copy of
        # a package in a distroseries
        spph = self.factory.makeSourcePackagePublishingHistory()
        copier = self.factory.makePerson()
        dest_distroseries = self.factory.makeDistroSeries()
        self.createCopiedPackage(
            spph, copier, dest_distroseries)
        copied_spph2 = self.createCopiedPackage(
            spph, copier, dest_distroseries)
        synchronised_spphs = copier.getLatestSynchronisedPublishings()

        self.assertContentEqual(
            [copied_spph2],
            synchronised_spphs)

    def test_getLatestSynchronisedPublishings_cross_archive_copies(self):
        # getLatestSynchronisedPublishings returns only the copies copied
        # cross archive.
        spph = self.factory.makeSourcePackagePublishingHistory()
        copier = self.factory.makePerson()
        dest_distroseries2 = self.factory.makeDistroSeries(
            distribution=spph.distroseries.distribution)
        self.createCopiedPackage(
            spph, copier, dest_distroseries2)
        synchronised_spphs = copier.getLatestSynchronisedPublishings()

        self.assertEqual(
            0,
            synchronised_spphs.count())

    def test_getLatestSynchronisedPublishings_main_archive(self):
        # getLatestSynchronisedPublishings returns only the copies copied in
        # a primary archive (as opposed to a ppa).
        spph = self.factory.makeSourcePackagePublishingHistory()
        copier = self.factory.makePerson()
        dest_distroseries = self.factory.makeDistroSeries()
        ppa = self.factory.makeArchive(
            distribution=dest_distroseries.distribution)
        self.createCopiedPackage(
            spph, copier, dest_distroseries, ppa)
        synchronised_spphs = copier.getLatestSynchronisedPublishings()

        self.assertEqual(
            0,
            synchronised_spphs.count())

    def test_product_isAnyPillarOwner(self):
        # Test isAnyPillarOwner for products
        person = self.factory.makePerson()
        owner = self.factory.makePerson()
        self.factory.makeProduct(owner=owner)
        self.assertTrue(owner.isAnyPillarOwner())
        self.assertFalse(person.isAnyPillarOwner())

    def test_projectgroup_isAnyPillarOwner(self):
        # Test isAnyPillarOwner for project groups
        person = self.factory.makePerson()
        owner = self.factory.makePerson()
        self.factory.makeProject(owner=owner)
        self.assertTrue(owner.isAnyPillarOwner())
        self.assertFalse(person.isAnyPillarOwner())

    def test_distribution_isAnyPillarOwner(self):
        # Test isAnyPillarOwner for distributions
        person = self.factory.makePerson()
        owner = self.factory.makePerson()
        self.factory.makeDistribution(owner=owner)
        self.assertTrue(owner.isAnyPillarOwner())
        self.assertFalse(person.isAnyPillarOwner())

    def test_product_isAnySecurityContact(self):
        # Test isAnySecurityContact for products
        person = self.factory.makePerson()
        contact = self.factory.makePerson()
        self.factory.makeProduct(security_contact=contact)
        self.assertTrue(contact.isAnySecurityContact())
        self.assertFalse(person.isAnySecurityContact())

    def test_distribution_isAnySecurityContact(self):
        # Test isAnySecurityContact for distributions
        person = self.factory.makePerson()
        contact = self.factory.makePerson()
        self.factory.makeDistribution(security_contact=contact)
        self.assertTrue(contact.isAnySecurityContact())
        self.assertFalse(person.isAnySecurityContact())


class TestPersonStates(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self, 'foo.bar@canonical.com')
        person_set = getUtility(IPersonSet)
        self.myteam = person_set.getByName('myteam')
        self.otherteam = person_set.getByName('otherteam')
        self.guadamen = person_set.getByName('guadamen')
        product_set = getUtility(IProductSet)
        self.bzr = product_set.getByName('bzr')
        self.now = datetime.now(pytz.UTC)

    def test_deactivateAccount_copes_with_names_already_in_use(self):
        """When a user deactivates his account, its name is changed.

        We do that so that other users can use that name, which the original
        user doesn't seem to want anymore.

        It may happen that we attempt to rename an account to something that
        is already in use. If this happens, we'll simply append an integer to
        that name until we can find one that is free.
        """
        sample_person = Person.byName('name12')
        login(sample_person.preferredemail.email)
        sample_person.deactivateAccount("blah!")
        self.failUnlessEqual(sample_person.name, 'name12-deactivatedaccount')
        # Now that name12 is free Foo Bar can use it.
        foo_bar = Person.byName('name16')
        foo_bar.name = 'name12'
        # If Foo Bar deactivates his account, though, we'll have to use a name
        # other than name12-deactivatedaccount because that is already in use.
        login(foo_bar.preferredemail.email)
        foo_bar.deactivateAccount("blah!")
        self.failUnlessEqual(foo_bar.name, 'name12-deactivatedaccount1')

    def test_deactivateAccountReassignsOwnerAndDriver(self):
        """Product owner and driver are reassigned.

        If a user is a product owner and/or driver, when the user is
        deactivated the roles are assigned to the registry experts team.  Note
        a person can have both roles and the method must handle both at once,
        that's why this is one test.
        """
        user = self.factory.makePerson()
        product = self.factory.makeProduct(owner=user)
        with person_logged_in(user):
            product.driver = user
            user.deactivateAccount("Going off the grid.")
        registry_team = getUtility(ILaunchpadCelebrities).registry_experts
        self.assertEqual(registry_team, product.owner,
                         "Owner is not registry team.")
        self.assertEqual(registry_team, product.driver,
                         "Driver is not registry team.")

    def test_getDirectMemberIParticipateIn(self):
        sample_person = Person.byName('name12')
        warty_team = Person.byName('name20')
        ubuntu_team = Person.byName('ubuntu-team')
        # Sample Person is an active member of Warty Security Team which in
        # turn is a proposed member of Ubuntu Team. That means
        # sample_person._getDirectMemberIParticipateIn(ubuntu_team) will fail
        # with an AssertionError.
        self.failUnless(sample_person in warty_team.activemembers)
        self.failUnless(warty_team in ubuntu_team.invited_members)
        self.failUnlessRaises(
            AssertionError, sample_person._getDirectMemberIParticipateIn,
            ubuntu_team)

        # If we make warty_team an active member of Ubuntu team, then the
        # _getDirectMemberIParticipateIn() call will actually return
        # warty_team.
        login(warty_team.teamowner.preferredemail.email)
        warty_team.acceptInvitationToBeMemberOf(ubuntu_team, comment="foo")
        self.failUnless(warty_team in ubuntu_team.activemembers)
        self.failUnlessEqual(
            sample_person._getDirectMemberIParticipateIn(ubuntu_team),
            warty_team)

    def test_AnswerContact_person_validator(self):
        answer_contact = AnswerContact.select(limit=1)[0]
        self.assertRaises(
            PrivatePersonLinkageError,
            setattr, answer_contact, 'person', self.myteam)

    def test_Bug_person_validator(self):
        bug = Bug.select(limit=1)[0]
        for attr_name in ['owner', 'who_made_private']:
            self.assertRaises(
                PrivatePersonLinkageError,
                setattr, bug, attr_name, self.myteam)

    def test_Specification_person_validator(self):
        specification = Specification.select(limit=1)[0]
        for attr_name in ['assignee', 'drafter', 'approver', 'owner',
                          'goal_proposer', 'goal_decider', 'completer',
                          'starter']:
            self.assertRaises(
                PrivatePersonLinkageError,
                setattr, specification, attr_name, self.myteam)

    def test_visibility_validator_caching(self):
        # The method Person.visibilityConsistencyWarning can be called twice
        # when editing a team.  The first is part of the form validator.  It
        # is then called again as part of the database validator.  The test
        # can be expensive so the value is cached so that the queries are
        # needlessly run.
        fake_warning = 'Warning!  Warning!'
        naked_team = removeSecurityProxy(self.otherteam)
        naked_team._visibility_warning_cache = fake_warning
        warning = self.otherteam.visibilityConsistencyWarning(
            PersonVisibility.PRIVATE)
        self.assertEqual(fake_warning, warning)

    def test_visibility_validator_team_ss_prod_pub_to_private(self):
        # A PUBLIC team with a structural subscription to a product can
        # convert to a PRIVATE team.
        foo_bar = Person.byName('name16')
        self.bzr.addSubscription(self.otherteam, foo_bar)
        self.otherteam.visibility = PersonVisibility.PRIVATE

    def test_visibility_validator_team_private_to_public(self):
        # A PRIVATE team cannot convert to PUBLIC.
        self.otherteam.visibility = PersonVisibility.PRIVATE
        try:
            self.otherteam.visibility = PersonVisibility.PUBLIC
        except ImmutableVisibilityError, exc:
            self.assertEqual(
                str(exc),
                'A private team cannot change visibility.')

    def test_visibility_validator_team_private_to_public_view(self):
        # A PRIVATE team cannot convert to PUBLIC.
        self.otherteam.visibility = PersonVisibility.PRIVATE
        view = create_initialized_view(self.otherteam, '+edit', {
            'field.name': 'otherteam',
            'field.displayname': 'Other Team',
            'field.subscriptionpolicy': 'RESTRICTED',
            'field.renewal_policy': 'NONE',
            'field.visibility': 'PUBLIC',
            'field.actions.save': 'Save',
            })
        self.assertEqual(len(view.errors), 0)
        self.assertEqual(len(view.request.notifications), 1)
        self.assertEqual(view.request.notifications[0].message,
                         'A private team cannot change visibility.')

    def test_person_snapshot(self):
        omitted = (
            'activemembers', 'adminmembers', 'allmembers',
            'all_members_prepopulated', 'approvedmembers',
            'deactivatedmembers', 'expiredmembers', 'inactivemembers',
            'invited_members', 'member_memberships', 'pendingmembers',
            'proposedmembers', 'unmapped_participants', 'longitude',
            'latitude', 'time_zone',
            )
        snap = Snapshot(self.myteam, providing=providedBy(self.myteam))
        for name in omitted:
            self.assertFalse(
                hasattr(snap, name),
                "%s should be omitted from the snapshot but is not." % name)

    def test_person_repr_ansii(self):
        # Verify that ANSI displayname is ascii safe.
        person = self.factory.makePerson(
            name="user", displayname=u'\xdc-tester')
        ignore, name, displayname = repr(person).rsplit(' ', 2)
        self.assertEqual('user', name)
        self.assertEqual('(\\xdc-tester)>', displayname)

    def test_person_repr_unicode(self):
        # Verify that Unicode displayname is ascii safe.
        person = self.factory.makePerson(
            name="user", displayname=u'\u0170-tester')
        ignore, displayname = repr(person).rsplit(' ', 1)
        self.assertEqual('(\\u0170-tester)>', displayname)


class TestPersonRelatedBugTaskSearch(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestPersonRelatedBugTaskSearch, self).setUp()
        self.user = self.factory.makePerson(displayname="User")
        self.context = self.factory.makePerson(displayname="Context")

    def checkUserFields(
        self, params, assignee=None, bug_subscriber=None,
        owner=None, bug_commenter=None, bug_reporter=None,
        structural_subscriber=None):
        self.failUnlessEqual(assignee, params.assignee)
        # fromSearchForm() takes a bug_subscriber parameter, but saves
        # it as subscriber on the parameter object.
        self.failUnlessEqual(bug_subscriber, params.subscriber)
        self.failUnlessEqual(owner, params.owner)
        self.failUnlessEqual(bug_commenter, params.bug_commenter)
        self.failUnlessEqual(bug_reporter, params.bug_reporter)
        self.failUnlessEqual(structural_subscriber,
                             params.structural_subscriber)

    def test_get_related_bugtasks_search_params(self):
        # With no specified options, get_related_bugtasks_search_params()
        # returns 5 BugTaskSearchParams objects, each with a different
        # user field set.
        search_params = get_related_bugtasks_search_params(
            self.user, self.context)
        self.assertEqual(len(search_params), 5)
        self.checkUserFields(
            search_params[0], assignee=self.context)
        self.checkUserFields(
            search_params[1], bug_subscriber=self.context)
        self.checkUserFields(
            search_params[2], owner=self.context, bug_reporter=self.context)
        self.checkUserFields(
            search_params[3], bug_commenter=self.context)
        self.checkUserFields(
            search_params[4], structural_subscriber=self.context)

    def test_get_related_bugtasks_search_params_with_assignee(self):
        # With assignee specified, get_related_bugtasks_search_params()
        # returns 4 BugTaskSearchParams objects.
        search_params = get_related_bugtasks_search_params(
            self.user, self.context, assignee=self.user)
        self.assertEqual(len(search_params), 4)
        self.checkUserFields(
            search_params[0], assignee=self.user, bug_subscriber=self.context)
        self.checkUserFields(
            search_params[1], assignee=self.user, owner=self.context,
            bug_reporter=self.context)
        self.checkUserFields(
            search_params[2], assignee=self.user, bug_commenter=self.context)
        self.checkUserFields(
            search_params[3], assignee=self.user,
            structural_subscriber=self.context)

    def test_get_related_bugtasks_search_params_with_owner(self):
        # With owner specified, get_related_bugtasks_search_params() returns
        # 4 BugTaskSearchParams objects.
        search_params = get_related_bugtasks_search_params(
            self.user, self.context, owner=self.user)
        self.assertEqual(len(search_params), 4)
        self.checkUserFields(
            search_params[0], owner=self.user, assignee=self.context)
        self.checkUserFields(
            search_params[1], owner=self.user, bug_subscriber=self.context)
        self.checkUserFields(
            search_params[2], owner=self.user, bug_commenter=self.context)
        self.checkUserFields(
            search_params[3], owner=self.user,
            structural_subscriber=self.context)

    def test_get_related_bugtasks_search_params_with_bug_reporter(self):
        # With bug reporter specified, get_related_bugtasks_search_params()
        # returns 4 BugTaskSearchParams objects, but the bug reporter
        # is overwritten in one instance.
        search_params = get_related_bugtasks_search_params(
            self.user, self.context, bug_reporter=self.user)
        self.assertEqual(len(search_params), 5)
        self.checkUserFields(
            search_params[0], bug_reporter=self.user,
            assignee=self.context)
        self.checkUserFields(
            search_params[1], bug_reporter=self.user,
            bug_subscriber=self.context)
        # When a BugTaskSearchParams is prepared with the owner filled
        # in, the bug reporter is overwritten to match.
        self.checkUserFields(
            search_params[2], bug_reporter=self.context,
            owner=self.context)
        self.checkUserFields(
            search_params[3], bug_reporter=self.user,
            bug_commenter=self.context)
        self.checkUserFields(
            search_params[4], bug_reporter=self.user,
            structural_subscriber=self.context)

    def test_get_related_bugtasks_search_params_illegal(self):
        self.assertRaises(
            IllegalRelatedBugTasksParams,
            get_related_bugtasks_search_params, self.user, self.context,
            assignee=self.user, owner=self.user, bug_commenter=self.user,
            bug_subscriber=self.user, structural_subscriber=self.user)

    def test_get_related_bugtasks_search_params_illegal_context(self):
        # in case the `context` argument is not  of type IPerson an
        # AssertionError is raised
        self.assertRaises(
            AssertionError,
            get_related_bugtasks_search_params, self.user, "Username",
            assignee=self.user)


class KarmaTestMixin:
    """Helper methods for setting karma."""

    def _makeKarmaCache(self, person, product, category_name_values):
        """Create a KarmaCache entry with the given arguments.

        In order to create the KarmaCache record we must switch to the DB
        user 'karma'. This invalidates the objects under test so they
        must be retrieved again.
        """
        with dbuser('karma'):
            total = 0
            # Insert category total for person and project.
            for category_name, value in category_name_values:
                category = KarmaCategory.byName(category_name)
                self.cache_manager.new(
                    value, person.id, category.id, product_id=product.id)
                total += value
            # Insert total cache for person and project.
            self.cache_manager.new(
                total, person.id, None, product_id=product.id)

    def _makeKarmaTotalCache(self, person, total):
        """Create a KarmaTotalCache entry.

        In order to create the KarmaTotalCache record we must switch to the DB
        user 'karma'. This invalidates the objects under test so they
        must be retrieved again.
        """
        with dbuser('karma'):
            KarmaTotalCache(person=person.id, karma_total=total)


class TestPersonKarma(TestCaseWithFactory, KarmaTestMixin):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestPersonKarma, self).setUp()
        self.person = self.factory.makePerson()
        a_product = self.factory.makeProduct(name='aa')
        b_product = self.factory.makeProduct(name='bb')
        self.c_product = self.factory.makeProduct(name='cc')
        self.cache_manager = getUtility(IKarmaCacheManager)
        self._makeKarmaCache(
            self.person, a_product, [('bugs', 10)])
        self._makeKarmaCache(
            self.person, b_product, [('answers', 50)])
        self._makeKarmaCache(
            self.person, self.c_product, [('code', 100), (('bugs', 50))])

    def test__getProjectsWithTheMostKarma_ordering(self):
        # Verify that pillars are ordered by karma.
        results = removeSecurityProxy(
            self.person)._getProjectsWithTheMostKarma()
        self.assertEqual(
            [('cc', 150), ('bb', 50), ('aa', 10)], results)

    def test__getContributedCategories(self):
        # Verify that a iterable of karma categories is returned.
        categories = removeSecurityProxy(
            self.person)._getContributedCategories(self.c_product)
        names = sorted(category.name for category in categories)
        self.assertEqual(['bugs', 'code'], names)

    def test_getProjectsAndCategoriesContributedTo(self):
        # Verify that a list of projects and contributed karma categories
        # is returned.
        results = removeSecurityProxy(
            self.person).getProjectsAndCategoriesContributedTo()
        names = [entry['project'].name for entry in results]
        self.assertEqual(
            ['cc', 'bb', 'aa'], names)
        project_categories = results[0]
        names = [
            category.name for category in project_categories['categories']]
        self.assertEqual(
            ['code', 'bugs'], names)

    def test_getProjectsAndCategoriesContributedTo_active_only(self):
        # Verify that deactivated pillars are not included.
        login('admin@canonical.com')
        a_product = getUtility(IProductSet).getByName('cc')
        a_product.active = False
        results = removeSecurityProxy(
            self.person).getProjectsAndCategoriesContributedTo()
        names = [entry['project'].name for entry in results]
        self.assertEqual(
            ['bb', 'aa'], names)

    def test_getProjectsAndCategoriesContributedTo_limit(self):
        # Verify the limit of 5 is honored.
        d_product = self.factory.makeProduct(name='dd')
        self._makeKarmaCache(
            self.person, d_product, [('bugs', 5)])
        e_product = self.factory.makeProduct(name='ee')
        self._makeKarmaCache(
            self.person, e_product, [('bugs', 4)])
        f_product = self.factory.makeProduct(name='ff')
        self._makeKarmaCache(
            self.person, f_product, [('bugs', 3)])
        results = removeSecurityProxy(
            self.person).getProjectsAndCategoriesContributedTo()
        names = [entry['project'].name for entry in results]
        self.assertEqual(
            ['cc', 'bb', 'aa', 'dd', 'ee'], names)


class TestAPIPartipication(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_participation_query_limit(self):
        # A team with 3 members should only query once for all their
        # attributes.
        team = self.factory.makeTeam()
        with person_logged_in(team.teamowner):
            team.addMember(self.factory.makePerson(), team.teamowner)
            team.addMember(self.factory.makePerson(), team.teamowner)
            team.addMember(self.factory.makePerson(), team.teamowner)
        webservice = LaunchpadWebServiceCaller()
        collector = QueryCollector()
        collector.register()
        self.addCleanup(collector.unregister)
        url = "/~%s/participants" % team.name
        logout()
        response = webservice.get(url,
            headers={'User-Agent': 'AnonNeedsThis'})
        self.assertEqual(response.status, 200,
            "Got %d for url %r with response %r" % (
            response.status, url, response.body))
        # XXX: This number should really be 12, but see
        # https://bugs.launchpad.net/storm/+bug/619017 which is adding 3
        # queries to the test.
        self.assertThat(collector, HasQueryCount(LessThan(16)))


class TestGetRecipients(TestCaseWithFactory):
    """Tests for get_recipients"""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestGetRecipients, self).setUp()
        login('foo.bar@canonical.com')

    def test_get_recipients_indirect(self):
        """Ensure get_recipients uses indirect memberships."""
        owner = self.factory.makePerson(
            displayname='Foo Bar', email='foo@bar.com')
        team = self.factory.makeTeam(owner)
        super_team = self.factory.makeTeam(team)
        recipients = get_recipients(super_team)
        self.assertEqual(set([owner]), set(recipients))

    def test_get_recipients_team(self):
        """Ensure get_recipients uses teams with preferredemail."""
        owner = self.factory.makePerson(
            displayname='Foo Bar', email='foo@bar.com')
        team = self.factory.makeTeam(owner, email='team@bar.com')
        super_team = self.factory.makeTeam(team)
        recipients = get_recipients(super_team)
        self.assertEqual(set([team]), set(recipients))

    def test_get_recipients_team_with_unvalidated_address(self):
        """Ensure get_recipients handles teams with non-preferred addresses.

        If there is no preferred address but one or more non-preferred ones,
        email should still be sent to the members.
        """
        owner = self.factory.makePerson(email='foo@bar.com')
        team = self.factory.makeTeam(owner, email='team@bar.com')
        self.assertContentEqual([team], get_recipients(team))
        team.preferredemail.status = EmailAddressStatus.NEW
        clear_property_cache(team)
        self.assertContentEqual([owner], get_recipients(team))

    def makePersonWithNoPreferredEmail(self, **kwargs):
        kwargs['email_address_status'] = EmailAddressStatus.NEW
        return self.factory.makePerson(**kwargs)

    def get_test_recipients_person(self):
        person = self.factory.makePerson()
        recipients = get_recipients(person)
        self.assertEqual(set([person]), set(recipients))

    def test_get_recipients_empty(self):
        """get_recipients returns empty set for person with no preferredemail.
        """
        recipients = get_recipients(self.makePersonWithNoPreferredEmail())
        self.assertEqual(set(), set(recipients))

    def test_get_recipients_complex_indirect(self):
        """Ensure get_recipients uses indirect memberships."""
        owner = self.factory.makePerson(
            displayname='Foo Bar', email='foo@bar.com')
        team = self.factory.makeTeam(owner)
        super_team_member_person = self.factory.makePerson(
            displayname='Bing Bar', email='bing@bar.com')
        super_team_member_team = self.factory.makeTeam(
            email='baz@bar.com')
        super_team = self.factory.makeTeam(
            team, members=[super_team_member_person,
                           super_team_member_team,
                           self.makePersonWithNoPreferredEmail()])
        super_team_member_team.acceptInvitationToBeMemberOf(
            super_team, u'Go Team!')
        recipients = list(get_recipients(super_team))
        self.assertEqual(set([owner,
                              super_team_member_person,
                              super_team_member_team]),
                         set(recipients))

    def test_get_recipients_team_with_disabled_owner_account(self):
        """Mail is not sent to a team owner whose account is disabled.

        See <https://bugs.launchpad.net/launchpad/+bug/855150>
        """
        owner = self.factory.makePerson(email='foo@bar.com')
        team = self.factory.makeTeam(owner)
        owner.account.status = AccountStatus.DEACTIVATED
        self.assertContentEqual([], get_recipients(team))

    def test_get_recipients_team_with_disabled_member_account(self):
        """Mail is not sent to a team member whose account is disabled.

        See <https://bugs.launchpad.net/launchpad/+bug/855150>
        """
        person = self.factory.makePerson(email='foo@bar.com')
        person.account.status = AccountStatus.DEACTIVATED
        team = self.factory.makeTeam(members=[person])
        self.assertContentEqual([team.teamowner], get_recipients(team))

    def test_get_recipients_team_with_nested_disabled_member_account(self):
        """Mail is not sent to transitive team member with disabled account.

        See <https://bugs.launchpad.net/launchpad/+bug/855150>
        """
        person = self.factory.makePerson(email='foo@bar.com')
        person.account.status = AccountStatus.DEACTIVATED
        team1 = self.factory.makeTeam(members=[person])
        team2 = self.factory.makeTeam(members=[team1])
        self.assertContentEqual(
            [team2.teamowner],
            get_recipients(team2))
