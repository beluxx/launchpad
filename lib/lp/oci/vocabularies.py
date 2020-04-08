# Copyright 2020 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""OCI vocabularies."""

from __future__ import absolute_import, print_function, unicode_literals

__metaclass__ = type
__all__ = []

from zope.schema.vocabulary import SimpleTerm

from lp.services.webapp.vocabulary import StormVocabularyBase
from lp.soyuz.model.distroarchseries import DistroArchSeries


class OCIRecipeDistroArchSeriesVocabulary(StormVocabularyBase):
    """All architectures of an OCI recipe's distribution series."""

    _table = DistroArchSeries

    def toTerm(self, das):
        return SimpleTerm(das, das.id, das.architecturetag)

    def __iter__(self):
        for obj in self.context.getAllowedArchitectures():
            yield self.toTerm(obj)

    def __len__(self):
        return len(self.context.getAllowedArchitectures())
