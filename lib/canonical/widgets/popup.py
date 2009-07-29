# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# pylint: disable-msg=E0211

"""Single selection widget using a popup to select one item from many."""

__metaclass__ = type

import os
import cgi
import simplejson

from zope.interface import Attribute, implements, Interface
from zope.component import getUtility
from zope.schema import TextLine
from zope.schema.interfaces import IChoice
from zope.app.form.browser.interfaces import ISimpleInputWidget
from zope.app.form.browser.itemswidgets import (
    ItemsWidgetBase, SingleDataHelper)
from zope.app.schema.vocabulary import IVocabularyFactory
from zope.publisher.interfaces import NotFound
from zope.component.interfaces import ComponentLookupError

from z3c.ptcompat import ViewPageTemplateFile

from canonical.launchpad.webapp import canonical_url
from canonical.launchpad.webapp.batching import BatchNavigator
from canonical.launchpad.webapp.vocabulary import IHugeVocabulary
from canonical.launchpad.interfaces import UnexpectedFormData
from canonical.cachedproperty import cachedproperty


class VocabularyPickerWidget(SingleDataHelper, ItemsWidgetBase):
    """Wrapper for the lazr-js picker/picker.js widget."""

    __call__ = ViewPageTemplateFile('templates/form-picker.pt')

    popup_name = 'popup-vocabulary-picker'

    # Override inherited attributes for the form field.
    displayWidth = '20'
    displayMaxWidth = ''
    default = ''
    onKeyPress = ''
    style = ''
    cssClass = ''

    # Defaults to self.vocabulary.displayname.
    header = None

    step_title = 'Search'

    @cachedproperty
    def form_token(self):
        val = self._getFormValue()

        # We have a valid object - return the corresponding token
        if not isinstance(val, basestring):
            return self.vocabulary.getTerm(val).token

        # Just return the existing invalid token
        return val

    @property
    def suffix(self):
        return self.name.replace('.', '-')

    @property
    def show_widget_id(self):
        return 'show-widget-%s' % self.suffix

    @property
    def vocabulary_name(self):
        """The name of the field's vocabulary."""
        choice = IChoice(self.context)
        if choice.vocabularyName is None:
            # The webservice that provides the results of the search
            # must be passed in the name of the vocabulary which is looked
            # up by the vocabulary registry.
            raise ValueError(
                "The %r.%s interface attribute doesn't have its "
                "vocabulary specified as a string, so it can't be loaded "
                "by the vocabulary registry."
                % (choice.context, choice.__name__))
        return choice.vocabularyName

    def chooseLink(self):
        js_file = os.path.join(os.path.dirname(__file__),
                               'templates/vocabulary-picker.js')
        js_template = open(js_file).read()

        if self.header is None:
            header = self.vocabulary.displayname
        else:
            header = self.header

        js = js_template % dict(
            vocabulary=self.vocabulary_name,
            header=header,
            step_title=self.step_title,
            show_widget_id=self.show_widget_id,
            input_id=self.name)
        # If the YUI widget or javascript is not supported in the browser,
        # it will degrade to being this "Find..." link instead of the
        # "Choose..." link.
        return ('(<a id="%s" href="/people/">'
                'Find&hellip;</a>)'
                '\n<script>\n%s\n</script>') % (self.show_widget_id, js)


class PersonPickerWidget(VocabularyPickerWidget):
    include_create_team_link = False

    def chooseLink(self):
        link = super(PersonPickerWidget, self).chooseLink()
        if self.include_create_team_link:
            link += ('or (<a href="/people/+newteam">'
                     'Create a new team&hellip;</a>)')
        return link
