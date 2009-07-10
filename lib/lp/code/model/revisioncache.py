# Copyright 2009 Canonical Ltd.  All rights reserved.

"""Implementation for the IRevisionCache and IRevisionCollection."""

__metaclass__ = type
__all__ = [
    'GenericRevisionCollection',
    ]

from datetime import datetime, timedelta

import pytz
from storm.expr import Desc, Func, SQL
from zope.component import getUtility
from zope.interface import implements

from canonical.launchpad.webapp.interfaces import (
    IStoreSelector, MAIN_STORE, DEFAULT_FLAVOR)
from lp.code.interfaces.revisioncache import IRevisionCollection
from lp.code.model.revision import Revision, RevisionAuthor, RevisionCache
from lp.registry.model.distroseries import DistroSeries
from lp.registry.model.product import Product
from lp.registry.model.teammembership import TeamParticipation


class GenericRevisionCollection:
    """See `IRevisionCollection`."""

    implements(IRevisionCollection)

    def __init__(self, store=None, filter_expressions=None):
        self._store = store
        if filter_expressions is None:
            epoch = datetime.now(pytz.UTC) - timedelta(days=30)
            filter_expressions = [
                RevisionCache.revision_date >= epoch]
        self._filter_expressions = filter_expressions

    @property
    def store(self):
        # Although you might think we could set the default value for store in
        # the constructor, we can't. The IStoreSelector utility is not
        # available at the time that the branchcollection.zcml is parsed,
        # which means we get an error if this code is in the constructor.
        if self._store is None:
            return getUtility(IStoreSelector).get(MAIN_STORE, DEFAULT_FLAVOR)
        else:
            return self._store

    def _filterBy(self, expressions):
        return self.__class__(
            self.store,
            self._filter_expressions + expressions)

    def count(self):
        """See `IRevisionCollection`."""
        # Don't join in the Revision table if we are just counting unique ids.
        result_set = self.store.find(
            RevisionCache.revision_id, self._filter_expressions)
        result_set.config(distinct=True)
        return result_set.count()

    def authorCount(self):
        """See `IRevisionCollection`."""
        author = Func(
            'coalesce',
            RevisionAuthor.personID,
            SQL(0) - RevisionAuthor.id)
        expressions = [
            RevisionCache.revision_author == RevisionAuthor.id]
        expressions.extend(self._filter_expressions)
        result_set = self.store.find(author, expressions)
        result_set.config(distinct=True)
        return result_set.count()

    def getRevisions(self):
        """See `IRevisionCollection`."""
        expressions = [
            RevisionCache.revision == Revision.id]
        expressions.extend(self._filter_expressions)
        result_set = self.store.find(Revision, expressions)
        result_set.config(distinct=True)
        result_set.order_by(Desc(Revision.revision_date))
        return result_set

    def public(self):
        """See `IRevisionCollection`."""
        return self._filterBy(
            [RevisionCache.private == False])

    def inProduct(self, product):
        """See `IRevisionCollection`."""
        return self._filterBy(
            [RevisionCache.product == product])

    def inProject(self, project):
        """See `IRevisionCollection`."""
        return self._filterBy(
            [RevisionCache.product == Product.id,
             Product.project == project])

    def inSourcePackage(self, package):
        """See `IRevisionCollection`."""
        return self._filterBy(
            [RevisionCache.distroseries == package.distroseries,
             RevisionCache.sourcepackagename == package.sourcepackagename])

    def inDistribution(self, distribution):
        """See `IRevisionCollection`."""
        return self._filterBy(
            [DistroSeries.distribution == distribution,
             RevisionCache.distroseries == DistroSeries.id])

    def inDistroSeries(self, distro_series):
        """See `IRevisionCollection`."""
        return self._filterBy(
            [RevisionCache.distroseries == distro_series])

    def inDistributionSourcePackage(self, distro_source_package):
        """See `IRevisionCollection`."""
        distribution = distro_source_package.distribution
        sourcepackagename = distro_source_package.sourcepackagename
        return self._filterBy(
            [DistroSeries.distribution == distribution,
             RevisionCache.distroseries == DistroSeries.id,
             RevisionCache.sourcepackagename == sourcepackagename])

    def authoredBy(self, person):
        """See `IRevisionCollection`."""
        if person.is_team:
            query = [
                TeamParticipation.team == person,
                RevisionAuthor.personID == TeamParticipation.personID]
        else:
            query = [RevisionAuthor.person == person]

        query.append(RevisionCache.revision_author == RevisionAuthor.id)
        return self._filterBy(query)
