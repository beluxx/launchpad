# Copyright 2015-2019 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Snap views."""

__metaclass__ = type
__all__ = [
    'SnapAddView',
    'SnapAuthorizeView',
    'SnapContextMenu',
    'SnapDeleteView',
    'SnapEditView',
    'SnapNavigation',
    'SnapNavigationMenu',
    'SnapRequestBuildsView',
    'SnapView',
    ]

from urllib import urlencode

from lazr.restful.fields import Reference
from lazr.restful.interface import (
    copy_field,
    use_template,
    )
from zope.component import getUtility
from zope.error.interfaces import IErrorReportingUtility
from zope.formlib.widget import CustomWidgetFactory
from zope.interface import Interface
from zope.schema import (
    Choice,
    Dict,
    List,
    TextLine,
    )

from lp import _
from lp.app.browser.launchpadform import (
    action,
    LaunchpadEditFormView,
    LaunchpadFormView,
    render_radio_widget_part,
    )
from lp.app.browser.lazrjs import InlinePersonEditPickerWidget
from lp.app.browser.tales import format_link
from lp.app.enums import PRIVATE_INFORMATION_TYPES
from lp.app.interfaces.informationtype import IInformationType
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.app.widgets.itemswidgets import (
    LabeledMultiCheckBoxWidget,
    LaunchpadDropdownWidget,
    LaunchpadRadioWidget,
    )
from lp.buildmaster.interfaces.processor import IProcessorSet
from lp.code.browser.widgets.gitref import GitRefWidget
from lp.code.interfaces.gitref import IGitRef
from lp.registry.enums import VCSType
from lp.registry.interfaces.pocket import PackagePublishingPocket
from lp.services.features import getFeatureFlag
from lp.services.propertycache import cachedproperty
from lp.services.scripts import log
from lp.services.utils import seconds_since_epoch
from lp.services.webapp import (
    canonical_url,
    ContextMenu,
    enabled_with_permission,
    LaunchpadView,
    Link,
    Navigation,
    NavigationMenu,
    stepthrough,
    structured,
    )
from lp.services.webapp.breadcrumb import (
    Breadcrumb,
    NameBreadcrumb,
    )
from lp.services.webapp.url import urlappend
from lp.services.webhooks.browser import WebhookTargetNavigationMixin
from lp.snappy.browser.widgets.snaparchive import SnapArchiveWidget
from lp.snappy.browser.widgets.snapbuildchannels import (
    SnapBuildChannelsWidget,
    )
from lp.snappy.browser.widgets.storechannels import StoreChannelsWidget
from lp.snappy.interfaces.snap import (
    CannotAuthorizeStoreUploads,
    CannotFetchSnapcraftYaml,
    CannotParseSnapcraftYaml,
    ISnap,
    ISnapSet,
    MissingSnapcraftYaml,
    NoSuchSnap,
    SNAP_PRIVATE_FEATURE_FLAG,
    SnapPrivateFeatureDisabled,
    )
from lp.snappy.interfaces.snapbuild import ISnapBuildSet
from lp.snappy.interfaces.snappyseries import (
    ISnappyDistroSeriesSet,
    ISnappySeriesSet,
    )
from lp.snappy.interfaces.snapstoreclient import (
    BadRequestPackageUploadResponse,
    )
from lp.soyuz.browser.archive import EnableProcessorsMixin
from lp.soyuz.browser.build import get_build_by_id_str
from lp.soyuz.interfaces.archive import IArchive


class SnapNavigation(WebhookTargetNavigationMixin, Navigation):
    usedfor = ISnap

    @stepthrough('+build-request')
    def traverse_build_request(self, name):
        try:
            job_id = int(name)
        except ValueError:
            return None
        return self.context.getBuildRequest(job_id)

    @stepthrough('+build')
    def traverse_build(self, name):
        build = get_build_by_id_str(ISnapBuildSet, name)
        if build is None or build.snap != self.context:
            return None
        return build


class SnapBreadcrumb(NameBreadcrumb):

    @property
    def inside(self):
        return Breadcrumb(
            self.context.owner,
            url=canonical_url(self.context.owner, view_name="+snaps"),
            text="Snap packages", inside=self.context.owner)


class SnapNavigationMenu(NavigationMenu):
    """Navigation menu for snap packages."""

    usedfor = ISnap

    facet = 'overview'

    links = ('admin', 'edit', 'webhooks', 'delete')

    @enabled_with_permission('launchpad.Admin')
    def admin(self):
        return Link('+admin', 'Administer snap package', icon='edit')

    @enabled_with_permission('launchpad.Edit')
    def edit(self):
        return Link('+edit', 'Edit snap package', icon='edit')

    @enabled_with_permission('launchpad.Edit')
    def webhooks(self):
        return Link(
            '+webhooks', 'Manage webhooks', icon='edit',
            enabled=bool(getFeatureFlag('webhooks.new.enabled')))

    @enabled_with_permission('launchpad.Edit')
    def delete(self):
        return Link('+delete', 'Delete snap package', icon='trash-icon')


class SnapContextMenu(ContextMenu):
    """Context menu for snap packages."""

    usedfor = ISnap

    facet = 'overview'

    links = ('request_builds',)

    @enabled_with_permission('launchpad.Edit')
    def request_builds(self):
        return Link('+request-builds', 'Request builds', icon='add')


class SnapView(LaunchpadView):
    """Default view of a Snap."""

    @cachedproperty
    def builds_and_requests(self):
        return builds_and_requests_for_snap(self.context)

    @property
    def person_picker(self):
        field = copy_field(
            ISnap['owner'],
            vocabularyName='AllUserTeamsParticipationPlusSelfSimpleDisplay')
        return InlinePersonEditPickerWidget(
            self.context, field, format_link(self.context.owner),
            header='Change owner', step_title='Select a new owner')

    @property
    def build_frequency(self):
        if self.context.auto_build:
            return 'Built automatically'
        else:
            return 'Built on request'

    @property
    def sorted_auto_build_channels_items(self):
        if self.context.auto_build_channels is None:
            return []
        return sorted(self.context.auto_build_channels.items())

    @property
    def store_channels(self):
        return ', '.join(self.context.store_channels)


def builds_and_requests_for_snap(snap):
    """A list of interesting builds and build requests.

    All pending builds and pending build requests are shown, as well as up
    to 10 recent builds and recent failed build requests.  Pending items are
    ordered by the date they were created; recent items are ordered by the
    date they finished (if available) or the date they started (if the date
    they finished is not set due to an error).  This allows started but
    unfinished builds to show up in the view but be discarded as more recent
    builds become available.

    Builds that the user does not have permission to see are excluded (by
    the model code).
    """
    # We need to interleave items of different types, so SQL can't do all
    # the sorting for us.
    def make_sort_key(*date_attrs):
        def _sort_key(item):
            for date_attr in date_attrs:
                if getattr(item, date_attr, None) is not None:
                    return -seconds_since_epoch(getattr(item, date_attr))
            return 0

        return _sort_key

    items = sorted(
        list(snap.pending_builds) + list(snap.pending_build_requests),
        key=make_sort_key("date_created", "date_requested"))
    if len(items) < 10:
        # We need to interleave two unbounded result sets, but we only need
        # enough items from them to make the total count up to 10.  It's
        # simplest to just fetch the upper bound from each set and do our
        # own sorting.
        recent_items = sorted(
            list(snap.completed_builds[:10 - len(items)]) +
            list(snap.failed_build_requests[:10 - len(items)]),
            key=make_sort_key(
                "date_finished", "date_started",
                "date_created", "date_requested"))
        items.extend(recent_items[:10 - len(items)])
    return items


class SnapRequestBuildsView(LaunchpadFormView):
    """A view for requesting builds of a snap package."""

    @property
    def label(self):
        return 'Request builds for %s' % self.context.name

    page_title = 'Request builds'

    class schema(Interface):
        """Schema for requesting a build."""

        archive = Reference(IArchive, title=u'Source archive', required=True)
        distro_arch_series = List(
            Choice(vocabulary='SnapDistroArchSeries'),
            title=u'Architectures', required=True,
            description=(
                u'If you do not explicitly select any architectures, then '
                u'the snap package will be built for all architectures '
                u'allowed by its configuration.'))
        pocket = Choice(
            title=u'Pocket', vocabulary=PackagePublishingPocket, required=True,
            description=(
                u'The package stream within the source distribution series '
                u'to use when building the snap package.'))
        channels = Dict(
            title=u'Source snap channels', key_type=TextLine(), required=True,
            description=ISnap['auto_build_channels'].description)

    custom_widget_archive = SnapArchiveWidget
    custom_widget_distro_arch_series = LabeledMultiCheckBoxWidget
    custom_widget_pocket = LaunchpadDropdownWidget
    custom_widget_channels = SnapBuildChannelsWidget

    help_links = {
        "pocket": u"/+help-snappy/snap-build-pocket.html",
        }

    @property
    def cancel_url(self):
        return canonical_url(self.context)

    @property
    def initial_values(self):
        """See `LaunchpadFormView`."""
        return {
            'archive': (
                # XXX cjwatson 2019-02-04: In order to support non-Ubuntu
                # bases, we'd need to store this as None and infer it based
                # on the inferred distro series; but this will do for now.
                getUtility(ILaunchpadCelebrities).ubuntu.main_archive
                if self.context.distro_series is None
                else self.context.distro_series.main_archive),
            'distro_arch_series': [],
            'pocket': PackagePublishingPocket.UPDATES,
            'channels': self.context.auto_build_channels,
            }

    @action('Request builds', name='request')
    def request_action(self, action, data):
        if data.get('distro_arch_series', []):
            architectures = [
                arch.architecturetag for arch in data['distro_arch_series']]
        else:
            architectures = None
        self.context.requestBuilds(
            self.user, data['archive'], data['pocket'],
            architectures=architectures, channels=data['channels'])
        self.request.response.addNotification(
            _('Builds will be dispatched soon.'))
        self.next_url = self.cancel_url


class ISnapEditSchema(Interface):
    """Schema for adding or editing a snap package."""

    use_template(ISnap, include=[
        'owner',
        'name',
        'private',
        'require_virtualized',
        'allow_internet',
        'build_source_tarball',
        'auto_build',
        'auto_build_channels',
        'store_upload',
        ])
    store_distro_series = Choice(
        vocabulary='BuildableSnappyDistroSeries', required=True,
        title=u'Series')
    vcs = Choice(vocabulary=VCSType, required=True, title=u'VCS')

    # Each of these is only required if vcs has an appropriate value.  Later
    # validation takes care of adjusting the required attribute.
    branch = copy_field(ISnap['branch'], required=True)
    git_ref = copy_field(ISnap['git_ref'], required=True)

    # These are only required if auto_build is True.  Later validation takes
    # care of adjusting the required attribute.
    auto_build_archive = copy_field(ISnap['auto_build_archive'], required=True)
    auto_build_pocket = copy_field(ISnap['auto_build_pocket'], required=True)

    # This is only required if store_upload is True.  Later validation takes
    # care of adjusting the required attribute.
    store_name = copy_field(ISnap['store_name'], required=True)
    store_channels = copy_field(ISnap['store_channels'], required=True)


def log_oops(error, request):
    """Log an oops report without raising an error."""
    info = (error.__class__, error, None)
    getUtility(IErrorReportingUtility).raising(info, request)


class SnapAuthorizeMixin:

    def requestAuthorization(self, snap):
        try:
            self.next_url = SnapAuthorizeView.requestAuthorization(
                snap, self.request)
        except BadRequestPackageUploadResponse as e:
            self.setFieldError(
                'store_upload',
                'Cannot get permission from the store to upload this package.')
            log_oops(e, self.request)


class SnapAddView(
        LaunchpadFormView, SnapAuthorizeMixin, EnableProcessorsMixin):
    """View for creating snap packages."""

    page_title = label = 'Create a new snap package'

    schema = ISnapEditSchema
    field_names = [
        'owner',
        'name',
        'store_distro_series',
        'build_source_tarball',
        'auto_build',
        'auto_build_archive',
        'auto_build_pocket',
        'auto_build_channels',
        'store_upload',
        'store_name',
        'store_channels',
        ]
    custom_widget_store_distro_series = LaunchpadRadioWidget
    custom_widget_auto_build_archive = SnapArchiveWidget
    custom_widget_auto_build_pocket = LaunchpadDropdownWidget
    custom_widget_auto_build_channels = SnapBuildChannelsWidget
    custom_widget_store_channels = StoreChannelsWidget

    help_links = {
        "auto_build_pocket": u"/+help-snappy/snap-build-pocket.html",
        }

    def initialize(self):
        """See `LaunchpadView`."""
        super(SnapAddView, self).initialize()

        # Once initialized, if the private_snap flag is disabled, it
        # prevents snap creation for private contexts.
        if not getFeatureFlag(SNAP_PRIVATE_FEATURE_FLAG):
            if (IInformationType.providedBy(self.context) and
                self.context.information_type in PRIVATE_INFORMATION_TYPES):
                raise SnapPrivateFeatureDisabled

    def setUpFields(self):
        """See `LaunchpadFormView`."""
        super(SnapAddView, self).setUpFields()
        self.form_fields += self.createEnabledProcessors(
            getUtility(IProcessorSet).getAll(),
            u"The architectures that this snap package builds for. Some "
            u"architectures are restricted and may only be enabled or "
            u"disabled by administrators.")

    def setUpWidgets(self):
        """See `LaunchpadFormView`."""
        super(SnapAddView, self).setUpWidgets()
        self.widgets['processors'].widget_class = 'processors'

    @property
    def cancel_url(self):
        return canonical_url(self.context)

    @property
    def initial_values(self):
        store_name = None
        if self.has_snappy_distro_series:
            # Try to extract Snap store name from snapcraft.yaml file.
            try:
                snapcraft_data = getUtility(ISnapSet).getSnapcraftYaml(
                    self.context, logger=log)
            except (MissingSnapcraftYaml, CannotFetchSnapcraftYaml,
                    CannotParseSnapcraftYaml):
                pass
            else:
                store_name = snapcraft_data.get('name')

        store_series = getUtility(ISnappySeriesSet).getAll().first()
        if store_series.can_infer_distro_series:
            distro_series = None
        elif store_series.preferred_distro_series is not None:
            distro_series = store_series.preferred_distro_series
        else:
            distro_series = store_series.usable_distro_series.first()
        sds_set = getUtility(ISnappyDistroSeriesSet)
        store_distro_series = sds_set.getByBothSeries(
            store_series, distro_series)

        return {
            'store_name': store_name,
            'owner': self.user,
            'store_distro_series': store_distro_series,
            'processors': [
                p for p in getUtility(IProcessorSet).getAll()
                if p.build_by_default],
            'auto_build_archive': (
                # XXX cjwatson 2019-02-04: In order to support non-Ubuntu
                # bases, we'd need to store this as None and infer it based
                # on the inferred distro series; but this will do for now.
                getUtility(ILaunchpadCelebrities).ubuntu.main_archive
                if distro_series is None
                else distro_series.main_archive),
            'auto_build_pocket': PackagePublishingPocket.UPDATES,
            }

    @property
    def has_snappy_distro_series(self):
        return not getUtility(ISnappyDistroSeriesSet).getAll().is_empty()

    def validate_widgets(self, data, names=None):
        """See `LaunchpadFormView`."""
        if self.widgets.get('auto_build') is not None:
            # Set widgets as required or optional depending on the
            # auto_build field.
            super(SnapAddView, self).validate_widgets(data, ['auto_build'])
            auto_build = data.get('auto_build', False)
            self.widgets['auto_build_archive'].context.required = auto_build
            self.widgets['auto_build_pocket'].context.required = auto_build
        if self.widgets.get('store_upload') is not None:
            # Set widgets as required or optional depending on the
            # store_upload field.
            super(SnapAddView, self).validate_widgets(data, ['store_upload'])
            store_upload = data.get('store_upload', False)
            self.widgets['store_name'].context.required = store_upload
            self.widgets['store_channels'].context.required = store_upload
        super(SnapAddView, self).validate_widgets(data, names=names)

    @action('Create snap package', name='create')
    def create_action(self, action, data):
        if IGitRef.providedBy(self.context):
            kwargs = {'git_ref': self.context}
        else:
            kwargs = {'branch': self.context}
        private = not getUtility(
            ISnapSet).isValidPrivacy(False, data['owner'], **kwargs)
        if not data.get('auto_build', False):
            data['auto_build_archive'] = None
            data['auto_build_pocket'] = None
        snap = getUtility(ISnapSet).new(
            self.user, data['owner'],
            data['store_distro_series'].distro_series, data['name'],
            auto_build=data['auto_build'],
            auto_build_archive=data['auto_build_archive'],
            auto_build_pocket=data['auto_build_pocket'],
            auto_build_channels=data['auto_build_channels'],
            processors=data['processors'], private=private,
            build_source_tarball=data['build_source_tarball'],
            store_upload=data['store_upload'],
            store_series=data['store_distro_series'].snappy_series,
            store_name=data['store_name'],
            store_channels=data.get('store_channels'), **kwargs)
        if data['store_upload']:
            self.requestAuthorization(snap)
        else:
            self.next_url = canonical_url(snap)

    def validate(self, data):
        super(SnapAddView, self).validate(data)
        owner = data.get('owner', None)
        name = data.get('name', None)
        if owner and name:
            if getUtility(ISnapSet).exists(owner, name):
                self.setFieldError(
                    'name',
                    'There is already a snap package owned by %s with this '
                    'name.' % owner.displayname)


class BaseSnapEditView(LaunchpadEditFormView, SnapAuthorizeMixin):

    schema = ISnapEditSchema

    @property
    def cancel_url(self):
        return canonical_url(self.context)

    def setUpWidgets(self):
        """See `LaunchpadFormView`."""
        super(BaseSnapEditView, self).setUpWidgets()
        widget = self.widgets.get('vcs')
        if widget is not None:
            current_value = widget._getFormValue()
            self.vcs_bzr_radio, self.vcs_git_radio = [
                render_radio_widget_part(widget, value, current_value)
                for value in (VCSType.BZR, VCSType.GIT)]

    @property
    def has_snappy_distro_series(self):
        return not getUtility(ISnappyDistroSeriesSet).getAll().is_empty()

    def validate_widgets(self, data, names=None):
        """See `LaunchpadFormView`."""
        if self.widgets.get('vcs') is not None:
            # Set widgets as required or optional depending on the vcs
            # field.
            super(BaseSnapEditView, self).validate_widgets(data, ['vcs'])
            vcs = data.get('vcs')
            if vcs == VCSType.BZR:
                self.widgets['branch'].context.required = True
                self.widgets['git_ref'].context.required = False
            elif vcs == VCSType.GIT:
                self.widgets['branch'].context.required = False
                self.widgets['git_ref'].context.required = True
            else:
                raise AssertionError("Unknown branch type %s" % vcs)
        if self.widgets.get('auto_build') is not None:
            # Set widgets as required or optional depending on the
            # auto_build field.
            super(BaseSnapEditView, self).validate_widgets(
                data, ['auto_build'])
            auto_build = data.get('auto_build', False)
            self.widgets['auto_build_archive'].context.required = auto_build
            self.widgets['auto_build_pocket'].context.required = auto_build
        if self.widgets.get('store_upload') is not None:
            # Set widgets as required or optional depending on the
            # store_upload field.
            super(BaseSnapEditView, self).validate_widgets(
                data, ['store_upload'])
            store_upload = data.get('store_upload', False)
            self.widgets['store_name'].context.required = store_upload
            self.widgets['store_channels'].context.required = store_upload
        super(BaseSnapEditView, self).validate_widgets(data, names=names)

    def validate(self, data):
        super(BaseSnapEditView, self).validate(data)
        if data.get('private', self.context.private) is False:
            if 'private' in data or 'owner' in data:
                owner = data.get('owner', self.context.owner)
                if owner is not None and owner.private:
                    self.setFieldError(
                        'private' if 'private' in data else 'owner',
                        u'A public snap cannot have a private owner.')
            if 'private' in data or 'branch' in data:
                branch = data.get('branch', self.context.branch)
                if branch is not None and branch.private:
                    self.setFieldError(
                        'private' if 'private' in data else 'branch',
                        u'A public snap cannot have a private branch.')
            if 'private' in data or 'git_ref' in data:
                ref = data.get('git_ref', self.context.git_ref)
                if ref is not None and ref.private:
                    self.setFieldError(
                        'private' if 'private' in data else 'git_ref',
                        u'A public snap cannot have a private repository.')

    def _needStoreReauth(self, data):
        """Does this change require reauthorizing to the store?"""
        store_upload = data.get('store_upload', False)
        store_distro_series = data.get('store_distro_series')
        store_name = data.get('store_name')
        if (not store_upload or
                store_distro_series is None or store_name is None):
            return False
        if not self.context.store_upload:
            return True
        if store_distro_series.snappy_series != self.context.store_series:
            return True
        if store_name != self.context.store_name:
            return True
        return False

    @action('Update snap package', name='update')
    def request_action(self, action, data):
        vcs = data.pop('vcs', None)
        if vcs == VCSType.BZR:
            data['git_ref'] = None
        elif vcs == VCSType.GIT:
            data['branch'] = None
        new_processors = data.get('processors')
        if new_processors is not None:
            if set(self.context.processors) != set(new_processors):
                self.context.setProcessors(
                    new_processors, check_permissions=True, user=self.user)
            del data['processors']
        if not data.get('auto_build', False):
            if 'auto_build_archive' in data:
                del data['auto_build_archive']
            if 'auto_build_pocket' in data:
                del data['auto_build_pocket']
            if 'auto_build_channels' in data:
                del data['auto_build_channels']
        store_upload = data.get('store_upload', False)
        if not store_upload:
            if 'store_name' in data:
                del data['store_name']
            if 'store_channels' in data:
                del data['store_channels']
        need_store_reauth = self._needStoreReauth(data)
        self.updateContextFromData(data)
        if need_store_reauth:
            self.requestAuthorization(self.context)
        else:
            self.next_url = canonical_url(self.context)

    @property
    def adapters(self):
        """See `LaunchpadFormView`."""
        return {ISnapEditSchema: self.context}


class SnapAdminView(BaseSnapEditView):
    """View for administering snap packages."""

    @property
    def label(self):
        return 'Administer %s snap package' % self.context.name

    page_title = 'Administer'

    field_names = ['private', 'require_virtualized', 'allow_internet']

    def validate(self, data):
        super(SnapAdminView, self).validate(data)
        # BaseSnapEditView.validate checks the rules for 'private' in
        # combination with other attributes.
        if data.get('private', None) is True:
            if not getFeatureFlag(SNAP_PRIVATE_FEATURE_FLAG):
                self.setFieldError(
                    'private',
                    u'You do not have permission to create private snaps.')


class SnapEditView(BaseSnapEditView, EnableProcessorsMixin):
    """View for editing snap packages."""

    @property
    def label(self):
        return 'Edit %s snap package' % self.context.name

    page_title = 'Edit'

    field_names = [
        'owner',
        'name',
        'store_distro_series',
        'vcs',
        'branch',
        'git_ref',
        'build_source_tarball',
        'auto_build',
        'auto_build_archive',
        'auto_build_pocket',
        'auto_build_channels',
        'store_upload',
        'store_name',
        'store_channels',
        ]
    custom_widget_store_distro_series = LaunchpadRadioWidget
    custom_widget_vcs = LaunchpadRadioWidget
    custom_widget_git_ref = CustomWidgetFactory(
        GitRefWidget, allow_external=True)
    custom_widget_auto_build_archive = SnapArchiveWidget
    custom_widget_auto_build_pocket = LaunchpadDropdownWidget
    custom_widget_auto_build_channels = SnapBuildChannelsWidget
    custom_widget_store_channels = StoreChannelsWidget

    help_links = {
        "auto_build_pocket": u"/+help-snappy/snap-build-pocket.html",
        }

    def setUpFields(self):
        """See `LaunchpadFormView`."""
        super(SnapEditView, self).setUpFields()
        self.form_fields += self.createEnabledProcessors(
            self.context.available_processors,
            u"The architectures that this snap package builds for. Some "
            u"architectures are restricted and may only be enabled or "
            u"disabled by administrators.")

    @property
    def initial_values(self):
        initial_values = {}
        if self.context.git_ref is not None:
            initial_values['vcs'] = VCSType.GIT
        else:
            initial_values['vcs'] = VCSType.BZR
        if self.context.auto_build_pocket is None:
            initial_values['auto_build_pocket'] = (
                PackagePublishingPocket.UPDATES)
        return initial_values

    def validate(self, data):
        super(SnapEditView, self).validate(data)
        owner = data.get('owner', None)
        name = data.get('name', None)
        if owner and name:
            try:
                snap = getUtility(ISnapSet).getByName(owner, name)
                if snap != self.context:
                    self.setFieldError(
                        'name',
                        'There is already a snap package owned by %s with '
                        'this name.' % owner.displayname)
            except NoSuchSnap:
                pass
        if 'processors' in data:
            available_processors = set(self.context.available_processors)
            widget = self.widgets['processors']
            for processor in self.context.processors:
                if processor not in data['processors']:
                    if processor not in available_processors:
                        # This processor is not currently available for
                        # selection, but is enabled.  Leave it untouched.
                        data['processors'].append(processor)
                    elif processor.name in widget.disabled_items:
                        # This processor is restricted and currently
                        # enabled. Leave it untouched.
                        data['processors'].append(processor)


class SnapAuthorizationException(Exception):
    pass


class SnapAuthorizeView(LaunchpadEditFormView):
    """View for authorizing snap package uploads to the store."""

    @property
    def label(self):
        return 'Authorize store uploads of %s' % self.context.name

    page_title = 'Authorize store uploads'

    class schema(Interface):
        """Schema for authorizing snap package uploads to the store."""

        discharge_macaroon = TextLine(
            title=u'Serialized discharge macaroon', required=True)

    render_context = False

    focusedElementScript = None

    @property
    def cancel_url(self):
        return canonical_url(self.context)

    @classmethod
    def requestAuthorization(cls, snap, request):
        """Begin the process of authorizing uploads of a snap package."""
        try:
            sso_caveat_id = snap.beginAuthorization()
            base_url = canonical_url(snap, view_name='+authorize')
            login_url = urlappend(base_url, '+login')
            login_url += '?%s' % urlencode([
                ('macaroon_caveat_id', sso_caveat_id),
                ('discharge_macaroon_action', 'field.actions.complete'),
                ('discharge_macaroon_field', 'field.discharge_macaroon'),
                ])
            return login_url
        except CannotAuthorizeStoreUploads as e:
            request.response.addInfoNotification(unicode(e))
            request.response.redirect(canonical_url(snap))
            return

    @action('Begin authorization', name='begin')
    def begin_action(self, action, data):
        login_url = self.requestAuthorization(self.context, self.request)
        if login_url is not None:
            self.request.response.redirect(login_url)

    @action('Complete authorization', name='complete')
    def complete_action(self, action, data):
        if not data.get('discharge_macaroon'):
            self.addError(structured(
                _(u'Uploads of %(snap)s to the store were not authorized.'),
                snap=self.context.name))
            return
        self.context.completeAuthorization(
            discharge_macaroon=data['discharge_macaroon'])
        self.request.response.addInfoNotification(structured(
            _(u'Uploads of %(snap)s to the store are now authorized.'),
            snap=self.context.name))
        self.request.response.redirect(canonical_url(self.context))

    @property
    def adapters(self):
        """See `LaunchpadFormView`."""
        return {self.schema: self.context}


class SnapDeleteView(BaseSnapEditView):
    """View for deleting snap packages."""

    @property
    def label(self):
        return 'Delete %s snap package' % self.context.name

    page_title = 'Delete'

    field_names = []

    @action('Delete snap package', name='delete')
    def delete_action(self, action, data):
        owner = self.context.owner
        self.context.destroySelf()
        self.next_url = canonical_url(owner, view_name='+snaps')
