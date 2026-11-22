"""Clear an unsubmitted experiment after the operator stops Ax3l services."""

import argparse
import sys

from ax3l.app.DbMgr import DbMgr
from ax3l.app.snakelab.ExperimentDb import ExperimentDb


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check database access without changing state")
    args = parser.parse_args(argv)
    db = DbMgr(initialize_event_tables=False)
    try:
        experiments = ExperimentDb(db)
        if args.check:
            experiments.draft()
            return 0
        try:
            result = experiments.wipe_workspace()
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 1
        if result is None:
            print("No unfinished experiment setup to clear.")
        else:
            draft_id, count = result
            print(f"Cleared experiment {draft_id}: {count} setup events and their details.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
