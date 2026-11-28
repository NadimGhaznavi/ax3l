"""Accept observations or a configuration proposal from a fresh LLM conversation."""

from collections.abc import Callable
from copy import deepcopy
import json
from math import ceil
from time import monotonic
from typing import TypeVar

from jsonschema import Draft202012Validator

from ax3l.activity.ViewConfiguration import parameter_schema
from ax3l.interface.database.EventLogDb import EventLogDb
from ax3l.constants.DEventCategory import DEventCategory as Events
from ax3l.constants.DViewConversation import DViewConversation
from ax3l.entities.ExperimentView import ExperimentView
from ax3l.entities.ViewProposal import ViewProposal
from ax3l.interface.LLM import LLM, LLMTimeoutError
from ax3l.interface.LLMResponseCapture import LLMResponseCapture


Result = TypeVar("Result")


def _nonfinite(value):
    raise ValueError(f"Nonfinite JSON number: {value}")


def _validate_arguments(schema: dict, arguments: dict, tool_name: str) -> str | None:
    """Validate the submission, returning feedback for overlong text only."""
    errors = list(Draft202012Validator(schema).iter_errors(arguments))
    for error in errors:
        if error.validator != "maxLength":
            raise error
    if not errors:
        return None
    lengths = "; ".join(f"{'.'.join(error.path)} is {len(error.instance)} characters; "
                        f"the maximum is {error.validator_value}" for error in errors)
    return (f"Submission rejected: {lengths}. Shorten the text while preserving its meaning "
            f"and any proposed parameter values, then call {tool_name} again.")


class ViewConversation:
    def __init__(self, llm: LLM, events: EventLogDb):
        self._llm = llm
        self._events = events

    def propose(self, view: ExperimentView, prompt: str | list[dict],
                experiment_id: str) -> ViewProposal:
        schema = dict(type="object", additionalProperties=False,
                      required=["hypothesis", "values"], properties={
            "hypothesis": dict(type="string", minLength=1, pattern=r"\S",
                               maxLength=DViewConversation.HYPOTHESIS_MAX_LENGTH),
            "values": dict(type="object", minProperties=1, additionalProperties=False, properties={
                name: parameter_schema(name) for name in view.parameters
            }),
        })

        arguments_schema = deepcopy(schema)
        arguments_schema["properties"]["values"]["properties"] = {name: {} for name in view.parameters}

        return self._request(view, prompt, schema, "submit_view", "Tuning",
                             "Record your next hypothesis and proposed parameter values.", experiment_id,
                             lambda arguments: ViewProposal(**arguments), arguments_schema=arguments_schema)

    def evaluate(self, view: ExperimentView, content: list[dict], experiment_id: str) -> str:
        schema = dict(type="object", additionalProperties=False, required=["observations"], properties={
            "observations": dict(type="string", minLength=1, pattern=r"\S",
                                 maxLength=DViewConversation.OBSERVATIONS_MAX_LENGTH),
        })
        return self._request(view, content, schema, "submit_observations", "Evaluating",
                             "Record short observations about the results against the hypothesis.",
                             experiment_id, lambda arguments: arguments["observations"], arguments_schema=schema)

    def _request(self, view: ExperimentView, content: str | list[dict], schema: dict, tool_name: str,
                 action: str, description: str, experiment_id: str,
                 accept: Callable[[dict], Result], *, arguments_schema: dict) -> Result:
        tool = dict(type="function", function=dict(
            name=tool_name, description=description, parameters=schema,
        ))
        tools = [tool]
        timer_schema = dict(type="object", additionalProperties=False, properties={})
        if tool_name == "submit_view":
            tools.append(dict(type="function", function=dict(
                name="timer", description="Check the selection countdown (MM:SS). Negative values show time past zero.",
                parameters=timer_schema,
            )))
        timer_deadline = None
        conversation = self._events.log(Events.Conversation.STARTED, Events.Conversation.CATEGORY, "INFO",
                                    f"{action} {view.name} with {self._llm.url}.", process_id=experiment_id)

        def log(category, name, content, level="INFO"):
            return self._events.log(name, category.CATEGORY, level, content, process_id=experiment_id,
                                parent_event_id=conversation, parameter=view.name,
                                source_name="selection" if tool_name == "submit_view" else "evaluation")

        outcome, level = "View submission accepted.", "INFO"
        executing_tool = False
        try:
            message = dict(role="user", content=content)
            messages = []
            while True:
                executing_tool = False
                messages.append(message)
                log(Events.Conversation, Events.Conversation.PROMPT, json.dumps(message, ensure_ascii=False))
                payload = json.dumps(dict(messages=messages, tools=tools, tool_choice="required",
                                          parallel_tool_calls=False, stream=True,
                                          stream_options=dict(include_usage=True)), allow_nan=False).encode()
                request = log(Events.LLM, Events.LLM.REQUEST_STARTED, f"{action} {view.name}.")
                with LLMResponseCapture(
                        self._events, request, process_id=experiment_id, parent_event_id=conversation,
                        parameter=view.name,
                        source_name="selection" if tool_name == "submit_view" else "evaluation") as capture:
                    if timer_deadline is None and tool_name == "submit_view":
                        timer_deadline = monotonic() + DViewConversation.SELECTION_TIMER_SECONDS
                    status, _, body = self._llm.complete(payload, on_progress=capture.receive)
                    if status in (408, 504):
                        raise LLMTimeoutError(f"LLM HTTP {status}: {body.decode(errors='replace')}")
                    if status >= 400:
                        raise RuntimeError(f"LLM HTTP {status}: {body.decode(errors='replace')}")
                log(Events.Conversation, Events.Conversation.RESPONSE, body.decode(errors="backslashreplace"))
                response = json.loads(body, parse_constant=_nonfinite)
                envelope = {
                    "type": "object", "required": ["choices"], "properties": {
                        "choices": {"type": "array", "minItems": 1, "maxItems": 1, "items": {
                            "type": "object", "required": ["message"], "properties": {"message": {
                                "type": "object", "required": ["tool_calls"], "properties": {"tool_calls": {
                                    "type": "array", "minItems": 1, "maxItems": 1, "items": {
                                        "type": "object", "required": ["function"], "properties": {"function": {
                                            "type": "object", "required": ["name", "arguments"], "properties": {
                                                "name": {"enum": [t["function"]["name"] for t in tools]},
                                                "arguments": {"type": "string"},
                                            },
                                        }},
                                    },
                                }},
                            }},
                        }},
                    },
                }
                Draft202012Validator(envelope).validate(response)
                assistant = response["choices"][0]["message"]
                call = assistant["tool_calls"][0]
                log(Events.Tool, Events.Tool.STARTED, json.dumps(call))
                executing_tool = True
                arguments = json.loads(call["function"]["arguments"], parse_constant=_nonfinite)
                if call["function"]["name"] == "timer":
                    Draft202012Validator(timer_schema).validate(arguments)
                    seconds = ceil(timer_deadline - monotonic())
                    minutes, seconds_part = divmod(abs(seconds), 60)
                    remaining = f"{'-' if seconds < 0 else ''}{minutes:02d}:{seconds_part:02d}"
                    log(Events.Tool, Events.Tool.COMPLETED, json.dumps(dict(status="completed", page=remaining)))
                    messages.append(assistant)
                    message = dict(role="tool", tool_call_id=call["id"], content=remaining)
                    continue
                feedback = _validate_arguments(arguments_schema, arguments, tool_name)
                if feedback is not None:
                    log(Events.Tool, Events.Tool.FAILED, feedback, "WARNING")
                    messages.append(assistant)
                    message = dict(role="tool", tool_call_id=call["id"], content=feedback)
                    continue
                result = accept(arguments)
                log(Events.Tool, Events.Tool.COMPLETED, json.dumps(dict(status="accepted", **arguments), allow_nan=False))
                return result
        except KeyboardInterrupt:
            outcome = "View conversation interrupted."
            raise
        except Exception as error:
            outcome, level = f"{type(error).__name__}: {error}", "ERROR"
            if executing_tool:
                log(Events.Tool, Events.Tool.FAILED, outcome, level)
            else:
                log(Events.LLM, Events.LLM.REQUEST_FAILED, outcome, level)
            raise
        finally:
            log(Events.Conversation, Events.Conversation.ENDED, outcome, level)
