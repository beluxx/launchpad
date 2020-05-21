-- Copyright 2020 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE OCIProject ADD COLUMN project integer REFERENCES product;

ALTER TABLE OCIProject
    ALTER COLUMN distribution
    DROP NOT NULL,
    ADD CONSTRAINT one_container
        CHECK ((project IS NULL) != (distribution IS NULL));

COMMENT ON COLUMN OCIProject.project
    IS 'The project that this OCI project is associated with.';

CREATE UNIQUE INDEX ociproject__project__ociprojectname__key
    ON OCIProject (project, ociprojectname) WHERE project IS NOT NULL;


-- Alter GitRepository table to allow oci_project.
COMMENT ON COLUMN GitRepository.ociprojectname
    IS 'Deprecated column. Should be removed, together with corresponding indexes.';

ALTER TABLE GitRepository
    ADD COLUMN oci_project integer REFERENCES ociproject,
    DROP CONSTRAINT one_container,
    ADD CONSTRAINT one_container CHECK (
        -- Distribution + OCIProjectName, to keep compatibility temporarily
        (project IS NULL AND distribution IS NOT NULL AND sourcepackagename IS NULL AND ociprojectname IS NOT NULL) OR
        -- Project
        (project IS NOT NULL AND distribution IS NULL AND sourcepackagename IS NULL AND oci_project IS NULL) OR
        -- Distribution source package
        (project IS NULL AND distribution IS NOT NULL AND sourcepackagename IS NOT NULL AND oci_project IS NULL) OR
        -- OCI project
        (project IS NULL AND distribution IS NULL AND sourcepackagename IS NULL AND oci_project IS NOT NULL) OR
        -- Personal
        (project IS NULL AND distribution IS NULL AND sourcepackagename IS NULL AND oci_project IS NULL));

INSERT INTO LaunchpadDatabaseRevision VALUES (2210, 8, 8);
