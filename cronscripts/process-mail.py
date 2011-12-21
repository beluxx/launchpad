#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# pylint: disable-msg=C0103,W0403
"""Fetches mail from the mail box and feeds them to the handlers."""

import _pythonpath

from zope.component.interfaces import ComponentLookupError

from canonical.config import config
from lp.services.scripts.base import (
    LaunchpadCronScript, LaunchpadScriptFailure)
from lp.services.mail.incoming import handleMail
from lp.services.mail.mailbox import IMailBox


class ProcessMail(LaunchpadCronScript):
    usage = """%prog [options]

    """ + __doc__

    def main(self):
        try:
            handleMail(self.txn)
        except ComponentLookupError, lookup_error:
            if lookup_error.args[0] != IMailBox:
                raise
            raise LaunchpadScriptFailure(
                "No mail box is configured. "
                "Please see mailbox.txt for info on how to configure one.")


if __name__ == '__main__':
    script = ProcessMail('process-mail', dbuser=config.processmail.dbuser)
    script.lock_and_run(use_web_security=True)
