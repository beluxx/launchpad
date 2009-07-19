# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Validators for bug attachments."""

__metaclass__ = type
__all__ = ['bug_attachment_size_constraint']

from canonical.config import config
from canonical.launchpad.validators import LaunchpadValidationError

def bug_attachment_size_constraint(value):
    """Constraint for a bug attachment's file size.

    The file is not allowed to be empty.
    """
    size = len(value)
    max_size = config.launchpad.max_bug_attachment_size
    if size == 0:
        raise LaunchpadValidationError(u'Cannot upload empty file.')
    elif max_size > 0 and size > max_size:
        raise LaunchpadValidationError(
            u'Cannot upload files larger than %i bytes' % max_size)
    else:
        return True

