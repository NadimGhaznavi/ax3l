"""Request one native tool call from the local LLM and validate its proposal."""

import json

from jsonschema import Draft202012Validator

from ax3l.activity.ViewConfiguration import apply_values
from ax3l.app.DbMgr import DbMgr
from ax3l.constants.DEventCategory import DEventCategory as Events
from ax3l.entities.ExperimentView import ExperimentView
from ax3l.entities.ViewProposal import ViewProposal
from ax3l.interface.LLM import LLM
from ax3l.interface.SimulationConfiguration import SimulationConfiguration


def _nonfinite(value):
    raise ValueError(f"Nonfinite JSON number: {value}")


class ViewConversation:
    def __init__(self, llm: LLM, db: DbMgr):
        self._llm = llm
        self._db = db

    def propose(self, view: ExperimentView, prompt: str, config: dict, experiment_id: str) -> ViewProposal:
        text = dict(type="string", minLength=1, pattern=r"\S")
        schema = dict(type="object", additionalProperties=False,
                      required=["evaluation", "hypothesis", "expected_effect", "values"], properties={
            "evaluation": text, "hypothesis": text, "expected_effect": text,
            "values": dict(type="object", minProperties=1, additionalProperties=False, properties={
                name: SimulationConfiguration.field(tuple(name.split("."))) for name in view.parameters
            }),
        })
        tool = dict(type="function", function=dict(
            name="submit_view", description="Record your hypothesis assessment and proposed parameter values.",
            parameters=schema,
        ))
        conversation = self._db.log(Events.Conversation.STARTED, Events.Conversation.CATEGORY, "INFO",
                                    f"Tuning {view.name} with {self._llm.url}.", process_id=experiment_id)

        def log(category, name, content, level="INFO"):
            return self._db.log(name, category.CATEGORY, level, content, process_id=experiment_id,
                                parent_event_id=conversation, parameter=view.name, source_name=view.name)

        outcome, level = "View proposal accepted.", "INFO"
        executing_tool = False
        try:
            message = dict(role="user", content=prompt)
            log(Events.Conversation, Events.Conversation.PROMPT, json.dumps(message, ensure_ascii=False))
            payload = json.dumps(dict(messages=[message], tools=[tool], tool_choice="required",
                                      parallel_tool_calls=False, stream=False), allow_nan=False).encode()
            log(Events.LLM, Events.LLM.REQUEST_STARTED, f"Request for {view.name}.")
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
                                            "name": {"const": "submit_view"}, "arguments": {"type": "string"},
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
            Draft202012Validator(schema).validate(arguments)
            candidate = apply_values(config, arguments["values"])
            SimulationConfiguration.validate(candidate)
            proposal = ViewProposal(**arguments)
            log(Events.Tool, Events.Tool.COMPLETED, json.dumps(dict(status="accepted", **arguments), allow_nan=False))
            return proposal
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
