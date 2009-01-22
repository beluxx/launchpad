# Copyright 2008 Canonical Ltd.  All rights reserved.

"""Test for the WADL generation."""

__metaclass__ = type

import sys
from types import ModuleType
import unittest

from zope.component import getGlobalSiteManager
from zope.configuration import xmlconfig
from zope.interface import implements, Interface
from zope.schema import Date, Datetime, TextLine
from zope.testing.cleanup import CleanUp

from canonical.lazr.fields import Reference
from canonical.lazr.interfaces.rest import (
    ICollection, IEntry, IResourceGETOperation, WebServiceLayer)
from canonical.lazr.rest import ServiceRootResource
from canonical.lazr.rest.declarations import (
    collection_default_content, exported, export_as_webservice_collection,
    export_as_webservice_entry, export_read_operation, operation_parameters)
from canonical.lazr.rest.operation import ResourceGETOperation
from canonical.lazr.testing.tales import test_tales


def get_resource_factory(model_interface, resource_interface):
    """Return the autogenerated adapter class for a model_interface.

    :param model_interface: the annnotated interface for which we are looking
        for the web service resource adapter
    :param resource_interface: the method provided by the resource, usually
        `IEntry` or `ICollection`.
    :return: the resource factory (the autogenerated adapter class.
    """
    return getGlobalSiteManager().adapters.lookup1(
        model_interface, resource_interface)


def get_operation_factory(model_interface, name):
    """Find the factory for a GET operation adapter.

    :param model_interface: the model interface on which the operation is
        defined.
    :param name: the name of the exported method.
    :return: the factory (autogenerated class) that implements the operation
        on the webservice.
    """
    return getGlobalSiteManager().adapters.lookup(
            (model_interface, WebServiceLayer), IResourceGETOperation,
            name=name)


class IGenericEntry(Interface):
    """A simple, reusable entry interface.

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


class IGenericCollection(Interface):
    """A simple collection containing `IGenericEntry`."""
    export_as_webservice_collection(IGenericEntry)

    # pylint: disable-msg=E0211
    @collection_default_content()
    def getAll():
        """Returns all the entries."""


class WebServiceTestCase(CleanUp, unittest.TestCase):
    """A test case for web service operations."""

    testmodule_objects = []

    def setUp(self):
        """Set the component registry with the given model."""
        super(WebServiceTestCase, self).setUp()

        # Build a test module that exposes the given resource interfaces.
        testmodule = ModuleType('testmodule')
        for interface in self.testmodule_objects:
            setattr(testmodule, interface.__name__, interface)
        sys.modules['canonical.lazr.testmodule'] = testmodule

        # Register the test module in the ZCML configuration: adapter
        # classes will be built automatically.
        xmlconfig.string("""
        <configure
           xmlns="http://namespaces.zope.org/zope"
           xmlns:webservice="http://namespaces.canonical.com/webservice">
         <include package="zope.app.component" file="meta.zcml" />
         <include package="canonical.lazr.rest" file="meta.zcml" />
         <include package="canonical.lazr.rest" file="configure.zcml" />

        <adapter for="*"
            factory="zope.traversing.adapters.DefaultTraversable"
            provides="zope.traversing.interfaces.ITraversable" />

        <webservice:register module="canonical.lazr.testmodule" />
        </configure>
        """)


class IHas_getitem(Interface):
    pass

class Has_getitem:
    implements(IHas_getitem)
    def __getitem__(self, item):
        return "wibble"


class ResourceOperationTestCase(unittest.TestCase):
    """A test case for resource operations."""

    def test_object_with_getitem_should_not_batch(self):
        """Test ResourceOperation.should_batch().

        Custom operations returning a Reference to objects that
        implement __getitem__ should not batch the results (iter() on
        such objects does not fail).
        """
        return_type = Reference(IHas_getitem)
        result = Has_getitem()

        operation = ResourceGETOperation("fake context", "fake request")
        operation.return_type = return_type

        self.assertFalse(
            operation.should_batch(result),
            "Batching should not happen for Reference return types.")


class WadlAPITestCase(WebServiceTestCase):
    """Test the docstring generation."""

    # This one is used to test when docstrings are missing.
    class IUndocumentedEntry(Interface):
        export_as_webservice_entry()

        a_field = exported(TextLine())

    testmodule_objects = [
        IGenericEntry, IGenericCollection, IUndocumentedEntry]

    def test_wadl_field_type(self):
        """Test the generated XSD field types for various fields."""
        self.assertEquals(test_tales("field/wadl:type", field=TextLine()),
                          None)
        self.assertEquals(test_tales("field/wadl:type", field=Date()),
                          "xsd:date")
        self.assertEquals(test_tales("field/wadl:type", field=Datetime()),
                          "xsd:dateTime")

    def test_wadl_entry_doc(self):
        """Test the wadl:doc generated for an entry adapter."""
        entry = get_resource_factory(IGenericEntry, IEntry)
        doclines = test_tales(
            'entry/wadl_entry:doc', entry=entry).splitlines()
        self.assertEquals([
            '<wadl:doc xmlns="http://www.w3.org/1999/xhtml">',
            '<p>A simple, reusable entry interface.</p>',
            '<p>This is the description of the entry.</p>',
            '',
            '</wadl:doc>'], doclines)

    def test_empty_wadl_entry_doc(self):
        """Test that no docstring on an entry results in no wadl:doc."""
        entry = get_resource_factory(self.IUndocumentedEntry, IEntry)
        self.assertEquals(
            None, test_tales('entry/wadl_entry:doc', entry=entry))

    def test_wadl_collection_doc(self):
        """Test the wadl:doc generated for a collection adapter."""
        collection = get_resource_factory(IGenericCollection, ICollection)
        doclines = test_tales(
            'collection/wadl_collection:doc', collection=collection
            ).splitlines()
        self.assertEquals([
            '<wadl:doc xmlns="http://www.w3.org/1999/xhtml">',
            'A simple collection containing IGenericEntry.',
            '</wadl:doc>'], doclines)

    def test_field_wadl_doc (self):
        """Test the wadl:doc generated for an exported field."""
        entry = get_resource_factory(IGenericEntry, IEntry)
        field = entry.schema['a_field']
        doclines = test_tales(
            'field/wadl:doc', field=field).splitlines()
        self.assertEquals([
            '<wadl:doc xmlns="http://www.w3.org/1999/xhtml">',
            '<p>A &quot;field&quot;</p>',
            '<p>The only field that can be &lt;&gt; 0 in the entry.</p>',
            '',
            '</wadl:doc>'], doclines)

    def test_field_empty_wadl_doc(self):
        """Test that no docstring on a collection results in no wadl:doc."""
        entry = get_resource_factory(self.IUndocumentedEntry, IEntry)
        field = entry.schema['a_field']
        self.assertEquals(None, test_tales('field/wadl:doc', field=field))

    def test_wadl_operation_doc(self):
        """Test the wadl:doc generated for an operation adapter."""
        operation = get_operation_factory(IGenericEntry, 'greet')
        doclines = test_tales(
            'operation/wadl_operation:doc', operation=operation).splitlines()
        # Only compare the first 2 lines and the last one.
        # we dont care about the formatting of the parameters table.
        self.assertEquals([
            '<wadl:doc xmlns="http://www.w3.org/1999/xhtml">',
            '<p>Print an appropriate greeting based on the message.</p>',],
            doclines[0:2])
        self.assertEquals('</wadl:doc>', doclines[-1])
        self.failUnless(len(doclines) > 3,
            'Missing the parameter table: %s' % "\n".join(doclines))


class DuplicateNameTestCase(WebServiceTestCase):
    """Test AssertionError when two resources expose the same name.

    This class contains no tests of its own. It's up to the subclass
    to define IDuplicate and call doDuplicateTest().
    """

    def doDuplicateTest(self, expected_error_message):
        """Try to generate a WADL representation of the root.

        This will fail due to a name conflict.
        """
        resource = ServiceRootResource()
        try:
            resource.toWADL()
            self.fail('Expected toWADL to fail with an AssertionError')
        except AssertionError, e:
            self.assertEquals(str(e), expected_error_message)


class DuplicateSingularNameTestCase(DuplicateNameTestCase):
    """Test AssertionError when resource types share a singular name."""

    class IDuplicate(Interface):
        """An entry that reuses the singular name of IGenericEntry."""
        export_as_webservice_entry('generic_entry')

    testmodule_objects = [IGenericEntry, IDuplicate]

    def test_duplicate_singular(self):
        self.doDuplicateTest("Both IDuplicate and IGenericEntry expose the "
                             "singular name 'generic_entry'.")


class DuplicatePluralNameTestCase(DuplicateNameTestCase):
    """Test AssertionERror when resource types share a plural name."""

    class IDuplicate(Interface):
        """An entry that reuses the plural name of IGenericEntry."""
        export_as_webservice_entry(plural_name='generic_entrys')

    testmodule_objects = [IGenericEntry, IDuplicate]

    def test_duplicate_plural(self):
        self.doDuplicateTest("Both IDuplicate and IGenericEntry expose the "
                             "plural name 'generic_entrys'.")


def test_suite():
    return unittest.TestLoader().loadTestsFromName(__name__)

