# Copyright 2009 Canonical Ltd.  All rights reserved.

"""Test the database garbage collector."""

__metaclass__ = type
__all__ = []

from datetime import datetime, timedelta
import time
import unittest

from pytz import UTC
from storm.expr import Min
from storm.store import Store
import transaction
from zope.component import getUtility

from lp.code.model.codeimportresult import CodeImportResult
from canonical.launchpad.database.oauth import OAuthNonce
from canonical.launchpad.database.openidconsumer import OpenIDConsumerNonce
from canonical.launchpad.interfaces import IMasterStore
from canonical.launchpad.interfaces.emailaddress import EmailAddressStatus
from lp.code.interfaces.codeimportresult import CodeImportResultStatus
from canonical.launchpad.testing import TestCase, TestCaseWithFactory
from canonical.launchpad.scripts.garbo import (
    DailyDatabaseGarbageCollector, HourlyDatabaseGarbageCollector,
    OpenIDAssociationPruner, OpenIDConsumerAssociationPruner)
from canonical.launchpad.scripts.tests import run_script
from canonical.launchpad.scripts.logger import QuietFakeLogger
from canonical.launchpad.webapp.interfaces import (
    IStoreSelector, MASTER_FLAVOR)
from canonical.testing.layers import (
    DatabaseLayer, LaunchpadScriptLayer, LaunchpadZopelessLayer)
from lp.registry.interfaces.person import PersonCreationRationale


class TestGarboScript(TestCase):
    layer = LaunchpadScriptLayer

    def test_daily_script(self):
        """Ensure garbo-daily.py actually runs."""
        rv, out, err = run_script(
            "cronscripts/garbo-daily.py", ["-q"], expect_returncode=0)
        self.failIf(out.strip(), "Output to stdout: %s" % out)
        self.failIf(err.strip(), "Output to stderr: %s" % err)
        DatabaseLayer.force_dirty_database()

    def test_hourly_script(self):
        """Ensure garbo-hourly.py actually runs."""
        rv, out, err = run_script(
            "cronscripts/garbo-hourly.py", ["-q"], expect_returncode=0)
        self.failIf(out.strip(), "Output to stdout: %s" % out)
        self.failIf(err.strip(), "Output to stderr: %s" % err)


class TestGarbo(TestCaseWithFactory):
    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestGarbo, self).setUp()
        # Run the garbage collectors to remove any existing garbage,
        # starting us in a known state.
        self.runDaily()
        self.runHourly()

    def runDaily(self, maximum_chunk_size=2):
        LaunchpadZopelessLayer.switchDbUser('garbo_daily')
        collector = DailyDatabaseGarbageCollector(test_args=[])
        collector._maximum_chunk_size = maximum_chunk_size
        collector.logger = QuietFakeLogger()
        collector.main()

    def runHourly(self, maximum_chunk_size=2):
        LaunchpadZopelessLayer.switchDbUser('garbo_hourly')
        collector = HourlyDatabaseGarbageCollector(test_args=[])
        collector._maximum_chunk_size = maximum_chunk_size
        collector.logger = QuietFakeLogger()
        collector.main()

    def test_OAuthNoncePruner(self):
        now = datetime.utcnow().replace(tzinfo=UTC)
        timestamps = [
            now - timedelta(days=2), # Garbage
            now - timedelta(days=1) - timedelta(seconds=60), # Garbage
            now - timedelta(days=1) + timedelta(seconds=60), # Not garbage
            now, # Not garbage
            ]
        LaunchpadZopelessLayer.switchDbUser('testadmin')
        store = IMasterStore(OAuthNonce)

        # Make sure we start with 0 nonces.
        self.failUnlessEqual(store.find(OAuthNonce).count(), 0)

        for timestamp in timestamps:
            OAuthNonce(
                access_tokenID=1,
                request_timestamp = timestamp,
                nonce = str(timestamp))
        transaction.commit()

        # Make sure we have 4 nonces now.
        self.failUnlessEqual(store.find(OAuthNonce).count(), 4)

        self.runHourly(maximum_chunk_size=60) # 1 minute maximum chunk size

        store = IMasterStore(OAuthNonce)

        # Now back to two, having removed the two garbage entries.
        self.failUnlessEqual(store.find(OAuthNonce).count(), 2)

        # And none of them are older than a day.
        # Hmm... why is it I'm putting tz aware datetimes in and getting
        # naive datetimes back? Bug in the SQLObject compatibility layer?
        # Test is still fine as we know the timezone.
        self.failUnless(
            store.find(
                Min(OAuthNonce.request_timestamp)).one().replace(tzinfo=UTC)
            >= now - timedelta(days=1))

    def test_OpenIDConsumerNoncePruner(self):
        now = int(time.mktime(time.gmtime()))
        MINUTES = 60
        HOURS = 60 * 60
        DAYS = 24 * HOURS
        timestamps = [
            now - 2 * DAYS, # Garbage
            now - 1 * DAYS - 1 * MINUTES, # Garbage
            now - 1 * DAYS + 1 * MINUTES, # Not garbage
            now, # Not garbage
            ]
        LaunchpadZopelessLayer.switchDbUser('testadmin')

        store = IMasterStore(OpenIDConsumerNonce)

        # Make sure we start with 0 nonces.
        self.failUnlessEqual(store.find(OpenIDConsumerNonce).count(), 0)

        for timestamp in timestamps:
            nonce = store.add(OpenIDConsumerNonce())
            nonce.server_url = unicode(timestamp)
            nonce.timestamp = timestamp
            nonce.salt = u'aa'
            store.add(nonce)
        transaction.commit()

        # Make sure we have 4 nonces now.
        self.failUnlessEqual(store.find(OpenIDConsumerNonce).count(), 4)

        # Run the garbage collector.
        self.runHourly(maximum_chunk_size=60) # 1 minute maximum chunks.

        store = IMasterStore(OpenIDConsumerNonce)

        # We should now have 2 nonces.
        self.failUnlessEqual(store.find(OpenIDConsumerNonce).count(), 2)

        # And none of them are older than 1 day
        earliest = store.find(Min(OpenIDConsumerNonce.timestamp)).one()
        self.failUnless(earliest >= now - 24*60*60, 'Still have old nonces')

    def test_CodeImportResultPruner(self):
        now = datetime.utcnow().replace(tzinfo=UTC)
        store = IMasterStore(CodeImportResult)

        def new_code_import_result(timestamp):
            LaunchpadZopelessLayer.switchDbUser('testadmin')
            CodeImportResult(
                date_created=timestamp,
                code_importID=1, machineID=1, requesting_userID=1,
                status=CodeImportResultStatus.FAILURE,
                date_job_started=timestamp)
            transaction.commit()

        new_code_import_result(now - timedelta(days=60))
        new_code_import_result(now - timedelta(days=19))
        new_code_import_result(now - timedelta(days=20))
        new_code_import_result(now - timedelta(days=21))

        # Run the garbage collector
        self.runDaily()

        # Nothing is removed, because we always keep the 4 latest.
        store = IMasterStore(CodeImportResult)
        self.failUnlessEqual(
            store.find(CodeImportResult).count(), 4)

        new_code_import_result(now - timedelta(days=31))
        self.runDaily()
        store = IMasterStore(CodeImportResult)
        self.failUnlessEqual(
            store.find(CodeImportResult).count(), 4)

        new_code_import_result(now - timedelta(days=29))
        self.runDaily()
        store = IMasterStore(CodeImportResult)
        self.failUnlessEqual(
            store.find(CodeImportResult).count(), 4)

        # We now have no CodeImportResults older than 30 days
        self.failUnless(
            store.find(
                Min(CodeImportResult.date_created)).one().replace(tzinfo=UTC)
            >= now - timedelta(days=30))

    def test_OpenIDAssociationPruner(self, pruner=OpenIDAssociationPruner):
        store_name = pruner.store_name
        table_name = pruner.table_name
        LaunchpadZopelessLayer.switchDbUser('testadmin')
        store_selector = getUtility(IStoreSelector)
        store = store_selector.get(store_name, MASTER_FLAVOR)
        now = time.time()
        # Create some associations in the past with lifetimes
        for delta in range(0, 20):
            store.execute("""
                INSERT INTO %s (server_url, handle, issued, lifetime)
                VALUES (%s, %s, %d, %d)
                """ % (table_name, str(delta), str(delta), now-10, delta))
        transaction.commit()

        # Ensure that we created at least one expirable row (using the
        # test start time as 'now').
        num_expired = store.execute("""
            SELECT COUNT(*) FROM %s
            WHERE issued + lifetime < %f
            """ % (table_name, now)).get_one()[0]
        self.failUnless(num_expired > 0)

        # Expire all those expirable rows, and possibly a few more if this
        # test is running slow.
        self.runHourly()

        LaunchpadZopelessLayer.switchDbUser('testadmin')
        store = store_selector.get(store_name, MASTER_FLAVOR)
        # Confirm all the rows we know should have been expired have
        # been expired. These are the ones that would be expired using
        # the test start time as 'now'.
        num_expired = store.execute("""
            SELECT COUNT(*) FROM %s
            WHERE issued + lifetime < %f
            """ % (table_name, now)).get_one()[0]
        self.failUnlessEqual(num_expired, 0)

        # Confirm that we haven't expired everything. This test will fail
        # if it has taken 10 seconds to get this far.
        num_unexpired = store.execute(
            "SELECT COUNT(*) FROM %s" % table_name).get_one()[0]
        self.failUnless(num_unexpired > 0)

    def test_OpenIDConsumerAssociationPruner(self):
        self.test_OpenIDAssociationPruner(OpenIDConsumerAssociationPruner)

    def test_RevisionAuthorEmailLinker(self):
        LaunchpadZopelessLayer.switchDbUser('testadmin')
        rev1 = self.factory.makeRevision('Author 1 <author-1@Example.Org>')
        rev2 = self.factory.makeRevision('Author 2 <author-2@Example.Org>')
        rev3 = self.factory.makeRevision('Author 3 <author-3@Example.Org>')

        person1 = self.factory.makePerson(email='Author-1@example.org')
        person2 = self.factory.makePerson(
            email='Author-2@example.org',
            email_address_status=EmailAddressStatus.NEW)
        account3 = self.factory.makeAccount(
            'Author 3', 'Author-3@example.org')

        self.assertEqual(rev1.revision_author.person, None)
        self.assertEqual(rev2.revision_author.person, None)
        self.assertEqual(rev3.revision_author.person, None)

        self.runDaily()

        # Only the validated email address associated with a Person
        # causes a linkage.
        LaunchpadZopelessLayer.switchDbUser('testadmin')
        self.assertEqual(rev1.revision_author.person, person1)
        self.assertEqual(rev2.revision_author.person, None)
        self.assertEqual(rev3.revision_author.person, None)

        # Validating an email address creates a linkage.
        person2.validateAndEnsurePreferredEmail(person2.guessedemails[0])
        self.assertEqual(rev2.revision_author.person, None)
        transaction.commit()

        self.runDaily()
        LaunchpadZopelessLayer.switchDbUser('testadmin')
        self.assertEqual(rev2.revision_author.person, person2)

        # Creating a person for an existing account creates a linkage.
        person3 = account3.createPerson(PersonCreationRationale.UNKNOWN)
        self.assertEqual(rev3.revision_author.person, None)
        transaction.commit()

        self.runDaily()
        LaunchpadZopelessLayer.switchDbUser('testadmin')
        self.assertEqual(rev3.revision_author.person, person3)

    def test_HWSubmissionEmailLinker(self):
        LaunchpadZopelessLayer.switchDbUser('testadmin')
        sub1 = self.factory.makeHWSubmission(
            emailaddress='author-1@Example.Org')
        sub2 = self.factory.makeHWSubmission(
            emailaddress='author-2@Example.Org')
        sub3 = self.factory.makeHWSubmission(
            emailaddress='author-3@Example.Org')

        person1 = self.factory.makePerson(email='Author-1@example.org')
        person2 = self.factory.makePerson(
            email='Author-2@example.org',
            email_address_status=EmailAddressStatus.NEW)
        account3 = self.factory.makeAccount(
            'Author 3', 'Author-3@example.org')

        self.assertEqual(sub1.owner, None)
        self.assertEqual(sub2.owner, None)
        self.assertEqual(sub3.owner, None)

        self.runDaily()

        # Only the validated email address associated with a Person
        # causes a linkage.
        LaunchpadZopelessLayer.switchDbUser('testadmin')
        self.assertEqual(sub1.owner, person1)
        self.assertEqual(sub2.owner, None)
        self.assertEqual(sub3.owner, None)

        # Validating an email address creates a linkage.
        person2.validateAndEnsurePreferredEmail(person2.guessedemails[0])
        self.assertEqual(sub2.owner, None)
        transaction.commit()

        self.runDaily()
        LaunchpadZopelessLayer.switchDbUser('testadmin')
        self.assertEqual(sub2.owner, person2)

        # Creating a person for an existing account creates a linkage.
        person3 = account3.createPerson(PersonCreationRationale.UNKNOWN)
        self.assertEqual(sub3.owner, None)
        transaction.commit()

        self.runDaily()
        LaunchpadZopelessLayer.switchDbUser('testadmin')
        self.assertEqual(sub3.owner, person3)

    def test_MailingListSubscriptionPruner(self):
        LaunchpadZopelessLayer.switchDbUser('testadmin')
        team, mailing_list = self.factory.makeTeamAndMailingList(
            'mlist-team', 'mlist-owner')
        person = self.factory.makePerson(email='preferred@example.org')
        email = self.factory.makeEmail('secondary@example.org', person)
        transaction.commit()
        mailing_list.subscribe(person, email)
        transaction.commit()

        # User remains subscribed if we run the garbage collector.
        self.runDaily()
        self.assertNotEqual(mailing_list.getSubscription(person), None)

        # If we remove the email address that was subscribed, the
        # garbage collector removes the subscription.
        Store.of(email).remove(email)
        transaction.commit()
        self.runDaily()
        self.assertEqual(mailing_list.getSubscription(person), None)


def test_suite():
    return unittest.TestLoader().loadTestsFromName(__name__)
