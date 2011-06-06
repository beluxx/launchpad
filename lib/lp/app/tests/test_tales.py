# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""tales.py doctests."""

from lxml import html

from zope.component import (
    getAdapter,
    getUtility
    )
from zope.traversing.interfaces import (
    IPathAdapter,
    TraversalError,
    )

from canonical.testing.layers import (
    DatabaseFunctionalLayer,
    FunctionalLayer,
    )
from lp.app.browser.tales import (
    format_link,
    PersonFormatterAPI,
    )
from lp.registry.interfaces.irc import IIrcIDSet
from lp.testing import (
    test_tales,
    TestCaseWithFactory,
    )


def test_requestapi():
    """
    >>> from lp.app.browser.tales import IRequestAPI, RequestAPI
    >>> from lp.registry.interfaces.person import IPerson
    >>> from zope.interface.verify import verifyObject

    >>> class FakePrincipal:
    ...     def __conform__(self, protocol):
    ...         if protocol is IPerson:
    ...             return "This is a person"
    ...

    >>> class FakeApplicationRequest:
    ...    principal = FakePrincipal()
    ...    def getURL(self):
    ...        return 'http://launchpad.dev/'
    ...

    Let's make a fake request, where request.principal is a FakePrincipal
    object.  We can use a class or an instance here.  It really doesn't
    matter.

    >>> request = FakeApplicationRequest()
    >>> adapter = RequestAPI(request)

    >>> verifyObject(IRequestAPI, adapter)
    True

    >>> adapter.person
    'This is a person'

    """


def test_cookie_scope():
    """
    The 'request/lp:cookie_scope' TALES expression returns a string
    that represents the scope parameters necessary for a cookie to be
    available for the entire Launchpad site.  It takes into account
    the request URL and the cookie_domains setting in launchpad.conf.

        >>> from lp.app.browser.tales import RequestAPI
        >>> def cookie_scope(url):
        ...     class FakeRequest:
        ...         def getURL(self):
        ...             return url
        ...     return RequestAPI(FakeRequest()).cookie_scope

    The cookie scope will use the secure attribute if the request was
    secure:

        >>> print cookie_scope('http://launchpad.net/')
        ; Path=/; Domain=.launchpad.net
        >>> print cookie_scope('https://launchpad.net/')
        ; Path=/; Secure; Domain=.launchpad.net

    The domain parameter is omitted for domains that appear to be
    separate from a Launchpad instance:

        >>> print cookie_scope('https://example.com/')
        ; Path=/; Secure
    """


def test_dbschemaapi():
    """
    >>> from lp.app.browser.tales import DBSchemaAPI
    >>> from lp.code.enums import BranchType

    The syntax to get the title is: number/lp:DBSchemaClass

    >>> (str(DBSchemaAPI(1).traverse('BranchType', []))
    ...  == BranchType.HOSTED.title)
    True

    Using an inappropriate number should give a KeyError.

    >>> DBSchemaAPI(99).traverse('BranchType', [])
    Traceback (most recent call last):
    ...
    KeyError: 99

    Using a dbschema name that doesn't exist should give a LocationError

    >>> DBSchemaAPI(99).traverse('NotADBSchema', [])
    Traceback (most recent call last):
    ...
    LocationError: 'NotADBSchema'

    """


class TestPersonFormatterAPI(TestCaseWithFactory):
    """Tests for PersonFormatterAPI"""

    layer = DatabaseFunctionalLayer

    def test_link_display_name_id(self):
        """The link to the user profile page using displayname and id."""
        person = self.factory.makePerson()
        # Enable the picker_enhancements feature to test the commenter name.
        from lp.services.features.testing import FeatureFixture
        feature_flag = {'disclosure.picker_enhancements.enabled': 'on'}
        flags = FeatureFixture(feature_flag)
        flags.setUp()
        self.addCleanup(flags.cleanUp)
        formatter = getAdapter(person, IPathAdapter, 'fmt')
        result = formatter.link_display_name_id(None)
        expected = '<a href="%s" class="sprite person">%s (%s)</a>' % (
            formatter.url(), person.displayname, person.name)
        self.assertEqual(expected, result)


class TestObjectFormatterAPI(TestCaseWithFactory):
    """Tests for ObjectFormatterAPI"""

    layer = DatabaseFunctionalLayer

    def test_object_link_ignores_default(self):
        # The rendering of an object's link ignores any specified default
        # value which would be used in the case where the object were None.
        person = self.factory.makePerson()
        person_link = test_tales(
            'person/fmt:link::default value', person=person)
        self.assertEqual(PersonFormatterAPI(person).link(None), person_link)
        person_link = test_tales(
            'person/fmt:link:bugs:default value', person=person)
        self.assertEqual(PersonFormatterAPI(person).link(
            None, rootsite='bugs'), person_link)


class TestFormattersAPI(TestCaseWithFactory):
    """Tests for FormattersAPI."""

    layer = DatabaseFunctionalLayer

    test_data = (
        'http://localhost:8086/bar/baz/foo.html\n'
        'ftp://localhost:8086/bar/baz/foo.bar.html\n'
        'sftp://localhost:8086/bar/baz/foo.bar.html.\n'
        'http://localhost:8086/bar/baz/foo.bar.html;\n'
        'news://localhost:8086/bar/baz/foo.bar.html:\n'
        'http://localhost:8086/bar/baz/foo.bar.html?\n'
        'http://localhost:8086/bar/baz/foo.bar.html,\n'
        '<http://localhost:8086/bar/baz/foo.bar.html>\n'
        '<http://localhost:8086/bar/baz/foo.bar.html>,\n'
        '<http://localhost:8086/bar/baz/foo.bar.html>.\n'
        '<http://localhost:8086/bar/baz/foo.bar.html>;\n'
        '<http://localhost:8086/bar/baz/foo.bar.html>:\n'
        '<http://localhost:8086/bar/baz/foo.bar.html>?\n'
        '(http://localhost:8086/bar/baz/foo.bar.html)\n'
        '(http://localhost:8086/bar/baz/foo.bar.html),\n'
        '(http://localhost:8086/bar/baz/foo.bar.html).\n'
        '(http://localhost:8086/bar/baz/foo.bar.html);\n'
        '(http://localhost:8086/bar/baz/foo.bar.html):\n'
        'http://localhost/bar/baz/foo.bar.html?a=b&b=a\n'
        'http://localhost/bar/baz/foo.bar.html?a=b&b=a.\n'
        'http://localhost/bar/baz/foo.bar.html?a=b&b=a,\n'
        'http://localhost/bar/baz/foo.bar.html?a=b&b=a;\n'
        'http://localhost/bar/baz/foo.bar.html?a=b&b=a:\n'
        'http://localhost/bar/baz/foo.bar.html?a=b&b='
            'a:b;c@d_e%f~g#h,j!k-l+m$n*o\'p\n'
        'http://www.searchtools.com/test/urls/(parens).html\n'
        'http://www.searchtools.com/test/urls/-dash.html\n'
        'http://www.searchtools.com/test/urls/_underscore.html\n'
        'http://www.searchtools.com/test/urls/period.x.html\n'
        'http://www.searchtools.com/test/urls/!exclamation.html\n'
        'http://www.searchtools.com/test/urls/~tilde.html\n'
        'http://www.searchtools.com/test/urls/*asterisk.html\n'
        'irc://irc.freenode.net/launchpad\n'
        'irc://irc.freenode.net/%23launchpad,isserver\n'
        'mailto:noreply@launchpad.net\n'
        'jabber:noreply@launchpad.net\n'
        'http://localhost/foo?xxx&\n'
        'http://localhost?testing=[square-brackets-in-query]\n')

    def test_linkification_with_target(self):
        # The text-to-html-with-target formatter sets the target
        # attribute of the links it produces to _new.
        linkified_text = test_tales(
            'foo/fmt:text-to-html-with-target', foo=self.test_data)
        tree = html.fromstring(linkified_text)
        for link in tree.xpath('//a'):
            self.assertEqual('_new', link.get('target'))


class TestNoneFormatterAPI(TestCaseWithFactory):
    """Tests for NoneFormatterAPI"""

    layer = FunctionalLayer

    def test_format_link_none(self):
        # Test that format_link() handles None correctly.
        self.assertEqual(format_link(None), 'None')
        self.assertEqual(format_link(None, empty_value=''), '')

    def test_valid_traversal(self):
        # Traversal of allowed names works as expected.

        allowed_names = set([
            'approximatedate',
            'approximateduration',
            'break-long-words',
            'date',
            'datetime',
            'displaydate',
            'isodate',
            'email-to-html',
            'exactduration',
            'lower',
            'nice_pre',
            'nl_to_br',
            'pagetitle',
            'rfc822utcdatetime',
            'text-to-html',
            'time',
            'url',
            'link',
            ])

        for name in allowed_names:
            self.assertEqual('', test_tales('foo/fmt:%s' % name, foo=None))

    def test_value_override(self):
        # Override of rendered value works as expected.
        self.assertEqual(
            'default value',
            test_tales('foo/fmt:link::default value', foo=None))
        self.assertEqual(
            'default value',
            test_tales('foo/fmt:link:rootsite:default value', foo=None))

    def test_invalid_traversal(self):
        # Traversal of invalid names raises an exception.
        adapter = getAdapter(None, IPathAdapter, 'fmt')
        traverse = getattr(adapter, 'traverse', None)
        self.failUnlessRaises(TraversalError, traverse, "foo", [])

    def test_shorten_traversal(self):
        # Traversal of 'shorten' works as expected.
        adapter = getAdapter(None, IPathAdapter, 'fmt')
        traverse = getattr(adapter, 'traverse', None)
        # We expect that the last item in extra will be popped off.
        extra = ['1', '2']
        self.assertEqual('', traverse('shorten', extra))
        self.assertEqual(['1'], extra)


class TestIRCNicknameFormatterAPI(TestCaseWithFactory):
    """Tests for IRCNicknameFormatterAPI"""

    layer = DatabaseFunctionalLayer

    def test_nick_displayname(self):
        person = self.factory.makePerson(name='fred')
        ircset = getUtility(IIrcIDSet)
        ircID = ircset.new(person, "irc.canonical.com", "fred")
        self.assertEqual(
            'fred on irc.canonical.com',
            test_tales('nick/fmt:displayname', nick=ircID))

    def test_nick_formatted_displayname(self):
        person = self.factory.makePerson(name='fred')
        ircset = getUtility(IIrcIDSet)
        # Include some bogus markup to check escaping works.
        ircID = ircset.new(person, "<b>irc.canonical.com</b>", "fred")
        expected_html = test_tales(
            'nick/fmt:formatted_displayname', nick=ircID)
        self.assertEquals(
            u'<strong>fred</strong>\n'
            '<span class="discreet"> on </span>\n'
            '<strong>&lt;b&gt;irc.canonical.com&lt;/b&gt;</strong>\n',
            expected_html)
