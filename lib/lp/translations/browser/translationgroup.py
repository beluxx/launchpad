# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Browser code for translation groups."""

__metaclass__ = type
__all__ = [
    'TranslationGroupAddTranslatorView',
    'TranslationGroupAddView',
    'TranslationGroupEditView',
    'TranslationGroupNavigation',
    'TranslationGroupReassignmentView',
    'TranslationGroupSetBreadcrumb',
    'TranslationGroupSetView',
    'TranslationGroupSetNavigation',
    'TranslationGroupView',
    ]

import operator

from zope.component import getUtility

from lp.translations.interfaces.translationgroup import (
    ITranslationGroup, ITranslationGroupSet)
from lp.translations.interfaces.translator import (
    ITranslator, ITranslatorSet)
from canonical.launchpad.browser.objectreassignment import (
    ObjectReassignmentView)
from canonical.launchpad.webapp.interfaces import NotFoundError
from canonical.launchpad.webapp import (
    action, canonical_url, GetitemNavigation, LaunchpadEditFormView,
    LaunchpadFormView
    )
from canonical.launchpad.webapp.breadcrumb import Breadcrumb


class TranslationGroupNavigation(GetitemNavigation):

    usedfor = ITranslationGroup


class TranslationGroupSetNavigation(GetitemNavigation):

    usedfor = ITranslationGroupSet


class TranslationGroupSetBreadcrumb(Breadcrumb):
    """Builds a breadcrumb for an `ITranslationGroupSet`."""
    text = u"Translation groups"


class TranslationGroupSetView:
    """Translation groups overview."""
    page_title = "Translation groups"
    label = page_title


class TranslationGroupView:

    def __init__(self, context, request):
        self.context = context
        self.request = request
        self.translation_groups = getUtility(ITranslationGroupSet)

    @property
    def label(self):
        return "%s translation group" % self.context.title

    @property
    def page_title(self):
        return self.context.title

    @property
    def translator_list(self):
        result = []
        for item in self.context.translators:
            result.append({'lang': item.language.englishname,
                           'person': item.translator,
                           'code': item.language.code,
                           'language' : item.language,
                           'datecreated': item.datecreated,
                           'style_guide_url': item.style_guide_url,
                           'context' : item,
                           })
        result.sort(key=operator.itemgetter('lang'))
        return result


class TranslationGroupAddTranslatorView(LaunchpadFormView):
    """View class for the "appoint a translator" page"""

    schema = ITranslator
    field_names = ['language', 'translator', 'style_guide_url']

    @action("Appoint", name="appoint")
    def appoint_action(self, action, data):
        """Appoint a translator to do translations for given language.

        Create a translator who, within this group, will be responsible for
        the selected language.  Within a translation group, a language can
        have at most one translator.  Of course the translator may be either a
        person or a group, however.
        """
        language = data.get('language')
        translator = data.get('translator')
        style_guide_url = data.get('style_guide_url')
        getUtility(ITranslatorSet).new(
            self.context, language, translator, style_guide_url)

    def validate(self, data):
        """Do not allow new translators for already existing languages."""
        language = data.get('language')
        if self.context.query_translator(language):
            self.setFieldError('language',
                "There is already a translator for this language")

    @property
    def cancel_url(self):
        return canonical_url(self.context)

    @property
    def next_url(self):
        return self.cancel_url

    label = "Appoint a translation team"

    @property
    def page_title(self):
        return self.label


class TranslationGroupEditView(LaunchpadEditFormView):
    """View class to edit ITranslationGroup details."""

    schema = ITranslationGroup
    field_names = ['name', 'title', 'summary', 'translation_guide_url']

    page_title = "Change details"

    @action("Change")
    def change_action(self, action, data):
        """Edit ITranslationGroup details."""
        self.updateContextFromData(data)

    def validate(self, data):
        """Check that we follow fields restrictions."""
        # Pylint wrongly reports that the try does not do anything.
        # pylint: disable-msg=W0104
        new_name = data.get('name')
        translation_group = getUtility(ITranslationGroupSet)
        if (self.context.name != new_name):
            try:
                translation_group[new_name]
            except NotFoundError:
                # The new name doesn't exist so it's valid.
                return
            self.setFieldError('name',
                "There is already a translation group with this name")

    @property
    def cancel_url(self):
        return canonical_url(self.context)

    @property
    def next_url(self):
        return self.cancel_url

    @property
    def label(self):
        return "Change %s details" % self.context.title


class TranslationGroupAddView(LaunchpadFormView):
    """View class to add ITranslationGroup objects."""

    schema = ITranslationGroup
    field_names = ['name', 'title', 'summary', 'translation_guide_url']
    label = "Create a new translation group"
    page_title = label

    @action("Create", name="create")
    def create_action(self, action, data):
        """Add a new translation group to Launchpad."""
        name = data.get('name')
        title = data.get('title')
        summary = data.get('summary')
        translation_guide_url = data.get('translation_guide_url')
        new_group = getUtility(ITranslationGroupSet).new(
            name=name, title=title, summary=summary,
            translation_guide_url=translation_guide_url, owner=self.user)

        self.next_url = canonical_url(new_group)

    def validate(self, data):
        """Do not allow new groups with duplicated names."""
        # Pylint wrongly reports that the try does not do anything.
        # pylint: disable-msg=W0104
        name = data.get('name')
        try:
            self.context[name]
        except NotFoundError:
            # The given name doesn't exist so it's valid.
            return
        self.setFieldError('name',
            "There is already a translation group with such name")

    @property
    def cancel_url(self):
        return canonical_url(getUtility(ITranslationGroupSet))


class TranslationGroupReassignmentView(ObjectReassignmentView):
    """View class for changing translation group owner."""

    page_title = "Change owner"

    @property
    def label(self):
        return "Change the owner of %s" % self.contextName

    @property
    def contextName(self):
        return self.context.title or self.context.name

    @property
    def next_url(self):
        return canonical_url(self.context)
