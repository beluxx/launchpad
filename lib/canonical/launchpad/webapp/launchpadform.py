# Copyright 2005 Canonical Ltd.  All rights reserved.

"""Launchpad Form View Classes
"""

__docformat__ = 'restructuredtext'

__all__ = [
    'GeneralFormView',
    'GeneralFormViewFactory',
    'NoRenderingOnRedirect',
    ]

import transaction
from zope.interface import Interface
from zope.schema import getFieldNamesInOrder
from zope.publisher.interfaces.browser import IBrowserRequest
from zope.security.checker import defineChecker, NamesChecker

from zope.app import zapi
from zope.app.form.interfaces import (
    IInputWidget, WidgetsError, ErrorContainer)
from zope.app.pagetemplate.viewpagetemplatefile import ViewPageTemplateFile
from zope.app.pagetemplate.simpleviewclass import SimpleViewClass
from zope.app.form.utility import setUpWidgets, getWidgetsData

from zope.formlib import form

from canonical.launchpad import _
from canonical.launchpad.webapp.publisher import LaunchpadView


class LaunchpadFormView(LaunchpadView):

    # the prefix used for all form inputs.
    prefix = 'field'

    # the form schema
    schema = None

    # the next URL to redirect to on successful form submission
    next_url = None

    errors = ()
    actions = ()

    def initialize(self):
        self.setUpFields()
        self.setUpWidgets()
        self.form_reset = False

        # validation performed before Zope 3 validation
        try:
            self.validateFromRequest()
        except WidgetsError, errors:
            self.errors = errors
            self._abortAndSetStatus()
            return
            
        data = {}
        errors, actions = handleSubmit(self.actions, data, self._validate)

        if errors:
            action.failure(data, errors)
            self._abortAndSetStatus()
        elif errors is not None:
            action.success(data)
            if self.next_url:
                self.request.response.redirect(self.next_url)
        
    def render(self):
        if self.request.response.getStatus() in [302, 303]:
            # Don't render the page on redirects.
            return u''
        else:
            LaunchpadView.render(self)

    def _abortAndSetStatus(self):
        """Abort the current transaction and set self.process_status."""
        self.process_status = _("Please fix the problems below and try again.")
        # XXX: 20060802 jamesh
        # This should really be dooming the transaction rather than
        # aborting -- we want to make sure anything further raises an
        # error rather than succeeds.
        transaction.abort()

    def setUpFields(self):
        assert schema is not None, "Schema must be set for LaunchpadFormView"
        # XXX: 20060802 jamesh
        # expose omit_readonly=True ??
        self.form_fields = form.Fields(self.schema)

    def setUpWidgets(self):
        # XXX: 20060802 jamesh
        # do we want to do anything with ignore_request?
        self.widgets = form.setUpWidgets(
            self.form_fields, self.prefix, self.context, self.request,
            data=initial_values, ignore_request=False)

    @property
    def initial_values(self):
        """Override this in your subclass if you want any widgets to have
        initial values.
        """
        return {}

    def _validate(self, action, data):
        widget_errors = form.getWidgetsData(self.widgets, self.prefix, data)
        form_errors = form.checkInvariants(self.form_fields, data)
        try:
            self.validate(data)
        except WidgetsError, errors:
            form_errors += errors

        self.errors = widget_errors + form_errors
        self.top_of_page_errors = form_errors
        return self.errors

    def validateFromRequest(self):
        """Validate the data, using self.request directly.

        Override this method if you want to do validation *before* Zope 3 widget
        validation is done.
        """

    def validate(self, data):
        """Validate the form.

        If errors are encountered, a WidgetsError exception is raised.

        Returns a dict of fieldname:value pairs if all form data
        submitted is valid.

        Override this method if you want to do validation *after* Zope 3 widget
        validation has already been done.
        """
        pass

