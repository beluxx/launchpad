#!/usr/bin/python -S
#
# Copyright 2009-2016 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Process a code import described by the command line arguments.

By 'processing a code import' we mean importing or updating code from a
remote, non-Bazaar, repository.

This script is usually run by the code-import-worker-monitor.py script that
communicates progress and results to the database.
"""

__metaclass__ = type


import _pythonpath

from optparse import OptionParser
import sys

from bzrlib.transport import get_transport
from bzrlib.url_policy_open import AcceptAnythingPolicy

from lp.codehosting.codeimport.worker import (
    BzrImportWorker,
    BzrSvnImportWorker,
    CodeImportBranchOpenPolicy,
    CodeImportSourceDetails,
    CSCVSImportWorker,
    get_default_bazaar_branch_store,
    GitImportWorker,
    GitToGitImportWorker,
    )
from lp.services import scripts
from lp.services.config import config
from lp.services.timeout import set_default_timeout_function


opener_policies = {
    "anything": lambda rcstype, target_rcstype: AcceptAnythingPolicy(),
    "default": CodeImportBranchOpenPolicy,
    }


def force_bzr_to_use_urllib():
    """Prevent bzr from using pycurl to connect to http: urls.

    We want this because pycurl rejects self signed certificates, which
    prevents a significant number of import branchs from updating.  Also see
    https://bugs.launchpad.net/bzr/+bug/516222.
    """
    from bzrlib.transport import register_lazy_transport
    register_lazy_transport('http://', 'bzrlib.transport.http._urllib',
                            'HttpTransport_urllib')
    register_lazy_transport('https://', 'bzrlib.transport.http._urllib',
                            'HttpTransport_urllib')


class CodeImportWorker:

    def __init__(self):
        parser = OptionParser()
        scripts.logger_options(parser)
        parser.add_option(
            "--access-policy", type="choice", metavar="ACCESS_POLICY",
            choices=["anything", "default"], default="default",
            help="Access policy to use when accessing branches to import.")
        self.options, self.args = parser.parse_args()
        self.logger = scripts.logger(self.options, 'code-import-worker')

    def main(self):
        force_bzr_to_use_urllib()
        set_default_timeout_function(lambda: 60.0)
        source_details = CodeImportSourceDetails.fromArguments(self.args)
        if source_details.rcstype == 'git':
            if source_details.target_rcstype == 'bzr':
                import_worker_cls = GitImportWorker
            else:
                import_worker_cls = GitToGitImportWorker
        elif source_details.rcstype == 'bzr-svn':
            import_worker_cls = BzrSvnImportWorker
        elif source_details.rcstype == 'bzr':
            import_worker_cls = BzrImportWorker
        elif source_details.rcstype == 'cvs':
            import_worker_cls = CSCVSImportWorker
        else:
            raise AssertionError(
                'unknown rcstype %r' % source_details.rcstype)
        opener_policy = opener_policies[self.options.access_policy](
            source_details.rcstype, source_details.target_rcstype)
        if source_details.target_rcstype == 'bzr':
            import_worker = import_worker_cls(
                source_details,
                get_transport(config.codeimport.foreign_tree_store),
                get_default_bazaar_branch_store(), self.logger, opener_policy)
        else:
            import_worker = import_worker_cls(
                source_details, self.logger, opener_policy)
        return import_worker.run()


if __name__ == '__main__':
    script = CodeImportWorker()
    sys.exit(script.main())
