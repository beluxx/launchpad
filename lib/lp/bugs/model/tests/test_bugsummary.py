# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the BugSummary class and underlying database triggers."""

__metaclass__ = type

from canonical.launchpad.interfaces.lpstorm import IMasterStore
from canonical.testing.layers import LaunchpadZopelessLayer
from lp.bugs.interfaces.bugsummary import IBugSummary
from lp.bugs.interfaces.bugtask import BugTaskStatus
from lp.bugs.model.bug import BugTag
from lp.bugs.model.bugsummary import BugSummary
from lp.bugs.model.bugtask import BugTask
from lp.registry.model.teammembership import TeamParticipation
from lp.testing import (
    login_celebrity,
    TestCaseWithFactory,
    )


class TestBugSummary(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestBugSummary, self).setUp()

        # Some things we are testing are impossible as mere mortals,
        # but might happen from the SQL command line.
        # XXX: Should we just grant mortals permission to UPDATE BugTag
        # etc. ?
        LaunchpadZopelessLayer.switchDbUser('testadmin')

        # XXX: Unnecessary?
        # And stop security wrappers getting in the way since they are
        # uninteresting to these tests.
        # login_celebrity('admin')

        self.store = IMasterStore(BugSummary)

    def getPublicCount(self, *bugsummary_find_expr):
        return self.getCount(None, *bugsummary_find_expr)

    def getCount(self, person, *bugsummary_find_expr):
        # Flush any changes. This causes the database triggers to fire
        # and BugSummary records to be created.
        self.store.flush()

        # Invalidate all BugSummary records from the cache. The current
        # test may have already pulled in BugSummary records that may
        # now be invalid. This normally isn't a problem, as normal code
        # is only ever interested in BugSummary records created in
        # previous transactions.
        self.store.invalidate()

        public_summaries = self.store.find(
            BugSummary,
            BugSummary.viewed_by == None,
            *bugsummary_find_expr)
        private_summaries = self.store.find(
            BugSummary,
            BugSummary.viewed_by_id == TeamParticipation.teamID,
            TeamParticipation.person == person)
        all_summaries = public_summaries.union(private_summaries, all=True)

        # Note that if there a 0 records found, sum() returns None, but
        # we prefer to return 0 here.
        return all_summaries.sum(BugSummary.count) or 0

    def test_providesInterface(self):
        bug_summary = self.store.find(BugSummary)[0]
        self.assertTrue(IBugSummary.providedBy(bug_summary))

    def test_addTag(self):
        tag = u'pustular'

        # Ensure nothing using our tag yet.
        self.assertEqual(self.getPublicCount(BugSummary.tag == tag), 0)

        product = self.factory.makeProduct()

        for count in range(3):
            bug = self.factory.makeBug(product=product)
            bug_tag = BugTag()
            bug_tag.bug = bug
            bug_tag.tag = tag
            self.store.add(bug_tag)

        # Number of tagged tasks for a particular product
        self.assertEqual(
            self.getPublicCount(
                BugSummary.product == product,
                BugSummary.tag == tag),
            3)

        # There should be no other BugSummary rows.
        self.assertEqual(self.getPublicCount(BugSummary.tag == tag), 3)

    def test_changeTag(self):
        old_tag = u'pustular'
        new_tag = u'flatulent'

        # Ensure nothing using our tags yet.
        self.assertEqual(self.getPublicCount(BugSummary.tag == old_tag), 0)
        self.assertEqual(self.getPublicCount(BugSummary.tag == new_tag), 0)

        product = self.factory.makeProduct()

        for count in range(3):
            bug = self.factory.makeBug(product=product)
            bug_tag = BugTag()
            bug_tag.bug = bug
            bug_tag.tag = old_tag
            self.store.add(bug_tag)

        # Number of tagged tasks for a particular product
        self.assertEqual(
            self.getPublicCount(
                BugSummary.product == product,
                BugSummary.tag == old_tag
                ), 3)

        for count in reversed(range(3)):
            bug_tag = self.store.find(BugTag, tag=old_tag).any()
            bug_tag.tag = new_tag

            self.assertEqual(
                self.getPublicCount(
                    BugSummary.product == product,
                    BugSummary.tag == old_tag),
                count)
            self.assertEqual(
                self.getPublicCount(
                    BugSummary.product == product,
                    BugSummary.tag == new_tag),
                3 - count)

        # There should be no other BugSummary rows.
        self.assertEqual(self.getPublicCount(BugSummary.tag == old_tag), 0)
        self.assertEqual(self.getPublicCount(BugSummary.tag == new_tag), 3)

    def test_removeTag(self):
        tag = u'pustular'

        # Ensure nothing using our tags yet.
        self.assertEqual(self.getPublicCount(BugSummary.tag == tag), 0)

        product = self.factory.makeProduct()

        for count in range(3):
            bug = self.factory.makeBug(product=product)
            bug_tag = BugTag()
            bug_tag.bug = bug
            bug_tag.tag = tag
            self.store.add(bug_tag)

        # Number of tagged tasks for a particular product
        self.assertEqual(
            self.getPublicCount(
                BugSummary.product == product,
                BugSummary.tag == tag
                ), 3)

        for count in reversed(range(3)):
            bug_tag = self.store.find(BugTag, tag=tag).any()
            self.store.remove(bug_tag)
            self.assertEqual(
                self.getPublicCount(
                    BugSummary.product == product,
                    BugSummary.tag == tag
                    ), count)

        # There should be no other BugSummary rows.
        self.assertEqual(self.getPublicCount(BugSummary.tag == tag), 0)

    def test_changeStatus(self):
        org_status = BugTaskStatus.NEW
        new_status = BugTaskStatus.INVALID

        product = self.factory.makeProduct()

        for count in range(3):
            bug = self.factory.makeBug(product=product)
            bug_task = self.store.find(BugTask, bug=bug).one()
            bug_task.status = org_status

            self.assertEqual(
                self.getPublicCount(
                    BugSummary.product == product,
                    BugSummary.status == org_status),
                count + 1)

        for count in reversed(range(3)):
            bug_task = self.store.find(
                BugTask, product=product, status=org_status).any()
            bug_task.status = new_status
            self.assertEqual(
                self.getPublicCount(
                    BugSummary.product == product,
                    BugSummary.status == org_status),
                count)
            self.assertEqual(
                self.getPublicCount(
                    BugSummary.product == product,
                    BugSummary.status == new_status),
                3 - count)

    def test_makePrivate(self):
        product = self.factory.makeProduct()
        bug = self.factory.makeBug(product=product)

        person_a = self.factory.makePerson()
        person_b = self.factory.makePerson()
        bug.subscribe(person=person_a, subscribed_by=person_a)

        # Make the bug private. We have to use the Python API to ensure
        # BugSubscription records get created for implicit
        # subscriptions.
        bug.setPrivate(True, bug.owner)

        # Confirm counts.
        self.assertEqual(
            self.getPublicCount(BugSummary.product == product),
            0)
        self.assertEqual(
            self.getCount(person_a, BugSummary.product == product),
            1)
        self.assertEqual(
            self.getCount(person_b, BugSummary.product == product),
            0)

    def test_makePublic(self):
        product = self.factory.makeProduct()
        bug = self.factory.makeBug(product=product, private=True)

        person_a = self.factory.makePerson()
        person_b = self.factory.makePerson()
        bug.subscribe(person=person_a, subscribed_by=person_a)

        # Make the bug public. We have to use the Python API to ensure
        # BugSubscription records get created for implicit
        # subscriptions.
        bug.setPrivate(False, bug.owner)

        self.assertEqual(
            self.getPublicCount(BugSummary.product==product),
            1)
        self.assertEqual(
            self.getCount(person_a, BugSummary.product==product),
            1)
        self.assertEqual(
            self.getCount(person_b, BugSummary.product==product),
            1)

    def test_subscribePrivate(self):
        product = self.factory.makeProduct()
        bug = self.factory.makeBug(product=product, private=True)

        person_a = self.factory.makePerson()
        person_b = self.factory.makePerson()
        bug.subscribe(person=person_a, subscribed_by=person_a)

        self.assertEqual(
            self.getPublicCount(BugSummary.product == product),
            0)
        self.assertEqual(
            self.getCount(person_a, BugSummary.product == product),
            1)
        self.assertEqual(
            self.getCount(person_b, BugSummary.product == product),
            0)

    def test_unsubscribePrivate(self):
        product = self.factory.makeProduct()
        bug = self.factory.makeBug(product=product, private=True)

        person_a = self.factory.makePerson()
        person_b = self.factory.makePerson()
        bug.subscribe(person=person_a, subscribed_by=person_a)
        bug.subscribe(person=person_b, subscribed_by=person_b)
        bug.unsubscribe(person=person_b, unsubscribed_by=person_b)

        self.assertEqual(
            self.getPublicCount(BugSummary.product == product),
            0)
        self.assertEqual(
            self.getCount(person_a, BugSummary.product == product),
            1)
        self.assertEqual(
            self.getCount(person_b, BugSummary.product == product),
            0)

    def test_subscribePublic(self):
        product = self.factory.makeProduct()
        bug = self.factory.makeBug(product=product)

        person_a = self.factory.makePerson()
        person_b = self.factory.makePerson()
        bug.subscribe(person=person_a, subscribed_by=person_a)

        self.assertEqual(
            self.getPublicCount(BugSummary.product == product),
            1)
        self.assertEqual(
            self.getCount(person_a, BugSummary.product == product),
            1)
        self.assertEqual(
            self.getCount(person_b, BugSummary.product == product),
            1)

    def test_unsubscribePublic(self):
        product = self.factory.makeProduct()
        bug = self.factory.makeBug(product=product)

        person_a = self.factory.makePerson()
        person_b = self.factory.makePerson()
        bug.subscribe(person=person_a, subscribed_by=person_a)
        bug.subscribe(person=person_b, subscribed_by=person_b)
        bug.unsubscribe(person=person_b, unsubscribed_by=person_b)

        self.assertEqual(
            self.getPublicCount(BugSummary.product == product),
            1)
        self.assertEqual(
            self.getCount(person_a, BugSummary.product == product),
            1)
        self.assertEqual(
            self.getCount(person_b, BugSummary.product == product),
            1)

    def test_addProduct(self):
        distribution = self.factory.makeDistribution()
        product = self.factory.makeProduct()
        bug = self.factory.makeBug(distribution=distribution)

        self.assertEqual(
            self.getPublicCount(BugSummary.distribution == distribution),
            1)
        self.assertEqual(
            self.getPublicCount(BugSummary.product == product),
            0)

        self.factory.makeBugTask(bug=bug, target=product)

        self.assertEqual(
            self.getPublicCount(BugSummary.distribution == distribution),
            1)
        self.assertEqual(
            self.getPublicCount(BugSummary.product == product),
            1)

    def test_changeProduct(self):
        product_a = self.factory.makeProduct()
        product_b = self.factory.makeProduct()
        bug_task = self.factory.makeBugTask(target=product_a)

        self.assertEqual(
            self.getPublicCount(BugSummary.product == product_a),
            1)
        self.assertEqual(
            self.getPublicCount(BugSummary.product == product_b),
            0)

        bug_task.product = product_b

        self.assertEqual(
            self.getPublicCount(BugSummary.product == product_a),
            0)
        self.assertEqual(
            self.getPublicCount(BugSummary.product == product_b),
            1)

    def test_removeProduct(self):
        distribution = self.factory.makeDistribution()
        product = self.factory.makeProduct()

        product_bug_task = self.factory.makeBugTask(target=product)
        distribution_bug_task = self.factory.makeBugTask(
            bug=product_bug_task.bug, target=distribution)

        self.assertEqual(
            self.getPublicCount(BugSummary.distribution == distribution),
            1)
        self.assertEqual(
            self.getPublicCount(BugSummary.product == product),
            1)

        self.store.remove(product_bug_task)

        self.assertEqual(
            self.getPublicCount(BugSummary.distribution == distribution),
            1)
        self.assertEqual(
            self.getPublicCount(BugSummary.product == product),
            0)

    def test_addProductSeries(self):
        bug = self.factory.makeBug()
        productseries = self.factory.makeProductSeries()
        product = productseries.product

        bug_task = self.factory.makeBugTask(bug=bug, target=productseries)

        self.assertTrue(bug_task.product is None)

        self.assertEqual(
            self.getPublicCount(BugSummary.product == product),
            1)
        self.assertEqual(
            self.getPublicCount(BugSummary.productseries == productseries),
            1)

    def test_changeProductSeries(self):
        product = self.factory.makeProduct()
        productseries_a = self.factory.makeProductSeries(product=product)
        productseries_b = self.factory.makeProductSeries(product=product)

        # You can't have a BugTask targetted to a productseries without
        # already having a BugTask targetted to the product. Create
        # this task explicitly.
        product_task = self.factory.makeBugTask(target=product)

        series_task = self.factory.makeBugTask(
            bug=product_task.bug, target=productseries_a)

        self.assertEqual(
            self.getPublicCount(BugSummary.product == product),
            1)
        self.assertEqual(
            self.getPublicCount(BugSummary.productseries == productseries_a),
            1)

        series_task.productseries = productseries_b

        self.assertEqual(
            self.getPublicCount(BugSummary.product == product),
            1)
        self.assertEqual(
            self.getPublicCount(BugSummary.productseries == productseries_a),
            0)
        self.assertEqual(
            self.getPublicCount(BugSummary.productseries == productseries_b),
            1)

    def test_removeProductSeries(self):
        series = self.factory.makeProductSeries()
        product = series.product
        bug_task = self.factory.makeBugTask(target=series)

        self.assertEqual(
            self.getPublicCount(BugSummary.product == product),
            1)
        self.assertEqual(
            self.getPublicCount(BugSummary.productseries == series),
            1)

        self.store.remove(bug_task)

        self.assertEqual(
            self.getPublicCount(BugSummary.product == product),
            1)
        self.assertEqual(
            self.getPublicCount(BugSummary.productseries == series),
            0)

    def test_addDistribution(self):
        distribution = self.factory.makeDistribution()
        bug_task = self.factory.makeBugTask(target=distribution)

        self.assertEqual(
            self.getPublicCount(BugSummary.distribution == distribution),
            1)

    def test_changeDistribution(self):
        distribution_a = self.factory.makeDistribution()
        distribution_b = self.factory.makeDistribution()
        bug_task = self.factory.makeBugTask(target=distribution_a)

        self.assertEqual(
            self.getPublicCount(BugSummary.distribution == distribution_a),
            1)

        bug_task.distribution = distribution_b

        self.assertEqual(
            self.getPublicCount(BugSummary.distribution == distribution_a),
            0)
        self.assertEqual(
            self.getPublicCount(BugSummary.distribution == distribution_b),
            1)

    def test_removeDistribution(self):
        distribution_a = self.factory.makeDistribution()
        distribution_b = self.factory.makeDistribution()
        bug_task_a = self.factory.makeBugTask(target=distribution_a)
        bug = bug_task_a.bug
        bug_task_b = self.factory.makeBugTask(bug=bug, target=distribution_b)

        self.assertEqual(
            self.getPublicCount(BugSummary.distribution == distribution_a),
            1)
        self.assertEqual(
            self.getPublicCount(BugSummary.distribution == distribution_b),
            1)

        self.store.remove(bug_task_b)

        self.assertEqual(
            self.getPublicCount(BugSummary.distribution == distribution_a),
            1)
        self.assertEqual(
            self.getPublicCount(BugSummary.distribution == distribution_b),
            0)

    def test_addDistroSeries(self):
        series = self.factory.makeDistroRelease()
        distribution = series.distribution

        # This first creates a BugTask on the distribution. We can't
        # have a distroseries BugTask without a distribution BugTask.
        self.factory.makeBugTask(target=series)

        self.assertEqual(
            self.getPublicCount(BugSummary.distribution == distribution),
            1)
        self.assertEqual(
            self.getPublicCount(BugSummary.distroseries == series),
            1)

    def test_changeDistroSeries(self):
        distribution = self.factory.makeDistribution()
        series_a = self.factory.makeDistroRelease(distribution=distribution)
        series_b = self.factory.makeDistroRelease(distribution=distribution)

        bug_task = self.factory.makeBugTask(target=series_a)

        self.assertEqual(
            self.getPublicCount(BugSummary.distribution == distribution),
            1)
        self.assertEqual(
            self.getPublicCount(BugSummary.distroseries == series_a),
            1)
        self.assertEqual(
            self.getPublicCount(BugSummary.distroseries == series_b),
            0)

        bug_task.distroseries = series_b

        self.assertEqual(
            self.getPublicCount(BugSummary.distribution == distribution),
            1)
        self.assertEqual(
            self.getPublicCount(BugSummary.distroseries == series_a),
            0)
        self.assertEqual(
            self.getPublicCount(BugSummary.distroseries == series_b),
            1)

    def test_removeDistroSeries(self):
        series = self.factory.makeDistroRelease()
        distribution = series.distribution
        bug_task = self.factory.makeBugTask(target=series)

        self.assertEqual(
            self.getPublicCount(BugSummary.distribution == distribution),
            1)
        self.assertEqual(
            self.getPublicCount(BugSummary.distroseries == series),
            1)

        self.store.remove(bug_task)

        self.assertEqual(
            self.getPublicCount(BugSummary.distribution == distribution),
            1)
        self.assertEqual(
            self.getPublicCount(BugSummary.distroseries == series),
            0)

    def test_addDistributionSourcePackage(self):
        distribution = self.factory.makeDistribution()
        sourcepackage = self.factory.makeDistributionSourcePackage(
            distribution=distribution)

        bug = self.factory.makeBug()
        bug_task = self.factory.makeBugTask(bug=bug, target=sourcepackage)

        self.assertEqual(
            self.getPublicCount(
                BugSummary.distribution == distribution,
                BugSummary.sourcepackagename == None),
            1)
        self.assertEqual(
            self.getPublicCount(
                BugSummary.distribution == distribution,
                BugSummary.sourcepackagename
                    == sourcepackage.sourcepackagename),
            1)

    def test_changeDistributionSourcePackage(self):
        distribution = self.factory.makeDistribution()
        sourcepackage_a = self.factory.makeDistributionSourcePackage(
            distribution=distribution)
        sourcepackage_b = self.factory.makeDistributionSourcePackage(
            distribution=distribution)

        bug_task = self.factory.makeBugTask(target=sourcepackage_a)

        self.assertEqual(
            self.getPublicCount(
                BugSummary.distribution == distribution,
                BugSummary.sourcepackagename == None),
            1)
        self.assertEqual(
            self.getPublicCount(
                BugSummary.distribution == distribution,
                BugSummary.sourcepackagename
                    == sourcepackage_a.sourcepackagename),
            1)
        self.assertEqual(
            self.getPublicCount(
                BugSummary.distribution == distribution,
                BugSummary.sourcepackagename
                    == sourcepackage_b.sourcepackagename),
            0)

        bug_task.sourcepackagename = sourcepackage_b.sourcepackagename

        self.assertEqual(
            self.getPublicCount(
                BugSummary.distribution == distribution,
                BugSummary.sourcepackagename == None),
            1)
        self.assertEqual(
            self.getPublicCount(
                BugSummary.distribution == distribution,
                BugSummary.sourcepackagename
                    == sourcepackage_a.sourcepackagename),
            0)
        self.assertEqual(
            self.getPublicCount(
                BugSummary.distribution == distribution,
                BugSummary.sourcepackagename
                    == sourcepackage_b.sourcepackagename),
            1)

    def test_removeDistributionSourcePackage(self):
        distribution = self.factory.makeDistribution()
        sourcepackage = self.factory.makeDistributionSourcePackage(
            distribution=distribution)

        bug_task = self.factory.makeBugTask(target=sourcepackage)

        self.assertEqual(
            self.getPublicCount(
                BugSummary.distribution == distribution,
                BugSummary.sourcepackagename == None),
            1)
        self.assertEqual(
            self.getPublicCount(
                BugSummary.distribution == distribution,
                BugSummary.sourcepackagename
                    == sourcepackage.sourcepackagename),
            1)

        bug_task.sourcepackagename = None

        self.assertEqual(
            self.getPublicCount(
                BugSummary.distribution == distribution,
                BugSummary.sourcepackagename == None),
            1)
        self.assertEqual(
            self.getPublicCount(
                BugSummary.distribution == distribution,
                BugSummary.sourcepackagename
                    == sourcepackage.sourcepackagename),
            0)

    def test_addDistroSeriesSourcePackage(self):
        distribution = self.factory.makeDistribution()
        series = self.factory.makeDistroRelease(distribution=distribution)
        package = self.factory.makeSourcePackage(distroseries=series)
        sourcepackagename = package.sourcepackagename
        bug_task = self.factory.makeBugTask(target=package)

        self.assertEqual(
            self.getPublicCount(
                BugSummary.distribution == distribution,
                BugSummary.sourcepackagename == None),
            1)
        self.assertEqual(
            self.getPublicCount(
                BugSummary.distribution == distribution,
                BugSummary.sourcepackagename == sourcepackagename),
            1)
        self.assertEqual(
            self.getPublicCount(
                BugSummary.distroseries == series,
                BugSummary.sourcepackagename == None),
            1)
        self.assertEqual(
            self.getPublicCount(
                BugSummary.distroseries == series,
                BugSummary.sourcepackagename == sourcepackagename),
            1)

    def test_changeDistroSeriesSourcePackage(self):
        distribution = self.factory.makeDistribution()
        series = self.factory.makeDistroRelease(distribution=distribution)
        package_a = self.factory.makeSourcePackage(distroseries=series)
        package_b = self.factory.makeSourcePackage(distroseries=series)
        sourcepackagename_a = package_a.sourcepackagename
        sourcepackagename_b = package_b.sourcepackagename
        bug_task = self.factory.makeBugTask(target=package_a)

        self.assertEqual(
            self.getPublicCount(
                BugSummary.distribution == distribution,
                BugSummary.sourcepackagename == None),
            1)
        self.assertEqual(
            self.getPublicCount(
                BugSummary.distribution == distribution,
                BugSummary.sourcepackagename == sourcepackagename_a),
            1)
        self.assertEqual(
            self.getPublicCount(
                BugSummary.distribution == distribution,
                BugSummary.sourcepackagename == sourcepackagename_b),
            0)
        self.assertEqual(
            self.getPublicCount(
                BugSummary.distroseries == series,
                BugSummary.sourcepackagename == None),
            1)
        self.assertEqual(
            self.getPublicCount(
                BugSummary.distroseries == series,
                BugSummary.sourcepackagename == sourcepackagename_a),
            1)
        self.assertEqual(
            self.getPublicCount(
                BugSummary.distroseries == series,
                BugSummary.sourcepackagename == sourcepackagename_b),
            0)

        bug_task.sourcepackagename = sourcepackagename_b

        self.assertEqual(
            self.getPublicCount(
                BugSummary.distribution == distribution,
                BugSummary.sourcepackagename == None),
            1)
        self.assertEqual(
            self.getPublicCount(
                BugSummary.distribution == distribution,
                BugSummary.sourcepackagename == sourcepackagename_a),
            0)
        self.assertEqual(
            self.getPublicCount(
                BugSummary.distribution == distribution,
                BugSummary.sourcepackagename == sourcepackagename_b),
            1)
        self.assertEqual(
            self.getPublicCount(
                BugSummary.distroseries == series,
                BugSummary.sourcepackagename == None),
            1)
        self.assertEqual(
            self.getPublicCount(
                BugSummary.distroseries == series,
                BugSummary.sourcepackagename == sourcepackagename_a),
            0)
        self.assertEqual(
            self.getPublicCount(
                BugSummary.distroseries == series,
                BugSummary.sourcepackagename == sourcepackagename_b),
            1)

    def test_removeDistroSeriesSourcePackage(self):
        distribution = self.factory.makeDistribution()
        series = self.factory.makeDistroRelease(distribution=distribution)
        package = self.factory.makeSourcePackage(distroseries=series)
        sourcepackagename = package.sourcepackagename
        bug_task = self.factory.makeBugTask(target=package)

        self.assertEqual(
            self.getPublicCount(
                BugSummary.distribution == distribution,
                BugSummary.sourcepackagename == None),
            1)
        self.assertEqual(
            self.getPublicCount(
                BugSummary.distribution == distribution,
                BugSummary.sourcepackagename == sourcepackagename),
            1)
        self.assertEqual(
            self.getPublicCount(
                BugSummary.distroseries == series,
                BugSummary.sourcepackagename == None),
            1)
        self.assertEqual(
            self.getPublicCount(
                BugSummary.distroseries == series,
                BugSummary.sourcepackagename == sourcepackagename),
            1)

        bug_task.sourcepackagename = None

        self.assertEqual(
            self.getPublicCount(
                BugSummary.distribution == distribution,
                BugSummary.sourcepackagename == None),
            1)
        self.assertEqual(
            self.getPublicCount(
                BugSummary.distribution == distribution,
                BugSummary.sourcepackagename == sourcepackagename),
            0)
        self.assertEqual(
            self.getPublicCount(
                BugSummary.distroseries == series,
                BugSummary.sourcepackagename == None),
            1)
        self.assertEqual(
            self.getPublicCount(
                BugSummary.distroseries == series,
                BugSummary.sourcepackagename == sourcepackagename),
            0)

    def test_addMilestone(self):
        raise NotImplemetnedError

    def test_changeMilestone(self):
        raise NotImplementedError

    def test_removeMilestone(self):
        raise NotImplementedError


