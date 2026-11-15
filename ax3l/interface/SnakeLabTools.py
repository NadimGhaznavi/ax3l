"""Use MCP for tool discovery/calls; the tool forwards actions to Ax3l over ZMQ."""

from copy import deepcopy
import json
from pathlib import Path
import sys

from ax3l.app.snakelab.SingleParameters import SINGLE_PARAMETERS
from ax3l.app.snakelab.PairParameters import PAIR_PARAMETERS
from ax3l.constants.DSnakeLab import DSnakeLab

from mcp import Client
from mcp.client.stdio import StdioServerParameters


class SnakeLabTools:
    def __init__(self, endpoint: str, parameter: str, *, draft_id: str | None = None,
                 run_id: str | None = None, section: str | None = None):
        if parameter not in SINGLE_PARAMETERS and parameter not in PAIR_PARAMETERS and parameter != "simulation_summary":
            raise ValueError(f"Unknown conversation parameter: {parameter}")
        self._tool_name = ("submit_simulation_summary" if parameter == "simulation_summary" else
                           "submit_pair_values" if parameter in PAIR_PARAMETERS else "submit_single_value")
        root = Path(__file__).resolve().parents[2]
        environment = {"PYTHONPATH": str(root), "AX3L_ZMQ_ENDPOINT": endpoint,
                       "AX3L_CONVERSATION_PARAMETER": parameter, "PYTHONDONTWRITEBYTECODE": "1"}
        if draft_id is not None:
            environment["AX3L_CONFIGURATION_DRAFT"] = draft_id
        if run_id is not None:
            environment["AX3L_ANALYSIS_RUN"] = run_id
        if section is not None:
            environment["AX3L_ANALYSIS_SECTION"] = section
        self._client = Client(StdioServerParameters(
            command=sys.executable, args=["-m", "ax3l.app.snakelab.tools"], cwd=str(root),
            env=environment,
        ), read_timeout_seconds=DSnakeLab.MCP_TIMEOUT_SECONDS)

    async def __aenter__(self):
        await self._client.__aenter__()
        try:
            tools = await self._client.list_tools()
            by_name = {tool.name: tool for tool in tools.tools}
            names = [self._tool_name, "kb_tool"]
            if self._tool_name != "submit_simulation_summary":
                names.append("data_tool")
            self.definitions = [{"type": "function", "function": {
                "name": tool.name, "description": tool.description, "parameters": deepcopy(tool.input_schema),
            }} for tool in (by_name[name] for name in names)]
            self.definition = self.definitions[0]
        except BaseException:
            await self._client.__aexit__(*sys.exc_info())
            raise
        return self

    async def __aexit__(self, *exc):
        return await self._client.__aexit__(*exc)

    async def submit(self, arguments: dict) -> dict:
        return await self._call(self._tool_name, arguments)

    async def reference(self, arguments: dict) -> dict:
        return await self._call("kb_tool", arguments)

    async def data(self, arguments: dict) -> dict:
        return await self._call("data_tool", arguments)

    async def _call(self, name: str, arguments: dict) -> dict:
        result = await self._client.call_tool(name, arguments)
        if result.is_error:
            raise RuntimeError("MCP tool failed; submission may have occurred. Do not automatically retry.")
        return json.loads(result.content[0].text)
