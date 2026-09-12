"""Dispatch domain tool requests on the Ax3l side of the transport boundary."""

from ax3l.app.DbMgr import DbMgr
from ax3l.app.snakelab.SubmitSingleValueHandler import SubmitSingleValueHandler
from ax3l.zmq.ZMQMsg import ZMQMsg


def handle_tool(request: ZMQMsg) -> dict:
    if (request.target, request.method) != ("snakelab", "submit_single_value"):
        return {"status": "error", "error": {"code": "unknown_method", "message": "Unknown domain or method"}}
    db = DbMgr()
    try:
        return SubmitSingleValueHandler(db).submit(request.payload)
    finally:
        db.close()
