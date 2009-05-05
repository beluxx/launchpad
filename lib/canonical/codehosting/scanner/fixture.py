# Copyright 2009 Canonical Ltd.  All rights reserved.

"""Module docstring goes here."""

__metaclass__ = type
__all__ = [
    'Fixtures',
    'FixtureWithCleanup',
    'IFixture',
    'run_with_fixture',
    'with_fixture',
    ]

from twisted.python.util import mergeFunctionMetadata
from zope.interface import implements, Interface


class IFixture(Interface):
    """A fixture has a setUp and a tearDown method."""

    def setUp():
        """Set up the fixture."""

    def tearDown():
        """Tear down the fixture."""


class FixtureWithCleanup:
    """Fixture that allows arbitrary cleanup methods to be added."""

    implements(IFixture)

    def setUp(self):
        """See `IFixture`."""
        self._cleanups = []

    def _runCleanups(self):
        if [] == self._cleanups:
            return
        f, args, kwargs = self._cleanups.pop()
        try:
            f(*args, **kwargs)
        finally:
            self._runCleanups()

    def tearDown(self):
        """See `IFixture`."""
        self._runCleanups()

    def addCleanup(self, function, *args, **kwargs):
        """Run 'function' with arguments during tear down."""
        self._cleanups.append((function, args, kwargs))


class Fixtures(FixtureWithCleanup):

    def __init__(self, fixtures):
        self._fixtures = fixtures

    def setUp(self):
        super(Fixtures, self).setUp()
        for fixture in self._fixtures:
            fixture.setUp()
            self.addCleanup(fixture.tearDown)


def with_fixture(fixture):
    """Decorate a function to run with a given fixture."""
    def decorator(f):
        def decorated(*args, **kwargs):
            return run_with_fixture(fixture, f, fixture, *args, **kwargs)
        return mergeFunctionMetadata(f, decorated)
    return decorator


def run_with_fixture(fixture, f, *args, **kwargs):
    """Run `f` within the given `fixture`."""
    fixture.setUp()
    try:
        return f(*args, **kwargs)
    finally:
        fixture.tearDown()
