# Copyright 2019 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""A person's view on an OCI project."""

from __future__ import absolute_import, print_function, unicode_literals

__metaclass__ = type
__all__ = [
    'IPersonOCIProject',
    'IPersonOCIProjectFactory',
    ]

from lazr.restful.fields import Reference
from zope.interface import Interface
from zope.schema import TextLine

from lp.registry.interfaces.ociproject import IOCIProject
from lp.registry.interfaces.person import IPerson


class IPersonOCIProject(Interface):
    """A person's view on an OCI project."""

    person = Reference(IPerson)
    oci_project = Reference(IOCIProject)
    display_name = TextLine()


class IPersonOCIProjectFactory(Interface):
    """Creates `IPersonOCIProject`s."""

    def create(person, oci_project):
        """Create and return an `IPersonOCIProject`."""
