# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import unittest

from zope.component import getUtility
from zope.interface.verify import verifyObject
from zope.security.proxy import removeSecurityProxy

from lp.translations.interfaces.productserieslanguage import (
    IProductSeriesLanguageSet)
from lp.translations.interfaces.translatedlanguage import ITranslatedLanguage
from lp.translations.model.pofile import DummyPOFile
from lp.testing import TestCaseWithFactory
from canonical.testing import ZopelessDatabaseLayer


class TestTranslatedLanguageMixin(TestCaseWithFactory):
    """Test TranslatedLanguageMixin."""

    layer = ZopelessDatabaseLayer

    def setUp(self):
        # Create a productseries that uses translations.
        TestCaseWithFactory.setUp(self)
        self.productseries = self.factory.makeProductSeries()
        self.productseries.product.official_rosetta = True
        self.parent = self.productseries
        self.psl_set = getUtility(IProductSeriesLanguageSet)
        self.language = self.factory.makeLanguage('sr@test')

    def getTranslatedLanguage(self, language):
        return self.psl_set.getProductSeriesLanguage(self.productseries,
                                                     language)

    def addPOTemplate(self, number_of_potmsgsets=5):
        potemplate = self.factory.makePOTemplate(
            productseries=self.productseries)
        for sequence in range(number_of_potmsgsets):
            self.factory.makePOTMsgSet(potemplate, sequence=sequence+1)
        removeSecurityProxy(potemplate).messagecount = number_of_potmsgsets
        return potemplate

    def test_interface(self):
        translated_language = self.getTranslatedLanguage(self.language)
        self.assertTrue(verifyObject(ITranslatedLanguage,
                                     translated_language))

    def test_language(self):
        translated_language = self.getTranslatedLanguage(self.language)
        self.assertEqual(self.language,
                         translated_language.language)

    def test_parent(self):
        translated_language = self.getTranslatedLanguage(self.language)
        self.assertEqual(self.parent,
                         translated_language.parent)

    def test_pofiles_notemplates(self):
        translated_language = self.getTranslatedLanguage(self.language)
        self.assertEqual([], list(translated_language.pofiles))

    def test_pofiles_template_no_pofiles(self):
        translated_language = self.getTranslatedLanguage(self.language)
        potemplate = self.addPOTemplate()
        dummy_pofile = potemplate.getDummyPOFile(self.language.code)
        pofiles = list(translated_language.pofiles)
        self.assertEqual(1, len(pofiles))
        #self.assertStatementCount(1, list, translated_language.pofiles)

        # When there are no actual PO files, we get a DummyPOFile object
        # instead.
        dummy_pofile = pofiles[0]
        naked_dummy = removeSecurityProxy(dummy_pofile)
        self.assertTrue(isinstance(naked_dummy, DummyPOFile))
        self.assertEqual(self.language, dummy_pofile.language)
        self.assertEqual(potemplate, dummy_pofile.potemplate)

    def test_pofiles_template_with_pofiles(self):
        translated_language = self.getTranslatedLanguage(self.language)
        potemplate = self.addPOTemplate()
        pofile = self.factory.makePOFile(self.language.code, potemplate)
        #self.assertStatementCount(1, getattr, translated_language, 'pofiles')
        self.assertEqual([pofile], list(translated_language.pofiles))

    def test_statistics_empty(self):
        translated_language = self.getTranslatedLanguage(self.language)

        expected = {
            'total_count' : 0,
            'translated_count' : 0,
            'new_count' : 0,
            'changed_count' : 0,
            'unreviewed_count' : 0,
            'untranslated_count' : 0,
            }
        self.assertEqual(expected,
                         translated_language.translation_statistics)

    def test_setCounts_statistics(self):
        translated_language = self.getTranslatedLanguage(self.language)

        total = 5
        translated = 4
        new = 3
        changed = 2
        unreviewed = 1
        untranslated = total - translated

        translated_language.setCounts(
            total, translated, new, changed, unreviewed)

        expected = {
            'total_count' : total,
            'translated_count' : translated,
            'new_count' : new,
            'changed_count' : changed,
            'unreviewed_count' : unreviewed,
            'untranslated_count' : untranslated,
            }
        self.assertEqual(expected,
                         translated_language.translation_statistics)

    def test_recalculateCounts_empty(self):
        translated_language = self.getTranslatedLanguage(self.language)

        translated_language.recalculateCounts()

        expected = {
            'total_count' : 0,
            'translated_count' : 0,
            'new_count' : 0,
            'changed_count' : 0,
            'unreviewed_count' : 0,
            'untranslated_count' : 0,
            }
        self.assertEqual(expected,
                         translated_language.translation_statistics)

    def test_recalculateCounts_total_one_pofile(self):
        translated_language = self.getTranslatedLanguage(self.language)
        potemplate = self.addPOTemplate(number_of_potmsgsets=5)
        pofile = self.factory.makePOFile(self.language.code, potemplate)

        translated_language.recalculateCounts()
        self.assertEqual(
            5, translated_language.translation_statistics['total_count'])

    def test_recalculateCounts_total_two_pofiles(self):
        translated_language = self.getTranslatedLanguage(self.language)
        potemplate1 = self.addPOTemplate(number_of_potmsgsets=5)
        pofile1 = self.factory.makePOFile(self.language.code, potemplate1)
        potemplate2 = self.addPOTemplate(number_of_potmsgsets=3)
        pofile2 = self.factory.makePOFile(self.language.code, potemplate2)

        translated_language.recalculateCounts()
        self.assertEqual(
            5+3, translated_language.translation_statistics['total_count'])

    def test_recalculateCounts_translated_one_pofile(self):
        translated_language = self.getTranslatedLanguage(self.language)
        potemplate = self.addPOTemplate(number_of_potmsgsets=5)
        pofile = self.factory.makePOFile(self.language.code, potemplate)
        naked_pofile = removeSecurityProxy(pofile)
        # translated count is current + rosetta
        naked_pofile.currentcount = 3
        naked_pofile.rosettacount = 1

        translated_language.recalculateCounts()
        self.assertEqual(
            4, translated_language.translation_statistics['translated_count'])

    def test_recalculateCounts_translated_two_pofiles(self):
        translated_language = self.getTranslatedLanguage(self.language)
        potemplate1 = self.addPOTemplate(number_of_potmsgsets=5)
        pofile1 = self.factory.makePOFile(self.language.code, potemplate1)
        naked_pofile1 = removeSecurityProxy(pofile1)
        # translated count is current + rosetta
        naked_pofile1.currentcount = 3
        naked_pofile1.rosettacount = 1

        potemplate2 = self.addPOTemplate(number_of_potmsgsets=3)
        pofile2 = self.factory.makePOFile(self.language.code, potemplate2)
        naked_pofile2 = removeSecurityProxy(pofile2)
        # translated count is current + rosetta
        naked_pofile2.currentcount = 1
        naked_pofile2.rosettacount = 1

        translated_language.recalculateCounts()
        self.assertEqual(
            6, translated_language.translation_statistics['translated_count'])

    def test_recalculateCounts_changed_one_pofile(self):
        translated_language = self.getTranslatedLanguage(self.language)
        potemplate = self.addPOTemplate(number_of_potmsgsets=5)
        pofile = self.factory.makePOFile(self.language.code, potemplate)
        naked_pofile = removeSecurityProxy(pofile)
        # translated count is current + rosetta
        naked_pofile.updatescount = 3

        translated_language.recalculateCounts()
        self.assertEqual(
            3, translated_language.translation_statistics['changed_count'])

    def test_recalculateCounts_changed_two_pofiles(self):
        translated_language = self.getTranslatedLanguage(self.language)
        potemplate1 = self.addPOTemplate(number_of_potmsgsets=5)
        pofile1 = self.factory.makePOFile(self.language.code, potemplate1)
        naked_pofile1 = removeSecurityProxy(pofile1)
        naked_pofile1.updatescount = 3

        potemplate2 = self.addPOTemplate(number_of_potmsgsets=3)
        pofile2 = self.factory.makePOFile(self.language.code, potemplate2)
        naked_pofile2 = removeSecurityProxy(pofile2)
        naked_pofile2.updatescount = 1

        translated_language.recalculateCounts()
        self.assertEqual(
            4, translated_language.translation_statistics['changed_count'])

    def test_recalculateCounts_new_one_pofile(self):
        translated_language = self.getTranslatedLanguage(self.language)
        potemplate = self.addPOTemplate(number_of_potmsgsets=5)
        pofile = self.factory.makePOFile(self.language.code, potemplate)
        naked_pofile = removeSecurityProxy(pofile)
        # new count is rosetta - changed
        naked_pofile.rosettacount = 3
        naked_pofile.updatescount = 1

        translated_language.recalculateCounts()
        self.assertEqual(
            2, translated_language.translation_statistics['new_count'])

    def test_recalculateCounts_new_two_pofiles(self):
        translated_language = self.getTranslatedLanguage(self.language)
        potemplate1 = self.addPOTemplate(number_of_potmsgsets=5)
        pofile1 = self.factory.makePOFile(self.language.code, potemplate1)
        naked_pofile1 = removeSecurityProxy(pofile1)
        # new count is rosetta - changed
        naked_pofile1.rosettacount = 3
        naked_pofile1.updatescount = 1

        potemplate2 = self.addPOTemplate(number_of_potmsgsets=3)
        pofile2 = self.factory.makePOFile(self.language.code, potemplate2)
        naked_pofile2 = removeSecurityProxy(pofile2)
        # new count is rosetta - changed
        naked_pofile2.rosettacount = 2
        naked_pofile2.updatescount = 1

        translated_language.recalculateCounts()
        self.assertEqual(
            3, translated_language.translation_statistics['new_count'])

    def test_recalculateCounts_unreviewed_one_pofile(self):
        translated_language = self.getTranslatedLanguage(self.language)
        potemplate = self.addPOTemplate(number_of_potmsgsets=5)
        pofile = self.factory.makePOFile(self.language.code, potemplate)
        naked_pofile = removeSecurityProxy(pofile)
        # translated count is current + rosetta
        naked_pofile.unreviewed_count = 3

        translated_language.recalculateCounts()
        self.assertEqual(
            3, translated_language.translation_statistics['unreviewed_count'])

    def test_recalculateCounts_unreviewed_two_pofiles(self):
        translated_language = self.getTranslatedLanguage(self.language)
        potemplate1 = self.addPOTemplate(number_of_potmsgsets=5)
        pofile1 = self.factory.makePOFile(self.language.code, potemplate1)
        naked_pofile1 = removeSecurityProxy(pofile1)
        naked_pofile1.unreviewed_count = 3

        potemplate2 = self.addPOTemplate(number_of_potmsgsets=3)
        pofile2 = self.factory.makePOFile(self.language.code, potemplate2)
        naked_pofile2 = removeSecurityProxy(pofile2)
        naked_pofile2.unreviewed_count = 1

        translated_language.recalculateCounts()
        self.assertEqual(
            4, translated_language.translation_statistics['unreviewed_count'])

    def test_recalculateCounts_one_pofile(self):
        translated_language = self.getTranslatedLanguage(self.language)
        potemplate = self.addPOTemplate(number_of_potmsgsets=5)
        pofile = self.factory.makePOFile(self.language.code, potemplate)
        naked_pofile = removeSecurityProxy(pofile)
        # translated count is current + rosetta
        naked_pofile.currentcount = 3
        naked_pofile.rosettacount = 1
        # Changed count is 'updatescount' on POFile.
        # It has to be lower or equal to currentcount.
        naked_pofile.updatescount = 1
        # new is rosettacount-updatescount.
        naked_pofile.newcount = 0
        naked_pofile.unreviewed_count = 3

        translated_language.recalculateCounts()

        expected = {
            'total_count' : 5,
            'translated_count' : 4,
            'new_count' : 0,
            'changed_count' : 1,
            'unreviewed_count' : 3,
            'untranslated_count' : 1,
            }
        self.assertEqual(expected,
                         translated_language.translation_statistics)

    def test_recalculateCounts_two_pofiles(self):
        translated_language = self.getTranslatedLanguage(self.language)

        # Set up one template with a single PO file.
        potemplate1 = self.addPOTemplate(number_of_potmsgsets=5)
        pofile1 = self.factory.makePOFile(self.language.code, potemplate1)
        naked_pofile1 = removeSecurityProxy(pofile1)
        # translated count is current + rosetta
        naked_pofile1.currentcount = 2
        naked_pofile1.rosettacount = 2
        # Changed count is 'updatescount' on POFile.
        # It has to be lower or equal to currentcount.
        # new is rosettacount-updatescount.
        naked_pofile1.updatescount = 1
        naked_pofile1.unreviewed_count = 3

        # Set up second template with a single PO file.
        potemplate2 = self.addPOTemplate(number_of_potmsgsets=3)
        pofile2 = self.factory.makePOFile(self.language.code, potemplate2)
        naked_pofile2 = removeSecurityProxy(pofile2)
        # translated count is current + rosetta
        naked_pofile2.currentcount = 1
        naked_pofile2.rosettacount = 2
        # Changed count is 'updatescount' on POFile.
        # It has to be lower or equal to currentcount.
        # new is rosettacount-updatescount.
        naked_pofile2.updatescount = 1
        naked_pofile2.unreviewed_count = 1

        translated_language.recalculateCounts()

        expected = {
            'total_count' : 8,
            'translated_count' : 7,
            'new_count' : 2,
            'changed_count' : 2,
            'unreviewed_count' : 4,
            'untranslated_count' : 1,
            }
        self.assertEqual(expected,
                         translated_language.translation_statistics)

    def test_recalculateCounts_two_templates_one_translation(self):
        # Make sure recalculateCounts works even if a POFile is missing
        # for one of the templates.
        translated_language = self.getTranslatedLanguage(self.language)

        # Set up one template with a single PO file.
        potemplate1 = self.addPOTemplate(number_of_potmsgsets=5)
        pofile1 = self.factory.makePOFile(self.language.code, potemplate1)
        naked_pofile1 = removeSecurityProxy(pofile1)
        # translated count is current + rosetta
        naked_pofile1.currentcount = 2
        naked_pofile1.rosettacount = 2
        # Changed count is 'updatescount' on POFile.
        # It has to be lower or equal to currentcount.
        # new is rosettacount-updatescount.
        naked_pofile1.updatescount = 1
        naked_pofile1.unreviewed_count = 3

        # Set up second template with a single PO file.
        potemplate2 = self.addPOTemplate(number_of_potmsgsets=3)

        translated_language.recalculateCounts()

        expected = {
            'total_count' : 8,
            'translated_count' : 4,
            'new_count' : 1,
            'changed_count' : 1,
            'unreviewed_count' : 3,
            'untranslated_count' : 4,
            }
        self.assertEqual(expected,
                         translated_language.translation_statistics)

