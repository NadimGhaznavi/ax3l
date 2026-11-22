"""Register SnakeLab tools here; Ax3l owns validation and submission."""

from mcp.server import MCPServer
import json
import os
from pydantic import StrictFloat, StrictInt, StrictStr

from ax3l.app.snakelab.tools.SubmitSingleValue import SubmitSingleValue
from ax3l.app.snakelab.tools.SubmitPairValues import SubmitPairValues
from ax3l.app.snakelab.tools.SelectParameter import SelectParameter
from ax3l.app.snakelab.tools.RunSimulation import RunSimulation
from ax3l.app.snakelab.tools.RequestSeedChange import RequestSeedChange
from ax3l.app.snakelab.tools.SubmitSimulationSummary import SubmitSimulationSummary
from ax3l.app.snakelab.tools.ReadSimulationData import ReadSimulationData
from ax3l.app.snakelab.PairParameters import PAIR_PARAMETERS, pair_instructions
from ax3l.app.snakelab.SingleParameters import SINGLE_PARAMETERS, parameter_instructions
from ax3l.constants.DSimulationAnalysis import DSimulationAnalysis
from ax3l.constants.DChoice import REVISION_PARAMETER
from ax3l.app.snakelab.PageBrowser import PageBrowser
from ax3l.presentation.snakelab.Templates import templates


mcp = MCPServer("snakelab")


assigned_parameter = os.environ.get("AX3L_CONVERSATION_PARAMETER")
draft_id = os.environ.get("AX3L_CONFIGURATION_DRAFT")
run_id = os.environ.get("AX3L_ANALYSIS_RUN")
section = os.environ.get("AX3L_ANALYSIS_SECTION")
description = templates.render("tools/submit_single_value.md.jinja",
                               rules=parameter_instructions(assigned_parameter)
                               if assigned_parameter in SINGLE_PARAMETERS else None)


@mcp.tool(description=description)
async def submit_single_value(value: StrictInt | StrictFloat) -> str:
    endpoint = os.environ.get("AX3L_ZMQ_ENDPOINT")
    if assigned_parameter not in SINGLE_PARAMETERS or not draft_id:
        raise ValueError("Ax3l must bind a configuration draft and single parameter before submission")
    return await SubmitSingleValue(endpoint).submit(draft_id, assigned_parameter, value)


pair_description = templates.render("tools/submit_pair_values.md.jinja",
                                    rules=pair_instructions(assigned_parameter)
                                    if assigned_parameter in PAIR_PARAMETERS else None)


@mcp.tool(description=pair_description)
async def submit_pair_values(value_1: StrictInt | StrictFloat,
                             value_2: StrictInt | StrictFloat) -> str:
    endpoint = os.environ.get("AX3L_ZMQ_ENDPOINT")
    if assigned_parameter not in PAIR_PARAMETERS or not draft_id:
        raise ValueError("Ax3l must bind a configuration draft and pair before submission")
    return await SubmitPairValues(endpoint).submit(draft_id, assigned_parameter, value_1, value_2)


@mcp.tool(description=templates.render("tools/select_parameter.md.jinja"))
async def select_parameter(parameter: StrictStr) -> str:
    if assigned_parameter != REVISION_PARAMETER or not draft_id:
        raise ValueError("Ax3l must bind a parameter-selection conversation before choosing a setting")
    return await SelectParameter(os.environ.get("AX3L_ZMQ_ENDPOINT")).submit(draft_id, parameter)


@mcp.tool(description=templates.render("tools/run_simulation.md.jinja"))
async def run_simulation() -> str:
    if assigned_parameter != REVISION_PARAMETER or not draft_id or os.environ.get("AX3L_ALLOW_RUN") != "1":
        raise ValueError("Ax3l must bind a unique configuration before Qwen can choose to run it")
    return await RunSimulation(os.environ.get("AX3L_ZMQ_ENDPOINT")).submit(draft_id)


@mcp.tool(description=templates.render("tools/request_seed_change.md.jinja"))
async def request_seed_change() -> str:
    if assigned_parameter != "seed" or not draft_id:
        raise ValueError("Ax3l must bind a seed-change conversation before requesting a seed change")
    return await RequestSeedChange(os.environ.get("AX3L_ZMQ_ENDPOINT")).submit(draft_id)


@mcp.tool(description=templates.render("tools/submit_simulation_summary.md.jinja"))
async def submit_simulation_summary(summary: StrictStr) -> str:
    if assigned_parameter != "simulation_summary" or not run_id or section not in DSimulationAnalysis.SECTIONS:
        raise ValueError("Ax3l must bind a completed run and chart before analysis submission")
    endpoint = os.environ.get("AX3L_ZMQ_ENDPOINT")
    return await SubmitSimulationSummary(endpoint).submit(run_id, section, summary)


async def _read_data(url: str) -> dict:
    if assigned_parameter == "simulation_summary":
        if not run_id or section not in DSimulationAnalysis.SECTIONS:
            raise ValueError("Ax3l must bind a completed run and chart before settings lookup")
        return await ReadSimulationData(os.environ.get("AX3L_ZMQ_ENDPOINT")).read_run(run_id, url)
    if (assigned_parameter not in SINGLE_PARAMETERS and assigned_parameter not in PAIR_PARAMETERS
            and assigned_parameter not in ("seed", REVISION_PARAMETER)) or not draft_id:
        raise ValueError("Ax3l must bind a configuration choice before data lookup")
    return await ReadSimulationData(os.environ.get("AX3L_ZMQ_ENDPOINT")).read(draft_id, url)


browser = PageBrowser(_read_data if assigned_parameter is not None else None)


@mcp.tool(description=templates.render("tools/browser.md.jinja", analysis=assigned_parameter == "simulation_summary"))
async def kb_tool(url: StrictStr) -> str:
    return json.dumps(await browser.read(url), ensure_ascii=False, allow_nan=False)
