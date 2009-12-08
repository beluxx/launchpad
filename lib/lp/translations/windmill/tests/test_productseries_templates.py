# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test for ProductSeries templates listing behaviour."""

__metaclass__ = type
__all__ = []

from windmill.authoring import WindmillTestClient

from canonical.launchpad.windmill.testing import constants, lpuser
from lp.translations.windmill.testing import TranslationsWindmillLayer
from lp.testing import TestCaseWithFactory

class EnableActionLinksTest(TestCaseWithFactory):
    """Test that action links are enabled on mouseover."""

    layer = TranslationsWindmillLayer

    MAX_ROW = 2

    def _xpath_action_links(self, row_index, active):
        """Return the xpath to the action links div of the specified row."""
        # xpath positions are 1-based
        row_pos = row_index+1
        if active:
            inactive_class = u"not(contains(@class, 'inactive_links'))"
        else:
            inactive_class = u"contains(@class, 'inactive_links')"
        return (u"//tr[contains(@class, 'template_row')][%d]"
                u"/td[contains(@class, 'actions_column')]"
                u"/div[%s]" % (row_pos, inactive_class))

    def test_template_listing_admin_links(self):
        """Tests that that action links are disabled and enabled.

        The test:
        * opens the templates listing for the Evolution:trunk ProductSeries;
        * verifies that all action_links are disabled initially;
        * repeats for all table rows:
          * simulates moving the mouse cursor onto the table row;
          * verifies that the action links of the row are activated;
          * simulates moving the mouse cursor off the table row;
          * verifies that the action links of the row are deactivated;
        """
        client = WindmillTestClient("Template links activation")
        url = ('http://translations.launchpad.dev:8085/evolution/trunk/'
               '+templates')
        user = lpuser.TRANSLATIONS_ADMIN
        # Go to templates page logged in as translations admin.
        client.open(url=url)
        client.waits.forPageLoad(timeout=u'20000')
        user.ensure_login(client)

        client.waits.forElement(id=u'templates_table', timeout=u'8000')
        # All links are inactive to start with.
        for row_num in range(self.MAX_ROW):
            client.waits.forElement(
                xpath=self._xpath_action_links(row_num, active=False),
                timeout=constants.FOR_ELEMENT)

        # Action links are activated when the mouse is over the row.
        for row_num in range(self.MAX_ROW):
            client.mouseOver(classname=('template_row,%d' % row_num))
            client.asserts.assertNode(
                xpath=self._xpath_action_links(row_num, active=True))

            client.mouseOut(classname=('template_row,%d' % row_num))
            client.asserts.assertNode(
                xpath=self._xpath_action_links(row_num, active=False))
