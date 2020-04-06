# Copyright 2009-2018 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for lp.services.utils."""

__metaclass__ = type

from contextlib import contextmanager
from datetime import datetime
from functools import partial
import hashlib
import itertools
import os
import sys

from fixtures import TempDir
from pytz import UTC
from testtools.matchers import (
    Equals,
    GreaterThan,
    LessThan,
    MatchesAny,
    )

from lp.services.utils import (
    AutoDecorate,
    base,
    CachingIterator,
    compress_hash,
    decorate_with,
    docstring_dedent,
    file_exists,
    iter_chunks,
    iter_split,
    load_bz2_pickle,
    obfuscate_structure,
    run_capturing_output,
    sanitise_urls,
    save_bz2_pickle,
    seconds_since_epoch,
    traceback_info,
    utc_now,
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
            [('one/two', ''), ('one', '/two')],
            list(iter_split('one/two', '/')))
        self.assertEqual(
            [('one/two/three', ''), ('one/two', '/three'),
             ('one', '/two/three')],
            list(iter_split('one/two/three', '/')))


class TestIterChunks(TestCase):
    """Tests for iter_chunks."""

    def test_empty(self):
        self.assertEqual([], list(iter_chunks([], 1)))

    def test_sequence(self):
        self.assertEqual(
            [('a', 'b'), ('c', 'd'), ('e',)], list(iter_chunks('abcde', 2)))

    def test_iterable(self):
        self.assertEqual(
            [('a', 'b'), ('c', 'd'), ('e',)],
            list(iter_chunks(iter('abcde'), 2)))

    def test_size_divides_exactly(self):
        self.assertEqual(
            [(1, 2, 3), (4, 5, 6), (7, 8, 9)],
            list(iter_chunks(range(1, 10), 3)))

    def test_size_does_not_divide_exactly(self):
        self.assertEqual(
            [(1, 2, 3), (4, 5, 6), (7, 8)],
            list(iter_chunks(range(1, 9), 3)))


class TestCachingIterator(TestCase):
    """Tests for CachingIterator."""

    def test_reuse(self):
        # The same iterator can be used multiple times.
        iterator = CachingIterator(itertools.count)
        self.assertEqual(
            [0, 1, 2, 3, 4], list(itertools.islice(iterator, 0, 5)))
        self.assertEqual(
            [0, 1, 2, 3, 4], list(itertools.islice(iterator, 0, 5)))

    def test_more_values(self):
        # If a subsequent call to iter causes more values to be fetched, they
        # are also cached.
        iterator = CachingIterator(itertools.count)
        self.assertEqual(
            [0, 1, 2], list(itertools.islice(iterator, 0, 3)))
        self.assertEqual(
            [0, 1, 2, 3, 4], list(itertools.islice(iterator, 0, 5)))

    def test_limited_iterator(self):
        # Make sure that StopIteration is handled correctly.
        iterator = CachingIterator(partial(iter, [0, 1, 2, 3, 4]))
        self.assertEqual(
            [0, 1, 2], list(itertools.islice(iterator, 0, 3)))
        self.assertEqual([0, 1, 2, 3, 4], list(iterator))

    def test_parallel_iteration(self):
        # There can be parallel iterators over the CachingIterator.
        ci = CachingIterator(partial(iter, [0, 1, 2, 3, 4]))
        i1 = iter(ci)
        i2 = iter(ci)
        self.assertEqual(0, next(i1))
        self.assertEqual(0, next(i2))
        self.assertEqual([1, 2, 3, 4], list(i2))
        self.assertEqual([1, 2, 3, 4], list(i1))

    def test_deferred_initialisation(self):
        # Initialising the iterator may be expensive, so CachingIterator
        # defers this until it needs it.
        self.initialised = False

        def iterator():
            self.initialised = True
            return iter([0, 1, 2])

        ci = CachingIterator(iterator)
        self.assertFalse(self.initialised)
        self.assertEqual([0, 1, 2], list(ci))
        self.assertTrue(self.initialised)
        self.assertEqual([0, 1, 2], list(ci))
        self.assertTrue(self.initialised)


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
        self.assertEqual(['before', 'after'], calls)

    def test_decorate_with_function(self):
        # The original function is actually called when we call the result of
        # decoration.
        calls = []

        @decorate_with(self.trivialContextManager)
        def function():
            calls.append('foo')
        function()
        self.assertEqual(['foo'], calls)

    def test_decorate_with_call_twice(self):
        # A function decorated with decorate_with can be called twice.
        calls = []

        @decorate_with(self.trivialContextManager)
        def function():
            calls.append('foo')
        function()
        function()
        self.assertEqual(['foo', 'foo'], calls)

    def test_decorate_with_arguments(self):
        # decorate_with passes through arguments.
        calls = []

        @decorate_with(self.trivialContextManager)
        def function(*args, **kwargs):
            calls.append((args, kwargs))
        function('foo', 'bar', qux=4)
        self.assertEqual([(('foo', 'bar'), {'qux': 4})], calls)

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


class TestFileExists(TestCase):
    """Tests for `file_exists`."""

    def setUp(self):
        super(TestFileExists, self).setUp()
        self.useTempDir()

    def test_finds_file(self):
        with open("a-real-file.txt", "w") as f:
            f.write("Here I am.")
        self.assertTrue(file_exists("a-real-file.txt"))

    def test_finds_directory(self):
        os.makedirs("a-real-directory")
        self.assertTrue(file_exists("a-real-directory"))

    def test_says_no_if_not_found(self):
        self.assertFalse(file_exists("a-nonexistent-file.txt"))

    def test_is_not_upset_by_missing_directory(self):
        self.assertFalse(
            file_exists("a-nonexistent-directory/a-nonexistent-file.txt"))


class TestUTCNow(TestCase):
    """Tests for `utc_now`."""

    def test_tzinfo(self):
        # utc_now() returns a timezone-aware timestamp with the timezone of
        # UTC.
        now = utc_now()
        self.assertEqual(now.tzinfo, UTC)

    def test_time_is_now(self):
        # utc_now() returns a timestamp which is now.
        LessThanOrEqual = lambda x: MatchesAny(LessThan(x), Equals(x))
        GreaterThanOrEqual = lambda x: MatchesAny(GreaterThan(x), Equals(x))
        old_now = datetime.utcnow().replace(tzinfo=UTC)
        now = utc_now()
        new_now = datetime.utcnow().replace(tzinfo=UTC)
        self.assertThat(now, GreaterThanOrEqual(old_now))
        self.assertThat(now, LessThanOrEqual(new_now))


class TestSecondsSinceEpoch(TestCase):
    """Tests for `seconds_since_epoch`."""

    def test_epoch(self):
        epoch = datetime.fromtimestamp(0, tz=UTC)
        self.assertEqual(0, seconds_since_epoch(epoch))

    def test_start_of_2018(self):
        dt = datetime(2018, 1, 1, tzinfo=UTC)
        self.assertEqual(1514764800, seconds_since_epoch(dt))


class TestBZ2Pickle(TestCase):
    """Tests for `save_bz2_pickle` and `load_bz2_pickle`."""

    def test_save_and_load(self):
        data = {1: 2, "room": 101}
        tempfile = self.useFixture(TempDir()).join("dump")
        save_bz2_pickle(data, tempfile)
        self.assertEqual(data, load_bz2_pickle(tempfile))


class TestObfuscateStructure(TestCase):

    def test_obfuscate_string(self):
        """Strings are obfuscated."""
        obfuscated = obfuscate_structure('My address is a@example.com')
        self.assertEqual(
            'My address is <email address hidden>', obfuscated)

    def test_obfuscate_list(self):
        """List elements are obfuscated."""
        obfuscated = obfuscate_structure(['My address is a@example.com'])
        self.assertEqual(
            ['My address is <email address hidden>'], obfuscated)

    def test_obfuscate_tuple(self):
        """Tuple elements are obfuscated."""
        obfuscated = obfuscate_structure(('My address is a@example.com',))
        self.assertEqual(
            ['My address is <email address hidden>'], obfuscated)

    def test_obfuscate_dict_key(self):
        """Dictionary keys are obfuscated."""
        obfuscated = obfuscate_structure(
            {'My address is a@example.com': 'foo'})
        self.assertEqual(
            {'My address is <email address hidden>': 'foo'}, obfuscated)

    def test_obfuscate_dict_value(self):
        """Dictionary values are obfuscated."""
        obfuscated = obfuscate_structure(
            {'foo': 'My address is a@example.com'})
        self.assertEqual(
            {'foo': 'My address is <email address hidden>'}, obfuscated)

    def test_recursion(self):
        """Values are obfuscated recursively."""
        obfuscated = obfuscate_structure({'foo': (['a@example.com'],)})
        self.assertEqual({'foo': [['<email address hidden>']]}, obfuscated)


class TestSanitiseURLs(TestCase):

    def test_already_clean(self):
        self.assertEqual('clean', sanitise_urls('clean'))

    def test_removes_credentials(self):
        self.assertEqual(
            'http://<redacted>@example.com/',
            sanitise_urls('http://user:secret@example.com/'))

    def test_non_greedy(self):
        self.assertEqual(
            '{"one": "http://example.com/", '
            '"two": "http://<redacted>@example.com/", '
            '"three": "http://<redacted>@example.org/"}',
            sanitise_urls(
                '{"one": "http://example.com/", '
                '"two": "http://alice:secret@example.com/", '
                '"three": "http://bob:hidden@example.org/"}'))
