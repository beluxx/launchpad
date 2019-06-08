-- Copyright 2018 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE TABLE GitRule (
    id serial PRIMARY KEY,
    repository integer NOT NULL REFERENCES gitrepository,
    position integer NOT NULL,
    ref_pattern text NOT NULL,
    creator integer NOT NULL REFERENCES person,
    date_created timestamp without time zone DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC') NOT NULL,
    date_last_modified timestamp without time zone DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC') NOT NULL,
    CONSTRAINT gitrule__repository__position__key UNIQUE (repository, position) DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT gitrule__repository__ref_pattern__key UNIQUE (repository, ref_pattern),
    -- Used by repository_matches_rule constraint on GitRuleGrant.
    CONSTRAINT gitrule__repository__id__key UNIQUE (repository, id)
);

COMMENT ON TABLE GitRule IS 'An access rule for a Git repository.';
COMMENT ON COLUMN GitRule.repository IS 'The repository that this rule is for.';
COMMENT ON COLUMN GitRule.position IS 'The position of this rule in its repository''s rule order.';
COMMENT ON COLUMN GitRule.ref_pattern IS 'The pattern of references matched by this rule.';
COMMENT ON COLUMN GitRule.creator IS 'The user who created this rule.';
COMMENT ON COLUMN GitRule.date_created IS 'The time when this rule was created.';
COMMENT ON COLUMN GitRule.date_last_modified IS 'The time when this rule was last modified.';

CREATE TABLE GitRuleGrant (
    id serial PRIMARY KEY,
    repository integer NOT NULL REFERENCES gitrepository,
    rule integer NOT NULL REFERENCES gitrule,
    grantee_type integer NOT NULL,
    grantee integer REFERENCES person,
    can_create boolean DEFAULT false NOT NULL,
    can_push boolean DEFAULT false NOT NULL,
    can_force_push boolean DEFAULT false NOT NULL,
    grantor integer NOT NULL REFERENCES person,
    date_created timestamp without time zone DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC') NOT NULL,
    date_last_modified timestamp without time zone DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC') NOT NULL,
    CONSTRAINT repository_matches_rule FOREIGN KEY (repository, rule) REFERENCES gitrule (repository, id),
    -- 2 == PERSON
    CONSTRAINT has_grantee CHECK ((grantee_type = 2) = (grantee IS NOT NULL))
);

CREATE INDEX gitrulegrant__repository__idx
    ON GitRuleGrant(repository);
CREATE UNIQUE INDEX gitrulegrant__rule__grantee_type__key
    ON GitRuleGrant(rule, grantee_type)
    -- 2 == PERSON
    WHERE grantee_type != 2;
CREATE UNIQUE INDEX gitrulegrant__rule__grantee_type__grantee_key
    ON GitRuleGrant(rule, grantee_type, grantee)
    -- 2 == PERSON
    WHERE grantee_type = 2;

COMMENT ON TABLE GitRuleGrant IS 'An access grant for a Git repository rule.';
COMMENT ON COLUMN GitRuleGrant.repository IS 'The repository that this grant is for.';
COMMENT ON COLUMN GitRuleGrant.rule IS 'The rule that this grant is for.';
COMMENT ON COLUMN GitRuleGrant.grantee_type IS 'The type of entity being granted access.';
COMMENT ON COLUMN GitRuleGrant.grantee IS 'The person or team being granted access.';
COMMENT ON COLUMN GitRuleGrant.can_create IS 'Whether creating references is allowed.';
COMMENT ON COLUMN GitRuleGrant.can_push IS 'Whether pushing references is allowed.';
COMMENT ON COLUMN GitRuleGrant.can_force_push IS 'Whether force-pushing references is allowed.';
COMMENT ON COLUMN GitRuleGrant.grantor IS 'The user who created this grant.';
COMMENT ON COLUMN GitRuleGrant.date_created IS 'The time when this grant was created.';
COMMENT ON COLUMN GitRuleGrant.date_last_modified IS 'The time when this grant was last modified.';

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 85, 0);
