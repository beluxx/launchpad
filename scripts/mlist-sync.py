#!/usr/bin/python -S
#
# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Sync Mailman data from one Launchpad to another."""

# XXX BarryWarsaw 2008-02-12:
# Things this script does NOT do correctly.
#
# - Fix up the deactivated lists.  This isn't done because that data lives in
#   the backed up tar file, so handling this would mean untar'ing, tricking
#   Mailman into loading the pickle (or manually loading and patching), then
#   re-tar'ing.  I don't think it's worth it because the only thing that will
#   be broken is if a list that's deactivated on production is re-activated on
#   staging.
#
# - Backpatch all the message footers and RFC 2369 headers of the messages in
#   the archive.  To do this, we'd have to iterate through all messages,
#   tweaking the List-* headers (easy) and ripping apart the footers,
#   recalculating them and reattaching them (difficult).  Doing the iteration
#   and update is quite painful in Python 2.4, but would be easier with Python
#   2.5's new mailbox module.  /Then/ we'd have to regenerate the archives.
#   Not doing this means that some of the links in staging's MHonArc archive
#   will point to production archives.

# pylint: disable-msg=W0403
import _pythonpath

import os
import sys
import logging
import textwrap
import subprocess

from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from canonical.config import config
from lp.registry.interfaces.mailinglist import IMailingListSet
from lp.registry.interfaces.person import IPersonSet
from lp.services.identity.interfaces.emailaddress import IEmailAddressSet
from lp.services.mailman.config import configure_prefix
from lp.services.scripts.base import LaunchpadScript


RSYNC_OPTIONS = ('-avz', '--delete')
RSYNC_COMMAND = '/usr/bin/rsync'
RSYNC_SUBDIRECTORIES = ('archives', 'backups', 'lists', 'mhonarc')
SPACE = ' '


class MailingListSyncScript(LaunchpadScript):
    """
    %prog [options] source_url

    Sync the Mailman data structures between production and staging.  This
    takes the most efficient route by rsync'ing over the list pickles, raw
    archive mboxes, and mhonarc files, then it fixes up anything that needs
    fixing.  This does /not/ sync over any qfiles because staging doesn't send
    emails anyway.

    source_url is required and it is the rsync source url which contains
    mailman's var directory.  The destination is taken from the launchpad.conf
    file.
    """

    loglevel = logging.INFO
    description = 'Sync the Mailman data structures with the database.'

    def __init__(self, name, dbuser=None):
        self.usage = textwrap.dedent(self.__doc__)
        super(MailingListSyncScript, self).__init__(name, dbuser)

    def add_my_options(self):
        """See `LaunchpadScript`."""
        # Add optional override of production mailing list host name.  In real
        # use, it's always going to be lists.launchpad.net so that makes a
        # reasonable default.  Some testing environments may override this.
        self.parser.add_option('--hostname', default='lists.launchpad.net',
                               help=('The hostname for the production '
                                     'mailing list system.  This is used to '
                                     'resolve teams which have multiple '
                                     'email addresses.'))

    def syncMailmanDirectories(self, source_url):
        """Synchronize the Mailman directories.

        :param source_url: the base url of the source
        """
        # This can't be done at module global scope.
        # pylint: disable-msg=F0401
        from Mailman import mm_cfg
        # Start by rsync'ing over the entire $vardir/lists, $vardir/archives,
        # $vardir/backups, and $vardir/mhonarc directories.  We specifically
        # do not rsync the data, locks, logs, qfiles, or spam directories.
        destination_url = config.mailman.build_var_dir
        # Do one rsync for all subdirectories.
        rsync_command = [RSYNC_COMMAND]
        rsync_command.extend(RSYNC_OPTIONS)
        rsync_command.append('--exclude=%s' % mm_cfg.MAILMAN_SITE_LIST)
        rsync_command.append('--exclude=%s.mbox' % mm_cfg.MAILMAN_SITE_LIST)
        rsync_command.extend(os.path.join(source_url, subdirectory)
                             for subdirectory in RSYNC_SUBDIRECTORIES)
        rsync_command.append(destination_url)
        self.logger.info('executing: %s', SPACE.join(rsync_command))
        process = subprocess.Popen(rsync_command,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        if process.returncode == 0:
            self.logger.info('%s', stdout)
        else:
            self.logger.error('rsync command failed with exit status: %s',
                              process.returncode)
            self.logger.error('STDOUT:\n%s\nSTDERR:\n%s', stdout, stderr)
        return process.returncode

    def fixHostnames(self):
        """Fix up the host names in Mailman and the LP database."""
        # These can't be done at module global scope.
        # pylint: disable-msg=F0401
        from Mailman import Utils
        from Mailman import mm_cfg
        from Mailman.MailList import MailList

        # Grab a couple of useful components.
        email_address_set = getUtility(IEmailAddressSet)
        mailing_list_set = getUtility(IMailingListSet)

        # Clean things up per mailing list.
        for list_name in Utils.list_names():
            # Skip the site list.
            if list_name == mm_cfg.MAILMAN_SITE_LIST:
                continue

            # The first thing to clean up is the mailing list pickles.  There
            # are things like host names in some attributes that need to be
            # converted.  The following opens a locked list.
            mailing_list = MailList(list_name)
            try:
                mailing_list.host_name = mm_cfg.DEFAULT_EMAIL_HOST
                mailing_list.web_page_url = (
                    mm_cfg.DEFAULT_URL_PATTERN % mm_cfg.DEFAULT_URL_HOST)
                mailing_list.Save()
            finally:
                mailing_list.Unlock()

            # Patch up the email address for the list in the Launchpad
            # database.
            lp_mailing_list = mailing_list_set.get(list_name)
            if lp_mailing_list is None:
                # We found a mailing list in Mailman that does not exist in
                # the Launchpad database.  This can happen if we rsync'd the
                # Mailman directories after the lists were created, but we
                # copied the LP database /before/ the lists were created.
                # If we don't delete the Mailman lists, we won't be able to
                # create the mailing lists on staging.
                self.logger.error('No LP mailing list for: %s', list_name)
                self.deleteMailmanList(list_name)
                continue

            # Clean up the team email addresses corresponding to their mailing
            # lists.  Note that teams can have two email addresses if they
            # have a different contact address.
            team = getUtility(IPersonSet).getByName(list_name)
            mlist_addresses = email_address_set.getByPerson(team)
            if mlist_addresses.count() == 0:
                self.logger.error('No LP email address for: %s', list_name)
            else:
                # Teams can have both a mailing list and a contact address.
                old_address = '%s@%s' % (list_name, self.options.hostname)
                for email_address in mlist_addresses:
                    if email_address.email == old_address:
                        new_address = lp_mailing_list.address
                        removeSecurityProxy(email_address).email = new_address
                        self.logger.info('%s -> %s', old_address, new_address)
                        break
                else:
                    self.logger.error('No change to LP email address for: %s',
                                      list_name)

    def deleteMailmanList(self, list_name):
        """Delete all Mailman data structures for `list_name`."""
        mailman_bindir = os.path.normpath(os.path.join(
            configure_prefix(config.mailman.build_prefix), 'bin'))
        process = subprocess.Popen(('./rmlist', '-a', list_name),
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   cwd=mailman_bindir)
        stdout, stderr = process.communicate()
        if process.returncode == 0:
            self.logger.info('%s', stdout)
        else:
            self.logger.error('rmlist command failed with exit status: %s',
                              process.returncode)
            self.logger.error('STDOUT:\n%s\nSTDERR:\n%s', stdout, stderr)
            # Keep going.

    def main(self):
        """See `LaunchpadScript`."""
        source_url = None
        if len(self.args) == 0:
            self.parser.error('Missing source_url')
        elif len(self.args) > 1:
            self.parser.error('Too many arguments')
        else:
            source_url = self.args[0]

        # We need to get to the Mailman API.  Set up the paths so that Mailman
        # can be imported.  This can't be done at module global scope.
        mailman_path = configure_prefix(config.mailman.build_prefix)
        sys.path.append(mailman_path)

        retcode = self.syncMailmanDirectories(source_url)
        if retcode != 0:
            return retcode

        self.fixHostnames()

        # All done; commit the database changes.
        self.txn.commit()
        return 0


if __name__ == '__main__':
    script = MailingListSyncScript('scripts.mlist-sync', 'mlist-sync')
    status = script.lock_and_run()
    sys.exit(status)
