"""Dispatch domain tool requests on the Ax3l side of the transport boundary."""

import json

from ax3l.app.DbMgr import DbMgr
from ax3l.constants.DEventCategory import DEventCategory
from ax3l.app.snakelab.SubmitSingleValueHandler import SubmitSingleValueHandler
from ax3l.app.snakelab.SubmitPairValuesHandler import SubmitPairValuesHandler
from ax3l.app.snakelab.SelectParameterHandler import SelectParameterHandler
from ax3l.app.snakelab.RunSimulationHandler import RunSimulationHandler
from ax3l.app.snakelab.RequestSeedChangeHandler import RequestSeedChangeHandler
from ax3l.app.snakelab.SubmitSimulationSummaryHandler import SubmitSimulationSummaryHandler
from ax3l.interface.SimulationData import SimulationData
from ax3l.zmq.ZMQMsg import ZMQMsg


def handle_tool(request: ZMQMsg) -> dict:
    db = DbMgr()
    try:
        category = DEventCategory.Tool
        db.log(category.RECEIVED, category.CATEGORY, "INFO",
               json.dumps(request.to_dict(), ensure_ascii=False))
        handlers = {"submit_single_value": SubmitSingleValueHandler,
                    "submit_pair_values": SubmitPairValuesHandler,
                    "select_parameter": SelectParameterHandler,
                    "run_simulation": RunSimulationHandler,
                    "request_seed_change": RequestSeedChangeHandler,
                    "submit_simulation_summary": SubmitSimulationSummaryHandler}
        if request.target == "snakelab" and request.method == "read_simulation_data":
            return SimulationData(db).read(request.payload)
        if request.target == "snakelab" and request.method == "read_analysis_data":
            return SimulationData(db).read_run(request.payload)
        if request.target != "snakelab" or request.method not in handlers:
            return {"status": "error", "error": {"code": "unknown_method", "message": "Unknown domain or method"}}
        return handlers[request.method](db).submit(request.payload)
    finally:
        db.close()
