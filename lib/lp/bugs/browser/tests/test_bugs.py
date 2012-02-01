# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version (see the file LICENSE).

"""Unit tests for bug set and bug application views."""

__metaclass__ = type

from contextlib import contextmanager
from zope.component import getUtility

from lp.bugs.interfaces.malone import IMaloneApplication
from lp.bugs.publisher import BugsLayer
from lp.testing import (
    set_feature_flag,
    feature_flags,
    )
from lp.services.webapp.publisher import canonical_url
from lp.testing import (
    celebrity_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.pages import find_tag_by_id
from lp.testing.views import create_initialized_view


@contextmanager
def dynamic_listings():
    """Context manager to enable new bug listings."""
    with feature_flags():
        set_feature_flag(u'bugs.dynamic_bug_listings.enabled', u'on')
        yield


class TestMaloneView(TestCaseWithFactory):
    """Test the MaloneView for the Bugs application."""
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestMaloneView, self).setUp()
        self.application = getUtility(IMaloneApplication)

    def test_redirect_id_success(self):
        # The view redirects to the bug when it is found.
        bug = self.factory.makeBug()
        form = dict(id=str(bug.id))
        view = create_initialized_view(
            self.application, name='+index', layer=BugsLayer, form=form)
        self.assertEqual(None, view.error_message)
        self.assertEqual(
            canonical_url(bug), view.request.response.getHeader('Location'))

    def test_redirect_name_success(self):
        # The view redirects to the bug when it is found.
        bug = self.factory.makeBug()
        with celebrity_logged_in('admin'):
            bug.name = 'bingo'
        form = dict(id='bingo')
        view = create_initialized_view(
            self.application, name='+index', layer=BugsLayer, form=form)
        self.assertEqual(None, view.error_message)
        self.assertEqual(
            canonical_url(bug), view.request.response.getHeader('Location'))

    def test_redirect_unknown_bug_fail(self):
        # The view reports an error and does not redirect if the bug is not
        # found.
        form = dict(id='fnord')
        view = create_initialized_view(
            self.application, name='+index', layer=BugsLayer, form=form)
        self.assertEqual(
            "Bug 'fnord' is not registered.", view.error_message)
        self.assertEqual(None, view.request.response.getHeader('Location'))

    def test_redirect_list_of_bug_fail(self):
        # The view reports an error and does not redirect if list is provided
        # instead of a string.
        form = dict(id=['fnord', 'pting'])
        view = create_initialized_view(
            self.application, name='+index', layer=BugsLayer, form=form)
        self.assertEqual(
            "Bug ['fnord', 'pting'] is not registered.", view.error_message)
        self.assertEqual(None, view.request.response.getHeader('Location'))

    def test_search_bugs_form_rendering(self):
        # The view's template directly renders the form widgets.
        view = create_initialized_view(self.application, '+index')
        content = find_tag_by_id(view.render(), 'search-all-bugs')
        self.assertEqual('form', content.name)
        self.assertIsNot(
            None, content.find(True, id='field.searchtext'))
        self.assertIsNot(
            None, content.find(True, id='field.actions.search'))
        self.assertIsNot(
            None, content.find(True, id='field.scope.option.all'))
        self.assertIsNot(
            None, content.find(True, id='field.scope.option.project'))
        target_widget = view.widgets['scope'].target_widget
        self.assertIsNot(
            None, content.find(True, id=target_widget.show_widget_id))
        text = str(content)
        picker_vocab = "DistributionOrProductOrProjectGroup"
        self.assertIn(picker_vocab, text)
        focus_script = "setFocusByName('field.searchtext')"
        self.assertIn(focus_script, text)

    def test_search_all_bugs_rendering(self):
        with dynamic_listings():
            view = create_initialized_view(
                self.application,
                '+bugs',
                rootsite='bugs')
            content = view.render()

        # we should get some valid content out of this
        self.assertIn('Search all bugs', content)
