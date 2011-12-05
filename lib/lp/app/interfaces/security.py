# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces for the Launchpad security policy."""

__metaclass__ = type

__all__ = [
    'IAuthorization',
    ]

from zope.interface import Interface


class IAuthorization(Interface):
    """Authorization policy for a particular object and permission."""

    def checkUnauthenticated():
        """Whether an unauthenticated user has `permission` on `obj`.

        Returns `True` if an unauthenticated user has that permission on the
        adapted object. Otherwise returns `False`.

        If the check must be delegated to other objects, this method can
        optionally instead generate `(object, permission)` tuples. It is then
        the security policy's job of checking authorization of those pairs.
        """

    def checkAccountAuthenticated(account):
        """Whether an authenticated user has `permission` on `obj`.

        Returns `True` if the account has that permission on the adapted
        object. Otherwise returns `False`.

        If the check must be delegated to other objects, this method can
        optionally instead generate `(object, permission)` tuples. It is then
        the security policy's job of checking authorization of those pairs.

        :param account: The account that is authenticated.
        """
