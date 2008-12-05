# Copyright 2008 Canonical Ltd.  All rights reserved.

"""Tests for ISeriesSourcePackageBranch."""

__metaclass__ = type

from datetime import datetime
import unittest

import pytz

import transaction

from zope.component import getUtility

from canonical.launchpad.interfaces.seriessourcepackagebranch import (
    ISeriesSourcePackageBranch, ISeriesSourcePackageBranchSet)
from canonical.launchpad.interfaces.publishing import PackagePublishingPocket
from canonical.launchpad.testing import TestCaseWithFactory
from canonical.testing import DatabaseFunctionalLayer


class TestSeriesSourcePackageBranch(TestCaseWithFactory):
    """Tests for ISeriesSourcePackageBranch."""

    layer = DatabaseFunctionalLayer

    def test_new_sets_attributes(self):
        # ISeriesSourcePackageBranchSet.new sets all the defined attributes on
        # the interface.
        series_set = getUtility(ISeriesSourcePackageBranchSet)
        distroseries = self.factory.makeDistroRelease()
        sourcepackagename = self.factory.makeSourcePackageName()
        registrant = self.factory.makePerson()
        branch = self.factory.makeBranch()
        now = datetime.now(pytz.UTC)
        sspb = series_set.new(
            distroseries, PackagePublishingPocket.RELEASE, sourcepackagename,
            branch, registrant, now)
        self.assertEqual(distroseries, sspb.distroseries)
        self.assertEqual(PackagePublishingPocket.RELEASE, sspb.pocket)
        self.assertEqual(sourcepackagename, sspb.sourcepackagename)
        self.assertEqual(branch, sspb.branch)
        self.assertEqual(registrant, sspb.registrant)
        self.assertEqual(now, sspb.date_created)

    def test_new_inserts_into_db(self):
        # ISeriesSourcePackageBranchSet.new inserts the new object into the
        # database, giving it an ID.
        series_set = getUtility(ISeriesSourcePackageBranchSet)
        distroseries = self.factory.makeDistroRelease()
        sourcepackagename = self.factory.makeSourcePackageName()
        registrant = self.factory.makePerson()
        branch = self.factory.makeBranch()
        sspb = series_set.new(
            distroseries, PackagePublishingPocket.RELEASE, sourcepackagename,
            branch, registrant)
        transaction.commit()
        self.assertIsNot(sspb.id, None)

    def test_new_returns_ISeriesSourcePackageBranch(self):
        # ISeriesSourcePackageBranchSet.new returns an
        # ISeriesSourcePackageBranch, know what I mean?
        series_set = getUtility(ISeriesSourcePackageBranchSet)
        distroseries = self.factory.makeDistroRelease()
        sourcepackagename = self.factory.makeSourcePackageName()
        registrant = self.factory.makePerson()
        branch = self.factory.makeBranch()
        sspb = series_set.new(
            distroseries, PackagePublishingPocket.RELEASE, sourcepackagename,
            branch, registrant)
        self.assertProvides(sspb, ISeriesSourcePackageBranch)


def test_suite():
    return unittest.TestLoader().loadTestsFromName(__name__)

