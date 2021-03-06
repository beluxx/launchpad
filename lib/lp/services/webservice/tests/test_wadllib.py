# Copyright 2009-2018 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Run the standalone wadllib tests."""

from __future__ import absolute_import, print_function

__metaclass__ = type
__all__ = ['test_suite']

import __future__
import os
import unittest

import scandir
import wadllib

from lp.testing.systemdocs import LayeredDocFileSuite


topdir = os.path.dirname(wadllib.__file__)


def setUp(test):
    for future_item in 'absolute_import', 'print_function':
        test.globs[future_item] = getattr(__future__, future_item)


def test_suite():
    suite = unittest.TestSuite()

    # Find all the doctests in wadllib.
    packages = []
    for dirpath, dirnames, filenames in scandir.walk(topdir):
        if 'docs' in dirnames:
            docsdir = os.path.join(dirpath, 'docs')[len(topdir) + 1:]
            packages.append(docsdir)
    doctest_files = {}
    for docsdir in packages:
        for filename in os.listdir(os.path.join(topdir, docsdir)):
            if os.path.splitext(filename)[1] == '.txt':
                doctest_files[filename] = os.path.join(docsdir, filename)
    # Sort the tests.
    for filename in sorted(doctest_files):
        path = doctest_files[filename]
        doctest = LayeredDocFileSuite(path, package=wadllib, setUp=setUp)
        suite.addTest(doctest)

    return suite
