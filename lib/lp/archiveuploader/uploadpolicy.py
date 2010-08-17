# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Policy management for the upload handler."""

__metaclass__ = type

__all__ = [
    "BuildDaemonUploadPolicy",
    "IArchiveUploadPolicy",
    "SOURCE_PACKAGE_RECIPE_UPLOAD_POLICY_NAME",
    "UploadPolicyError",
    ]

from zope.component import getGlobalSiteManager, getUtility
from zope.interface import implements, Interface

from canonical.launchpad.interfaces import ILaunchpadCelebrities
from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.series import SeriesStatus
from lp.registry.interfaces.pocket import PackagePublishingPocket


# Defined here so that uploadpolicy.py doesn't depend on lp.code.
SOURCE_PACKAGE_RECIPE_UPLOAD_POLICY_NAME = 'recipe'
# Number of seconds in an hour (used later)
HOURS = 3600


class UploadPolicyError(Exception):
    """Raised when a specific policy violation occurs."""


class IArchiveUploadPolicy(Interface):
    """The policy of an upload to a Launchpad archive.

    This is, in practice, just a marker interface for us to look up upload
    policies by name.

    If registered as a utility, any classes implementing this must be given as
    the 'component' argument of the <utility> directive so that a getUtility()
    call returns the class itself rather than an instance.  This is needed
    because the callsites usually change the policies (based on user-specified
    arguments).
    """


class AbstractUploadPolicy:
    """Encapsulate the policy of an upload to a launchpad archive.

    An upload policy consists of a list of attributes which are used to
    verify an upload is permissible (e.g. whether or not there must be
    a valid signature on the .changes file). The policy also contains the
    tests themselves and they operate on NascentUpload instances in order
    to verify them.
    """
    implements(IArchiveUploadPolicy)

    options = None
    name = 'abstract'

    def __init__(self):
        """Prepare a policy..."""
        self.distro = None
        self.distroseries = None
        self.pocket = None
        self.archive = None
        self.unsigned_changes_ok = False
        self.unsigned_dsc_ok = False
        self.create_people = True
        self.can_upload_source = True
        self.can_upload_binaries = True
        self.can_upload_mixed = True
        # future_time_grace is in seconds. 28800 is 8 hours
        self.future_time_grace = 8 * HOURS
        # The earliest year we accept in a deb's file's mtime
        self.earliest_year = 1984

    def getUploader(self, changes):
        """Get the person who is doing the uploading."""
        return changes.signer

    def setOptions(self, options):
        """Store the options for later."""
        self.options = options
        # Extract and locate the distribution though...
        self.distro = getUtility(IDistributionSet)[options.distro]
        if options.distroseries is not None:
            self.setDistroSeriesAndPocket(options.distroseries)

    def setDistroSeriesAndPocket(self, dr_name):
        """Set the distroseries and pocket from the provided name.

        It also sets self.archive to the distroseries main_archive.
        """
        if self.distroseries is not None:
            assert self.archive is not None, "Archive must be set."
            # We never override the policy
            return

        self.distroseriesname = dr_name
        (self.distroseries,
         self.pocket) = self.distro.getDistroSeriesAndPocket(dr_name)

        if self.archive is None:
            self.archive = self.distroseries.main_archive

    @property
    def announcelist(self):
        """Return the announcement list address."""
        announce_list = getattr(self.options, 'announcelist', None)
        if (announce_list is None and
            getattr(self, 'distroseries', None) is not None):
            announce_list = self.distroseries.changeslist
        return announce_list

    def checkUpload(self, upload):
        """Mandatory policy checks on NascentUploads."""
        if self.archive.is_copy:
            if upload.sourceful:
                upload.reject(
                    "Source uploads to copy archives are not allowed.")
            elif upload.binaryful:
                # Buildd binary uploads (resulting from successful builds)
                # to copy archives may go into *any* pocket.
                return

        # reject PPA uploads by default
        self.rejectPPAUploads(upload)

        # execute policy specific checks
        self.policySpecificChecks(upload)

    def rejectPPAUploads(self, upload):
        """Reject uploads targeted to PPA.

        We will only allow it on 'insecure' and 'buildd' policy because we
        ensure the uploads are signed.
        """
        if upload.is_ppa:
            upload.reject(
                "PPA upload are not allowed in '%s' policy" % self.name)

    def policySpecificChecks(self, upload):
        """Implement any policy-specific checks in child."""
        raise NotImplementedError(
            "Policy specific checks must be implemented in child policies.")

    def autoApprove(self, upload):
        """Return whether the upload should be automatically approved.

        This is called only if the upload is a recognised package; if it
        is new, autoApproveNew is used instead.
        """
        # The base policy approves of everything.
        return True

    def autoApproveNew(self, upload):
        """Return whether the NEW upload should be automatically approved."""
        return False


class InsecureUploadPolicy(AbstractUploadPolicy):
    """The insecure upload policy is used by the poppy interface."""

    name = 'insecure'

    def __init__(self):
        AbstractUploadPolicy.__init__(self)
        self.can_upload_binaries = False
        self.can_upload_mixed = False

    def rejectPPAUploads(self, upload):
        """Insecure policy allows PPA upload."""
        return False

    def checkSignerIsUbuntuCodeOfConductSignee(self, upload):
        """Reject the upload if not signed by an Ubuntu CoC signer."""
        if not upload.changes.signer.is_ubuntu_coc_signer:
            upload.reject(
                'PPA uploads must be signed by an Ubuntu '
                'Code of Conduct signer.')

    def checkSignerIsBetaTester(self, upload):
        """Reject the upload if the upload signer is not a 'beta-tester'.

        For being a 'beta-tester' a person must be a valid member of
        launchpad-beta-tester team/celebrity.
        """
        beta_testers = getUtility(
            ILaunchpadCelebrities).launchpad_beta_testers
        if not upload.changes.signer.inTeam(beta_testers):
            upload.reject(
                "PPA is only allowed for members of "
                "launchpad-beta-testers team.")

    def checkArchiveSizeQuota(self, upload):
        """Reject the upload if target archive size quota will be exceeded.

        This check will reject source upload exceeding the specified archive
        size quota.Binary upload will be skipped to avoid unnecessary hassle
        dealing with FAILEDTOUPLOAD builds.
        """
        # Skip the check for binary uploads.
        if upload.binaryful:
            return

        # Calculate the incoming upload total size.
        upload_size = 0
        for uploadfile in upload.changes.files:
            upload_size += uploadfile.size

        # All value in bytes.
        MEGA = 2 ** 20
        limit_size = self.archive.authorized_size * MEGA
        current_size = self.archive.estimated_size
        new_size = current_size + upload_size

        if new_size > limit_size:
            upload.reject(
                "PPA exceeded its size limit (%.2f of %.2f MiB). "
                "Ask a question in https://answers.launchpad.net/soyuz/ "
                "if you need more space." % (
                new_size / MEGA, self.archive.authorized_size))
        elif new_size > 0.95 * limit_size:
            # Warning users about a PPA over 95 % of the size limit.
            upload.warn(
                "PPA exceeded 95 %% of its size limit (%.2f of %.2f MiB). "
                "Ask a question in https://answers.launchpad.net/soyuz/ "
                "if you need more space." % (
                new_size / MEGA, self.archive.authorized_size))
        else:
            # No need to warn user about his PPA's size.
            pass

    def policySpecificChecks(self, upload):
        """The insecure policy does not allow SECURITY uploads for now.

        If the upload is targeted to any PPA, checks if the signer is an
        Ubuntu Code of Conduct signer, and if so is a member of
        'launchpad-beta-tests'.
        """
        if upload.is_ppa:
            # XXX cprov 2007-06-13: checks for PPA uploads are not yet
            # established. We may decide for only one of the checks.  Either
            # in a specific team or having an Ubuntu CoC signer (or similar
            # flag). This code will be revisited before releasing PPA
            # publicly.
            self.checkSignerIsUbuntuCodeOfConductSignee(upload)
            #self.checkSignerIsBetaTester(upload)
            self.checkArchiveSizeQuota(upload)
        else:
            if self.pocket == PackagePublishingPocket.SECURITY:
                upload.reject(
                    "This upload queue does not permit SECURITY uploads.")

    def autoApprove(self, upload):
        """The insecure policy only auto-approves RELEASE pocket stuff.

        PPA uploads are always auto-approved.
        Other uploads (to main archives) are only auto-approved if the
        distroseries is not FROZEN (note that we already performed the
        IDistroSeries.canUploadToPocket check in the checkUpload base method).
        """
        if upload.is_ppa:
            return True

        if self.pocket == PackagePublishingPocket.RELEASE:
            if (self.distroseries.status !=
                SeriesStatus.FROZEN):
                return True
        return False


class BuildDaemonUploadPolicy(AbstractUploadPolicy):
    """The build daemon upload policy is invoked by the slave scanner."""

    name = 'buildd'

    def __init__(self):
        super(BuildDaemonUploadPolicy, self).__init__()
        # We permit unsigned uploads because we trust our build daemons
        self.unsigned_changes_ok = True
        self.unsigned_dsc_ok = True
        self.can_upload_source = False
        self.can_upload_mixed = False

    def setOptions(self, options):
        AbstractUploadPolicy.setOptions(self, options)
        # We require a buildid to be provided
        if getattr(options, 'buildid', None) is None:
            raise UploadPolicyError("BuildID required for buildd context")

    def policySpecificChecks(self, upload):
        """The buildd policy should enforce that the buildid matches."""
        # XXX: dsilvers 2005-10-14 bug=3135:
        # Implement this to check the buildid etc.
        pass

    def rejectPPAUploads(self, upload):
        """Buildd policy allows PPA upload."""
        return False


class SyncUploadPolicy(AbstractUploadPolicy):
    """This policy is invoked when processing sync uploads."""

    name = 'sync'

    def __init__(self):
        AbstractUploadPolicy.__init__(self)
        # We don't require changes or dsc to be signed for syncs
        self.unsigned_changes_ok = True
        self.unsigned_dsc_ok = True
        # We don't want binaries in a sync
        self.can_upload_mixed = False
        self.can_upload_binaries = False

    def policySpecificChecks(self, upload):
        """Perform sync specific checks."""
        # XXX: dsilvers 2005-10-14 bug=3135:
        # Implement this to check the sync
        pass


class AnythingGoesUploadPolicy(AbstractUploadPolicy):
    """This policy is invoked when processing uploads from the test process.

    We require a signed changes file but that's it.
    """

    name = 'anything'

    def __init__(self):
        AbstractUploadPolicy.__init__(self)
        # We require the changes to be signed but not the dsc
        self.unsigned_dsc_ok = True

    def policySpecificChecks(self, upload):
        """Nothing, let it go."""
        pass

    def rejectPPAUploads(self, upload):
        """We allow PPA uploads."""
        return False


class AbsolutelyAnythingGoesUploadPolicy(AnythingGoesUploadPolicy):
    """This policy is invoked when processing uploads from the test process.

    Absolutely everything is allowed, for when you don't want the hassle
    of dealing with inappropriate checks in tests.
    """

    name = 'absolutely-anything'

    def __init__(self):
        AnythingGoesUploadPolicy.__init__(self)
        self.unsigned_changes_ok = True

    def policySpecificChecks(self, upload):
        """Nothing, let it go."""
        pass


class SecurityUploadPolicy(AbstractUploadPolicy):
    """The security-upload policy.

    It allows unsigned changes and binary uploads.
    """

    name = 'security'

    def __init__(self):
        AbstractUploadPolicy.__init__(self)
        self.unsigned_dsc_ok = True
        self.unsigned_changes_ok = True
        self.can_upload_mixed = True
        self.can_upload_binaries = True

    def policySpecificChecks(self, upload):
        """Deny uploads to any pocket other than the security pocket."""
        if self.pocket != PackagePublishingPocket.SECURITY:
            upload.reject(
                "Not permitted to do security upload to non SECURITY pocket")


def register_archive_upload_policy_adapters():
    policies = [
        BuildDaemonUploadPolicy,
        InsecureUploadPolicy,
        SyncUploadPolicy, 
        AnythingGoesUploadPolicy,
        AbsolutelyAnythingGoesUploadPolicy,
        SecurityUploadPolicy]
    sm = getGlobalSiteManager()
    for policy in policies:
        sm.registerUtility(
            component=policy, provided=IArchiveUploadPolicy, name=policy.name)
