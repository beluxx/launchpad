#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# pylint: disable-msg=C0103,W0403

"""Check for invalid/missing TeamParticipation entries.

Invalid TP entries are the ones for which there are no active TeamMemberships
leading to.

This script is usually run on staging to find discrepancies between the
TeamMembership and TeamParticipation tables which are a good indication of
bugs in the code which maintains the TeamParticipation table.

Ideally there should be database constraints to prevent this sort of
situation, but that's not a simple thing and this should do for now.
"""

import _pythonpath
import transaction
from zope.component import getUtility

from canonical.database.sqlbase import cursor
from lp.registry.interfaces.person import IPersonSet
from lp.services.scripts.base import (
    LaunchpadScript,
    LaunchpadScriptFailure,
    )


def chunked(things, chunk_size=50):
    """Yield `things` in chunks of not more than `chunk_size` slices."""
    for offset in xrange(0, len(things), chunk_size):
        yield things[offset:offset + chunk_size]


def check_teamparticipation(log):
    # Check self-participation.
    query = """
        SELECT id, name
        FROM Person WHERE id NOT IN (
            SELECT person FROM Teamparticipation WHERE person = team
            ) AND merged IS NULL
        """
    cur = cursor()
    cur.execute(query)
    non_self_participants = cur.fetchall()
    if len(non_self_participants) > 0:
        log.warn("Some people/teams are not members of themselves: %s"
                 % non_self_participants)

    # Check if there are any circular references between teams.
    cur.execute("""
        SELECT tp.team, tp2.team
        FROM teamparticipation AS tp, teamparticipation AS tp2
        WHERE tp.team = tp2.person
            AND tp.person = tp2.team
            AND tp.id != tp2.id;
        """)
    circular_references = cur.fetchall()
    if len(circular_references) > 0:
        raise LaunchpadScriptFailure(
            "Circular references found: %s" % circular_references)

    # Check if there are any missing/spurious TeamParticipation entries.
    cur.execute("SELECT id FROM Person WHERE teamowner IS NOT NULL")
    team_ids = [row[0] for row in cur.fetchall()]
    transaction.abort()

    def get_participants(team):
        """Recurse through the team's members to get all its participants."""
        participants = set()
        for member in team.activemembers:
            participants.add(member)
            if member.is_team:
                participants.update(get_participants(member))
        return participants

    load_teams = getUtility(IPersonSet).getPrecachedPersonsFromIDs

    for batch in chunked(team_ids):
        for team in load_teams(batch):
            expected = get_participants(team)
            found = set(team.allmembers)
            difference = expected.difference(found)
            if len(difference) > 0:
                people = ", ".join("%s (%s)" % (person.name, person.id)
                                   for person in difference)
                log.warn("%s (%s): missing TeamParticipation entries for %s."
                         % (team.name, team.id, people))
            reverse_difference = found.difference(expected)
            if len(reverse_difference) > 0:
                people = ", ".join("%s (%s)" % (person.name, person.id)
                                   for person in reverse_difference)
                log.warn("%s (%s): spurious TeamParticipation entries for %s."
                         % (team.name, team.id, people))
            transaction.abort()


class CheckTeamParticipationScript(LaunchpadScript):
    description = "Check for invalid/missing TeamParticipation entries."

    def main(self):
        check_teamparticipation(self.logger)

if __name__ == '__main__':
    CheckTeamParticipationScript("check-teamparticipation").run()
