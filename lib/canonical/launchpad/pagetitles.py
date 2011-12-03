# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""*** PLEASE STOP ADDING TO THIS FILE ***

This module is used as a last resort when the view fails to provide a
page_title attribute
"""
__metaclass__ = type

DEFAULT_LAUNCHPAD_TITLE = 'Launchpad'

# Helpers.


class SubstitutionHelper:
    """An abstract class for substituting values into formatted strings."""
    def __init__(self, text):
        self.text = text

    def __call__(self, context, view):
        raise NotImplementedError


class ContextDisplayName(SubstitutionHelper):
    """Return the formatted string with context's displayname."""
    def __call__(self, context, view):
        return self.text % context.displayname


class ContextTitle(SubstitutionHelper):
    """Return the formatted string with context's title."""
    def __call__(self, context, view):
        return self.text % context.title


distroseries_translations = ContextTitle('Translations of %s in Launchpad')

object_templates = ContextDisplayName('Translation templates for %s')

person_translations_to_review = ContextDisplayName(
    'Translations for review by %s')

product_translations = ContextTitle('Translations of %s in Launchpad')

productseries_translations = ContextTitle('Translations overview for %s')

productseries_translations_settings = 'Settings for translations'

project_translations = ContextTitle('Translatable projects for %s')

rosetta_index = 'Launchpad Translations'

rosetta_products = 'Projects with Translations in Launchpad'
