# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Branch targets."""

__metaclass__ = type
__all__ = [
    'branch_to_target',
    'PackageBranchTarget',
    'PersonBranchTarget',
    'ProductBranchTarget',
    'ProductSeriesBranchTarget',
    ]

from zope.component import getUtility
from zope.interface import implements
from zope.security.proxy import isinstance as zope_isinstance

from lp.code.interfaces.branchcollection import IAllBranches
from lp.code.interfaces.branchtarget import (
    check_default_stacked_on, IBranchTarget)
from lp.code.interfaces.codeimport import ICodeImportSet
from lp.registry.interfaces.pocket import PackagePublishingPocket
from canonical.launchpad.webapp.interfaces import ICanonicalUrlData


def branch_to_target(branch):
    """Adapt an IBranch to an IBranchTarget."""
    return branch.target


class _BaseBranchTarget:

    def __eq__(self, other):
        return self.context == other.context

    def __ne__(self, other):
        return self.context != other.context

    def newCodeImport(self, registrant, branch_name, rcs_type, url=None,
            cvs_root=None, cvs_module=None):
        return getUtility(ICodeImportSet).new(
            registrant, self, branch_name, rcs_type, url=url,
            cvs_root=cvs_root, cvs_module=cvs_module)


class PackageBranchTarget(_BaseBranchTarget):
    implements(IBranchTarget)

    def __init__(self, sourcepackage):
        self.sourcepackage = sourcepackage

    @property
    def name(self):
        """See `IBranchTarget`."""
        return self.sourcepackage.path

    @property
    def components(self):
        """See `IBranchTarget`."""
        return [
            self.sourcepackage.distribution,
            self.sourcepackage.distroseries,
            self.sourcepackage,
            ]

    @property
    def context(self):
        """See `IBranchTarget`."""
        return self.sourcepackage

    def getNamespace(self, owner):
        """See `IBranchTarget`."""
        from lp.code.model.branchnamespace import (
            PackageNamespace)
        return PackageNamespace(owner, self.sourcepackage)

    @property
    def collection(self):
        """See `IBranchTarget`."""
        return getUtility(IAllBranches).inSourcePackage(self.sourcepackage)

    @property
    def default_stacked_on_branch(self):
        """See `IBranchTarget`."""
        return check_default_stacked_on(
            self.sourcepackage.development_version.getBranch(
                PackagePublishingPocket.RELEASE))

    @property
    def default_merge_target(self):
        """See `IBranchTarget`."""
        return self.sourcepackage.getBranch(PackagePublishingPocket.RELEASE)

    @property
    def displayname(self):
        """See `IBranchTarget`."""
        return self.sourcepackage.displayname

    @property
    def supports_merge_proposals(self):
        """See `IBranchTarget`."""
        return True

    @property
    def supports_code_imports(self):
        """See `IBranchTarget`."""
        return True

    def areBranchesMergeable(self, other_target):
        """See `IBranchTarget`."""
        # Branches are mergable into a PackageTarget if the source package
        # name is the same, or the branch is associated with the linked
        # product.
        if zope_isinstance(other_target, PackageBranchTarget):
            my_sourcepackagename = self.context.sourcepackagename
            other_sourcepackagename = other_target.context.sourcepackagename
            return my_sourcepackagename == other_sourcepackagename
        elif zope_isinstance(other_target, ProductBranchTarget):
            # If the sourcepackage has a related product, then branches of
            # that product are mergeable.
            product_series = self.sourcepackage.productseries
            if product_series is None:
                return False
            else:
                return other_target.context == product_series.product
        else:
            return False

    def assignKarma(self, person, action_name, date_created=None):
        """See `IBranchTarget`."""
        return person.assignKarma(
            action_name,
            distribution=self.context.distribution,
            sourcepackagename=self.context.sourcepackagename,
            datecreated=date_created)

    def getBugTask(self, bug):
        """See `IBranchTarget`."""
        # XXX: rockstar - See bug 397251.  Basically, source packages may have
        # specific bug tasks.  This should return those specific bugtasks in
        # those cases.
        return bug.default_bugtask

    def _retargetBranch(self, branch):
        """Set the branch target to refer to this target.

        This only updates the target related attributes of the branch, and
        expects a branch without a security proxy as a parameter.
        """
        branch.product = None
        branch.distroseries = self.sourcepackage.distroseries
        branch.sourcepackagename = self.sourcepackage.sourcepackagename


class PersonBranchTarget(_BaseBranchTarget):
    implements(IBranchTarget)

    name = '+junk'
    default_stacked_on_branch = None
    default_merge_target = None

    def __init__(self, person):
        self.person = person

    @property
    def components(self):
        """See `IBranchTarget`."""
        return [self.person]

    @property
    def context(self):
        """See `IBranchTarget`."""
        return self.person

    @property
    def displayname(self):
        """See `IBranchTarget`."""
        return "~%s/+junk" % self.person.name

    def getNamespace(self, owner):
        """See `IBranchTarget`."""
        from lp.code.model.branchnamespace import (
            PersonalNamespace)
        return PersonalNamespace(owner)

    @property
    def collection(self):
        """See `IBranchTarget`."""
        return getUtility(IAllBranches).ownedBy(self.person).isJunk()

    @property
    def supports_merge_proposals(self):
        """See `IBranchTarget`."""
        return False

    @property
    def supports_code_imports(self):
        """See `IBranchTarget`."""
        return False

    def areBranchesMergeable(self, other_target):
        """See `IBranchTarget`."""
        return False

    def assignKarma(self, person, action_name, date_created=None):
        """See `IBranchTarget`."""
        # Does nothing. No karma for +junk.
        return None

    def getBugTask(self, bug):
        """See `IBranchTarget`."""
        return bug.default_bugtask

    def _retargetBranch(self, branch):
        """Set the branch target to refer to this target.

        This only updates the target related attributes of the branch, and
        expects a branch without a security proxy as a parameter.
        """
        branch.product = None
        branch.distroseries = None
        branch.sourcepackagename = None


class ProductBranchTarget(_BaseBranchTarget):
    implements(IBranchTarget)

    def __init__(self, product):
        self.product = product

    @property
    def components(self):
        """See `IBranchTarget`."""
        return [self.product]

    @property
    def context(self):
        """See `IBranchTarget`."""
        return self.product

    @property
    def displayname(self):
        """See `IBranchTarget`."""
        return self.product.displayname

    @property
    def name(self):
        """See `IBranchTarget`."""
        return self.product.name

    @property
    def default_stacked_on_branch(self):
        """See `IBranchTarget`."""
        return check_default_stacked_on(self.product.development_focus.branch)

    @property
    def default_merge_target(self):
        """See `IBranchTarget`."""
        return self.product.development_focus.branch

    def getNamespace(self, owner):
        """See `IBranchTarget`."""
        from lp.code.model.branchnamespace import (
            ProductNamespace)
        return ProductNamespace(owner, self.product)

    @property
    def collection(self):
        """See `IBranchTarget`."""
        return getUtility(IAllBranches).inProduct(self.product)

    @property
    def supports_merge_proposals(self):
        """See `IBranchTarget`."""
        return True

    @property
    def supports_code_imports(self):
        """See `IBranchTarget`."""
        return True

    def areBranchesMergeable(self, other_target):
        """See `IBranchTarget`."""
        # Branches are mergable into a PackageTarget if the source package
        # name is the same, or the branch is associated with the linked
        # product.
        if zope_isinstance(other_target, ProductBranchTarget):
            return self.product == other_target.context
        elif zope_isinstance(other_target, PackageBranchTarget):
            # If the sourcepackage has a related product, and that product is
            # the same as ours, then the branches are mergeable.
            product_series = other_target.context.productseries
            if product_series is None:
                return False
            else:
                return self.product == product_series.product
        else:
            return False

    def assignKarma(self, person, action_name, date_created=None):
        """See `IBranchTarget`."""
        return person.assignKarma(
            action_name, product=self.product, datecreated=date_created)

    def getBugTask(self, bug):
        """See `IBranchTarget`."""
        task = bug.getBugTask(self.product)
        if task is None:
            # Just choose the first task for the bug.
            task = bug.bugtasks[0]
        return task

    def _retargetBranch(self, branch):
        """Set the branch target to refer to this target.

        This only updates the target related attributes of the branch, and
        expects a branch without a security proxy as a parameter.
        """
        branch.product = self.product
        branch.distroseries = None
        branch.sourcepackagename = None


class ProductSeriesBranchTarget(ProductBranchTarget):

    def __init__(self, productseries):
        self.productseries = productseries
        self.product = productseries.product

    @property
    def context(self):
        """See `IBranchTarget`."""
        return self.productseries

    @property
    def supports_code_imports(self):
        """See `IBranchTarget`."""
        return False


def get_canonical_url_data_for_target(branch_target):
    """Return the `ICanonicalUrlData` for an `IBranchTarget`."""
    return ICanonicalUrlData(branch_target.context)
