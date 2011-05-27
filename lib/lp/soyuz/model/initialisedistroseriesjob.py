# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    "InitialiseDistroSeriesJob",
]

from zope.interface import (
    classProvides,
    implements,
    )
from canonical.launchpad.interfaces.lpstorm import (
    IMasterStore,
    IStore,
    )
from lp.registry.model.distroseries import DistroSeries
from lp.soyuz.interfaces.distributionjob import (
    DistributionJobType,
    IInitialiseDistroSeriesJob,
    IInitialiseDistroSeriesJobSource,
    )
from lp.soyuz.model.distributionjob import (
    DistributionJob,
    DistributionJobDerived,
    )
from lp.soyuz.scripts.initialise_distroseries import InitialiseDistroSeries
from lp.services.job.model.job import Job
from lp.services.database import bulk


class InitialiseDistroSeriesJob(DistributionJobDerived):

    implements(IInitialiseDistroSeriesJob)

    class_job_type = DistributionJobType.INITIALISE_SERIES
    classProvides(IInitialiseDistroSeriesJobSource)

    @classmethod
    def create(cls, child, parents, arches=(), packagesets=(), rebuild=False):
        """See `IInitialiseDistroSeriesJob`."""
        metadata = {
            'parents': [parent.id for parent in parents],
            'arches': arches,
            'packagesets': packagesets,
            'rebuild': rebuild,
            }
        job = DistributionJob(
            child.distribution, child, cls.class_job_type,
            metadata)
        IMasterStore(DistributionJob).add(job)
        return cls(job)

    @classmethod
    def getPendingJobsForDistroseries(cls, distroseries):
        """See `IInitialiseDistroSeriesJob`."""
        return IStore(DistributionJob).find(
            DistributionJob,
            DistributionJob.job_id == Job.id,
            DistributionJob.job_type ==
                DistributionJobType.INITIALISE_SERIES,
            DistributionJob.distroseries_id == distroseries.id,
            Job._status.is_in(Job.PENDING_STATUSES))

    @property
    def parents(self):
        return bulk.load(DistroSeries, self.metadata['parents'])

    @property
    def arches(self):
        return tuple(self.metadata['arches'])

    @property
    def packagesets(self):
        return tuple(self.metadata['packagesets'])

    @property
    def rebuild(self):
        return self.metadata['rebuild']

    def run(self):
        """See `IRunnableJob`."""
        ids = InitialiseDistroSeries(
            self.distroseries, self.parents, self.arches,
            self.packagesets, self.rebuild)
        ids.check()
        ids.initialise()

    def getOopsVars(self):
        """See `IRunnableJob`."""
        vars = super(InitialiseDistroSeriesJob, self).getOopsVars()
        vars.append(('parent_distroseries_ids', self.metadata.get("parents")))
        return vars
