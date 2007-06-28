# Copyright 2007 Canonical Ltd.  All rights reserved.

"""Broswer views for CodeImports."""

__metaclass__ = type

__all__ = [
    'CodeImportSetNavigation',
    'CodeImportSetView',
    'CodeImportView',
    ]


from canonical.launchpad import _
from canonical.launchpad.interfaces import ICodeImportSet
from canonical.launchpad.webapp import LaunchpadView, Navigation
from canonical.launchpad.webapp.batching import BatchNavigator
from canonical.widgets import LaunchpadDropdownWidget

from zope.app.form import CustomWidgetFactory
from zope.app.form.interfaces import IInputWidget
from zope.app.form.utility import setUpWidget
from zope.schema import Choice

import operator


class CodeImportSetNavigation(Navigation):

    usedfor = ICodeImportSet

    def breadcrumb(self):
        return "Code Imports"

    def traverse(self, id):
        try:
            return self.context.get(id)
        except LookupError:
            return None


class ReviewStatusDropdownWidget(LaunchpadDropdownWidget):
    """A DropdownWidget that says 'Any' instead of '(no value)'."""
    _messageNoValue = _('Any')


class CodeImportSetView(LaunchpadView):
    def initialize(self):
        # ICodeImport['review_status'].required is True, which means the
        # generated <select> widget lacks a 'no choice' option.
        status_field = Choice(
            __name__='status', title=_("Review Status"),
            vocabulary='CodeImportReviewStatus', required=False)
        self.status_widget = CustomWidgetFactory(ReviewStatusDropdownWidget)
        setUpWidget(self, 'status',  status_field, IInputWidget)

        status = None
        if self.status_widget.hasValidInput():
            status = self.status_widget.getInputValue()

        if status is not None:
            imports = self.context.search(review_status=status)
        else:
            imports = self.context.getAll()

        imports = sorted(imports, key=operator.attrgetter('id'))

        self.batchnav = BatchNavigator(imports, self.request)


class CodeImportView(LaunchpadView):
    def initialize(self):
        self.title = "Code Import for %s"%(self.context.product.name,)
