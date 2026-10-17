"""Populate Ax3l reporting tables and incrementally consume completed source data."""

import argparse
import json

from ax3l.activity.CompletedRounds import completed_rounds
from ax3l.app.DbMgr import DbMgr
from ax3l.app.ReportingDb import ReportingDb
from ax3l.app.snakelab.RoundRobinState import ROUND_ROBIN_ORDER


class ReportingRefresh:
    def __init__(self, db: DbMgr):
        self._db = db
        self._reports = ReportingDb(db)

    def refresh(self, *, initialize: bool = False, rebuild: bool = False) -> dict:
        if initialize:
            self._reports.initialize()
        with self._db.transaction():
            state = self._reports.lock_state()
            if rebuild:
                self._reports.reset()
                state = self._reports.lock_state()
            last_summary = self._reports.last_summary_id()
            while runs := self._reports.pending_runs():
                self._reports.summarize_runs([run["run_id"] for run in runs])
            self._reports.add_run_totals(last_summary)

            last_event = self._reports.last_event_id()
            reordered = False
            pending_events = self._reports.pending_events()
            for offset in range(0, len(pending_events), 512):
                events = self._reports.events([
                    event["event_id"] for event in pending_events[offset:offset + 512]])
                for event in events:
                    reordered |= event["event_id"] < last_event
                    self._reports.save_event(event)
            if reordered:
                # An earlier checkpoint/proposal can change a turn's meaning.
                # Resolve it again from the local event projection.
                self._reports.reset_turns()
            last_completion = state["last_completion_id"]
            replay = reordered
            after_turn = 0
            while turns := self._reports.pending_turns(after_turn):
                replay |= any(turn["parameter_index"] is not None
                              and turn["completion_id"] <= last_completion for turn in turns)
                for turn in turns:
                    self._reports.save_turn(turn)
                after_turn = turns[-1]["completion_id"]
            # A late-committing source transaction can insert an earlier turn.
            # Recompute from our small projection only in that case.
            turns = self._reports.turns_after(0 if replay else last_completion)
            rounds, expected = completed_rounds(
                turns, len(ROUND_ROBIN_ORDER),
                0 if replay else state["experiment_cycles"],
                0 if replay else state["expected_parameter"])
            if turns:
                last_completion = turns[-1]["completion_id"]
            self._reports.save_progress(rounds, expected, last_completion)
            return self._reports.totals()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild", action="store_true",
                        help="Rebuild only Ax3l reporting tables from source data")
    args = parser.parse_args()
    db = DbMgr(initialize_event_tables=False)
    try:
        print(json.dumps(ReportingRefresh(db).refresh(initialize=True, rebuild=args.rebuild)))
    finally:
        db.close()


if __name__ == "__main__":
    main()
