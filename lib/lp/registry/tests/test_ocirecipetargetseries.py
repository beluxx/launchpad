# Copyright 2019 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test OCIRecipeTargetSeries."""

from __future__ import absolute_import, print_function, unicode_literals

__metaclass__ = type

from zope.component import getUtility

from lp.registry.interfaces.ocirecipetargetseries import (
    IOCIRecipeTargetSeries,
    IOCIRecipeTargetSeriesSet,
    )
from lp.registry.model.ocirecipetargetseries import OCIRecipeTargetSeries
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestOCIRecipeTargetSeries(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_implements_interface(self):
        recipe_target = self.factory.makeOCIRecipeTarget()
        target_series = OCIRecipeTargetSeries(recipe_target, 'test-name')
        self.assertProvides(target_series, IOCIRecipeTargetSeries)

    def test_init(self):
        name = 'test-name'
        recipe_target = self.factory.makeOCIRecipeTarget()
        target_series = OCIRecipeTargetSeries(recipe_target, name)
        self.assertEqual(recipe_target, target_series.ocirecipetarget)
        self.assertEqual(name, target_series.name)


class TestOCIRecipeTargetSeriesSet(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_implements_interface(self):
        target_series_set = getUtility(IOCIRecipeTargetSeriesSet)
        self.assertProvides(target_series_set, IOCIRecipeTargetSeriesSet)

    def test_new(self):
        name = 'test-name'
        recipe_target = self.factory.makeOCIRecipeTarget()
        target_series = getUtility(IOCIRecipeTargetSeriesSet).new(
            recipe_target, name)
        self.assertEqual(recipe_target, target_series.ocirecipetarget)
        self.assertEqual(name, target_series.name)
