"""Refresh the persistent reporting summaries from the command line."""

import argparse
import json

from ax3l.app.reporting.ReportingRefresh import ReportingRefresh
from ax3l.interface.database.DbMgr import DbMgr


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
