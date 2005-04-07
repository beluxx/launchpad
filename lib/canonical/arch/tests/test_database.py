#!/usr/bin/env python
#
# arch-tag: 794e491c-ce40-4a66-a325-72984e7dbbbd
#
# Copyright (C) 2004 Canonical Software
# 	Authors: Rob Weir <rob.weir@canonical.com>
#		 Robert Collins <robert.collins@canonical.com>

"""Test suite for Canonical broker broker module."""

import unittest
import sys
from zope.interface.verify import verifyClass, verifyObject

from canonical.arch.tests.framework import DatabaseTestCase

from canonical.launchpad.interfaces import VersionAlreadyRegistered
from canonical.launchpad.interfaces import VersionAlreadyRegistered
from canonical.launchpad.interfaces import BranchAlreadyRegistered
from canonical.launchpad.interfaces import CategoryAlreadyRegistered
from canonical.launchpad.interfaces import ArchiveLocationDoublyRegistered



class Database(DatabaseTestCase):

    tests = []

    def test_imports(self):
        """canonical.launchpad.database is importable."""
        import canonical.launchpad.database
    tests.append('test_imports')

    def test_archive_doesnt_exist(self):
        """a query for a non extant archive returns false"""
        import canonical.launchpad.database
        cursor = self.cursor()
        archive_name = "test@example.com--archive"
        cursor.execute("DELETE FROM ArchArchive WHERE name = '%s'" % archive_name)
        self.commit()
        self.failIf(canonical.launchpad.database.archive_present(archive_name))
    tests.append('test_archive_doesnt_exist')


class ArchiveMapper(DatabaseTestCase):

    def test_ArchiveMapperFindMissing(self):
        """test ArchiveMapper.findByName("foo") returns a MissingArchive"""
        from canonical.launchpad.database import ArchiveMapper
        from canonical.arch.broker import MissingArchive
        name="foo@bar"
        mapper=ArchiveMapper()
        self.failUnless(isinstance(mapper.findByName(name), MissingArchive))

    def insertArchive(self, name):
        from canonical.launchpad.database.archarchive import ArchArchive
        return ArchArchive(name = name,
                           title = 'a title', description = 'a description',
                           visible = True, owner = None)

    def test_ArchiveMapperFindPresent(self):
        """test ArchiveMapper.findByName("foo") returns an Archive"""
        from canonical.launchpad.database import ArchiveMapper
        from canonical.arch.broker import MissingArchive
        name="foo@bar"
        self.insertArchive(name)
        mapper=ArchiveMapper()
        archive=mapper.findByName(name)
        self.failIf(isinstance(archive, MissingArchive))
        self.assertEqual(archive.name, name)
        self.failUnless(archive.exists())

    def test_ArchiveMapperFindMultiple(self):
        """test ArchiveMapper.findByName("foo@%") returns a list of archives"""
        from canonical.launchpad.database import ArchiveMapper
        from canonical.arch.broker import MissingArchive
        name1="foo@bar"
        name2="foo@gam"
        self.insertArchive(name1)
        self.insertArchive(name2)
        mapper=ArchiveMapper()
        archives=mapper.findByMatchingName('foo@%')
        self.failIf(isinstance(archives, MissingArchive))
        self.assertEqual(archives[0].name, name1)
        self.assertEqual(archives[1].name, name2)
        self.failUnless(archives[0].exists())
        self.failUnless(archives[1].exists())

    def test_ArchiveMapperInsertPresent(self):
        """test canonical.arch.ArchiveMapper.insert fails when an archive already exists."""
        from canonical.launchpad.database import ArchiveMapper
        from canonical.arch.broker import Archive
        name="foo@bar"
        self.insertArchive(name)
        mapper=ArchiveMapper()
        self.assertRaises(KeyError, mapper.insert, Archive(name))

    def test_ArchiveMapperInsertNew(self):
        """test ArchiveMapper.insert works when an archive is new."""
        from canonical.launchpad.database import ArchiveMapper
        from canonical.arch.broker import MissingArchive
        name="foo@bar"
        mapper=ArchiveMapper()
        mapper.insert(MissingArchive(name))
        archive=mapper.findByName(name)
        self.failUnless(archive.exists())

    def test_ArchiveMapperGetId(self):
        """test we can get the archive id correctly"""
        from canonical.launchpad.database import ArchiveMapper
        from canonical.arch.broker import Archive
        name="foo@bar"
        archive = self.insertArchive(name)
        new_id = archive.id
        mapper=ArchiveMapper()
        self.assertEqual(new_id, mapper._getId(Archive(name)))


class ArchiveLocationMapper(DatabaseTestCase):

    tests = []

    def test_ArchiveLocationMapperGetAllNone(self):
        """test that we can get an empty list when there are no registered Locations"""
        from canonical.arch.broker import Archive
        from canonical.launchpad.database import ArchiveMapper, ArchiveLocationMapper
        cursor = self.cursor()
        archive = self.getTestArchive()
        archiveLocationMapper = ArchiveLocationMapper()
        self.assertEqual(archiveLocationMapper.getAll(archive), [])
    tests.append('test_ArchiveLocationMapperGetAllNone')
    
    def test_ArchiveLocationMapperGetAllLots(self):
        """test that we can get back the correct urls from the db"""
        locations = ["http://googo.com/foo", "http://fooboo.com/bar", "http://barbar.com/bleh"]
        from canonical.launchpad.database import ArchiveMapper, ArchiveLocationMapper
        cursor = self.cursor()
        archive = self.getTestArchive()
        archiveMapper = ArchiveMapper()
        archiveLocationMapper = ArchiveLocationMapper()
        for location in locations:
            cursor.execute("INSERT INTO ArchArchiveLocation (archive, archivetype, url, gpgsigned) " \
                           "VALUES (%s, %s, '%s', '%s')" %
                           (archiveMapper._getId(archive, cursor), '0', location, 'true'))
        self.commit()
        output = archiveLocationMapper.getAll(archive)
        for (l,r) in zip(locations, output):
            print
            print l
            print r.url
            self.assertEqual(l, r.url)
    #tests.append('test_ArchiveLocationMapperGetAllLots')

    def makeLocation(self, archive, url):
        from canonical.lp.dbschema import ArchArchiveType
        from canonical.arch.broker import ArchiveLocation
        return ArchiveLocation(archive, url, ArchArchiveType.READWRITE)

    def test_ArchiveLocationMapperInsertLocation(self):
        """test that we can insert a location"""
        url = "http://googo.com/foo"
        from canonical.arch.broker import Archive
        from canonical.launchpad.database import ArchiveMapper, ArchiveLocationMapper
        archive = self.getTestArchive()
        archiveLocationMapper = ArchiveLocationMapper()
        location = self.makeLocation(archive, url)
        archiveLocationMapper.insertLocation(location)
        self.commit()
        cursor = self.cursor()
        cursor.execute("SELECT count(*) FROM ArchArchiveLocation WHERE url = '%s'" % location.url)
        self.assertEqual(cursor.fetchone()[0], 1)
        self.failUnless(archiveLocationMapper.locationExists(location))
    tests.append('test_ArchiveLocationMapperInsertLocation')

    def test_ArchiveLocationMapperExistsNone(self):
        """Test we can tell if a location is not in the db"""
        from canonical.launchpad.database import ArchiveMapper, ArchiveLocationMapper
        from canonical.arch.broker import Archive, ArchiveLocation
        location = "http://foo.com/"
        archive = self.getTestArchive()
        archiveLocationMapper = ArchiveLocationMapper()
        location = self.makeLocation(archive, location)
        self.commit()
        self.failIf(archiveLocationMapper.locationExists(location))
    tests.append('test_ArchiveLocationMapperExistsNone')

    def test_ArchiveLocationMapperExistsOne(self):
        """Test we can tell if a location is in the db"""
        from canonical.launchpad.database import ArchiveMapper, ArchiveLocationMapper
        from canonical.arch.broker import Archive
        location = "http://foo.com/"
        archive = self.getTestArchive()
        archiveLocationMapper = ArchiveLocationMapper()
        location = self.makeLocation(archive, location)
        archiveLocationMapper.insertLocation(location)
        self.commit()
        self.failUnless(archiveLocationMapper.locationExists(location))
    tests.append('test_ArchiveLocationMapperExistsOne')

    def test_ArchiveLocationMapperExistsTwo(self):
        """Test that duplicated urls are an error"""
        from canonical.launchpad.database import ArchiveMapper, ArchiveLocationMapper
        from canonical.arch.broker import Archive
        location = "http://foo.com/"
        archive = self.getTestArchive()
        archiveLocationMapper = ArchiveLocationMapper()

        location1 = self.makeLocation(archive, location)
        archiveLocationMapper.insertLocation(location1)

        location2 = self.makeLocation(archive, location)
        archiveLocationMapper.insertLocation(location2)

        self.commit()
        self.assertRaises(ArchiveLocationDoublyRegistered, archiveLocationMapper.locationExists, location1)
        self.assertRaises(ArchiveLocationDoublyRegistered, archiveLocationMapper.locationExists, location2)
    tests.append('test_ArchiveLocationMapperExistsTwo')

    def test_ArchiveLocationMapperGetSomeNone(self):
        """Test that we can get no locations with a criteria"""
        from canonical.lp.dbschema import ArchArchiveType
        from canonical.launchpad.database import ArchiveMapper, ArchiveLocationMapper
        from canonical.arch.broker import Archive, ArchiveLocation
        location = "http://foo.com/"
        archive = self.getTestArchive()
        mapper = ArchiveLocationMapper()
        self.commit()
        self.assertEqual(mapper.getSome(archive, ArchArchiveType.READWRITE), [])
    tests.append('test_ArchiveLocationMapperGetSomeNone')

    def test_ArchiveLocationMapperGetSomeMore(self):
        """Test that we can get some locations with criteria"""
        from canonical.lp.dbschema import ArchArchiveType
        from canonical.launchpad.database import ArchiveMapper, ArchiveLocationMapper
        from canonical.arch.broker import Archive, ArchiveLocation
        locations = ["http://googo.com/foo", "http://fooboo.com/bar", "http://barbar.com/bleh"]
        archive = self.getTestArchive()
        mapper = ArchiveLocationMapper()
        archive_locations = []
        archive_types = [getattr(ArchArchiveType, X)
                         for X in ('READWRITE', 'READONLY', 'MIRRORTARGET')]
        for archive_type, location in zip(archive_types, locations):
            archive_location = ArchiveLocation(archive, location, archive_type)
            archive_locations.append(archive_location)
            mapper.insertLocation(archive_location)
        for archive_type, location in zip(archive_types, locations):
            locs = mapper.getSome(archive, archive_type)
            self.assertEqual(len(locs), 1)
            self.assertEqual(locs[0].url, location)

    tests.append('test_ArchiveLocationMapperGetSomeMore')

class CategoryMapper(DatabaseTestCase):

    def test_CategoryMapperInstantiation(self):
        """Test that we can create a CategoryMapper object"""
        from canonical.launchpad.database import CategoryMapper
        foo = CategoryMapper()

    def test_CategoryMapperInsertNew(self):
        """Test that CategoryMapper.insert works for non-existent categories"""
        from canonical.launchpad.database import ArchiveMapper, CategoryMapper
        from canonical.arch.broker import Archive, Category
        archive = self.getTestArchive()
        name = "fnord"
        mapper = CategoryMapper()
        category = Category(name, archive)
        mapper.insert(category)
        self.commit()
        # FIXME: read the category back in and check that the data matches
        self.failUnless(category.exists())

    def test_CategoryMapperInsertExisting(self):
        """Test that inserting an existing Category raises an exception"""
        from canonical.launchpad.database import ArchiveMapper, CategoryMapper
        from canonical.arch.broker import Archive, Category
        archive = self.getTestArchive()
        name = "fnord"
        mapper = CategoryMapper()
        category = Category(name, archive)
        mapper.insert(category)
        self.commit()
        self.assertRaises(CategoryAlreadyRegistered, mapper.insert, category)
        self.failUnless(mapper.exists(category))

    def test_category_exist_missing(self):
        """Test that we can tell that a category doesn't exist."""
        from canonical.launchpad.database import CategoryMapper
        from canonical.arch.broker import Category
        name = "blah"
        archive = self.getTestArchive()
        mapper = CategoryMapper()
        category = Category(name, archive)
        self.commit()
        self.failIf(mapper.exists(category))

    def test_category_exist_present(self):
        """Test that we can tell that a category does exist."""
        from canonical.arch.broker import Category, Archive
        from canonical.launchpad.database import CategoryMapper
        name = "category"
        archive = self.getTestArchive()
        category = Category(name, archive)
        mapper = CategoryMapper()
        mapper.insert(category)
        self.commit()
        self.failUnless(mapper.exists(category))


class BranchMapper(DatabaseTestCase):

    tests = []

    def test_BranchMapperInstantiation(self):
        """Test that we can create a BranchMapper object"""
        from canonical.launchpad.database import BranchMapper
        foo = BranchMapper()
    tests.append('test_BranchMapperInstantiation')

    def test_BranchMapperInsertNew(self):
        """Test that BranchMapper.insert works for non-existent categories"""
        from canonical.launchpad.database import ArchiveMapper, CategoryMapper, BranchMapper
        from canonical.arch.broker import Archive, Category, Branch
        archive = self.getTestArchive()
        name = "fnord"
        mapper = CategoryMapper()
        category = Category(name, archive)
        mapper.insert(category)
        name = "barnch" # deliberate, smart-arse
        mapper = BranchMapper()
        branch = Branch(name, category)
        mapper.insert(branch)
        self.commit()
        # FIXME: read the branch back in and check that the data matches
        self.failUnless(branch.exists())
    tests.append('test_BranchMapperInsertNew')

    def test_BranchMapperInsertExisting(self):
        """Test that inserting an existing Branch raises an exception"""
        from canonical.launchpad.database import ArchiveMapper, CategoryMapper, BranchMapper
        from canonical.arch.broker import Archive, Category, Branch
        name = "barnch"
        mapper = BranchMapper()
        branch = Branch(name, self.getTestCategory())
        mapper.insert(branch)
        self.commit()
        self.assertRaises(BranchAlreadyRegistered, mapper.insert, branch)
        self.failUnless(mapper.exists(branch))
    tests.append('test_BranchMapperInsertExisting')

    def test_branch_exist_missing(self):
        """Test that we can tell that a Branch doesn't exist."""
        from canonical.launchpad.database import BranchMapper
        from canonical.arch.broker import Branch
        name = "blah"
        branch = Branch(name, self.getTestCategory())
        mapper = BranchMapper()
        self.commit()
        self.failIf(mapper.exists(branch))
    tests.append('test_branch_exist_missing')
        
    def test_branch_exist_present(self):
        """Test that we can tell that a Branch does exist."""
        from canonical.arch.broker import Branch
        from canonical.launchpad.database import BranchMapper
        name = "branch"
        branch = Branch(name, self.getTestCategory())
        mapper = BranchMapper()
        mapper.insert(branch)
        self.commit()
        self.failUnless(mapper.exists(branch))
    tests.append('test_branch_exist_present')

class VersionMapper(DatabaseTestCase):

    tests = []
    
    def test_VersionMapperInstantiation(self):
        """Test that we can create a VersionMapper object"""
        from canonical.launchpad.database import VersionMapper
        foo = VersionMapper()
    tests.append('test_VersionMapperInstantiation')

    def test_VersionMapperInsertNew(self):
        """Test that VersionMapper.insert works for non-existent versions"""
        from canonical.launchpad.database import ArchiveMapper, CategoryMapper, BranchMapper, VersionMapper
        from canonical.arch.broker import Archive, Category, Branch, Version
        archive = self.getTestArchive()
        name = "fnord"
        mapper = CategoryMapper()
        category = Category(name, archive)
        mapper.insert(category)
        name = "barnch" # deliberate, smart-arse
        mapper = BranchMapper()
        branch = Branch(name, category)
        mapper.insert(branch)
        name = "0"
        mapper = VersionMapper()
        version = Version(name, branch)
        mapper.insert(version)
        self.commit()
        # FIXME: read the branch back in and check that the data matches
        self.failUnless(mapper.exists(version))
    tests.append('test_VersionMapperInsertNew')

    def test_VersionMapperInsertExisting(self):
        """Test that inserting an existing Version raises an exception"""
        from canonical.launchpad.database import ArchiveMapper, CategoryMapper, BranchMapper, VersionMapper
        from canonical.arch.broker import Archive, Category, Branch, Version
        name = "0"
        mapper = VersionMapper()
        version = Version(name, self.getTestBranch())
        mapper.insert(version)
        self.commit()
        self.assertRaises(VersionAlreadyRegistered, mapper.insert, version)
        self.failUnless(mapper.exists(version))
    tests.append('test_VersionMapperInsertExisting')

    def test_version_exist_missing(self):
        """Test that we can tell that a Version doesn't exist."""
        from canonical.launchpad.database import VersionMapper
        from canonical.arch.broker import Version
        name = "0"
        version = Version(name, self.getTestVersion())
        self.commit()
        mapper = VersionMapper()
        self.failIf(mapper.exists(version))
    tests.append('test_version_exist_missing')
        
    def test_version_exist_present(self):
        """Test that we can tell that a Version does exist."""
        from canonical.arch.broker import Version
        from canonical.launchpad.database import VersionMapper
        name = "0"
        version = Version(name, self.getTestBranch())
        mapper = VersionMapper()
        mapper.insert(version)
        self.commit()
        self.failUnless(mapper.exists(version))
    tests.append('test_version_exist_present')

    def test_VersionMapperGetId(self):
        """test we can get the Version id correctly"""
        from canonical.launchpad.database import ArchiveMapper, VersionMapper
        from canonical.arch.broker import Archive
        version = self.getTestVersion()
        self.commit()
        cursor = self.cursor()
        cursor.execute("SELECT id FROM archnamespace WHERE category = '%s' AND branch = '%s' AND version = '%s'" %
                       (version.branch.category.name, version.branch.name, version.name))
        expected_id = cursor.fetchall()[0][0]
        mapper = VersionMapper()
        self.assertEqual(expected_id, mapper._getId(version))
    tests.append('test_VersionMapperGetId')
    def test_VersionMapperGetDBBranchId(self):
        """test we can get the Version id for the 'Branch' correctly"""
        from canonical.launchpad.database import ArchiveMapper, VersionMapper
        from canonical.arch.broker import Archive
        version = self.getTestVersion()
        self.commit()
        version_id=VersionMapper()._getId(version)
        cursor = self.cursor()
        cursor.execute("SELECT id FROM branch WHERE archnamespace = %d" % version_id)
        expected_id = cursor.fetchall()[0][0]
        mapper = VersionMapper()
        self.assertEqual(expected_id, mapper._getDBBranchId(version))
    tests.append('test_VersionMapperGetDBBranchId')


class RevisionMapper(DatabaseTestCase):

    tests = []
    
    def test_RevisionMapperInstantiation(self):
        """Test that we can create a RevisionMapper object"""
        from canonical.launchpad.database import RevisionMapper
        foo = RevisionMapper()
    tests.append('test_RevisionMapperInstantiation')

    def test_RevisionMapperInsertNew(self):
        """Test that RevisionMapper.insert works for non-existent revisions"""
        from canonical.launchpad.database import RevisionMapper
        mapper = RevisionMapper()
        revision = self.getTestRevision()
        self.commit()
        # FIXME: read the branch back in and check that the data matches
        self.failUnless(mapper.exists(revision))
    tests.append('test_RevisionMapperInsertNew')

    def test_RevisionMapperExists(self):
        """test revision mapper exists works for existing ones"""
        from canonical.launchpad.database import VersionMapper, RevisionMapper
        mapper = RevisionMapper()
        revision = self.getTestRevision()
        self.commit()
        c = self.cursor()
        branchid = VersionMapper()._getDBBranchId(revision.version)
        print "branchid = %r" % branchid
        c.execute("SELECT count(*) FROM Changeset where branch = %d" % branchid)
        self.assertEqual(c.fetchone()[0], 1)
        self.failUnless(mapper.exists(revision), "It's in the DB, why isn't the mapper noticing?")
    tests.append('test_RevisionMapperExists')

    def test_RevisionMapperDoesntExist(self):
        """test revision mapper exists works for non-exustant ones"""
        from canonical.launchpad.database import VersionMapper, RevisionMapper, BranchMapper
        from canonical.arch.broker import Revision
        mapper = RevisionMapper()
        version = self.getTestVersion()
        self.commit()
        c = self.cursor()
        branchid = VersionMapper()._getId(version)
        revision = Revision("base-0", version)
        c.execute("SELECT count(*) FROM Changeset WHERE branch = %d" % branchid)
        self.assertEqual(c.fetchone()[0], 0)
        self.failIf(mapper.exists(revision), "It's not in the DB, why does the mapper think it is?")
    tests.append('test_RevisionMapperDoesntExist')

    def test_VersionMapperInsertExisting(self):
        """Test that inserting an existing Version raises an exception"""
        from canonical.launchpad.database import ArchiveMapper, CategoryMapper, BranchMapper, VersionMapper
        from canonical.arch.broker import Archive, Category, Branch, Version
        name = "0"
        mapper = VersionMapper()
        version = Version(name, self.getTestBranch())
        mapper.insert(version)
        self.commit()
        self.assertRaises(VersionAlreadyRegistered, mapper.insert, version)
        self.failUnless(mapper.exists(version))
#    tests.append('test_VersionMapperInsertExisting')

    def test_version_exist_missing(self):
        """Test that we can tell that a Version doesn't exist."""
        from canonical.launchpad.database import VersionMapper
        from canonical.arch.broker import Version
        name = "0"
        version = Version(name, self.getTestVersion())
        mapper = VersionMapper()
        self.failIf(mapper.exists(version))
#    tests.append('test_version_exist_missing')
        
    def test_version_exist_present(self):
        """Test that we can tell that a Version does exist."""
        from canonical.arch.broker import Version
        from canonical.launchpad.database import VersionMapper
        cursor = self.cursor()
        name = "0"
        version = Version(name, self.getTestBranch())
        mapper = VersionMapper()
        mapper.insert(version)
        self.commit()
        self.failUnless(mapper.exists(version))
#    tests.append('test_version_exist_present')

    def test_version_exist_imposter(self):
        """Test that we can tell that a Version doesn't exist, regardless of
        other branches."""
        from canonical.arch.broker import Version
        from canonical.launchpad.database import VersionMapper
        cursor = self.cursor()
        name = "0"
        version = Version(name, self.getTestBranch())
        mapper = VersionMapper()
        mapper.insert(version)
        self.commit()
        otherversion = Version(name, self.getTestBranch('other'))
        self.failIf(mapper.exists(otherversion))
    # 2004-09-09 ddaa: test_version_exist_missing is disabled, no
    #    wonder this test fails too.
    # tests.append('test_version_exist_imposter')

    def test_VersionMapperGetId(self):
        """test we can get the Version id correctly"""
        from canonical.launchpad.database import ArchiveMapper, VersionMapper
        from canonical.arch.broker import Archive
        cursor = self.cursor()
        version = self.getTestVersion()
        self.commit()
        mapper = ArchiveMapper()
        archive_id = mapper._getId(version.branch.category.archive, cursor)
        cursor.execute("SELECT currval('branch_id_seq')");
        new_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO Branch (archive, category, branch, version, title, description, visible) VALUES"
                       "(%d, '%s', '%s', '%s', 'a title', 'a description', true)" %
                       (archive_id, version.branch.category.name, version.branch.name, version.name))
        mapper = VersionMapper()
        self.assertEqual(new_id, mapper._getId(version, cursor))
        #    tests.append('test_VersionMapperGetId')

    def test_insert_file(self):
        """test we can insert a file into the database"""
        version = self.getTestVersion()
        revision = version.create_revision("base-0")
        print revision
        revision.add_file("foo", "baaaz", {"md5": "1234"})
        self.commit()
        c = self.cursor()
        c.execute("SELECT count(*) FROM changesetfile")
        self.assertEqual(c.fetchone()[0], 1)
        c.execute("SELECT count(*) FROM changesetfilename")
        self.assertEqual(c.fetchone()[0], 1)
        c.execute("SELECT count(*) FROM changesetfilehash")
        self.assertEqual(c.fetchone()[0], 1)

    tests.append('test_insert_file')


import framework
framework.register(__name__)
