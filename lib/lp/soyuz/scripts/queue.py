# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# pylint: disable-msg=W0231
"""Ftpmaster queue tool libraries."""

# XXX StuartBishop 2007-01-31:
# This should be renamed to ftpmasterqueue.py or just ftpmaster.py
# as Launchpad contains lots of queues.

__metaclass__ = type
__all__ = [
    'CommandRunner',
    'CommandRunnerError',
    'QueueActionError',
    'name_queue_map',
    ]

from datetime import datetime
import errno
import hashlib

import pytz
from zope.component import getUtility

from lp.app.browser.tales import DurationFormatterAPI
from lp.app.errors import NotFoundError
from lp.services.config import config
from lp.services.librarian.utils import filechunks
from lp.services.propertycache import cachedproperty
from lp.soyuz.enums import PackageUploadStatus
from lp.soyuz.interfaces.component import IComponentSet
from lp.soyuz.interfaces.queue import (
    IPackageUploadSet,
    QueueInconsistentStateError,
    )
from lp.soyuz.interfaces.section import ISectionSet


name_queue_map = {
    "new": PackageUploadStatus.NEW,
    "unapproved": PackageUploadStatus.UNAPPROVED,
    "accepted": PackageUploadStatus.ACCEPTED,
    "done": PackageUploadStatus.DONE,
    "rejected": PackageUploadStatus.REJECTED,
    }

#XXX cprov 2006-09-19: We need to use template engine instead of harcoded
# format variables.
HEAD = "-" * 9 + "|----|" + "-" * 22 + "|" + "-" * 22 + "|" + "-" * 15
FOOT_MARGIN = " " * (9 + 6 + 1 + 22 + 1 + 22 + 2)
RULE = "-" * (12 + 9 + 6 + 1 + 22 + 1 + 22 + 2)

FILTERMSG = """
    Omit the filter for all records.
    Filter string consists of a queue ID or a pair <name>[/<version>]:

    28
    apt
    apt/1

    Use '-e' command line argument for exact matches:

    -e apt
    -e apt/1.0-1
"""


class QueueActionError(Exception):
    """Identify Errors occurred within QueueAction class and its children."""


class QueueAction:
    """Queue Action base class.

    Implements a bunch of common/useful method designed to provide easy
    PackageUpload handling.
    """

    def __init__(self, distribution_name, suite_name, queue, terms,
                 component_name, section_name, priority_name,
                 display, no_mail=True, exact_match=False, log=None):
        """Initializes passed variables. """
        self.terms = terms
        # Some actions have addtional commands at the start of the terms
        # so allow them to state that here by specifiying the start index.
        self.terms_start_index = 0
        self.component_name = component_name
        self.section_name = section_name
        self.priority_name = priority_name
        self.exact_match = exact_match
        self.queue = queue
        self.no_mail = no_mail
        self.distribution_name = distribution_name
        self.suite_name = suite_name
        self.default_sender = "%s <%s>" % (
            config.uploader.default_sender_name,
            config.uploader.default_sender_address)
        self.default_recipient = "%s <%s>" % (
            config.uploader.default_recipient_name,
            config.uploader.default_recipient_address)
        self.display = display
        self.log = log

    @cachedproperty
    def size(self):
        """Return the size of the queue in question."""
        return getUtility(IPackageUploadSet).count(
            status=self.queue, distroseries=self.distroseries,
            pocket=self.pocket)

    def setDefaultContext(self):
        """Set default distribuiton, distroseries."""
        # if not found defaults to 'ubuntu'

        # Avoid circular imports.
        from lp.registry.interfaces.distribution import IDistributionSet
        from lp.registry.interfaces.pocket import PackagePublishingPocket

        distroset = getUtility(IDistributionSet)
        try:
            self.distribution = distroset[self.distribution_name]
        except NotFoundError:
            self.distribution = distroset['ubuntu']

        if self.suite_name:
            # defaults to distro.currentseries if passed distroseries is
            # misapplied or not found.
            try:
                self.distroseries, self.pocket = (
                    self.distribution.getDistroSeriesAndPocket(
                        self.suite_name))
            except NotFoundError:
                raise QueueActionError('Context not found: "%s/%s"'
                                       % (self.distribution.name,
                                          self.suite_name))
        else:
            self.distroseries = self.distribution.currentseries
            self.pocket = PackagePublishingPocket.RELEASE

    def initialize(self):
        """Builds a list of affected records based on the filter argument."""
        self.setDefaultContext()

        self.package_names = []
        self.items = []
        self.items_size = 0

        # Will be set to true if the command line specified package IDs.
        # This is required because package_names is expanded into IDs so we
        # need another way of knowing whether the user typed them.
        self.explicit_ids_specified = False

        terms = self.terms[self.terms_start_index:]
        if len(terms) == 0:
            # If no argument is passed, present all available results in
            # the selected queue.
            terms.append('')

        for term in terms:
            # refuse old-style '*' argument since we do not support
            # wildcards yet.
            if term == '*':
                self.displayUsage(FILTERMSG)

            if term.isdigit():
                # retrieve PackageUpload item by id
                try:
                    item = getUtility(IPackageUploadSet).get(int(term))
                except NotFoundError as info:
                    raise QueueActionError('Queue Item not found: %s' % info)

                if item.status != self.queue:
                    raise QueueActionError(
                        'Item %s is in queue %s' % (
                            item.id, item.status.name))

                if (item.distroseries != self.distroseries or
                    item.pocket != self.pocket):
                    raise QueueActionError(
                        'Item %s is in %s/%s-%s not in %s/%s-%s'
                        % (item.id, item.distroseries.distribution.name,
                           item.distroseries.name, item.pocket.name,
                           self.distroseries.distribution.name,
                           self.distroseries.name, self.pocket.name))

                if item not in self.items:
                    self.items.append(item)
                self.explicit_ids_specified = True
            else:
                # retrieve PackageUpload item by name/version key
                version = None
                if '/' in term:
                    term, version = term.strip().split('/')

                # Expand SQLObject results.
                queue_items = self.distroseries.getPackageUploads(
                    status=self.queue, name=term, version=version,
                    exact_match=self.exact_match, pocket=self.pocket)
                for item in queue_items:
                    if item not in self.items:
                        self.items.append(item)
                self.package_names.append(term)

        self.items_size = len(self.items)

    def run(self):
        """Place holder for command action."""
        raise NotImplementedError('No action implemented.')

    def displayTitle(self, action):
        """Common title/summary presentation method."""
        self.display("%s %s/%s (%s) %s/%s" % (
            action, self.distribution.name, self.suite_name,
            self.queue.name, self.items_size, self.size))

    def displayHead(self):
        """Table head presentation method."""
        self.display(HEAD)

    def displayBottom(self):
        """Displays the table bottom and a small statistic information."""
        self.display(
            FOOT_MARGIN + "%d/%d total" % (self.items_size, self.size))

    def displayRule(self):
        """Displays a rule line. """
        self.display(RULE)

    def displayUsage(self, extended_info=None):
        """Display the class docstring as usage message.

        Raise QueueActionError with optional extended_info argument
        """
        self.display(self.__doc__)
        raise QueueActionError(extended_info)

    def _makeTag(self, queue_item):
        """Compose an upload type tag for `queue_item`.

        A source upload without binaries is tagged as "S-".
        A binary upload without source is tagged as "-B."
        An upload with both source and binaries is tagged as "SB".
        An upload with a package copy job is tagged as "X-".
        """
        # XXX cprov 2006-07-31: source_tag and build_tag ('S' & 'B')
        # are necessary simply to keep the format legaxy.
        # We may discuss a more reasonable output format later
        # and avoid extra boring code. The IDRQ.displayname should
        # do should be enough.
        if queue_item.package_copy_job is not None:
            return "X-"

        source_tag = {
            True: 'S',
            False: '-',
        }
        binary_tag = {
            True: 'B',
            False: '-',
        }
        return (
            source_tag[queue_item.contains_source] +
            binary_tag[queue_item.contains_build])

    def displayItem(self, queue_item):
        """Display one line summary of the queue item provided."""
        tag = self._makeTag(queue_item)
        displayname = queue_item.displayname
        version = queue_item.displayversion
        age = DurationFormatterAPI(
            datetime.now(pytz.timezone('UTC')) -
            queue_item.date_created).approximateduration()

        if queue_item.contains_build:
            displayname = "%s (%s)" % (queue_item.displayname,
                                       queue_item.displayarchs)

        self.display("%8d | %s | %s | %s | %s" %
                     (queue_item.id, tag, displayname.ljust(20)[:20],
                     version.ljust(20)[:20], age))

    def displayInfo(self, queue_item, only=None):
        """Displays additional information about the provided queue item.

        Optionally pass a binarypackagename via 'only' argument to display
        only exact matches within the selected build queue items.
        """
        if queue_item.package_copy_job or queue_item.sources:
            self.display(
                "\t | * %s/%s Component: %s Section: %s" % (
                    queue_item.package_name,
                    queue_item.package_version,
                    queue_item.component_name,
                    queue_item.section_name,
                    ))

        for queue_build in queue_item.builds:
            for bpr in queue_build.build.binarypackages:
                if only and only != bpr.name:
                    continue
                if bpr.is_new:
                    status_flag = "N"
                else:
                    status_flag = "*"
                self.display(
                    "\t | %s %s/%s/%s Component: %s Section: %s Priority: %s"
                    % (status_flag, bpr.name, bpr.version,
                       bpr.build.distro_arch_series.architecturetag,
                       bpr.component.name, bpr.section.name,
                       bpr.priority.name))

        for queue_custom in queue_item.customfiles:
            self.display("\t | * %s Format: %s"
                         % (queue_custom.libraryfilealias.filename,
                            queue_custom.customformat.name))


class QueueActionHelp(QueueAction):
    """Present provided actions summary"""

    def __init__(self, **kargs):
        self.kargs = kargs
        self.kargs['no_mail'] = True
        self.actions = kargs['terms']
        self.display = kargs['display']

    def initialize(self):
        """Mock initialization """
        pass

    def run(self):
        """Present the actions description summary"""
        # present summary for specific or all actions
        if not self.actions:
            actions_help = queue_actions.items()
            not_available_actions = []
        else:
            actions_help = [
                (action, provider)
                for action, provider in queue_actions.items()
                if action in self.actions]
            not_available_actions = [
                action for action in self.actions
                if action not in queue_actions.keys()]
        # present not available requested action if any.
        if not_available_actions:
            self.display(
                "Not available action(s): %s" %
                ", ".join(not_available_actions))

        # extract summary from docstring of specified available actions
        for action, wrapper in actions_help:
            if action is 'help':
                continue
            wobj = wrapper(**self.kargs)
            summary = wobj.__doc__.splitlines()[0]
            self.display('\t%s : %s ' % (action, summary))


class QueueActionReport(QueueAction):
    """Present a report about the size of available queues"""

    def initialize(self):
        """Mock initialization """
        self.setDefaultContext()

    def run(self):
        """Display the queues size."""
        self.display("Report for %s/%s" % (self.distribution.name,
                                           self.distroseries.name))

        for queue in name_queue_map.values():
            size = getUtility(IPackageUploadSet).count(
                status=queue, distroseries=self.distroseries,
                pocket=self.pocket)
            self.display("\t%s -> %s entries" % (queue.name, size))


class QueueActionInfo(QueueAction):
    """Present the Queue item including its contents.

    Presents the contents of the selected upload(s).

    queue info <filter>
    """

    def run(self):
        """Present the filtered queue ordered by date."""
        self.displayTitle('Listing')
        self.displayHead()
        for queue_item in self.items:
            self.displayItem(queue_item)
            self.displayInfo(queue_item)
        self.displayHead()
        self.displayBottom()


class QueueActionFetch(QueueAction):
    """Fetch the contents of a queue item.

    Download the contents of the selected upload(s).

    queue fetch <filter>
    """

    def run(self):
        self.displayTitle('Fetching')
        self.displayRule()
        for queue_item in self.items:
            file_list = []
            if queue_item.changesfile is not None:
                file_list.append(queue_item.changesfile)

            for source in queue_item.sources:
                for spr_file in source.sourcepackagerelease.files:
                    file_list.append(spr_file.libraryfile)

            for build in queue_item.builds:
                for bpr in build.build.binarypackages:
                    for bpr_file in bpr.files:
                        file_list.append(bpr_file.libraryfile)

            for custom in queue_item.customfiles:
                file_list.append(custom.libraryfilealias)

            for libfile in file_list:
                self.display("Constructing %s" % libfile.filename)
                # do not overwrite files on disk (bug # 62976)
                try:
                    existing_file = open(libfile.filename, "r")
                except IOError as e:
                    if not e.errno == errno.ENOENT:
                        raise
                    # File does not already exist, so read file from librarian
                    # and write to disk.
                    libfile.open()
                    out_file = open(libfile.filename, "w")
                    for chunk in filechunks(libfile):
                        out_file.write(chunk)
                    out_file.close()
                    libfile.close()
                else:
                    # Check sha against existing file (bug #67014)
                    existing_sha = hashlib.sha1()
                    for chunk in filechunks(existing_file):
                        existing_sha.update(chunk)
                    existing_file.close()

                    # bail out if the sha1 differs
                    if libfile.content.sha1 != existing_sha.hexdigest():
                        raise CommandRunnerError("%s already present on disk "
                                                 "and differs from new file"
                                                 % libfile.filename)
                    else:
                        self.display("%s already on disk and checksum "
                                     "matches, skipping.")

        self.displayRule()
        self.displayBottom()


class QueueActionReject(QueueAction):
    """Reject the contents of a queue item.

    Move the selected upload(s) to the REJECTED queue.

    queue reject <filter>
    """

    def run(self):
        """Perform Reject action."""
        self.displayTitle('Rejecting')
        self.displayRule()
        for queue_item in self.items:
            self.display('Rejecting %s' % queue_item.displayname)
            try:
                queue_item.rejectFromQueue(
                    logger=self.log, dry_run=self.no_mail)
            except QueueInconsistentStateError as info:
                self.display('** %s could not be rejected due %s'
                             % (queue_item.displayname, info))

        self.displayRule()
        self.displayBottom()


class QueueActionAccept(QueueAction):
    """Accept the contents of a queue item.

    Move the selected upload(s) to the ACCEPTED queue.

    queue accept <filter>
    """

    def run(self):
        """Perform Accept action."""
        self.displayTitle('Accepting')
        self.displayRule()
        for queue_item in self.items:
            self.display('Accepting %s' % queue_item.displayname)
            try:
                queue_item.acceptFromQueue(
                    logger=self.log, dry_run=self.no_mail)
            except QueueInconsistentStateError as info:
                self.display('** %s could not be accepted due to %s'
                             % (queue_item.displayname, info))
                continue

        self.displayRule()
        self.displayBottom()


class QueueActionOverride(QueueAction):
    """Override information in a queue item content.

    queue override [-c|--component] [-x|--section] [-p|--priority]
        <override_stanza> <filter>

    Where override_stanza is one of:
    source
    binary

    In each case, when you want to set an override supply the relevant option.

    So, to set a binary to have section 'editors' but leave the
    component and priority alone, do:

    queue override -x editors binary <filter>

    Binaries can only be overridden by passing a name filter, so it will
    only override the binary package which matches the filter.

    Or, to set a source's section to editors, do:

    queue override -x editors source <filter>
    """
    supported_override_stanzas = ['source', 'binary']

    def __init__(self, distribution_name, suite_name, queue, terms,
                 component_name, section_name, priority_name,
                 display, no_mail=True, exact_match=False, log=None):
        """Constructor for QueueActionOverride."""

        # This exists so that self.terms_start_index can be set as this action
        # class has a command at the start of the terms.
        # Our first term is "binary" or "source" to specify the type of
        # over-ride.
        QueueAction.__init__(self, distribution_name, suite_name, queue,
                             terms, component_name, section_name,
                             priority_name, display, no_mail=True,
                             exact_match=False, log=log)
        self.terms_start_index = 1
        self.overrides_performed = 0

    def run(self):
        """Perform Override action."""
        self.displayTitle('Overriding')
        self.displayRule()

        # "terms" is the list of arguments starting at the override stanza
        # ("source" or "binary").
        try:
            override_stanza = self.terms[0]
        except IndexError:
            self.displayUsage('Missing override_stanza.')
            return

        if override_stanza not in self.supported_override_stanzas:
            self.displayUsage('Not supported override_stanza: %s'
                            % override_stanza)
            return

        return getattr(self, '_override_' + override_stanza)()

    def _override_source(self):
        """Overrides sourcepackagereleases selected.

        It doesn't check Component/Section Selection, this is a task
        for queue state-machine.
        """
        component = None
        section = None
        try:
            if self.component_name:
                component = getUtility(IComponentSet)[self.component_name]
            if self.section_name:
                section = getUtility(ISectionSet)[self.section_name]
        except NotFoundError as info:
            raise QueueActionError('Not Found: %s' % info)

        for queue_item in self.items:
            # We delegate to the queue_item itself to override any/all
            # of its sources.
            if queue_item.contains_source or queue_item.package_copy_job:
                if queue_item.sourcepackagerelease:
                    old_component = queue_item.sourcepackagerelease.component
                else:
                    old_component = getUtility(IComponentSet)[
                        queue_item.package_copy_job.component_name]
                queue_item.overrideSource(
                    component, section, [
                        component, old_component])
                self.overrides_performed += 1
            self.displayInfo(queue_item)

    def _override_binary(self):
        """Overrides binarypackagereleases selected"""
        from lp.soyuz.interfaces.publishing import name_priority_map
        if self.explicit_ids_specified:
            self.displayUsage('Cannot Override BinaryPackage retrieved by ID')

        component = None
        section = None
        priority = None
        try:
            if self.component_name:
                component = getUtility(IComponentSet)[self.component_name]
            if self.section_name:
                section = getUtility(ISectionSet)[self.section_name]
            if self.priority_name:
                priority = name_priority_map[self.priority_name]
        except (NotFoundError, KeyError) as info:
            raise QueueActionError('Not Found: %s' % info)

        overridden = []
        for queue_item in self.items:
            for build in queue_item.builds:
                # Different than PackageUploadSources
                # PackageUploadBuild points to a Build, that can,
                # and usually does, point to multiple BinaryPackageReleases.
                # So we need to carefully select the requested package to be
                # overridden
                for binary in build.build.binarypackages:
                    if binary.name in self.package_names:
                        overridden.append(binary.name)
                        self.display("Overriding %s_%s (%s/%s/%s)"
                                     % (binary.name, binary.version,
                                        binary.component.name,
                                        binary.section.name,
                                        binary.priority.name))
                        binary.override(component=component, section=section,
                                        priority=priority)
                        self.overrides_performed += 1
                        self.displayInfo(queue_item, only=binary.name)
                # See if the new component requires a new archive on the
                # build:
                if component:
                    distroarchseries = build.build.distro_arch_series
                    distribution = distroarchseries.distroseries.distribution
                    new_archive = distribution.getArchiveByComponent(
                        self.component_name)
                    if (new_archive != build.build.archive):
                        raise QueueActionError(
                            "Overriding component to '%s' failed because it "
                            "would require a new archive."
                            % self.component_name)

        not_overridden = set(self.package_names) - set(overridden)
        if len(not_overridden) > 0:
            self.displayUsage('No matches for %s' % ",".join(not_overridden))


queue_actions = {
    'help': QueueActionHelp,
    'info': QueueActionInfo,
    'fetch': QueueActionFetch,
    'accept': QueueActionAccept,
    'reject': QueueActionReject,
    'override': QueueActionOverride,
    'report': QueueActionReport,
    }


def default_display(text):
    """Unified presentation method."""
    print text


class CommandRunnerError(Exception):
    """Command Runner Failure"""


class CommandRunner:
    """A wrapper for queue_action classes."""

    def __init__(self, queue, distribution_name, suite_name,
                 no_mail, component_name, section_name, priority_name,
                 display=default_display, log=None):
        self.queue = queue
        self.distribution_name = distribution_name
        self.suite_name = suite_name
        self.no_mail = no_mail
        self.component_name = component_name
        self.section_name = section_name
        self.priority_name = priority_name
        self.display = display
        self.log = log

    def execute(self, terms, exact_match=False):
        """Execute a single queue action."""
        self.display('Running: "%s"' % " ".join(terms))

        # check syntax, abort process if anything gets wrong
        try:
            action = terms[0]
            arguments = [unicode(term) for term in terms[1:]]
        except IndexError:
            raise CommandRunnerError('Invalid sentence, use help.')

        # check action availability,
        try:
            queue_action_class = queue_actions[action]
        except KeyError:
            raise CommandRunnerError('Unknown Action: %s' % action)

        # perform the required action on queue.
        try:
            # be sure to send every args via kargs
            queue_action = queue_action_class(
                distribution_name=self.distribution_name,
                suite_name=self.suite_name,
                queue=self.queue,
                no_mail=self.no_mail,
                display=self.display,
                terms=arguments,
                component_name=self.component_name,
                section_name=self.section_name,
                priority_name=self.priority_name,
                exact_match=exact_match,
                log=self.log)
            queue_action.initialize()
            queue_action.run()
        except QueueActionError as info:
            raise CommandRunnerError(info)

        return queue_action
