import argparse
import os

from ax3l.interface.database.DbMgr import DbMgr
from ax3l.app.experiment.ExperimentLoop import ExperimentLoop
from ax3l.interface.Configuration import Configuration
from ax3l.interface.LLM import LLM
from ax3l.interface.Network import Network
from ax3l.interface.SnakeLab import SnakeLab
from ax3l.server.ToolHandler import handle_tool
from ax3l.zmq.ZMQServer import ZMQServer


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Ax3l's four-view experiment cycle.")
    parser.add_argument("--zmq-endpoint", default=None)
    parser.add_argument("--llm-url", type=Configuration.validate_llamasrv_url,
                        help="Override the configured LlamaSrv base URL")
    parser.add_argument("--cycles", type=int, help="Stop after this many completed single-view experiments")
    args = parser.parse_args()
    if args.cycles is not None and args.cycles < 1:
        parser.error("--cycles must be a positive integer")
    endpoint = args.zmq_endpoint if args.zmq_endpoint is not None else os.environ.get("AX3L_ZMQ_ENDPOINT")
    if endpoint is None:
        endpoint = Network.endpoint()
    llm_url = args.llm_url if args.llm_url is not None else Network.llamasrv_url()
    try:
        db = DbMgr()
        try:
            with ZMQServer(endpoint, handle_tool) as server:
                print(f"Ax3l listening on {server.endpoint}; starting four-view experiments.", flush=True)
                ExperimentLoop(db, LLM(llm_url), SnakeLab()).run(cycles=args.cycles, check=server.check)
        finally:
            db.close()
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
