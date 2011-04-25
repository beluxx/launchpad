# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests the security.cfg auditor."""

__metaclass__ = type

import os

from canonical.testing.layers import BaseLayer
from lp.scripts.utilities.settingsauditor import SettingsAuditor
from lp.testing import TestCase


class TestAuditSecuritySettings(TestCase):

    layer = BaseLayer

    def setUp(self):
        super(TestAuditSecuritySettings, self).setUp()
        self.test_settings = (
            '# This is the header.\n'
            '[good]\n'
            'public.foo = SELECT\n'
            'public.bar = SELECT, INSERT\n'
            'public.baz = SELECT\n'
            '\n'
            '[bad]\n'
            'public.foo = SELECT\n'
            'public.bar = SELECT, INSERT\n'
            'public.bar = SELECT\n'
            'public.baz = SELECT\n')

    def test_getHeader(self):
        sa = SettingsAuditor(self.test_settings)
        header = sa._getHeader()
        self.assertEqual(
            header,
            '# This is the header.\n')

    def test_extract_config_blocks(self):
        test_settings = self.test_settings.replace(
            '# This is the header.\n', '')
        sa = SettingsAuditor(test_settings)
        sa._separateConfigBlocks()
        self.assertContentEqual(
            ['[good]', '[bad]'],
            sa.config_blocks.keys())

    def test_audit_block(self):
        sa = SettingsAuditor('')
        test_block = (
            '[bad]\n'
            'public.foo = SELECT\n'
            'public.bar = SELECT, INSERT\n'
            'public.bar = SELECT\n'
            'public.baz = SELECT\n')
        sa.config_blocks = {'[bad]': test_block}
        sa._processBlocks()
        expected = (
            '[bad]\n'
            'public.bar = SELECT\n'
            'public.bar = SELECT, INSERT\n'
            'public.baz = SELECT\n'
            'public.foo = SELECT')
        self.assertEqual(expected, sa.config_blocks['[bad]'])

def NOPE_duplicate_parsing(self):
        sa = SettingsAuditor()
        sa.audit(self.test_settings)
        expected = '[bad]\n\tDuplicate setting found: public.bar'
        self.assertTrue(expected in sa.error_data)
