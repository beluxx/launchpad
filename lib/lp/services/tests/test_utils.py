# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for lp.services.utils."""

__metaclass__ = type

from contextlib import contextmanager
import hashlib
import itertools
import sys
import unittest

from lp.services.utils import (
    AutoDecorate,
    base,
    compress_hash,
    CachingIterator,
    decorate_with,
    docstring_dedent,
    iter_split,
    run_capturing_output,
    traceback_info,
    )
from lp.testing import TestCase



class TestAutoDecorate(TestCase):
    """Tests for AutoDecorate."""

    def setUp(self):
        super(TestAutoDecorate, self).setUp()
        self.log = None

    def decorator_1(self, f):
        def decorated(*args, **kwargs):
            self.log.append(1)
            return f(*args, **kwargs)
        return decorated

    def decorator_2(self, f):
        def decorated(*args, **kwargs):
            self.log.append(2)
            return f(*args, **kwargs)
        return decorated

    def test_auto_decorate(self):
        # All of the decorators passed to AutoDecorate are applied as
        # decorators in reverse order.

        class AutoDecoratedClass:
            __metaclass__ = AutoDecorate(self.decorator_1, self.decorator_2)
            def method_a(s):
                self.log.append('a')
            def method_b(s):
                self.log.append('b')

        obj = AutoDecoratedClass()
        self.log = []
        obj.method_a()
        self.assertEqual([2, 1, 'a'], self.log)
        self.log = []
        obj.method_b()
        self.assertEqual([2, 1, 'b'], self.log)


class TestBase(TestCase):

    def test_simple_base(self):
        # 35 in base 36 is lowercase 'z'
        self.assertEqual('z', base(35, 36))

    def test_extended_base(self):
        # There is no standard representation for numbers in bases above 36
        # (all the digits, all the letters of the English alphabet). However,
        # we can represent bases up to 62 by using upper case letters on top
        # of lower case letters. This is useful as a cheap compression
        # algorithm.
        self.assertEqual('A', base(36, 62))
        self.assertEqual('B', base(37, 62))
        self.assertEqual('Z', base(61, 62))

    def test_negative_numbers(self):
        # We don't convert negative numbers at all.
        self.assertRaises(ValueError, base, -43, 62)

    def test_base_matches_builtin_hex(self):
        # We get identical results to the hex builtin, without the 0x prefix
        numbers = list(range(5000))
        using_hex = [hex(i)[2:] for i in numbers]
        using_base = [base(i, 16) for i in numbers]
        self.assertEqual(using_hex, using_base)

    def test_compress_md5_hash(self):
        # compress_hash compresses MD5 hashes down to 22 URL-safe characters.
        compressed = compress_hash(hashlib.md5('foo'))
        self.assertEqual('5fX649Stem9fET0lD46zVe', compressed)
        self.assertEqual(22, len(compressed))

    def test_compress_sha1_hash(self):
        # compress_hash compresses SHA1 hashes down to 27 URL-safe characters.
        compressed = compress_hash(hashlib.sha1('foo'))
        self.assertEqual('1HyPQr2xj1nmnkQXBCJXUdQoy5l', compressed)
        self.assertEqual(27, len(compressed))


class TestIterateSplit(TestCase):
    """Tests for iter_split."""

    def test_iter_split(self):
        # iter_split loops over each way of splitting a string in two using
        # the given splitter.
        self.assertEqual([('one', '')], list(iter_split('one', '/')))
        self.assertEqual([], list(iter_split('', '/')))
        self.assertEqual(
            [('one/two', ''), ('one', 'two')],
            list(iter_split('one/two', '/')))
        self.assertEqual(
            [('one/two/three', ''), ('one/two', 'three'),
             ('one', 'two/three')],
            list(iter_split('one/two/three', '/')))


class TestCachingIterator(TestCase):
    """Tests for CachingIterator."""

    def test_reuse(self):
        # The same iterator can be used multiple times.
        iterator = CachingIterator(itertools.count())
        self.assertEqual(
            [0, 1, 2, 3, 4], list(itertools.islice(iterator, 0, 5)))
        self.assertEqual(
            [0, 1, 2, 3, 4], list(itertools.islice(iterator, 0, 5)))

    def test_more_values(self):
        # If a subsequent call to iter causes more values to be fetched, they
        # are also cached.
        iterator = CachingIterator(itertools.count())
        self.assertEqual(
            [0, 1, 2], list(itertools.islice(iterator, 0, 3)))
        self.assertEqual(
            [0, 1, 2, 3, 4], list(itertools.islice(iterator, 0, 5)))

    def test_limited_iterator(self):
        # Make sure that StopIteration is handled correctly.
        iterator = CachingIterator(iter([0, 1, 2, 3, 4]))
        self.assertEqual(
            [0, 1, 2], list(itertools.islice(iterator, 0, 3)))
        self.assertEqual([0, 1, 2, 3, 4], list(iterator))

    def test_parallel_iteration(self):
        # There can be parallel iterators over the CachingIterator.
        ci = CachingIterator(iter([0, 1, 2, 3, 4]))
        i1 = iter(ci)
        i2 = iter(ci)
        self.assertEqual(0, i1.next())
        self.assertEqual(0, i2.next())
        self.assertEqual([1, 2, 3, 4], list(i2))
        self.assertEqual([1, 2, 3, 4], list(i1))


class TestDecorateWith(TestCase):
    """Tests for `decorate_with`."""

    @contextmanager
    def trivialContextManager(self):
        """A trivial context manager, used for testing."""
        yield

    def test_decorate_with_calls_context(self):
        # When run, a function decorated with decorated_with runs with the
        # context given to decorated_with.
        calls = []
        @contextmanager
        def appending_twice():
            calls.append('before')
            yield
            calls.append('after')
        @decorate_with(appending_twice)
        def function():
            pass
        function()
        self.assertEquals(['before', 'after'], calls)

    def test_decorate_with_function(self):
        # The original function is actually called when we call the result of
        # decoration.
        calls = []
        @decorate_with(self.trivialContextManager)
        def function():
            calls.append('foo')
        function()
        self.assertEquals(['foo'], calls)

    def test_decorate_with_call_twice(self):
        # A function decorated with decorate_with can be called twice.
        calls = []
        @decorate_with(self.trivialContextManager)
        def function():
            calls.append('foo')
        function()
        function()
        self.assertEquals(['foo', 'foo'], calls)

    def test_decorate_with_arguments(self):
        # decorate_with passes through arguments.
        calls = []
        @decorate_with(self.trivialContextManager)
        def function(*args, **kwargs):
            calls.append((args, kwargs))
        function('foo', 'bar', qux=4)
        self.assertEquals([(('foo', 'bar'), {'qux': 4})], calls)

    def test_decorate_with_name_and_docstring(self):
        # decorate_with preserves function names and docstrings.
        @decorate_with(self.trivialContextManager)
        def arbitrary_name():
            """Arbitrary docstring."""
        self.assertEqual('arbitrary_name', arbitrary_name.__name__)
        self.assertEqual('Arbitrary docstring.', arbitrary_name.__doc__)

    def test_decorate_with_returns(self):
        # decorate_with returns the original function's return value.
        decorator = decorate_with(self.trivialContextManager)
        arbitrary_value = self.getUniqueString()
        result = decorator(lambda: arbitrary_value)()
        self.assertEqual(arbitrary_value, result)


class TestDocstringDedent(TestCase):
    """Tests for `docstring_dedent`."""

    def test_single_line(self):
        self.assertEqual(docstring_dedent('docstring'), 'docstring')

    def test_multi_line(self):
        docstring = """This is a multiline docstring.

        This is the second line.
        """
        result = 'This is a multiline docstring.\n\nThis is the second line.'
        self.assertEqual(docstring_dedent(docstring), result)


class TestTracebackInfo(TestCase):
    """Tests of `traceback_info`."""

    def test(self):
        # `traceback_info` sets the local variable __traceback_info__ in the
        # caller's frame.
        self.assertEqual(None, locals().get("__traceback_info__"))
        traceback_info("Pugwash")
        self.assertEqual("Pugwash", locals().get("__traceback_info__"))


class TestRunCapturingOutput(TestCase):
    """Test `run_capturing_output`."""

    def test_run_capturing_output(self):
        def f(a, b):
            sys.stdout.write(str(a))
            sys.stderr.write(str(b))
            return a + b
        c, stdout, stderr = run_capturing_output(f, 3, 4)
        self.assertEqual(7, c)
        self.assertEqual('3', stdout)
        self.assertEqual('4', stderr)


def test_suite():
    return unittest.TestLoader().loadTestsFromName(__name__)
