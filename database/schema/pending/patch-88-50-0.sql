BEGIN;

SET client_min_messages=ERROR;

-- DistroRelease table -> DistroSeries
ALTER TABLE DistroRelease RENAME TO DistroSeries;

ALTER TABLE distrorelease_id_seq RENAME TO distroseries_id_seq;
ALTER TABLE DistroSeries ALTER COLUMN id
    SET DEFAULT nextval('distroseries_id_seq');

ALTER TABLE distrorelease_pkey RENAME TO distroseries_pkey;
ALTER TABLE distrorelease_distribution_key
    RENAME TO distroseries__distribution__name__key;

ALTER TABLE distrorelease_distro_release_unique
    RENAME TO distroseries__distribution__id__key;

ALTER TABLE DistroSeries ADD CONSTRAINT distroseries__distribution__fk
    FOREIGN KEY (distribution) REFERENCES Distribution;
ALTER TABLE DistroSeries DROP CONSTRAINT distrorelease_distribution_fk;

ALTER TABLE DistroSeries ADD CONSTRAINT distroseries__driver__fk
    FOREIGN KEY (driver) REFERENCES Person;
ALTER TABLE DistroSeries DROP CONSTRAINT distrorelease_driver_fk;
CREATE INDEX distroseries__driver__idx ON DistroSeries(driver)
    WHERE driver IS NOT NULL;

ALTER TABLE DistroSeries ADD CONSTRAINT distroseries__nominatedarchindep__fk
    FOREIGN KEY (nominatedarchindep) REFERENCES DistroArchRelease;
ALTER TABLE DistroSeries DROP CONSTRAINT distrorelease_nominatedarchindep_fk;

ALTER TABLE DistroSeries ADD CONSTRAINT distroseries__owner__fk
    FOREIGN KEY (owner) REFERENCES Person;
ALTER  TABLE DistroSeries DROP CONSTRAINT distrorelease_owner_fk;
CREATE INDEX distroseries__owner__idx ON DistroSeries(owner);

ALTER TABLE DistroSeries RENAME COLUMN parentrelease TO parent_series;
ALTER TABLE DistroSeries ADD CONSTRAINT distroseries__parent_series__fk
    FOREIGN KEY (parent_series) REFERENCES DistroSeries;

-- DistroReleaseLanguage table -> DistroSeriesLanguage
ALTER TABLE DistroReleaseLanguage RENAME TO DistroSeriesLanguage;

ALTER TABLE distroreleaselanguage_id_seq RENAME TO distroserieslanguage_id_seq;
ALTER TABLE DistroSeriesLanguage ALTER COLUMN id
    SET DEFAULT nextval('distroserieslanguage_id_seq');

ALTER TABLE DistroSeriesLanguage RENAME COLUMN distrorelease TO distroseries;

ALTER TABLE distroreleaselanguage_pkey RENAME TO distroserieslanguage_pkey;
ALTER TABLE distroreleaselanguage_distrorelease_language_uniq
    RENAME TO distroserieslanguage__distroseries__language__key;
ALTER TABLE DistroSeriesLanguage
    ADD CONSTRAINT distroserieslanguage__distroseries__fk
    FOREIGN KEY (distroseries) REFERENCES DistroSeries;
ALTER TABLE DistroSeriesLanguage
    DROP CONSTRAINT distroreleaselanguage_distrorelease_fk;
ALTER TABLE DistroSeriesLanguage
    ADD CONSTRAINT distroserieslanguage__language__fk
    FOREIGN KEY (language) REFERENCES Language;

-- DistroArchRelease -> DistroArchSeries
ALTER TABLE DistroArchRelease RENAME TO DistroArchSeries;

ALTER TABLE distroarchrelease_id_seq RENAME TO distroarchseries_id_seq;
ALTER TABLE DistroArchSeries ALTER COLUMN id
    SET DEFAULT nextval('distroarchseries_id_seq');

ALTER TABLE DistroArchSeries RENAME COLUMN distrorelease TO distroseries;

ALTER TABLE distroarchrelease_pkey RENAME TO distroarchseries_pkey;
ALTER TABLE DistroArchSeries
    ADD CONSTRAINT distroarchseries__architecturetag__distroseries__key
    UNIQUE (architecturetag, distroseries);
ALTER TABLE DistroArchSeries DROP CONSTRAINT
    distroarchrelease_distrorelease_architecturetag_unique;
DROP INDEX distroarchrelease_architecturetag_idx;
ALTER TABLE distroarchrelease_distrorelease_idx
    RENAME TO distroarchseries__distroseries__idx;
ALTER TABLE DistroArchSeries
    DROP CONSTRAINT distroarchrelease_distrorelease_processorfamily_unique;
ALTER TABLE DistroArchSeries
    ADD CONSTRAINT distroarchseries__processorfamily__distroseries__key
    UNIQUE (processorfamily, distroseries);
DROP INDEX distroarchrelease_processorfamily_idx;

ALTER TABLE DistroArchSeries ADD CONSTRAINT distroarchseries__distroseries__fk
    FOREIGN KEY (distroseries) REFERENCES DistroSeries;
ALTER TABLE DistroArchSeries DROP CONSTRAINT "$1";
ALTER TABLE DistroArchSeries
    ADD CONSTRAINT distroarchseries__processorfamily__fk
    FOREIGN KEY (processorfamily) REFERENCES ProcessorFamily;
ALTER TABLE DistroArchSeries DROP CONSTRAINT "$2";
ALTER TABLE DistroArchSeries ADD CONSTRAINT distroarchseries__owner__fk
    FOREIGN KEY (owner) REFERENCES Person;
CREATE INDEX distroarchseries__owner__idx ON DistroArchSeries(owner);
ALTER TABLE DistroArchSeries DROP CONSTRAINT "$3";

-- DistroReleasePackageCache -> DistroSeriesPackageCache
ALTER TABLE DistroReleasePackageCache RENAME TO DistroSeriesPackageCache;

ALTER TABLE distroreleasepackagecache_id_seq
    RENAME TO distroseriespackagecache_id_seq;
ALTER TABLE DistroSeriesPackageCache ALTER COLUMN id
    SET DEFAULT nextval('distroseriespackagecache');

ALTER TABLE DistroSeriesPackageCache
    RENAME COLUMN distrorelease TO distroseries;

ALTER TABLE distroreleasepackagecache_pkey
    RENAME TO distroseriespackagecache_pkey;
ALTER TABLE distroreleasepackagecache_fti
    RENAME TO distroseriespackagecache_fti;

ALTER TABLE DistroSeriesPackageCache
    ADD CONSTRAINT
    distroseriespackagecache__binarypackagename_distroseries__key
    UNIQUE (binarypackagename, distroseries),

    DROP CONSTRAINT
    distroreleasepackagecache_distrorelease_binarypackagename_uniq,

    DROP CONSTRAINT distroreleasepackagecache_binarypackagename_fk,

    ADD CONSTRAINT distroseriespackagecache__binarypackagename__fk
    FOREIGN KEY (binarypackagename) REFERENCES BinaryPackageName,

    DROP CONSTRAINT distroreleasepackagecache_distrorelease_fk,

    ADD CONSTRAINT distroseriespackagecache__distroseries__fk
    FOREIGN KEY (distroseries) REFERENCES DistroSeries;

CREATE INDEX distroseriespackagecache__distroseries__idx
    ON DistroSeriesPackageCache(distroseries);


-- BugNomination
ALTER TABLE BugNomination RENAME COLUMN distrorelease TO distroseries;
ALTER TABLE BugNomination
    DROP CONSTRAINT bugnomination__distrorelease__fk,
    ADD CONSTRAINT bugnomination__distroseries__fk
        FOREIGN KEY (distroseries) REFERENCES DistroSeries;


-- BugTask
ALTER TABLE BugTask RENAME COLUMN distrorelease TO distroseries;
ALTER TABLE bugtask_product_key RENAME TO bugtask__product__bug__key;
ALTER TABLE bugtask_assignee_idx RENAME TO bugtask__assignee__idx;
ALTER TABLE bugtask_bug_idx RENAME TO bugtask__bug__idx;
ALTER TABLE bugtask_datecreated_idx RENAME TO bugtask__datecreated__idx;
ALTER TABLE bugtask_distribution_and_sourcepackagename_idx
    RENAME TO bugtask__distribution__sourcepackagename__idx;
DROP INDEX bugtask_distribution_idx;
ALTER TABLE bugtask_distrorelease_and_sourcepackagename_idx
    RENAME TO bugtask__distroseries__sourcepackagename__idx;
DROP INDEX bugtask_distrorelease_idx;
ALTER TABLE bugtask_milestone_idx RENAME TO bugtask__milestone__idx;
ALTER TABLE bugtask_owner_idx RENAME TO bugtask__owner__idx;
DROP INDEX bugtask_sourcepackagename_idx;
CREATE INDEX bugtask__sourcepackagename__idx ON BugTask(sourcepackagename)
    WHERE sourcepackagename IS NOT NULL;
DROP INDEX bugtask_binarypackagename_idx;
CREATE INDEX bugtask__binarypackagename__idx ON BugTask(binarypackagename)
    WHERE binarypackagename IS NOT NULL;

ALTER TABLE BugTask
    DROP CONSTRAINT bugtask_binarypackagename_fk,
    ADD CONSTRAINT bugtask__binarypackagename__fk
        FOREIGN KEY (binarypackagename) REFERENCES BinaryPackageName,
    DROP CONSTRAINT bugtask_bug_fk,
    ADD CONSTRAINT bugtask__bug__fk
        FOREIGN KEY (bug) REFERENCES Bug,
    DROP CONSTRAINT bugtask_bugwatch_fk,
    ADD CONSTRAINT bugtask__bugwatch__fk
        FOREIGN KEY (bugwatch) REFERENCES BugWatch,
    DROP CONSTRAINT bugtask_distribution_fk,
    ADD CONSTRAINT bugtask__distribution__fk
        FOREIGN KEY (distribution) REFERENCES Distribution,
    DROP CONSTRAINT bugtask_distribution_milestone_fk,
    ADD CONSTRAINT bugtask__distribution__milestone__fk FOREIGN KEY (
        distribution, milestone) REFERENCES Milestone(distribution, id),
    DROP CONSTRAINT bugtask_distrorelease_fk,
    ADD CONSTRAINT bugtask__distroseries__fk
        FOREIGN KEY (distroseries) REFERENCES DistroSeries,
    DROP CONSTRAINT bugtask_owner_fk,
    ADD CONSTRAINT bugtask__owner__fk FOREIGN KEY (owner) REFERENCES Person,
    DROP CONSTRAINT bugtask_person_fk,
    ADD CONSTRAINT bugtask__assignee__fk
        FOREIGN KEY (assignee) REFERENCES Person,
    DROP CONSTRAINT bugtask_product_fk,
    ADD CONSTRAINT bugtask__product__fk
        FOREIGN KEY (product) REFERENCES Product,
    DROP CONSTRAINT bugtask_product_milestone_fk,
    ADD CONSTRAINT bugtask__product__milestone__fk
        FOREIGN KEY (product, milestone) REFERENCES Milestone(product, id),
    DROP CONSTRAINT bugtask_productseries_fk,
    ADD CONSTRAINT bugtask__productseries__fk
        FOREIGN KEY (productseries) REFERENCES ProductSeries,
    DROP CONSTRAINT bugtask_sourcepackagename_fk,
    ADD CONSTRAINT bugtask__sourcepackagename__fk
        FOREIGN KEY (sourcepackagename) REFERENCES SourcepackageName;


-- ComponentSelection
ALTER TABLE ComponentSelection RENAME COLUMN distrorelease TO distroseries;
DROP INDEX componentselection__distrorelease__component__uniq;
ALTER TABLE ComponentSelection
    ADD CONSTRAINT componentselection__distroseries__component__key
        UNIQUE (distroseries, component),
    DROP CONSTRAINT "$1",
    ADD CONSTRAINT componentselection__distroseries__fk
        FOREIGN KEY (distroseries) REFERENCES DistroSeries,
    DROP CONSTRAINT "$2",
    ADD CONSTRAINT componentselection__component__fk
        FOREIGN KEY (component) REFERENCES Component;


-- DevelopmentManifest
/*
ALTER TABLE DevelopmentManifest RENAME COLUMN distrorelease TO distroseries;
ALTER TABLE DevelopmentManifest
    ADD CONSTRAINT developmentmanifest__distroseries__fk
        FOREIGN KEY (distroseries) REFERENCES DistroSeries,
    DROP CONSTRAINT developmentmanifest_distrorelease_fk;
ALTER TABLE developmentmanifest_manifest_idx
    RENAME TO developmentmanifest__manifest__idx;
ALTER TABLE developmentmanifest_datecreated_idx
    RENAME TO developmentmanifest__datecreated__idx;
ALTER TABLE developmentmanifest_owner_datecreated_idx
    RENAME TO developmentmanifest__owner__datecreated__idx;
*/


-- DistroReleaseRole
DROP SEQUENCE distroreleaserole_id_seq;


-- MirrorCdImageDistroRelease
ALTER TABLE MirrorCdImageDistroRelease RENAME TO MirrorCdImageDistroSeries;
ALTER TABLE MirrorCdImageDistroSeries
    RENAME COLUMN distrorelease TO distroseries;
ALTER TABLE mirrorcdimagedistrorelease_pkey
    RENAME TO mirrorcdimagedistroseries_pkey;
ALTER TABLE mirrorcdimagedistrorelease_id_seq
    RENAME TO mirrorcdimagedistroseries_id_seq;
ALTER TABLE MirrorCdImageDistroSeries
    ALTER COLUMN id SET DEFAULT nextval('mirrorcdimagedistroseries_id_seq'),
    ADD CONSTRAINT mirrorcdimagedistroseries__distroseries__fk
        FOREIGN KEY (distroseries) REFERENCES DistroSeries,
    DROP CONSTRAINT mirrorcdimagedistrorelease_distrorelease_fkey,
    ADD CONSTRAINT mirrorcdimagedistroseries__distribution_mirror__fk
        FOREIGN KEY (distribution_mirror) REFERENCES DistributionMirror,
    DROP CONSTRAINT mirrorcdimagedistrorelease_distribution_mirror_fkey,
    ADD CONSTRAINT mirrorcdimagedistroseries__unq
        UNIQUE (distroseries, flavour, distribution_mirror),
    DROP CONSTRAINT mirrorcdimagedistrorelease__unq;


-- MirrorDistroReleaseSource
ALTER TABLE MirrorDistroReleaseSource RENAME TO MirrorDistroSeriesSource;
ALTER TABLE mirrordistroreleasesource_pkey
    RENAME TO mirrordistroseriessource_pkey;
ALTER TABLE MirrorDistroSeriesSource
    RENAME COLUMN distrorelease TO distroseries;
ALTER TABLE mirrordistroreleasesource_id_seq
    RENAME TO mirrordistroseriessource_id_seq;
ALTER TABLE MirrorDistroSeriesSource
    ALTER COLUMN id SET DEFAULT nextval('mirrordistroseriessource_id_seq');
ALTER TABLE mirrordistroreleasesource_uniq
    RENAME TO mirrordistroseriessource_uniq;
ALTER TABLE MirrorDistroSeriesSource
    DROP CONSTRAINT mirrordistroreleasesource__component__fk,
    DROP CONSTRAINT mirrordistroreleasesource_distribution_mirror_fkey,
    DROP CONSTRAINT mirrordistroreleasesource_distro_release_fkey;
ALTER TABLE MirrorDistroSeriesSource
    ADD CONSTRAINT mirrordistroseriessource__component__fk
        FOREIGN KEY (component) REFERENCES Component,
    ADD CONSTRAINT mirrordistroseriessource__distribution_mirror__fk
        FOREIGN KEY (distribution_mirror) REFERENCES DistributionMirror,
    ADD CONSTRAINT mirrordistroseriessource__distroseries__fk
        FOREIGN KEY (distroseries) REFERENCES DistroSeries;


-- POTemplate
ALTER TABLE POTemplate RENAME COLUMN distrorelease TO distroseries;
ALTER TABLE potemplate_distrorelease_key
    RENAME TO potemplate_distroseries_uniq;
ALTER TABLE POTemplate
    DROP CONSTRAINT potemplate_distrorelease_fk,
    DROP CONSTRAINT "$2";
ALTER TABLE POTemplate
    ADD CONSTRAINT potemplate__distrorelease__fk
        FOREIGN KEY (distroseries) REFERENCES DistroSeries,
    ADD CONSTRAINT potemplate__from_sourcepackagename__fk
        FOREIGN KEY (from_sourcepackagename) REFERENCES SourcepackageName;


-- SecureSourcePackagePublishingHistory
ALTER TABLE SecureSourcePackagePublishingHistory
    RENAME COLUMN distrorelease TO distroseries;
ALTER TABLE SecureSourcePackagePublishingHistory
    DROP CONSTRAINT securesourcepackagepublishinghistory_distrorelease_fk;
ALTER TABLE SecureSourcePackagePublishingHistory
    ADD CONSTRAINT securesourcepackagepublishinghistory__distroseries__fk
        FOREIGN KEY (distroseries) REFERENCES DistroSeries;
ALTER TABLE securesourcepackagepublishinghistory_distrorelease_idx
    RENAME TO securesourcepackagepublishinghistory__distroseries__idx;


-- PackageUploadBuild
ALTER TABLE distroreleasequeuebuild_pkey RENAME TO packageuploadbuild_pkey;
ALTER TABLE distroreleasequeuebuild__distroreleasequeue__build__unique
    RENAME TO packageuploadbuild__packageupload__build__key;


-- PackageUploadSource
ALTER TABLE distroreleasequeuesource_pkey RENAME TO packageuploadsource_pkey;
ALTER TABLE distroreleasequeuesource__distroreleasequeue__sourcepackagerele
    RENAME TO packageuploadsource__packageupload__sourcepackagerelease__key;


-- PackageUploadCustom
ALTER TABLE distroreleasequeuecustom_pkey RENAME TO packageuploadcustom_pkey;


-- PackageUpload
ALTER TABLE distroreleasequeue_pkey RENAME TO packageupload_pkey;
ALTER TABLE PackageUpload RENAME COLUMN distrorelease TO distroseries;
ALTER TABLE PackageUpload DROP CONSTRAINT packageupload__distrorelease__fk;
ALTER TABLE PackageUpload ADD CONSTRAINT packageupload__distroseries__fk
    FOREIGN KEY (distroseries) REFERENCES DistroSeries;
ALTER TABLE packageupload__distrorelease__key
    RENAME TO packageupload__distroseries__key;
ALTER TABLE packageupload__distrorelease__status__idx
    RENAME TO packageupload__distroseries__status__idx;


-- Packaging
ALTER TABLE Packaging RENAME COLUMN distrorelease TO distroseries;
ALTER TABLE packaging_distrorelease_and_sourcepackagename_idx
    RENAME TO packaging__distroseries__sourcepackagename__idx;
ALTER TABLE Packaging DROP CONSTRAINT packaging_distrorelease_fk;
ALTER TABLE Packaging ADD CONSTRAINT packaging__distroseries__fk
    FOREIGN KEY (distroseries) REFERENCES DistroSeries;


-- MirrorDistroArchRelease
ALTER TABLE MirrorDistroArchRelease RENAME TO MirrorDistroArchSeries;
ALTER TABLE mirrordistroarchrelease_pkey RENAME TO mirrordistroarchseries_pkey;
ALTER TABLE mirrordistroarchrelease_uniq RENAME TO mirrordistroarchseries_uniq;
ALTER TABLE mirrordistroarchrelease_id_seq
    RENAME TO mirrordistroarchseries_id_seq;
ALTER TABLE MirrorDistroArchSeries
    ALTER COLUMN id SET DEFAULT nextval('mirrordistroarchseries_id_seq');
ALTER TABLE MirrorDistroArchSeries
    RENAME COLUMN distro_arch_release TO distro_arch_series;
ALTER TABLE MirrorDistroArchSeries
    DROP CONSTRAINT mirrordistroarchrelease__component__fk,
    DROP CONSTRAINT mirrordistroarchrelease_distribution_mirror_fkey,
    DROP CONSTRAINT mirrordistroarchrelease_distro_arch_release_fkey;
ALTER TABLE MirrorDistroArchSeries
    ADD CONSTRAINT mirrordistroarchseries__component__fk
        FOREIGN KEY (component) REFERENCES Component,
    ADD CONSTRAINT mirrordistroarchseries__distribution_mirror__fk
        FOREIGN KEY (distribution_mirror) REFERENCES DistributionMirror,
    ADD CONSTRAINT mirrordistroarchseries__distro_arch_series__fk
        FOREIGN KEY (distro_arch_series) REFERENCES DistroArchSeries;


-- PocketChroot
ALTER TABLE pocketchroot_distroarchrelease_key
    RENAME TO pocketchroot__distroarchseries__key;
ALTER TABLE PocketChroot RENAME COLUMN distroarchrelease TO distroarchseries;
ALTER TABLE PocketChroot DROP CONSTRAINT "$1", DROP CONSTRAINT "$2";
ALTER TABLE PocketChroot
    ADD CONSTRAINT pocketchroot__distroarchseries__fk
        FOREIGN KEY (distroarchseries) REFERENCES DistroArchSeries,
    ADD CONSTRAINT pocketchroot__libraryfilealias__fk
        FOREIGN KEY (chroot) REFERENCES LibraryFileAlias;


-- Build
ALTER TABLE Build RENAME COLUMN distroarchrelease TO distroarchseries;
ALTER TABLE build_distroarchrelease_and_datebuilt_idx
    RENAME TO build__distroarchseries__datebuilt__idx;
ALTER TABLE Build
    DROP CONSTRAINT "$1", DROP CONSTRAINT "$2",
    DROP CONSTRAINT "$3", DROP CONSTRAINT "$4", DROP CONSTRAINT "$6";
ALTER TABLE Build
    ADD CONSTRAINT build__processor__fk
        FOREIGN KEY (processor) REFERENCES Processor,
    ADD CONSTRAINT build__distroarchseries__fk
        FOREIGN KEY (distroarchseries) REFERENCES DistroArchSeries,
    ADD CONSTRAINT build__buildlog__fk
        FOREIGN KEY (buildlog) REFERENCES LibraryFileAlias,
    ADD CONSTRAINT build__builder__fk
        FOREIGN KEY (builder) REFERENCES Builder,
    ADD CONSTRAINT build__sourcepackagerelease__fk
        FOREIGN KEY (sourcepackagerelease) REFERENCES SourcePackageRelease;


-- Detect remaining tables
SELECT relname from pg_class where relname like '%distrorelease%';
SELECT relname from pg_class where relname like '%distroarchrelease%';

-- Remaining columns
-- ???

\d Build

INSERT INTO LaunchpadDatabaseRevision VALUES (88, 50, 0);
ABORT;
