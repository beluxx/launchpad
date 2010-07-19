# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Implementation for `IProductSeriesLanguage`."""

__metaclass__ = type

__all__ = [
    'ProductSeriesLanguage',
    'ProductSeriesLanguageSet',
    ]

from zope.interface import implements

from storm.expr import Coalesce, Sum
from storm.store import Store

from lp.translations.utilities.rosettastats import RosettaStats
from lp.translations.model.pofile import DummyPOFile, POFile
from lp.translations.model.potemplate import get_pofiles_for, POTemplate
from lp.translations.model.translatedlanguage import TranslatedLanguageMixin
from lp.translations.interfaces.translations import ITranslatedLanguage
from lp.translations.interfaces.productserieslanguage import (
    IProductSeriesLanguage, IProductSeriesLanguageSet)


class ProductSeriesLanguage(RosettaStats, TranslatedLanguageMixin):
    """See `IProductSeriesLanguage`."""
    implements(IProductSeriesLanguage)

    def __init__(self, productseries, language, variant=None, pofile=None):
        assert 'en' != language.code, (
            'English is not a translatable language.')
        RosettaStats.__init__(self)
        TranslatedLanguageMixin.__init__(self)
        self.productseries = productseries
        self.parent = productseries
        self.language = language
        self.variant = variant
        self.pofile = pofile
        self.id = 0
        self.last_changed_date = None

    def _getMessageCount(self):
        store = Store.of(self.language)
        query = store.find(Sum(POTemplate.messagecount),
                           POTemplate.productseries==self.productseries,
                           POTemplate.iscurrent==True)
        total, = query
        if total is None:
            total = 0
        return total

    @property
    def title(self):
        """See `IProductSeriesLanguage`."""
        return '%s translations for %s %s' % (
            self.language.englishname,
            self.productseries.product.displayname,
            self.productseries.displayname)

    def messageCount(self):
        """See `IProductSeriesLanguage`."""
        return self._translation_statistics['total_count']

    def currentCount(self, language=None):
        """See `IProductSeriesLanguage`."""
        translated = self._translation_statistics['translated_count']
        new = self._translation_statistics['new_count']
        changed = self._translation_statistics['changed_count']
        current = translated - (new - changed)
        return current

    def updatesCount(self, language=None):
        """See `IProductSeriesLanguage`."""
        return self._translation_statistics['changed_count']

    def rosettaCount(self, language=None):
        """See `IProductSeriesLanguage`."""
        new = self._translation_statistics['new_count']
        changed = self._translation_statistics['changed_count']
        rosetta = new - changed
        return rosetta

    def unreviewedCount(self):
        """See `IProductSeriesLanguage`."""
        return self._translation_statistics['unreviewed_count']

    def getPOFilesFor(self, potemplates):
        """See `IProductSeriesLanguage`."""
        return get_pofiles_for(potemplates, self.language, self.variant)


class ProductSeriesLanguageSet:
    """See `IProductSeriesLanguageSet`.

    Provides a means to get a ProductSeriesLanguage.
    """
    implements(IProductSeriesLanguageSet)

    def getProductSeriesLanguage(self, productseries, language,
                                 variant=None, pofile=None):
        """See `IProductSeriesLanguageSet`."""
        return ProductSeriesLanguage(productseries, language, variant, pofile)
