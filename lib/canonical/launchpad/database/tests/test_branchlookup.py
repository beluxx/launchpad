# Copyright 2009 Canonical Ltd.  All rights reserved.

"""Tests for the IBranchLookup implementation."""

__metaclass__ = type

import unittest

from lazr.uri import URI

from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from canonical.config import config
from canonical.launchpad.interfaces.branch import NoSuchBranch
from canonical.launchpad.interfaces.branchlookup import (
    CannotHaveLinkedBranch, IBranchLookup, ILinkedBranchTraverser,
    NoLinkedBranch)
from canonical.launchpad.interfaces.branchnamespace import (
    get_branch_namespace, InvalidNamespace)
from canonical.launchpad.interfaces.person import NoSuchPerson
from canonical.launchpad.interfaces.product import (
    InvalidProductName, NoSuchProduct)
from canonical.launchpad.interfaces.productseries import NoSuchProductSeries
from canonical.launchpad.interfaces.publishing import PackagePublishingPocket
from canonical.launchpad.interfaces.sourcepackagename import (
    NoSuchSourcePackageName)
from canonical.launchpad.testing import TestCaseWithFactory
from canonical.testing.layers import DatabaseFunctionalLayer


class TestGetByUniqueName(TestCaseWithFactory):
    """Tests for `IBranchLookup.getByUniqueName`."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.branch_set = getUtility(IBranchLookup)

    def test_not_found(self):
        unused_name = self.factory.getUniqueString()
        found = self.branch_set.getByUniqueName(unused_name)
        self.assertIs(None, found)

    def test_junk(self):
        branch = self.factory.makePersonalBranch()
        found_branch = self.branch_set.getByUniqueName(branch.unique_name)
        self.assertEqual(branch, found_branch)

    def test_product(self):
        branch = self.factory.makeProductBranch()
        found_branch = self.branch_set.getByUniqueName(branch.unique_name)
        self.assertEqual(branch, found_branch)

    def test_source_package(self):
        branch = self.factory.makePackageBranch()
        found_branch = self.branch_set.getByUniqueName(branch.unique_name)
        self.assertEqual(branch, found_branch)


class TestGetByPath(TestCaseWithFactory):
    """Test `IBranchLookup._getByPath`."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.branch_lookup = removeSecurityProxy(getUtility(IBranchLookup))

    def getByPath(self, path):
        return self.branch_lookup.getByLPPath(path)

    def makeRelativePath(self):
        arbitrary_num_segments = 7
        return '/'.join([
            self.factory.getUniqueString()
            for i in range(arbitrary_num_segments)])

    def test_finds_exact_personal_branch(self):
        branch = self.factory.makePersonalBranch()
        found_branch, suffix = self.getByPath(branch.unique_name)
        self.assertEqual(branch, found_branch)
        self.assertEqual(None, suffix)

    def test_finds_suffixed_personal_branch(self):
        branch = self.factory.makePersonalBranch()
        suffix = self.makeRelativePath()
        found_branch, found_suffix = self.getByPath(
            branch.unique_name + '/' + suffix)
        self.assertEqual(branch, found_branch)
        self.assertEqual(suffix, found_suffix)

    def test_missing_personal_branch(self):
        owner = self.factory.makePerson()
        namespace = get_branch_namespace(owner)
        branch_name = namespace.getBranchName(self.factory.getUniqueString())
        self.assertRaises(NoSuchBranch, self.getByPath, branch_name)

    def test_missing_suffixed_personal_branch(self):
        owner = self.factory.makePerson()
        namespace = get_branch_namespace(owner)
        branch_name = namespace.getBranchName(self.factory.getUniqueString())
        suffix = self.makeRelativePath()
        self.assertRaises(
            NoSuchBranch, self.getByPath, branch_name + '/' + suffix)

    def test_finds_exact_product_branch(self):
        branch = self.factory.makeProductBranch()
        found_branch, suffix = self.getByPath(branch.unique_name)
        self.assertEqual(branch, found_branch)
        self.assertEqual(None, suffix)

    def test_finds_suffixed_product_branch(self):
        branch = self.factory.makeProductBranch()
        suffix = self.makeRelativePath()
        found_branch, found_suffix = self.getByPath(
            branch.unique_name + '/' + suffix)
        self.assertEqual(branch, found_branch)
        self.assertEqual(suffix, found_suffix)

    def test_missing_product_branch(self):
        owner = self.factory.makePerson()
        product = self.factory.makeProduct()
        namespace = get_branch_namespace(owner, product=product)
        branch_name = namespace.getBranchName(self.factory.getUniqueString())
        self.assertRaises(NoSuchBranch, self.getByPath, branch_name)

    def test_missing_suffixed_product_branch(self):
        owner = self.factory.makePerson()
        product = self.factory.makeProduct()
        namespace = get_branch_namespace(owner, product=product)
        suffix = self.makeRelativePath()
        branch_name = namespace.getBranchName(self.factory.getUniqueString())
        self.assertRaises(
            NoSuchBranch, self.getByPath, branch_name + '/' + suffix)

    def test_finds_exact_package_branch(self):
        branch = self.factory.makePackageBranch()
        found_branch, suffix = self.getByPath(branch.unique_name)
        self.assertEqual(branch, found_branch)
        self.assertEqual(None, suffix)

    def test_missing_package_branch(self):
        owner = self.factory.makePerson()
        distroseries = self.factory.makeDistroRelease()
        sourcepackagename = self.factory.makeSourcePackageName()
        namespace = get_branch_namespace(
            owner, distroseries=distroseries,
            sourcepackagename=sourcepackagename)
        branch_name = namespace.getBranchName(self.factory.getUniqueString())
        self.assertRaises(NoSuchBranch, self.getByPath, branch_name)

    def test_missing_suffixed_package_branch(self):
        owner = self.factory.makePerson()
        distroseries = self.factory.makeDistroRelease()
        sourcepackagename = self.factory.makeSourcePackageName()
        namespace = get_branch_namespace(
            owner, distroseries=distroseries,
            sourcepackagename=sourcepackagename)
        suffix = self.makeRelativePath()
        branch_name = namespace.getBranchName(self.factory.getUniqueString())
        self.assertRaises(
            NoSuchBranch, self.getByPath, branch_name + '/' + suffix)

    def test_too_short(self):
        person = self.factory.makePerson()
        self.assertRaises(
            InvalidNamespace, self.getByPath, '~%s' % person.name)

    def test_no_such_product(self):
        person = self.factory.makePerson()
        branch_name = '~%s/%s/%s' % (
            person.name, self.factory.getUniqueString(), 'branch-name')
        self.assertRaises(NoSuchProduct, self.getByPath, branch_name)


class TestGetByUrl(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def makeProductBranch(self):
        """Create a branch with aa/b/c as its unique name."""
        # XXX: JonathanLange 2009-01-13 spec=package-branches: This test is
        # bad because it assumes that the interesting branches for testing are
        # product branches.
        owner = self.factory.makePerson(name='aa')
        product = self.factory.makeProduct('b')
        return self.factory.makeProductBranch(
            owner=owner, product=product, name='c')

    def test_getByUrl_with_http(self):
        """getByUrl recognizes LP branches for http URLs."""
        branch = self.makeProductBranch()
        branch_set = getUtility(IBranchLookup)
        branch2 = branch_set.getByUrl('http://bazaar.launchpad.dev/~aa/b/c')
        self.assertEqual(branch, branch2)

    def test_getByUrl_with_ssh(self):
        """getByUrl recognizes LP branches for bzr+ssh URLs."""
        branch = self.makeProductBranch()
        branch_set = getUtility(IBranchLookup)
        branch2 = branch_set.getByUrl(
            'bzr+ssh://bazaar.launchpad.dev/~aa/b/c')
        self.assertEqual(branch, branch2)

    def test_getByUrl_with_sftp(self):
        """getByUrl recognizes LP branches for sftp URLs."""
        branch = self.makeProductBranch()
        branch_set = getUtility(IBranchLookup)
        branch2 = branch_set.getByUrl('sftp://bazaar.launchpad.dev/~aa/b/c')
        self.assertEqual(branch, branch2)

    def test_getByUrl_with_ftp(self):
        """getByUrl does not recognize LP branches for ftp URLs.

        This is because Launchpad doesn't currently support ftp.
        """
        branch = self.makeProductBranch()
        branch_set = getUtility(IBranchLookup)
        branch2 = branch_set.getByUrl('ftp://bazaar.launchpad.dev/~aa/b/c')
        self.assertIs(None, branch2)

    def test_getByURL_with_lp_prefix(self):
        """lp: URLs for the configured prefix are supported."""
        branch_set = getUtility(IBranchLookup)
        url = '%s~aa/b/c' % config.codehosting.bzr_lp_prefix
        self.assertRaises(NoSuchPerson, branch_set.getByUrl, url)
        owner = self.factory.makePerson(name='aa')
        product = self.factory.makeProduct('b')
        branch2 = branch_set.getByUrl(url)
        self.assertIs(None, branch2)
        branch = self.factory.makeProductBranch(
            owner=owner, product=product, name='c')
        branch2 = branch_set.getByUrl(url)
        self.assertEqual(branch, branch2)

    def test_getByURL_for_production(self):
        """test_getByURL works with production values."""
        branch_set = getUtility(IBranchLookup)
        branch = self.makeProductBranch()
        self.pushConfig('codehosting', lp_url_hosts='edge,production,,')
        branch2 = branch_set.getByUrl('lp://staging/~aa/b/c')
        self.assertIs(None, branch2)
        branch2 = branch_set.getByUrl('lp://asdf/~aa/b/c')
        self.assertIs(None, branch2)
        branch2 = branch_set.getByUrl('lp:~aa/b/c')
        self.assertEqual(branch, branch2)
        branch2 = branch_set.getByUrl('lp://production/~aa/b/c')
        self.assertEqual(branch, branch2)
        branch2 = branch_set.getByUrl('lp://edge/~aa/b/c')
        self.assertEqual(branch, branch2)

    def test_uriToUniqueName(self):
        """Ensure uriToUniqueName works.

        Only codehosting-based using http, sftp or bzr+ssh URLs will
        be handled. If any other URL gets passed the returned will be
        None.
        """
        branch_set = getUtility(IBranchLookup)
        uri = URI(config.codehosting.supermirror_root)
        uri.path = '/~foo/bar/baz'
        # Test valid schemes
        uri.scheme = 'http'
        self.assertEqual('~foo/bar/baz', branch_set.uriToUniqueName(uri))
        uri.scheme = 'sftp'
        self.assertEqual('~foo/bar/baz', branch_set.uriToUniqueName(uri))
        uri.scheme = 'bzr+ssh'
        self.assertEqual('~foo/bar/baz', branch_set.uriToUniqueName(uri))
        # Test invalid scheme
        uri.scheme = 'ftp'
        self.assertIs(None, branch_set.uriToUniqueName(uri))
        # Test valid scheme, invalid domain
        uri.scheme = 'sftp'
        uri.host = 'example.com'
        self.assertIs(None, branch_set.uriToUniqueName(uri))


class TestLinkedBranchTraverser(TestCaseWithFactory):
    """Tests for the linked branch traverser."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.traverser = getUtility(ILinkedBranchTraverser)

    def assertTraverses(self, path, result):
        """Assert that 'path' resolves to 'result'."""
        self.assertEqual(
            result, self.traverser.traverse(path),
            "Traversed to wrong result")

    def test_error_fallthrough_product_series(self):
        # For the short name of a series branch, `traverse` raises
        # `NoSuchProduct` if the first component refers to a non-existent
        # product, and `NoSuchSeries` if the second component refers to a
        # non-existent series.
        self.assertRaises(
            NoSuchProduct, self.traverser.traverse, 'bb/dd')
        product = self.factory.makeProduct('bb')
        self.assertRaises(
            NoSuchProductSeries, self.traverser.traverse, 'bb/dd')

    def test_product_series(self):
        # `traverse` resolves the short name for a product series to the
        # branch associated with that series, and includes the series in the
        # tuple.
        series = self.factory.makeSeries()
        short_name = '%s/%s' % (series.product.name, series.name)
        self.assertTraverses(short_name, series)

    def test_product_that_doesnt_exist(self):
        # `traverse` raises `NoSuchProduct` when resolving an lp path of
        # 'product' if the product doesn't exist.
        self.assertRaises(NoSuchProduct, self.traverser.traverse, 'bb')

    def test_invalid_product(self):
        # `traverse` raises `InvalidProductIdentifier` when resolving an lp
        # path for a completely invalid product development focus branch.
        self.assertRaises(
            InvalidProductName, self.traverser.traverse, 'b')

    def test_product(self):
        # `traverse` resolves 'product' to the development focus branch for
        # the product and the series that is the development focus.
        product = self.factory.makeProduct()
        self.assertTraverses(product.name, product)

    def test_source_package(self):
        # `traverse` resolves 'distro/series/package' to the official branch
        # for the release pocket of that package in that series.
        package = self.factory.makeSourcePackage()
        self.assertTraverses(
            package.path, (package, PackagePublishingPocket.RELEASE))

    def test_no_such_sourcepackagename(self):
        # `traverse` raises `NoSuchSourcePackageName` if the package in
        # distro/series/package doesn't exist.
        distroseries = self.factory.makeDistroRelease()
        path = '%s/%s/doesntexist' % (
            distroseries.distribution.name, distroseries.name)
        self.assertRaises(
            NoSuchSourcePackageName, self.traverser.traverse, path)


class TestGetByLPPath(TestCaseWithFactory):
    """Ensure URLs are correctly expanded."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.branch_lookup = getUtility(IBranchLookup)

    def test_error_fallthrough_product_branch(self):
        # getByLPPath raises `NoSuchPerson` if the person component is not
        # found, then `NoSuchProduct` if the person component is found but the
        # product component isn't, then `NoSuchBranch` if the first two
        # components are found.
        self.assertRaises(
            NoSuchPerson, self.branch_lookup.getByLPPath, '~aa/bb/c')
        owner = self.factory.makePerson(name='aa')
        self.assertRaises(
            NoSuchProduct, self.branch_lookup.getByLPPath, '~aa/bb/c')
        product = self.factory.makeProduct('bb')
        self.assertRaises(
            NoSuchBranch, self.branch_lookup.getByLPPath, '~aa/bb/c')

    def test_private_branch(self):
        # If the unique name refers to an invisible branch, getByLPPath raises
        # NoSuchBranch, just as if the branch weren't there at all.
        branch = self.factory.makeAnyBranch(private=True)
        path = removeSecurityProxy(branch).unique_name
        self.assertRaises(
            NoSuchBranch, self.branch_lookup.getByLPPath, path)

    def test_resolve_product_branch_unique_name(self):
        # getByLPPath returns the branch, no trailing path and no series if
        # given the unique name of an existing product branch.
        branch = self.factory.makeProductBranch()
        self.assertEqual(
            (branch, None),
            self.branch_lookup.getByLPPath(branch.unique_name))

    def test_resolve_product_branch_unique_name_with_trailing(self):
        # getByLPPath returns the branch and the trailing path (with no
        # series) if the given path is inside an existing branch.
        branch = self.factory.makeProductBranch()
        path = '%s/foo/bar/baz' % (branch.unique_name,)
        self.assertEqual(
            (branch, 'foo/bar/baz'), self.branch_lookup.getByLPPath(path))

    def test_error_fallthrough_personal_branch(self):
        # getByLPPath raises `NoSuchPerson` if the first component doesn't
        # match an existing person, and `NoSuchBranch` if the last component
        # doesn't match an existing branch.
        self.assertRaises(
            NoSuchPerson, self.branch_lookup.getByLPPath, '~aa/+junk/c')
        owner = self.factory.makePerson(name='aa')
        self.assertRaises(
            NoSuchBranch, self.branch_lookup.getByLPPath, '~aa/+junk/c')

    def test_resolve_personal_branch_unique_name(self):
        # getByLPPath returns the branch, no trailing path and no series if
        # given the unique name of an existing junk branch.
        branch = self.factory.makePersonalBranch()
        self.assertEqual(
            (branch, None),
            self.branch_lookup.getByLPPath(branch.unique_name))

    def test_resolve_personal_branch_unique_name_with_trailing(self):
        # getByLPPath returns the branch and the trailing path (with no
        # series) if the given path is inside an existing branch.
        branch = self.factory.makePersonalBranch()
        path = '%s/foo/bar/baz' % (branch.unique_name,)
        self.assertEqual(
            (branch, 'foo/bar/baz'),
            self.branch_lookup.getByLPPath(path))

    def test_no_product_series_branch(self):
        # getByLPPath raises `NoLinkedBranch` if there's no branch registered
        # linked to the requested series.
        series = self.factory.makeSeries()
        short_name = '%s/%s' % (series.product.name, series.name)
        exception = self.assertRaises(
            NoLinkedBranch, self.branch_lookup.getByLPPath, short_name)
        self.assertEqual(series, exception.component)

    def test_product_with_no_dev_focus(self):
        # getByLPPath raises `NoLinkedBranch` if the product is found but
        # doesn't have a development focus branch.
        product = self.factory.makeProduct()
        exception = self.assertRaises(
            NoLinkedBranch, self.branch_lookup.getByLPPath, product.name)
        self.assertEqual(product, exception.component)

    def test_private_linked_branch(self):
        # If the given path refers to an object with an invisible linked
        # branch, then getByLPPath raises `NoLinkedBranch`, as if the branch
        # weren't there at all.
        branch = self.factory.makeProductBranch(private = True)
        product = removeSecurityProxy(branch).product
        removeSecurityProxy(product).development_focus.user_branch = branch
        self.assertRaises(
            NoLinkedBranch, self.branch_lookup.getByLPPath, product.name)

    def test_no_official_branch(self):
        sourcepackage = self.factory.makeSourcePackage()
        exception = self.assertRaises(
            NoLinkedBranch,
            self.branch_lookup.getByLPPath, sourcepackage.path)
        self.assertEqual(
            (sourcepackage, PackagePublishingPocket.RELEASE),
            exception.component)

    def test_distribution_linked_branch(self):
        # Distributions cannot have linked branches, so `getByLPPath` raises a
        # `CannotHaveLinkedBranch` error if we try to get the linked branch
        # for a distribution.
        distribution = self.factory.makeDistribution()
        exception = self.assertRaises(
            CannotHaveLinkedBranch,
            self.branch_lookup.getByLPPath, distribution.name)
        self.assertEqual(distribution, exception.component)

    def test_project_linked_branch(self):
        # Projects cannot have linked branches, so `getByLPPath` raises a
        # `CannotHaveLinkedBranch` error if we try to get the linked branch
        # for a project.
        project = self.factory.makeProject()
        exception = self.assertRaises(
            CannotHaveLinkedBranch,
            self.branch_lookup.getByLPPath, project.name)
        self.assertEqual(project, exception.component)

    def test_partial_lookup(self):
        owner = self.factory.makePerson()
        product = self.factory.makeProduct()
        path = '~%s/%s' % (owner.name, product.name)
        self.assertRaises(
            InvalidNamespace, self.branch_lookup.getByLPPath, path)

    # XXX: JonathanLange 2009-03-30 spec=package-branches bug=345739: Test for
    # pocket-linked branch paths.


def test_suite():
    return unittest.TestLoader().loadTestsFromName(__name__)
