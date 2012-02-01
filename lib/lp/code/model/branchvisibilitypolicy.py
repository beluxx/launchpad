# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# pylint: disable-msg=E0611,W0212

"""Implementation for the BranchVisibilityPolicy interfaces."""

__metaclass__ = type

__all__ = [
    'BranchVisibilityTeamPolicy',
    'BranchVisibilityPolicyMixin',
    ]

from sqlobject import ForeignKey
from zope.interface import implements

from lp.code.enums import BranchVisibilityRule
from lp.code.interfaces.branchvisibilitypolicy import (
    IBranchVisibilityTeamPolicy,
    InvalidVisibilityPolicy,
    )
from lp.registry.interfaces.person import validate_person
from lp.registry.interfaces.product import IProduct
from lp.registry.interfaces.projectgroup import IProjectGroup
from lp.services.database.enumcol import EnumCol
from lp.services.database.sqlbase import SQLBase
from lp.services.helpers import shortlist
from lp.services.propertycache import cachedproperty


class BranchVisibilityTeamPolicy(SQLBase):
    """A sequence of ordered revisions in Bazaar."""

    implements(IBranchVisibilityTeamPolicy)
    _table = 'BranchVisibilityPolicy'

    project = ForeignKey(dbName='project', foreignKey='ProjectGroup')
    product = ForeignKey(dbName='product', foreignKey='Product')
    team = ForeignKey(
        dbName='team', foreignKey='Person',
        storm_validator=validate_person,
        default=None)
    rule = EnumCol(
        dbName="policy", enum=BranchVisibilityRule, notNull=True,
        default=BranchVisibilityRule.PUBLIC)


def policy_item_key(item):
    if item.team is None:
        return None
    return item.team.displayname


class BranchVisibilityPolicyMixin:
    """Specifies a list of branch visibility policy items."""

    @cachedproperty
    def _policy_visibility_context(self):
        if IProjectGroup.providedBy(self):
            return dict(project=self, product=None)
        elif IProduct.providedBy(self):
            return dict(project=None, product=self)
        else:
            raise AssertionError(
                "%s doesn't implement IProjectGroup nor IProduct." % self)

    @property
    def _policy_items(self):
        return BranchVisibilityTeamPolicy.selectBy(
            **self._policy_visibility_context)

    def getBranchVisibilityTeamPolicies(self):
        """See `IHasBranchVisibilityPolicy`."""
        # If we are using the inherited policy return the items
        # from the inherited context.
        if self.isUsingInheritedBranchVisibilityPolicy():
            return self.project.getBranchVisibilityTeamPolicies()
        # Use shortlist here for policy items as we don't expect
        # many items, and want a warning emitted if we start
        # getting many items being created for projects as it
        # may indicate a design flaw.
        items = shortlist(self._policy_items)
        return sorted(items, key=policy_item_key)

    def _selectOneBranchVisibilityTeamPolicy(self, team):
        """Finds one particular policy item."""
        if self.isUsingInheritedBranchVisibilityPolicy():
            policy_visibility_ctx = self.project._policy_visibility_context
        else:
            policy_visibility_ctx = self._policy_visibility_context
        return BranchVisibilityTeamPolicy.selectOneBy(
                team=team, **policy_visibility_ctx)

    def getBaseBranchVisibilityRule(self):
        """See `IHasBranchVisibilityPolicy`."""
        item = self._selectOneBranchVisibilityTeamPolicy(None)
        # If there is no explicit item set, then public is the default.
        if item is None:
            return BranchVisibilityRule.PUBLIC
        else:
            return item.rule

    def getBranchVisibilityRuleForTeam(self, team):
        """See `IHasBranchVisibilityPolicy`."""
        item = self._selectOneBranchVisibilityTeamPolicy(team)
        if item is None:
            return None
        else:
            return item.rule

    def getBranchVisibilityRuleForBranch(self, branch):
        """See `IHasBranchVisibilityPolicy`."""
        rule = self.getBranchVisibilityRuleForTeam(branch.owner)
        if rule is None:
            # Determine the rule based on team membership.
            # Given the number of branch policies that are likely
            # for any given product, we are simply checking all the
            # policies rather than crafting a query on the branch's
            # owner's team memberships.
            rules = []
            owner = branch.owner
            for item in self.getBranchVisibilityTeamPolicies():
                if item.team is not None and owner.inTeam(item.team):
                    rules.append(item.rule)
            if len(rules) > 0:
                # max returns the most restrictive policy. The ordering
                # of the dbSchema items ensures this.
                rule = max(rules)
            else:
                rule = self.getBaseBranchVisibilityRule()

        return rule

    def isUsingInheritedBranchVisibilityPolicy(self):
        """See `IHasBranchVisibilityPolicy`."""
        # If there is no project to inherit a policy from,
        # then we cannot be using an inherited policy.
        if getattr(self, 'project', None) is None:
            return False
        # If there are no explictly defined policy items, use the
        # inherited policy.
        return self._policy_items.count() == 0

    def setBranchVisibilityTeamPolicy(self, team, rule):
        """See `IHasBranchVisibilityPolicy`."""
        if team is None and rule not in (
            BranchVisibilityRule.PUBLIC, BranchVisibilityRule.FORBIDDEN):
            raise InvalidVisibilityPolicy
        if team is not None and rule == BranchVisibilityRule.FORBIDDEN:
            raise InvalidVisibilityPolicy
        item = BranchVisibilityTeamPolicy.selectOneBy(
            team=team, **self._policy_visibility_context)
        if item is None:
            item = BranchVisibilityTeamPolicy(
                team=team, rule=rule, **self._policy_visibility_context)
        else:
            item.rule = rule

    def removeTeamFromBranchVisibilityPolicy(self, team):
        """See `IHasBranchVisibilityPolicy`."""
        item = BranchVisibilityTeamPolicy.selectOneBy(
            team=team, **self._policy_visibility_context)
        if item is not None:
            BranchVisibilityTeamPolicy.delete(item.id)
