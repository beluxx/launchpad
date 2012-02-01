# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'SourcePackageFormatSelection',
    'SourcePackageFormatSelectionSet',
    ]

from storm.locals import (
    Int,
    Reference,
    Storm,
    )
from zope.component import getUtility
from zope.interface import implements

from lp.services.database.enumcol import DBEnum
from lp.services.webapp.interfaces import (
    DEFAULT_FLAVOR,
    IStoreSelector,
    MAIN_STORE,
    MASTER_FLAVOR,
    )
from lp.soyuz.enums import SourcePackageFormat
from lp.soyuz.interfaces.sourcepackageformat import (
    ISourcePackageFormatSelection,
    ISourcePackageFormatSelectionSet,
    )


class SourcePackageFormatSelection(Storm):
    """See ISourcePackageFormatSelection."""

    implements(ISourcePackageFormatSelection)

    __storm_table__ = 'sourcepackageformatselection'

    id = Int(primary=True)

    distroseries_id = Int(name="distroseries")
    distroseries = Reference(distroseries_id, 'DistroSeries.id')

    format = DBEnum(enum=SourcePackageFormat)


class SourcePackageFormatSelectionSet:
    """See ISourcePackageFormatSelectionSet."""

    implements(ISourcePackageFormatSelectionSet)

    def getBySeriesAndFormat(self, distroseries, format):
        """See `ISourcePackageFormatSelection`."""
        return getUtility(IStoreSelector).get(
            MAIN_STORE, DEFAULT_FLAVOR).find(
                SourcePackageFormatSelection, distroseries=distroseries,
                format=format).one()

    def add(self, distroseries, format):
        """See `ISourcePackageFormatSelection`."""
        spfs = SourcePackageFormatSelection()
        spfs.distroseries = distroseries
        spfs.format = format
        return getUtility(IStoreSelector).get(MAIN_STORE, MASTER_FLAVOR).add(
            spfs)
