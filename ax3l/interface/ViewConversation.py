"""Accept observations or a configuration proposal from a fresh LLM conversation."""

from collections.abc import Callable
from copy import deepcopy
import json
from typing import TypeVar

from jsonschema import Draft202012Validator

from ax3l.activity.ViewConfiguration import parameter_schema
from ax3l.interface.database.EventLogDb import EventLogDb
from ax3l.constants.DEventCategory import DEventCategory as Events
from ax3l.constants.DViewConversation import DViewConversation
from ax3l.entities.ExperimentView import ExperimentView
from ax3l.entities.ViewProposal import ViewProposal
from ax3l.interface.LLM import LLM


Result = TypeVar("Result")


def _nonfinite(value):
    raise ValueError(f"Nonfinite JSON number: {value}")


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
            log(Events.Conversation, Events.Conversation.PROMPT, json.dumps(message, ensure_ascii=False))
            payload = json.dumps(dict(messages=[message], tools=[tool], tool_choice="required",
                                      parallel_tool_calls=False, stream=False), allow_nan=False).encode()
            log(Events.LLM, Events.LLM.REQUEST_STARTED, f"{action} {view.name}.")
            status, _, body = self._llm.complete(payload)
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
                                            "name": {"const": tool_name}, "arguments": {"type": "string"},
                                        },
                                    }},
                                },
                            }},
                        }},
                    }},
                },
            }
            Draft202012Validator(envelope).validate(response)
            call = response["choices"][0]["message"]["tool_calls"][0]
            log(Events.Tool, Events.Tool.STARTED, json.dumps(call))
            executing_tool = True
            arguments = json.loads(call["function"]["arguments"], parse_constant=_nonfinite)
            Draft202012Validator(arguments_schema).validate(arguments)
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
