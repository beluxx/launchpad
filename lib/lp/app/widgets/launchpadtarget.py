# Copyright 2009-2020 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from zope.browserpage import ViewPageTemplateFile
from zope.component import getUtility
from zope.formlib.interfaces import (
    ConversionError,
    IInputWidget,
    InputErrors,
    MissingInputError,
    WidgetInputError,
    )
from zope.formlib.utility import setUpWidget
from zope.formlib.widget import (
    BrowserWidget,
    CustomWidgetFactory,
    InputWidget,
    renderElement,
    )
from zope.interface import implementer
from zope.schema import Choice

from lp.app.errors import (
    NotFoundError,
    UnexpectedFormData,
    )
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.app.validators import LaunchpadValidationError
from lp.app.widgets.itemswidgets import LaunchpadDropdownWidget
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.distributionsourcepackage import (
    IDistributionSourcePackage,
    )
from lp.registry.interfaces.ociproject import IOCIProject
from lp.registry.interfaces.product import IProduct
from lp.services.features import getFeatureFlag
from lp.services.webapp.interfaces import (
    IAlwaysSubmittedWidget,
    IMultiLineWidgetLayout,
    )


@implementer(IAlwaysSubmittedWidget, IMultiLineWidgetLayout, IInputWidget)
class LaunchpadTargetWidget(BrowserWidget, InputWidget):
    """Widget for selecting a product, distribution, package target or OCI
    project (the last is disabled by default).

    To enable OCIProject as target, subclass LaunchpadTargetWidget and set
    `show_ociproject` to True.
    """

    template = ViewPageTemplateFile('templates/launchpad-target.pt')
    default_option = "package"
    _widgets_set_up = False
    show_ociproject = False

    def getDistributionVocabulary(self):
        return 'Distribution'

    def getProductVocabulary(self):
        return 'Product'

    def getOCIProjectVocabulary(self):
        return 'OCIProject'

    def setUpSubWidgets(self):
        if self._widgets_set_up:
            return
        if bool(getFeatureFlag('disclosure.dsp_picker.enabled')):
            # Replace the default field with a field that uses the better
            # vocabulary.
            package_vocab = 'DistributionSourcePackage'
        else:
            package_vocab = 'BinaryAndSourcePackageName'
        fields = [
            Choice(
                __name__='product', title=u'Project',
                required=True, vocabulary=self.getProductVocabulary()),
            Choice(
                __name__='distribution', title=u"Distribution",
                required=True, vocabulary=self.getDistributionVocabulary(),
                default=getUtility(ILaunchpadCelebrities).ubuntu),
            Choice(
                __name__='package', title=u"Package",
                required=False, vocabulary=package_vocab),
            ]
        if self.show_ociproject:
            fields.append(Choice(
                __name__='ociproject', title=u"OCI project",
                required=False, vocabulary=self.getOCIProjectVocabulary()))
        self.distribution_widget = CustomWidgetFactory(
            LaunchpadDropdownWidget)
        for field in fields:
            setUpWidget(
                self, field.__name__, field, IInputWidget, prefix=self.name)
        self._widgets_set_up = True

    def setUpOptions(self):
        """Set up options to be rendered."""
        self.options = {}
        option_names = ['package', 'product']
        if self.show_ociproject:
            option_names.append('ociproject')
        for option in option_names:
            attributes = dict(
                type='radio', name=self.name, value=option,
                id='%s.option.%s' % (self.name, option))
            if self.request.form_ng.getOne(
                     self.name, self.default_option) == option:
                attributes['checked'] = 'checked'
            self.options[option] = renderElement('input', **attributes)
        self.package_widget.onKeyPress = (
            "selectWidget('%s.option.package', event)" % self.name)
        self.product_widget.onKeyPress = (
            "selectWidget('%s.option.product', event)" % self.name)

    def hasInput(self):
        return self.name in self.request.form

    def hasValidInput(self):
        """See zope.formlib.interfaces.IInputWidget."""
        try:
            self.getInputValue()
            return True
        except InputErrors:
            return False
        except UnexpectedFormData:
            return False

    def getInputValue(self):
        """See zope.formlib.interfaces.IInputWidget."""
        self.setUpSubWidgets()
        form_value = self.request.form_ng.getOne(self.name)
        if form_value == 'product':
            try:
                return self.product_widget.getInputValue()
            except MissingInputError:
                self._error = WidgetInputError(
                    self.name, self.label,
                    LaunchpadValidationError('Please enter a project name'))
                raise self._error
            except ConversionError:
                entered_name = self.request.form_ng.getOne(
                    "%s.product" % self.name)
                self._error = WidgetInputError(
                    self.name, self.label,
                    LaunchpadValidationError(
                        "There is no project named '%s' registered in"
                        " Launchpad" % entered_name))
                raise self._error
        if form_value == 'ociproject':
            try:
                return self.ociproject_widget.getInputValue()
            except MissingInputError:
                self._error = WidgetInputError(
                    self.name, self.label,
                    LaunchpadValidationError(
                        'Please enter an OCI project name'))
                raise self._error
            except ConversionError:
                entered_name = self.request.form_ng.getOne(
                    "%s.ociproject" % self.name)
                self._error = WidgetInputError(
                    self.name, self.label,
                    LaunchpadValidationError(
                        "There is no OCI project named '%s' registered in"
                        " Launchpad" % entered_name))
                raise self._error
        elif form_value == 'package':
            try:
                distribution = self.distribution_widget.getInputValue()
            except ConversionError:
                entered_name = self.request.form_ng.getOne(
                    "%s.distribution" % self.name)
                self._error = WidgetInputError(
                    self.name, self.label,
                    LaunchpadValidationError(
                        "There is no distribution named '%s' registered in"
                        " Launchpad" % entered_name))
                raise self._error
            if self.package_widget.hasInput():
                if bool(getFeatureFlag('disclosure.dsp_picker.enabled')):
                    self.package_widget.vocabulary.setDistribution(
                        distribution)
                try:
                    package_name = self.package_widget.getInputValue()
                    if package_name is None:
                        return distribution
                    if IDistributionSourcePackage.providedBy(package_name):
                        dsp = package_name
                    else:
                        source_name = (
                            distribution.guessPublishedSourcePackageName(
                                package_name.name))
                        dsp = distribution.getSourcePackage(source_name)
                except (ConversionError, NotFoundError):
                    entered_name = self.request.form_ng.getOne(
                        '%s.package' % self.name)
                    self._error = WidgetInputError(
                        self.name, self.label,
                        LaunchpadValidationError(
                            "There is no package named '%s' published in %s."
                            % (entered_name, distribution.displayname)))
                    raise self._error
                return dsp
            else:
                return distribution
        else:
            raise UnexpectedFormData("No valid option was selected.")

    def setRenderedValue(self, value):
        """See IWidget."""
        self.setUpSubWidgets()
        if IProduct.providedBy(value):
            self.default_option = 'product'
            self.product_widget.setRenderedValue(value)
        elif IDistribution.providedBy(value):
            self.default_option = 'package'
            self.distribution_widget.setRenderedValue(value)
        elif IDistributionSourcePackage.providedBy(value):
            self.default_option = 'package'
            self.distribution_widget.setRenderedValue(value.distribution)
            self.package_widget.setRenderedValue(value.sourcepackagename)
        elif IOCIProject.providedBy(value):
            self.default_option = 'ociproject'
            self.ociproject_widget.setRenderedValue(value)
        else:
            raise AssertionError('Not a valid value: %r' % value)

    def __call__(self):
        """See zope.formlib.interfaces.IBrowserWidget."""
        self.setUpSubWidgets()
        self.setUpOptions()
        return self.template()
