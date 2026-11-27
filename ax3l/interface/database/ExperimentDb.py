"""Read and save four-view checkpoints through the shared event database."""

from dataclasses import asdict
import json

from ax3l.interface.database.DbMgr import DbMgr
from ax3l.interface.database.EventLogDb import EventLogDb
from ax3l.constants.DEventCategory import DEventCategory as Events
from ax3l.entities.ExperimentState import ExperimentState
from ax3l.entities.ViewProposal import ViewProposal


class ExperimentDb:
    def __init__(self, db: DbMgr):
        self._db = db

    def load(self) -> ExperimentState | None:
        rows = self._db.query("""
            SELECT m.content FROM events e JOIN event_messages m USING (event_id)
            WHERE e.category = %s AND e.name = %s ORDER BY e.event_id DESC LIMIT 1
        """, (Events.Configuration.CATEGORY, Events.Configuration.STATE_SAVED))
        if not rows:
            return None
        data = json.loads(rows[0]["content"])
        for key in ("previous", "proposals"):
            data[key] = {name: ViewProposal(proposal["hypothesis"], proposal["values"])
                         for name, proposal in data[key].items()}
        return ExperimentState(**data)

    def save(self, state: ExperimentState) -> None:
        EventLogDb(self._db).log(Events.Configuration.STATE_SAVED, Events.Configuration.CATEGORY, "INFO",
                     json.dumps(asdict(state), allow_nan=False), process_id=state.experiment_id)

    def initial_config(self, experiment_id: str) -> dict:
        rows = self._db.query("""
            SELECT JSON_EXTRACT(m.content, '$.config') AS config
            FROM events e JOIN event_messages m USING (event_id)
            WHERE e.category = %s AND e.name = %s AND e.process_id = %s
            ORDER BY e.event_id LIMIT 1
        """, (Events.Configuration.CATEGORY, Events.Configuration.STATE_SAVED, experiment_id))
        return json.loads(rows[0]["config"])

    def comparison(self, run_id: str) -> dict | None:
        rows = self._db.query("""
            SELECT m.content FROM events e JOIN event_messages m USING (event_id)
            WHERE e.category = %s AND e.name = %s AND e.process_id = %s
            ORDER BY e.event_id DESC LIMIT 1
        """, (Events.Configuration.CATEGORY, Events.Configuration.COMPARED, run_id))
        return json.loads(rows[0]["content"]) if rows else None

    def run_events(self, run_id: str) -> dict[str, int]:
        rows = self._db.query("""
            SELECT name, event_id FROM events WHERE process_id = %s AND
                ((category = %s AND name = %s) OR (category = %s AND name IN (%s, %s, %s)))
        """, (run_id, Events.Configuration.CATEGORY, Events.Configuration.PROPOSAL_ACCEPTED,
              Events.SnakeLab.CATEGORY, Events.SnakeLab.SUBMITTED, Events.SnakeLab.STARTED,
              Events.SnakeLab.COMPLETED))
        return {row["name"]: row["event_id"] for row in rows}
