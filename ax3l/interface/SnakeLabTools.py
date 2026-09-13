"""Use MCP for tool discovery/calls; the tool forwards actions to Ax3l over ZMQ."""

from copy import deepcopy
import json
from pathlib import Path
import sys

from ax3l.app.snakelab.SingleParameters import SINGLE_PARAMETERS
from ax3l.constants.DSnakeLab import DSnakeLab

from mcp import Client
from mcp.client.stdio import StdioServerParameters


class SnakeLabTools:
    def __init__(self, endpoint: str):
        root = Path(__file__).resolve().parents[2]
        self._client = Client(StdioServerParameters(
            command=sys.executable, args=["-m", "ax3l.app.snakelab.tools"], cwd=str(root),
            env={"PYTHONPATH": str(root), "AX3L_ZMQ_ENDPOINT": endpoint,
                 "PYTHONDONTWRITEBYTECODE": "1"},
        ), read_timeout_seconds=DSnakeLab.MCP_TIMEOUT_SECONDS)

    async def __aenter__(self):
        await self._client.__aenter__()
        try:
            tools = await self._client.list_tools()
            tool = next(tool for tool in tools.tools if tool.name == "submit_single_value")
            schema = deepcopy(tool.input_schema)
            schema["properties"]["parameter"]["enum"] = list(SINGLE_PARAMETERS)
            self.definition = {"type": "function", "function": {
                "name": tool.name, "description": tool.description, "parameters": schema,
            }}
        except BaseException:
            await self._client.__aexit__(*sys.exc_info())
            raise
        return self

    async def __aexit__(self, *exc):
        return await self._client.__aexit__(*exc)

    async def submit(self, arguments: dict) -> dict:
        result = await self._client.call_tool("submit_single_value", arguments)
        if result.is_error:
            raise RuntimeError("MCP tool failed; submission may have occurred. Do not automatically retry.")
        return json.loads(result.content[0].text)
