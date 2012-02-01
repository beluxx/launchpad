# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the IPerson.createPPA() method."""

__metaclass__ = type

from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestCreatePPA(TestCaseWithFactory):
    """Test that the IPerson.createPPA method behaves as expected."""

    layer = DatabaseFunctionalLayer

    def test_create_ppa(self):
        person = self.factory.makePerson()
        ppa = person.createPPA()
        self.assertEqual(ppa.name, 'ppa')
