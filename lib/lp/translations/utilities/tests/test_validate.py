# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import unittest

from lp.testing import TestCase
from lp.translations.utilities.validate import (
    GettextValidationError, validate_translation)


class TestTranslationValidation(TestCase):
    """Test how translation validation works."""

    def test_validate_translation_c_format(self):
        # Correct c-format translations will be validated.
        english = ["English %s number %d"]
        flags = ["c-format"]
        translations = {0: "Translation %s number %d"}
        # This should not raise GettextValidationError.
        validate_translation(english, translations, flags)

    def test_validate_translation_c_format_fail(self):
        # Mismatched format specifiers will not be validated.
        english = ["English %s number %d"]
        flags = ["c-format"]
        translations = {0: "Translation %d"}
        self.assertRaises(
            GettextValidationError,
            validate_translation, english, translations, flags)

    def test_validate_translation_c_format_plural(self):
        # Correct c-format translations will be validated on plurals.
        english = ["English %s number %d", "English plural %s number %d"]
        flags = ["c-format"]
        translations = {
            0: "Translation singular %s number %d",
            1: "Translation plural %s number %d",
            }
        # This should not raise GettextValidationError.
        validate_translation(english, translations, flags)

    def test_validate_translation_c_format_plural_no_singular_format(self):
        # As a special case, the singular does not need format specifiers.
        english = ["English %s number %d", "English plural %s number %d"]
        flags = ["c-format"]
        translations = {
            0: "Translation singular",
            1: "Translation plural %s number %d",
            }
        # This should not raise GettextValidationError.
        validate_translation(english, translations, flags)

    def test_validate_translation_c_format_plural_fail(self):
        # Not matching format specifiers will not be validated.
        english = ["English %s number %d", "English plural %s number %d"]
        flags = ["c-format"]
        translations = {
            0: "Translation singular %d",
            1: "Translation plural %s",
            }
        self.assertRaises(
            GettextValidationError,
            validate_translation, english, translations, flags)


def test_suite():
    return unittest.TestLoader().loadTestsFromName(__name__)
