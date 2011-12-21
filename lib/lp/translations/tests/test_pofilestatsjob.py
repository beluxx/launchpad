# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for merging translations."""

__metaclass__ = type


from canonical.config import config
from canonical.launchpad.webapp.testing import verifyObject
from canonical.testing.layers import LaunchpadZopelessLayer
from lp.app.enums import ServiceUsage
from lp.services.job.interfaces.job import (
    IJobSource,
    IRunnableJob,
    )
from lp.testing import TestCaseWithFactory
from lp.testing.dbuser import dbuser
from lp.translations.interfaces.pofilestatsjob import IPOFileStatsJobSource
from lp.translations.interfaces.side import TranslationSide
from lp.translations.model import pofilestatsjob
from lp.translations.model.pofilestatsjob import POFileStatsJob


class TestPOFileStatsJob(TestCaseWithFactory):

    layer = LaunchpadZopelessLayer

    def test_job_interface(self):
        # Instances of POFileStatsJob are runnable jobs.
        verifyObject(IRunnableJob, POFileStatsJob(0))

    def test_source_interface(self):
        # The POFileStatsJob class is a source of POFileStatsJobs.
        verifyObject(IPOFileStatsJobSource, POFileStatsJob)
        verifyObject(IJobSource, POFileStatsJob)

    def test_run(self):
        # Running a job causes the POFile statistics to be updated.
        singular = self.factory.getUniqueString()
        pofile = self.factory.makePOFile(side=TranslationSide.UPSTREAM)
        # Create a message so we have something to have statistics about.
        self.factory.makePOTMsgSet(pofile.potemplate, singular)
        # The statistics start at 0.
        self.assertEqual(pofile.potemplate.messageCount(), 0)
        job = pofilestatsjob.schedule(pofile.id)
        # Just scheduling the job doesn't update the statistics.
        self.assertEqual(pofile.potemplate.messageCount(), 0)
        with dbuser(config.pofile_stats.dbuser):
            job.run()
        # Now that the job ran, the statistics have been updated.
        self.assertEqual(pofile.potemplate.messageCount(), 1)

    def test_with_product(self):
        product = self.factory.makeProduct(
            translations_usage=ServiceUsage.LAUNCHPAD)
        productseries = self.factory.makeProductSeries(product=product)
        potemplate = self.factory.makePOTemplate(productseries=productseries)
        pofile = self.factory.makePOFile('en', potemplate)
        # Create a message so we have something to have statistics about.
        singular = self.factory.getUniqueString()
        self.factory.makePOTMsgSet(pofile.potemplate, singular)
        # The statistics are still at 0, even though there is a message.
        self.assertEqual(potemplate.messageCount(), 0)
        job = pofilestatsjob.schedule(pofile.id)
        # Just scheduling the job doesn't update the statistics.
        self.assertEqual(pofile.potemplate.messageCount(), 0)
        with dbuser(config.pofile_stats.dbuser):
            job.run()
        # Now that the job ran, the statistics have been updated.
        self.assertEqual(pofile.potemplate.messageCount(), 1)

    def test_iterReady(self):
        # The POFileStatsJob class provides a way to iterate over the jobs
        # that are ready to run.  Initially, there aren't any.
        self.assertEqual(len(list(POFileStatsJob.iterReady())), 0)
        # We need a POFile to update.
        pofile = self.factory.makePOFile(side=TranslationSide.UPSTREAM)
        # If we schedule a job, then we'll get it back.
        job = pofilestatsjob.schedule(pofile.id)
        self.assertIs(list(POFileStatsJob.iterReady())[0], job)

    def test_second_job_is_scheduled(self):
        # If there is already one POFileStatsJob scheduled for a particular
        # POFile, then a second one is scheduled.
        self.assertEqual(len(list(POFileStatsJob.iterReady())), 0)
        # We need a POFile to update.
        pofile = self.factory.makePOFile(side=TranslationSide.UPSTREAM)
        # If we schedule a job, then there will be one scheduled.
        pofilestatsjob.schedule(pofile.id)
        self.assertIs(len(list(POFileStatsJob.iterReady())), 1)
        # If we attempt to schedule another job for the same POFile, a new job
        # is added.
        pofilestatsjob.schedule(pofile.id)
        self.assertIs(len(list(POFileStatsJob.iterReady())), 2)
