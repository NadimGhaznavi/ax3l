"""Register SnakeLab tools here; Ax3l owns validation and submission."""

from mcp.server import MCPServer
import json
import os
from pydantic import StrictFloat, StrictInt, StrictStr

from ax3l.app.snakelab.tools.SubmitSingleValue import SubmitSingleValue
from ax3l.app.snakelab.tools.SubmitPairValues import SubmitPairValues
from ax3l.app.snakelab.tools.SubmitSimulationSummary import SubmitSimulationSummary
from ax3l.app.snakelab.PairParameters import PAIR_PARAMETERS, pair_instructions
from ax3l.app.snakelab.SingleParameters import SINGLE_PARAMETERS, parameter_instructions
from ax3l.constants.DSimulationAnalysis import DSimulationAnalysis
from ax3l.interface.KnowledgeBase import KnowledgeBase


mcp = MCPServer("snakelab")


parameter = os.environ.get("AX3L_CONVERSATION_PARAMETER")
draft_id = os.environ.get("AX3L_CONFIGURATION_DRAFT")
run_id = os.environ.get("AX3L_ANALYSIS_RUN")
section = os.environ.get("AX3L_ANALYSIS_SECTION")
description = (f"Save {parameter} in the configuration draft without running a simulation.\n{parameter_instructions(parameter)}"
               if parameter in SINGLE_PARAMETERS else "Submit a value for the Ax3l-assigned parameter.")


@mcp.tool(description=description)
async def submit_single_value(value: StrictInt | StrictFloat) -> str:
    endpoint = os.environ.get("AX3L_ZMQ_ENDPOINT")
    if parameter not in SINGLE_PARAMETERS or not draft_id:
        raise ValueError("Ax3l must bind a configuration draft and single parameter before submission")
    return await SubmitSingleValue(endpoint).submit(draft_id, parameter, value)


pair_description = ("Save this pair in the configuration draft without running a simulation.\n" + pair_instructions(parameter) if parameter in PAIR_PARAMETERS
                    else "Submit two values for the Ax3l-assigned parameter pair.")


@mcp.tool(description=pair_description)
async def submit_pair_values(value_1: StrictInt | StrictFloat,
                             value_2: StrictInt | StrictFloat) -> str:
    endpoint = os.environ.get("AX3L_ZMQ_ENDPOINT")
    if parameter not in PAIR_PARAMETERS or not draft_id:
        raise ValueError("Ax3l must bind a configuration draft and pair before submission")
    return await SubmitPairValues(endpoint).submit(draft_id, parameter, value_1, value_2)


@mcp.tool(description="Save an observation about the assigned chart: 1–2 sentences, at most 40 words. "
          "The run and chart are bound by Ax3l; supply only summary text, then stop.")
async def submit_simulation_summary(summary: StrictStr) -> str:
    if parameter != "simulation_summary" or not run_id or section not in DSimulationAnalysis.SECTIONS:
        raise ValueError("Ax3l must bind a completed run and chart before analysis submission")
    endpoint = os.environ.get("AX3L_ZMQ_ENDPOINT")
    return await SubmitSimulationSummary(endpoint).submit(run_id, section, summary)


@mcp.tool(description="Read one small Ax3l reference page. Begin at / and follow links to drill down, "
          "or open the guide URL supplied in your task. Read only what your assigned task needs.")
async def kb_tool(url: StrictStr) -> str:
    try:
        return json.dumps({"status": "ok", "page": KnowledgeBase().read(url)}, ensure_ascii=False)
    except ValueError as error:
        reason = str(error)
        return json.dumps({"status": "rejected", "code": "invalid_reference", "reason": reason,
                           "source_name": "KnowledgeBase", "prompt": {"role": "user", "content": reason}})
