# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Job for merging translations."""


__metaclass__ = type


__all__ = [
    'POFileStatsJob',
    ]

import logging

from storm.locals import (
    And,
    Int,
    Reference,
    )
from zope.component import getUtility
from zope.interface import (
    classProvides,
    implements,
    )

from canonical.launchpad.webapp.interfaces import (
    DEFAULT_FLAVOR,
    IStoreSelector,
    MAIN_STORE,
    )
from lp.services.database.stormbase import StormBase
from lp.services.job.interfaces.job import IRunnableJob
from lp.services.job.model.job import Job
from lp.services.job.runner import BaseRunnableJob
from lp.translations.interfaces.pofilestatsjob import IPOFileStatsJobSource
from lp.translations.model.pofile import POFile


class POFileStatsJob(StormBase, BaseRunnableJob):
    """The details for a POFile status update job."""

    __storm_table__ = 'POFileStatsJob'

    # Instances of this class are runnable jobs.
    implements(IRunnableJob)

    # Oddly, BaseRunnableJob inherits from BaseRunnableJobSource so this class
    # is both the factory for jobs (the "implements", above) and the source
    # for runnable jobs (not the constructor of the job source, the class
    # provides the IJobSource interface itself).
    classProvides(IPOFileStatsJobSource)

    # The Job table contains core job details.
    job_id = Int('job', primary=True)
    job = Reference(job_id, Job.id)

    # This is the POFile which needs its statistics updated.
    pofile_id = Int('pofile')
    pofile = Reference(pofile_id, POFile.id)

    def __init__(self, pofile):
        self.job = Job()
        self.pofile = pofile
        super(POFileStatsJob, self).__init__()

    def getOperationDescription(self):
        """See `IRunnableJob`."""
        return 'updating POFile statistics'

    def run(self):
        """See `IRunnableJob`."""
        logger = logging.getLogger()
        logger.info('Updating statistics for %s' % self.pofile.title)
        self.pofile.updateStatistics()

    @staticmethod
    def iterReady():
        """See `IJobSource`."""
        store = getUtility(IStoreSelector).get(MAIN_STORE, DEFAULT_FLAVOR)
        return store.find((POFileStatsJob),
            And(POFileStatsJob.job == Job.id,
                Job.id.is_in(Job.ready_jobs)))


def schedule(pofile):
    """Schedule a job to update a POFile's stats."""
    return POFileStatsJob(pofile)
