# Copyright 2004-2005 Canonical Ltd.  All rights reserved.
# pylint: disable-msg=E0611,W0212

__metaclass__ = type
__all__ = [
    'Section',
    'SectionSelection',
    'SectionSet'
    ]

from zope.interface import implements

from sqlobject import StringCol, ForeignKey

from canonical.database.sqlbase import SQLBase

from lp.soyuz.interfaces.section import ISectionSelection, ISectionSet
from canonical.launchpad.webapp.interfaces import NotFoundError
from canonical.lazr.interfaces.config import ISection
class Section(SQLBase):
    """See ISection"""
    implements(ISection)

    _defaultOrder= ['id']

    name = StringCol(notNull=True, alternateID=True)


class SectionSelection(SQLBase):
    """See ISectionSelection."""

    implements(ISectionSelection)

    _defaultOrder= ['id']

    distroseries = ForeignKey(dbName='distroseries',
        foreignKey='DistroSeries', notNull=True)
    section = ForeignKey(dbName='section',
        foreignKey='Section', notNull=True)


class SectionSet:
    """See ISectionSet."""
    implements(ISectionSet)

    def __iter__(self):
        """See ISectionSet."""
        return iter(Section.select())

    def __getitem__(self, name):
        """See ISectionSet."""
        section = Section.selectOneBy(name=name)
        if section is not None:
            return section
        raise NotFoundError(name)

    def get(self, section_id):
        """See ISectionSet."""
        return Section.get(section_id)

    def ensure(self, name):
        """See ISectionSet."""
        section = Section.selectOneBy(name=name)
        if section is not None:
            return section
        return self.new(name)

    def new(self, name):
        """See ISectionSet."""
        return Section(name=name)

