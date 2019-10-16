# Copyright 2019 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""OCI Recipe Target implementation."""

from __future__ import absolute_import, print_function, unicode_literals

__metaclass__ = type
__all__ = [
    'OCIRecipeTarget',
    'OCIRecipeTargetSet',
    ]

from datetime import datetime

import pytz
from storm.locals import (
    Bool,
    DateTime,
    Int,
    Reference,
    Unicode,
    )
from zope.interface import (
    implementer,
    provider,
    )

from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.ocirecipetarget import (
    IOCIRecipeTarget,
    IOCIRecipeTargetSet,
    )
from lp.registry.model.ocirecipename import OCIRecipeName
from lp.services.database.constants import DEFAULT
from lp.services.database.interfaces import (
    IMasterStore,
    IStore,
    )
from lp.services.database.stormbase import StormBase


@implementer(IOCIRecipeTarget)
class OCIRecipeTarget(StormBase):
    """See `IOCIRecipeTarget` and `IOCIRecipeTargetSet`."""

    __storm_table__ = "OCIRecipeTarget"

    id = Int(primary=True)
    date_created = DateTime(
        name="date_created", tzinfo=pytz.UTC, allow_none=False)
    date_last_modified = DateTime(
        name="date_last_modified", tzinfo=pytz.UTC, allow_none=False)

    registrant_id = Int(name='registrant', allow_none=False)
    registrant = Reference(registrant_id, "Person.id")

    distribution_id = Int(name="distribution", allow_none=True)
    distribution = Reference(distribution_id, "Distribution.id")

    ocirecipename_id = Int(name="ocirecipename", allow_none=False)
    ocirecipename = Reference(ocirecipename_id, "OCIRecipeName.id")

    description = Unicode(name="description")

    bug_reporting_guidelines = Unicode(name="bug_reporting_guidelines")
    bug_reported_acknowledgement = Unicode(name="bug_reported_acknowledgement")
    enable_bugfiling_duplicate_search = Bool(
        name="enable_bugfiling_duplicate_search")


@implementer(IOCIRecipeTargetSet)
class OCIRecipeTargetSet:

    def new(self, registrant, pillar, ocirecipename,
            date_created=DEFAULT, description=None, bug_supervisor=None,
            bug_reporting_guidelines=None,
            bug_reported_acknowledgement=None,
            bugfiling_duplicate_search=False):
        """See `IOCIRecipeTargetSet`."""
        store = IMasterStore(OCIRecipeTarget)
        target = OCIRecipeTarget()
        target.date_created = date_created
        target.date_last_modified = date_created

        # XXX twom 2019-10-10 This needs to have IProduct support
        # when the model supports it
        if IDistribution.providedBy(pillar):
            target.distribution = pillar
        else:
            raise ValueError(
                'The target of an OCIRecipeTarget must be either an '
                'IDistribution instance or an IProduct instance.')

        target.registrant = registrant
        target.ocirecipename = ocirecipename
        target.description = description
        target.bug_reporting_guidelines = bug_reporting_guidelines
        target.enable_bugfiling_duplicate_search = bugfiling_duplicate_search
        store.add(target)
        return target

    def getByDistributionAndName(self, distribution, search_name):
        """See `IOCIRecipeTargetSet`."""
        target = IStore(OCIRecipeTarget).find(
            OCIRecipeTarget,
            OCIRecipeTarget.distribution == distribution,
            OCIRecipeTarget.ocirecipename == OCIRecipeName.id,
            OCIRecipeName.name == search_name).one()
        return target
