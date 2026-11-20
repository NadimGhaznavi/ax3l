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
from ax3l.entities.ConfigurationDraft import PARAMETER_ORDER
from ax3l.interface.KnowledgeBase import KnowledgeBase


mcp = MCPServer("snakelab")


assigned_parameter = os.environ.get("AX3L_CONVERSATION_PARAMETER")
draft_id = os.environ.get("AX3L_CONFIGURATION_DRAFT")
run_id = os.environ.get("AX3L_ANALYSIS_RUN")
section = os.environ.get("AX3L_ANALYSIS_SECTION")
description = (f"Save one choice without running a simulation. The value must change.\n{parameter_instructions(assigned_parameter)}"
               if assigned_parameter in SINGLE_PARAMETERS else "Submit a value for the Ax3l-assigned parameter.")


@mcp.tool(description=description)
async def submit_single_value(value: StrictInt | StrictFloat) -> str:
    endpoint = os.environ.get("AX3L_ZMQ_ENDPOINT")
    if assigned_parameter not in SINGLE_PARAMETERS or not draft_id:
        raise ValueError("Ax3l must bind a configuration draft and single parameter before submission")
    return await SubmitSingleValue(endpoint).submit(draft_id, assigned_parameter, value)


pair_description = ("Save a pair without running a simulation. At least one value must change.\n" + pair_instructions(assigned_parameter) if assigned_parameter in PAIR_PARAMETERS
                    else "Submit two values for the Ax3l-assigned parameter pair.")


@mcp.tool(description=pair_description)
async def submit_pair_values(value_1: StrictInt | StrictFloat,
                             value_2: StrictInt | StrictFloat) -> str:
    endpoint = os.environ.get("AX3L_ZMQ_ENDPOINT")
    if assigned_parameter not in PAIR_PARAMETERS or not draft_id:
        raise ValueError("Ax3l must bind a configuration draft and pair before submission")
    return await SubmitPairValues(endpoint).submit(draft_id, assigned_parameter, value_1, value_2)


@mcp.tool(description="Choose one of the available parameter keys listed in the current task. "
          "Already chosen settings and settings with no untested changes are unavailable. "
          "Use one parameter key: " + ", ".join(PARAMETER_ORDER) + ". Paired settings are revised together.")
async def select_parameter(parameter: StrictStr) -> str:
    if assigned_parameter != REVISION_PARAMETER or not draft_id:
        raise ValueError("Ax3l must bind a parameter-selection conversation before choosing a setting")
    return await SelectParameter(os.environ.get("AX3L_ZMQ_ENDPOINT")).submit(draft_id, parameter)


@mcp.tool(description="Run the current unique configuration instead of making another change. No arguments.")
async def run_simulation() -> str:
    if assigned_parameter != REVISION_PARAMETER or not draft_id or os.environ.get("AX3L_ALLOW_RUN") != "1":
        raise ValueError("Ax3l must bind a unique configuration before Qwen can choose to run it")
    return await RunSimulation(os.environ.get("AX3L_ZMQ_ENDPOINT")).submit(draft_id)


@mcp.tool(description="Request a seed change without running a simulation. No arguments. "
          "Ax3l increments the draft seed, skipping stored draft configurations and golden baselines. "
          "When the draft runs, golden runs first with the new seed to set its local baseline, even if lower. "
          "Other saved changes then run on that seed and must beat the new baseline.")
async def request_seed_change() -> str:
    if assigned_parameter != "seed" or not draft_id:
        raise ValueError("Ax3l must bind a seed-change conversation before requesting a seed change")
    return await RequestSeedChange(os.environ.get("AX3L_ZMQ_ENDPOINT")).submit(draft_id)


@mcp.tool(description="Save this chart's observation and optional concrete value to try next: 1–2 sentences, at most 40 words, no theory. Supply summary only, then stop.")
async def submit_simulation_summary(summary: StrictStr) -> str:
    if assigned_parameter != "simulation_summary" or not run_id or section not in DSimulationAnalysis.SECTIONS:
        raise ValueError("Ax3l must bind a completed run and chart before analysis submission")
    endpoint = os.environ.get("AX3L_ZMQ_ENDPOINT")
    return await SubmitSimulationSummary(endpoint).submit(run_id, section, summary)


@mcp.tool(description="Read a Snake Lab guide. Use / for the guide list.")
async def kb_tool(url: StrictStr) -> str:
    try:
        return json.dumps({"status": "ok", "page": KnowledgeBase().read(url)}, ensure_ascii=False)
    except ValueError as error:
        reason = str(error)
        return json.dumps({"status": "rejected", "code": "invalid_reference", "reason": reason,
                           "source_name": "KnowledgeBase", "prompt": {"role": "user", "content": reason}})


data_description = (
    "Read the settings that produced this chart. Start at /run; follow links for settings and allowed value rules. "
    "Read current values and /run/rules before recommending a value. Data payloads are JSON."
    if assigned_parameter == "simulation_summary" else
    "Read experiment data using the path in your task, or use / for the menu. "
    "Data payloads are JSON. Null means unrecorded."
)


@mcp.tool(description=data_description)
async def data_tool(url: StrictStr) -> str:
    if assigned_parameter == "simulation_summary":
        if not run_id or section not in DSimulationAnalysis.SECTIONS:
            raise ValueError("Ax3l must bind a completed run and chart before settings lookup")
        return await ReadSimulationData(os.environ.get("AX3L_ZMQ_ENDPOINT")).read_run(run_id, url)
    if (assigned_parameter not in SINGLE_PARAMETERS and assigned_parameter not in PAIR_PARAMETERS
            and assigned_parameter not in ("seed", REVISION_PARAMETER)) or not draft_id:
        raise ValueError("Ax3l must bind a configuration choice before data lookup")
    return await ReadSimulationData(os.environ.get("AX3L_ZMQ_ENDPOINT")).read(draft_id, url)
