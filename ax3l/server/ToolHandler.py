"""Reject domain requests while no conversation workflow is installed."""

from ax3l.zmq.ZMQMsg import ZMQMsg


def handle_tool(request: ZMQMsg) -> dict:
    return {"status": "error", "error": {"code": "unknown_method", "message": "Unknown domain or method"}}
