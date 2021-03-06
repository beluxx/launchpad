#!/bin/bash
#
# Copyright 2009-2020 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
#
# Update version-info.py -- but only if the revision number has
# changed

newfile=version-info-${RANDOM}.py

if [ ! -e .git ]; then
    echo "Not in a Git working tree" >&2
    exit 1
fi

if ! which git > /dev/null || ! test -x $(which git); then
    echo "No working 'git' executable found" >&2
    exit 1
fi

branch_nick="$(git rev-parse --abbrev-ref HEAD | sed "s/'/\\\\'/g")"
revision_id="$(git rev-parse HEAD)"
date="$(git show -s --format=%ci HEAD)"
cat > $newfile <<EOF
#! /usr/bin/env python

from __future__ import print_function

version_info = {
    'branch_nick': u'$branch_nick',
    'date': u'$date',
    'revision_id': u'$revision_id',
    }

if __name__ == '__main__':
    print('revision id: %(revision_id)s' % version_info)
EOF

revision_id=$(python $newfile | sed -n 's/^revision id: //p')
if ! [ -f version-info.py ]; then
    echo "Creating version-info.py at revision $revision_id"
    mv ${newfile} version-info.py
else
    if cmp -s version-info.py "$newfile"; then
        echo "Skipping version-info.py update; already at revision $revision_id"
        rm ${newfile}
    else
        echo "Updating version-info.py to revision $revision_id"
        mv ${newfile} version-info.py
    fi
fi
