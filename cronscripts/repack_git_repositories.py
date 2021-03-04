#!/usr/bin/python2 -S
#
# Copyright 2009-2021 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import _pythonpath

from lp.code.scripts.requestgitrepack import RequestGitRepack


if __name__ == '__main__':
    script = RequestGitRepack(
        'repack_git_repositories',  dbuser='branchscanner')
    script.lock_and_run()
