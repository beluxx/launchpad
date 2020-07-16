# Copyright 2020 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""WSGI Middleware to add Launchpad revision headers to loggerhead."""

from __future__ import absolute_import, print_function, unicode_literals

__metaclass__ = type
__all__ = ['RevisionHeaderHandler']

from lp.app import versioninfo


class RevisionHeaderHandler:
    """Middleware that adds the X-Launchpad-Revision headers to a response."""

    def __init__(self, application):
        """Initialize a RevisionHeaderHandler instance.

        :param application: This is the wrapped application which will have
            access to the ``environ[session_var]`` dictionary managed by this
            middleware.
        """
        self.application = application

    def __call__(self, environ, start_response):
        """Process a request.

        Add the appropriate revision numbers in the response headers.
        """
        def response_hook(status, response_headers, exc_info=None):
            response_headers.append(
                ('X-Launchpad-Revision', versioninfo.revision))
            return start_response(status, response_headers, exc_info)
        return self.application(environ, response_hook)
