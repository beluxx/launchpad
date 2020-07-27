#!/usr/bin/python2
#
# Copyright 2009-2020 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET


class DistributionMirrorTestHTTPServer(Resource):
    """An HTTP server used to test the DistributionMirror probe script.

    This server will behave in a different way depending on the path that is
    accessed. These are the possible paths and how the server behaves for each
    of them:

    :valid-mirror/*: Respond with a '200 OK' status.

    :timeout: Do not respond, causing the client to keep waiting.

    :error: Respond with a '500 Internal Server Error' status.

    :redirect-to-valid-mirror/*: Respond with a '302 Found' status,
        redirecting to http(s)://localhost:%(port)s/valid-mirror/*.

    :redirect-infinite-loop: Respond with a '302 Found' status, redirecting
        to http(s)://localhost:%(port)s/redirect-infinite-loop.

    :redirect-unknown-url-scheme: Respond with a '302 Found' status,
        redirecting to ssh://localhost/redirect-unknown-url-scheme.

    Any other path will cause the server to respond with a '404 Not Found'
    status.
    """
    protocol = "http"

    def getChild(self, name, request):
        protocol = self.protocol
        port = request.getHost().port
        if name == b'valid-mirror':
            leaf = self.__class__()
            leaf.isLeaf = True
            return leaf
        elif name == b'timeout':
            return NeverFinishResource()
        elif name == b'error':
            return FiveHundredResource()
        elif name == b'redirect-to-valid-mirror':
            assert request.path != name, (
                'When redirecting to a valid mirror the path must have more '
                'than one component.')
            remaining_path = request.path.replace('/%s' % name, '')
            leaf = RedirectingResource(
                '%s://localhost:%s/valid-mirror%s' % (
                    protocol, port, remaining_path))
            leaf.isLeaf = True
            return leaf
        elif name == b'redirect-infinite-loop':
            return RedirectingResource(
                '%s://localhost:%s/redirect-infinite-loop' %
                (protocol, port))
        elif name == b'redirect-unknown-url-scheme':
            return RedirectingResource(
                'ssh://localhost/redirect-unknown-url-scheme')
        else:
            return Resource.getChild(self, name, request)

    def render_GET(self, request):
        return "Hi"


class DistributionMirrorTestSecureHTTPServer(DistributionMirrorTestHTTPServer):
    """HTTPS version of DistributionMirrorTestHTTPServer"""
    protocol = "https"


class RedirectingResource(Resource):

    def __init__(self, redirection_url):
        self.redirection_url = redirection_url
        Resource.__init__(self)

    def render_GET(self, request):
        request.redirect(self.redirection_url)
        request.write('Get Lost')


class NeverFinishResource(Resource):
    def render_GET(self, request):
        return NOT_DONE_YET


class FiveHundredResource(Resource):
    def render_GET(self, request):
        request.setResponseCode(500)
        request.write('ASPLODE!!!')
