"""Register SnakeLab tools here; Ax3l owns validation and submission."""

from mcp.server import MCPServer
import json
import os
from pydantic import StrictFloat, StrictInt, StrictStr

from ax3l.app.snakelab.tools.SubmitSingleValue import SubmitSingleValue
from ax3l.app.snakelab.tools.SubmitPairValues import SubmitPairValues
from ax3l.app.snakelab.tools.SubmitSimulationSummary import SubmitSimulationSummary
from ax3l.app.snakelab.tools.ReadSimulationData import ReadSimulationData
from ax3l.app.snakelab.PairParameters import PAIR_PARAMETERS, pair_instructions
from ax3l.app.snakelab.SingleParameters import SINGLE_PARAMETERS, parameter_instructions
from ax3l.constants.DSimulationAnalysis import DSimulationAnalysis
from ax3l.interface.KnowledgeBase import KnowledgeBase


mcp = MCPServer("snakelab")


parameter = os.environ.get("AX3L_CONVERSATION_PARAMETER")
draft_id = os.environ.get("AX3L_CONFIGURATION_DRAFT")
run_id = os.environ.get("AX3L_ANALYSIS_RUN")
section = os.environ.get("AX3L_ANALYSIS_SECTION")
description = (f"Save one choice without running a simulation.\n{parameter_instructions(parameter)}"
               if parameter in SINGLE_PARAMETERS else "Submit a value for the Ax3l-assigned parameter.")


@mcp.tool(description=description)
async def submit_single_value(value: StrictInt | StrictFloat) -> str:
    endpoint = os.environ.get("AX3L_ZMQ_ENDPOINT")
    if parameter not in SINGLE_PARAMETERS or not draft_id:
        raise ValueError("Ax3l must bind a configuration draft and single parameter before submission")
    return await SubmitSingleValue(endpoint).submit(draft_id, parameter, value)


pair_description = ("Save a pair without running a simulation.\n" + pair_instructions(parameter) if parameter in PAIR_PARAMETERS
                    else "Submit two values for the Ax3l-assigned parameter pair.")


@mcp.tool(description=pair_description)
async def submit_pair_values(value_1: StrictInt | StrictFloat,
                             value_2: StrictInt | StrictFloat) -> str:
    endpoint = os.environ.get("AX3L_ZMQ_ENDPOINT")
    if parameter not in PAIR_PARAMETERS or not draft_id:
        raise ValueError("Ax3l must bind a configuration draft and pair before submission")
    return await SubmitPairValues(endpoint).submit(draft_id, parameter, value_1, value_2)


@mcp.tool(description="Save this chart's observation and optional concrete value to try next: 1–2 sentences, at most 40 words, no theory. Supply summary only, then stop.")
async def submit_simulation_summary(summary: StrictStr) -> str:
    if parameter != "simulation_summary" or not run_id or section not in DSimulationAnalysis.SECTIONS:
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
    if parameter == "simulation_summary" else
    "Read experiment data using the path in your task, or use / for the menu. "
    "Data payloads are JSON. Null means unrecorded."
)


@mcp.tool(description=data_description)
async def data_tool(url: StrictStr) -> str:
    if parameter == "simulation_summary":
        if not run_id or section not in DSimulationAnalysis.SECTIONS:
            raise ValueError("Ax3l must bind a completed run and chart before settings lookup")
        return await ReadSimulationData(os.environ.get("AX3L_ZMQ_ENDPOINT")).read_run(run_id, url)
    if (parameter not in SINGLE_PARAMETERS and parameter not in PAIR_PARAMETERS) or not draft_id:
        raise ValueError("Ax3l must bind a configuration choice before data lookup")
    return await ReadSimulationData(os.environ.get("AX3L_ZMQ_ENDPOINT")).read(draft_id, url)
