"""Checkpoint the current parameter in the shared event database."""

import json

from ax3l.app.snakelab.SingleParameters import SINGLE_PARAMETERS
from ax3l.constants.DEventCategory import DEventCategory as Events


class RoundRobinState:
    def __init__(self, db):
        self.db = db
        self.order = list(SINGLE_PARAMETERS)

    def begin(self):
        """Resume an unfinished turn, or advance once past an accepted proposal.

        The acceptance event is already durable before MCP replies. Using it as
        the completion marker also handles a lost reply without skipping a turn.
        Like the legacy selector, refuse to reinterpret a changed parameter order.
        """
        rows = self.db.query("""
            SELECT e.event_id, m.content,
                   EXISTS(SELECT 1 FROM events p
                          WHERE p.event_id > e.event_id AND p.category = %s
                            AND p.name = %s) AS accepted
            FROM events e JOIN event_messages m USING (event_id)
            WHERE e.category = %s AND e.name = %s
            ORDER BY e.event_id DESC LIMIT 1
        """, (Events.Configuration.CATEGORY, Events.Configuration.PROPOSAL_ACCEPTED,
               Events.Configuration.CATEGORY, "round_robin_checkpoint"))
        index = 0
        if rows:
            saved = json.loads(rows[0]["content"])
            if saved["parameter_order"] != self.order:
                raise ValueError("Search parameter order changed; migrate the saved checkpoint before resuming")
            index = saved["index"]
            if type(index) is not int or not 0 <= index < len(self.order):
                raise ValueError("Invalid round-robin checkpoint index")
            if rows[0]["accepted"]:
                index = (index + 1) % len(self.order)
        self.db.log("round_robin_checkpoint", Events.Configuration.CATEGORY, "INFO",
                    json.dumps({"parameter_order": self.order, "index": index}))
        return self.order[index]
