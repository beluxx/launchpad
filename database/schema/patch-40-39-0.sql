SET client_min_messages=ERROR;

-- First, rename severity to importance, to avoid leaky abtractions
-- and to ensure we update all the callsites to reflect the new values.
ALTER TABLE BugTask RENAME COLUMN severity TO importance;

-- Alter the relevant karma action to match.
UPDATE KarmaAction SET name='bugtaskimportancechanged', title='Bug importance changed', summary='Updating the importance of a bug to a specific context. (The importance of a bug can vary depending on where the buggy code is being used.)' WHERE name='bugtaskseveritychanged';

-- Then, set the default to the new value 'Untriaged'.
ALTER TABLE BugTask ALTER COLUMN importance SET DEFAULT 5;

INSERT INTO LaunchpadDatabaseRevision VALUES (40, 39, 0);
