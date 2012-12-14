# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Views for SpecificationDependency."""

__metaclass__ = type

__all__ = [
    'SpecificationDependencyAddView',
    'SpecificationDependencyRemoveView',
    'SpecificationDependencyTreeView',
    ]

from lazr.restful.interface import copy_field
from zope.component import getUtility
from zope.interface import Interface

from lp import _
from lp.app.enums import InformationType
from lp.app.browser.launchpadform import (
    action,
    LaunchpadFormView,
    )
from lp.app.interfaces.services import IService
from lp.blueprints.interfaces.specificationdependency import (
    ISpecificationDependency,
    ISpecificationDependencyRemoval,
    )
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    canonical_url,
    LaunchpadView,
    )


class AddSpecificationDependencySchema(Interface):

    dependency = copy_field(
        ISpecificationDependency['dependency'],
        readonly=False,
        description=_(
            "If another blueprint needs to be fully implemented "
            "before this feature can be started, then specify that "
            "dependency here so Launchpad knows about it and can "
            "give you an accurate project plan.  You can enter the "
            "name of a blueprint that has the same target, or the "
            "URL of any blueprint."))


class SpecificationDependencyAddView(LaunchpadFormView):
    schema = AddSpecificationDependencySchema
    label = _('Depends On')

    def validate(self, data):
        """See `LaunchpadFormView.validate`.

        Because it's too hard to set a good error message from inside the
        widget -- it will be the infamously inscrutable 'Invalid Value' -- we
        replace it here.
        """
        if self.getFieldError('dependency'):
            token = self.request.form.get(self.widgets['dependency'].name)
            self.setFieldError(
                'dependency',
                'There is no blueprint named "%s" in %s, or '
                '%s isn\'t valid dependency of that blueprint.' %
                (token, self.context.target.name, self.context.name))

    @action(_('Continue'), name='linkdependency')
    def linkdependency_action(self, action, data):
        self.context.createDependency(data['dependency'])

    @property
    def next_url(self):
        return canonical_url(self.context)

    @property
    def cancel_url(self):
        return canonical_url(self.context)


class SpecificationDependencyRemoveView(LaunchpadFormView):
    schema = ISpecificationDependencyRemoval
    label = 'Remove a dependency'
    field_names = ['dependency']
    for_input = True

    @action('Continue', name='continue')
    def continue_action(self, action, data):
        self.context.removeDependency(data['dependency'])
        self.next_url = canonical_url(self.context)

    @property
    def cancel_url(self):
        return canonical_url(self.context)


class SpecificationDependencyTreeView(LaunchpadView):

    label = "Blueprint dependency tree"

    def __init__(self, *args, **kwargs):
        super(SpecificationDependencyTreeView, self).__init__(*args, **kwargs)
        self.service = getUtility(IService, 'sharing')

    @property
    def page_title(self):
        return self.label

    @cachedproperty
    def all_blocked(self):
        return self.context.all_blocked(self.user)

    @cachedproperty
    def all_deps(self):
        return self.context.all_deps(self.user)

    @cachedproperty
    def dependencies(self):
        deps = list(self.context.dependencies)
        if self.user:
            (ignore, ignore, deps) = self.service.getVisibleArtifacts(
                self.user, specifications=deps)
        else:
            deps = [d for d in deps if
                d.information_type == InformationType.PUBLIC]
        return deps

    @cachedproperty
    def blocked_specs(self):
        blocked = list(self.context.blocked_specs)
        if self.user:
            (ignore, ignore, blocked) = self.service.getVisibleArtifacts(
                self.user, specifications=blocked)
        else:
            blocked = [b for b in blocked if
                b.information_type == InformationType.PUBLIC]
        return blocked
