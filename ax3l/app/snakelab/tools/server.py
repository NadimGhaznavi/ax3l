"""Register SnakeLab tools here; Ax3l owns validation and submission."""

from mcp.server import MCPServer
import os
from pydantic import StrictFloat, StrictInt

from ax3l.app.snakelab.tools.SubmitSingleValue import SubmitSingleValue
from ax3l.constants.DAx3l import DAx3l


mcp = MCPServer("snakelab")


@mcp.tool()
async def submit_single_value(parameter: str, value: StrictInt | StrictFloat) -> str:
    """Propose one numeric parameter value for the next SnakeLab simulation.

    Use the parameter's exact JSON spec key, such as learning_rate, and a JSON
    number. Ax3l validates the proposal and either rejects it with a reason or
    submits it. Return the server's result; a timeout does not confirm rejection
    or submission, so do not automatically retry.
    """
    endpoint = os.environ.get("AX3L_ZMQ_ENDPOINT", DAx3l.ZMQ_ENDPOINT)
    return await SubmitSingleValue(endpoint).submit(parameter, value)
