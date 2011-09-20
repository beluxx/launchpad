# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Fixture code for YUITest + XHR integration testing."""

__metaclass__ = type
__all__ = [
    'login_as_person',
    'make_suite',
    'setup',
    'YUITestFixtureControllerView',
]

import os
import simplejson
import sys
from textwrap import dedent
import traceback
import unittest

from lazr.restful import ResourceJSONEncoder
from lazr.restful.utils import get_current_browser_request
from zope.component import getUtility
from zope.exceptions.exceptionformatter import format_exception
from zope.interface import implements
from zope.publisher.interfaces import NotFound
from zope.publisher.interfaces.http import IResult
from zope.security.checker import (
    NamesChecker,
    ProxyFactory)
from zope.security.management import getInteraction
from zope.security.proxy import removeSecurityProxy
from zope.session.interfaces import IClientIdManager

from canonical.config import config
from canonical.launchpad.webapp.interfaces import (
    IPlacelessAuthUtility,
    IOpenLaunchBag,
    )
from canonical.launchpad.webapp.login import logInPrincipal
from canonical.launchpad.webapp.publisher import LaunchpadView
from canonical.testing.layers import (
    DatabaseLayer,
    LaunchpadLayer,
    LibrarianLayer,
    LayerProcessController,
    YUIAppServerLayer,
    )
from lp.app.versioninfo import revno
from lp.testing import AbstractYUITestCase

EXPLOSIVE_ERRORS = (SystemExit, MemoryError, KeyboardInterrupt)

class setup:
    """Decorator to mark a function as a fixture available from JavaScript.

    This makes the function available to call from JS integration tests over
    XHR.  The fixture setup can have one or more cleanups tied to it with
    ``add_cleanup`` decorator/callable and can be composed with another
    function with the ``extend`` decorator/callable.
    """
    def __init__(self, function, extends=None):
        self._cleanups = []
        self._function = function
        self._extends = extends
        # We can't use locals because we want to affect the function's module,
        # not this one.
        module = sys.modules[function.__module__]
        fixtures = getattr(module, '_fixtures_', None)
        if fixtures is None:
            fixtures = module._fixtures_ = {}
        fixtures[function.__name__] = self

    def __call__(self, request, data):
        """Call the originally decorated setup function."""
        if self._extends is not None:
            self._extends(request, data)
        self._function(request, data)

    def add_cleanup(self, function):
        """Add a cleanup function to be executed on teardown, FILO."""
        self._cleanups.append(function)
        return self

    def teardown(self, request, data):
        """Run all registered cleanups.  If no cleanups, a no-op."""
        for f in reversed(self._cleanups):
            f(request, data)
        if self._extends is not None:
            self._extends.teardown(request, data)

    def extend(self, function):
        return setup(function, self)


def login_as_person(person):
    """This is a helper function designed to be used within a fixture.
    
    Provide a person, such as one generated by LaunchpadObjectFactory, and
    the browser will become logged in as this person.
    
    Explicit tear-down is unnecessary because the database is reset at the end
    of every test, and the cookie is discarded.
    """
    if person.is_team:
        raise AssertionError("Please do not try to login as a team")
    email = removeSecurityProxy(person.preferredemail).email
    request = get_current_browser_request()
    assert request is not None, "We do not have a browser request."
    authutil = getUtility(IPlacelessAuthUtility)
    principal = authutil.getPrincipalByLogin(email, want_password=False)
    launchbag = getUtility(IOpenLaunchBag)
    launchbag.setLogin(email)
    logInPrincipal(request, principal, email)


class CloseDbResult:
    implements(IResult)

    # This is machinery, not content.  We specify our security checker here
    # directly for clarity.
    __Security_checker__ = NamesChecker(['next', '__iter__'])

    def __iter__(self):
        try:
            # Reset the session.
            LaunchpadLayer.resetSessionDb()
            # Yield control to asyncore for a second, just to be a little bit
            # nice.  We could be even nicer by moving this whole teardown/setup
            # dance to a thread and waiting for it to be done, but there's not a
            # (known) compelling need for that right now, and doing it this way is
            # slightly simpler.
            yield '' 
            DatabaseLayer.testSetUp()
            yield '' 
            # Reset the librarian.
            LibrarianLayer.testTearDown()
            yield '' 
            # Reset the database.
            DatabaseLayer.testTearDown()
            yield '' 
            LibrarianLayer.testSetUp()
        except (SystemExit, KeyboardInterrupt):
            raise
        except:
            print "Hm, serious error when trying to clean up the test."
            traceback.print_exc()
        # We're done, so we can yield the body.
        yield '\n'


class YUITestFixtureControllerView(LaunchpadView):
    """Dynamically loads YUI test along their fixtures run over an app server.
    """

    JAVASCRIPT = 'JAVASCRIPT'
    HTML = 'HTML'
    SETUP = 'SETUP'
    TEARDOWN = 'TEARDOWN'

    page_template = dedent("""\
        <!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN"
          "http://www.w3.org/TR/html4/strict.dtd">
        <html>
          <head>
          <title>Test</title>
          <script type="text/javascript"
            src="/+icing/rev%(revno)s/build/launchpad.js"></script>
          <link rel="stylesheet"
            href="/+icing/yui/assets/skins/sam/skin.css"/>
          <link rel="stylesheet" href="/+icing/rev%(revno)s/combo.css"/>
          <style>
          /* Taken and customized from testlogger.css */
          .yui-console-entry-src { display:none; }
          
          .yui-console-entry.yui-console-entry-pass .yui-console-entry-cat {
            background-color: green;
            font-weight: bold;
            color: white;
          }
          .yui-console-entry.yui-console-entry-fail .yui-console-entry-cat {
            background-color: red;
            font-weight: bold;
            color: white;
          }
          .yui-console-entry.yui-console-entry-ignore .yui-console-entry-cat {
            background-color: #666;
            font-weight: bold;
            color: white;
          }
          </style>
          <script type="text/javascript" src="%(test_module)s"></script>
        </head>
        <body class="yui3-skin-sam">
          <div id="log"></div>
        </body>
        </html>
        """)

    def __init__(self, context, request):
        super(YUITestFixtureControllerView, self).__init__(context, request)
        self.names = []
        self.action = None
        self.fixtures = []

    @property
    def traversed_path(self):
        return os.path.join(*self.names)

    def initialize(self):
        path, ext = os.path.splitext(self.traversed_path)
        full_path = os.path.join(config.root, 'lib', path)
        if not os.path.exists(full_path + '.py'):
            raise NotFound(self, full_path + '.py', self.request)
        if not os.path.exists(full_path + '.js'):
            raise NotFound(self, full_path + '.js', self.request)

        if ext == '.js':
            self.action = self.JAVASCRIPT
        else:
            if self.request.method == 'GET':
                self.action = self.HTML
            else:
                self.fixtures = self.request.form['fixtures'].split(',')
                if self.request.form['action'] == 'setup':
                    self.action = self.SETUP
                else:
                    self.action = self.TEARDOWN

    # The following two zope methods publishTraverse and browserDefault
    # allow this view class to take control of traversal from this point
    # onwards.  Traversed names just end up in self.names.
    def publishTraverse(self, request, name):
        """Traverse to the given name."""
        # The two following constraints are enforced by the publisher.
        assert os.path.sep not in name, (
            'traversed name contains os.path.sep: %s' % name)
        assert name != '..', 'traversing to ..'
        self.names.append(name)
        return self

    def browserDefault(self, request):
        return self, ()

    def page(self):
        return self.page_template % dict(
            test_module='/+yuitest/%s.js' % self.traversed_path,
            revno=revno)

    def get_fixtures(self):
        module_name = '.'.join(self.names)
        test_module = __import__(
            module_name, globals(), locals(), ['_fixtures_'], 0)
        return test_module._fixtures_

    def render(self):
        if self.action == self.JAVASCRIPT:
            self.request.response.setHeader('Content-Type', 'text/javascript')
            result = open(os.path.join(config.root, 'lib', self.traversed_path))
        elif self.action == self.HTML:
            self.request.response.setHeader('Content-Type', 'text/html')
            result = self.page()
        elif self.action == self.SETUP:
            data = {}
            fixtures = self.get_fixtures()
            try:
                for fixture_name in self.fixtures:
                    __traceback_info__ = (fixture_name, data)
                    fixtures[fixture_name](self.request, data)
            except EXPLOSIVE_ERRORS:
                raise
            except:
                self.request.response.setStatus(500)
                result = ''.join(format_exception(*sys.exc_info()))
            else:
                self.request.response.setHeader(
                    'Content-Type', 'application/json')
                # We use the ProxyFactory so that the restful redaction code is
                # always used.
                result = simplejson.dumps(
                    ProxyFactory(data), cls=ResourceJSONEncoder)
        elif self.action == self.TEARDOWN:
            data = simplejson.loads(self.request.form['data'])
            fixtures = self.get_fixtures()
            try:
                for fixture_name in reversed(self.fixtures):
                    __traceback_info__ = (fixture_name, data)
                    fixtures[fixture_name].teardown(self.request, data)
            except EXPLOSIVE_ERRORS:
                raise
            except:
                self.request.response.setStatus(500)
                result = ''.join(format_exception(*sys.exc_info()))
            else:
                # Remove the session cookie, in case we have one.
                self.request.response.expireCookie(
                    getUtility(IClientIdManager).namespace)
                # Blow up the database once we are out of this transaction
                # by passing a result that will do so when it is iterated
                # through in asyncore.
                self.request.response.setHeader('Content-Length', 1)
                result = CloseDbResult()
        return result

# This class cannot be imported directly into a test suite because
# then the test loader will sniff and (try to) run it.  Use make_suite
# instead (or import this module rather than this class).
class YUIAppServerTestCase(AbstractYUITestCase):
    "Instantiate this test case with the Python fixture module name."

    layer = YUIAppServerLayer
    _testMethodName = 'runTest'

    def __init__(self, module_name=None):
        self.module_name = module_name
        # This needs to be done early so the "id" is set correctly.
        self.test_path = self.module_name.replace('.', '/')
        super(YUIAppServerTestCase, self).__init__()

    def setUp(self):
        root_url = LayerProcessController.appserver_root_url()
        self.html_uri = '%s+yuitest/%s' % (root_url, self.test_path)
        super(YUIAppServerTestCase, self).setUp()

    runTest = AbstractYUITestCase.checkResults


def make_suite(module_name):
    return unittest.TestSuite([YUIAppServerTestCase(module_name)])
