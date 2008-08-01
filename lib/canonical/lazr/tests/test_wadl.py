# Copyright 2008 Canonical Ltd.  All rights reserved.

"""Test for the WADL generation."""

__metaclass__ = type

import unittest
from textwrap import dedent

from zope.component import getGlobalSiteManager
from zope.configuration import xmlconfig
from zope.interface import Interface
from zope.schema import TextLine
from zope.testing.cleanup import CleanUp

from canonical.lazr.rest.declarations import (
    collection_default_content, exported, export_as_webservice_collection,
    export_as_webservice_entry, export_read_operation, operation_parameters)
from canonical.lazr.interfaces.rest import (
    ICollection, IEntry, IResourceGETOperation, WebServiceLayer)
from canonical.lazr.testing.tales import test_tales


# Define a simple model for our API.
class IAnEntry(Interface):
    """A simple entry.

    This is the description of the entry.
    """
    export_as_webservice_entry()

    # pylint: disable-msg=E0213
    a_field = exported(
        TextLine(
            title=u'A "field"',
            description=u'The only field that can be <> 0 in the entry.'))

    @operation_parameters(
        message=TextLine(title=u'Message to say'))
    @export_read_operation()
    def greet(message):
        """Print an appropriate greeting based on the message.

        :param message: This will be included in the greeting.
        """


class IACollection(Interface):
    """A simple collection containing `IAnEntry`."""
    export_as_webservice_collection(IAnEntry)

    # pylint: disable-msg=E0211
    @collection_default_content()
    def getAll():
        """Returns all the entries."""


class WadlAPITestCase(CleanUp, unittest.TestCase):
    """Tests for the WADL generation."""

    def setUp(self):
        """Set the component registry with our simple model."""
        super(WadlAPITestCase, self).setUp()
        zcmlcontext = xmlconfig.string("""
        <configure
           xmlns="http://namespaces.zope.org/zope"
           xmlns:webservice="http://namespaces.canonical.com/webservice">
         <include package="zope.app.component" file="meta.zcml" />
         <include package="canonical.lazr.rest" file="meta.zcml" />
         <include package="canonical.lazr.rest" file="configure.zcml" />

        <adapter for="*"
            factory="zope.app.traversing.adapters.DefaultTraversable"
            provides="zope.app.traversing.interfaces.ITraversable" />

         <webservice:register module="canonical.lazr.tests.test_wadl" />
        </configure>
        """)

    def test_wadl_entry_doc(self):
        """Test the wadl:doc generated for an entry adapter."""
        entry = getGlobalSiteManager().adapters.lookup1(IAnEntry, IEntry)
        doclines = test_tales(
            'entry/wadl_entry:doc', entry=entry).splitlines()
        self.assertEquals([
            '<wadl:doc xmlns="http://www.w3.org/1999/xhtml/">',
            '<p>A simple entry.</p>',
            '<blockquote>',
            'This is the description of the entry.</blockquote>',
            '',
            '</wadl:doc>'], doclines)

    def test_wadl_collection_doc(self):
        """Test the wadl:doc generated for a collection adapter."""
        collection = getGlobalSiteManager().adapters.lookup1(
            IACollection, ICollection)
        doclines = test_tales(
            'collection/wadl_collection:doc', collection=collection
            ).splitlines()
        self.assertEquals([
            '<wadl:doc xmlns="http://www.w3.org/1999/xhtml/">',
            'A simple collection containing IAnEntry.',
            '</wadl:doc>'], doclines)

    def test_field_wadl_doc (self):
        """Test the wadl:doc generated for an exported field."""
        entry = getGlobalSiteManager().adapters.lookup1(IAnEntry, IEntry)
        field = entry.schema['a_field']
        doclines = test_tales(
            'field/wadl:doc', field=field).splitlines()
        self.assertEquals([
            '<wadl:doc xmlns="http://www.w3.org/1999/xhtml/">',
            '<p>A &quot;field&quot;</p>',
            '<p>The only field that can be &lt;&gt; 0 in the entry.</p>',
            '',
            '</wadl:doc>'], doclines)

    def test_wadl_operation_doc(self):
        """Test the wadl:doc generated for an operation adapter."""
        operation = getGlobalSiteManager().adapters.lookup(
            (IAnEntry, WebServiceLayer), IResourceGETOperation, name='greet')
        doclines = test_tales(
            'operation/wadl_operation:doc', operation=operation).splitlines()
        # Only compare the first 2 lines and the last one.
        # we dont care about the formatting of the parameters table.
        self.assertEquals([
            '<wadl:doc xmlns="http://www.w3.org/1999/xhtml/">',
            '<p>Print an appropriate greeting based on the message.</p>',],
            doclines[0:2])
        self.assertEquals('</wadl:doc>', doclines[-1])
        self.failUnless(len(doclines) > 3,
            'Missing the parameter table: %s' % "\n".join(doclines))

def test_suite():
    return unittest.TestLoader().loadTestsFromName(__name__)

