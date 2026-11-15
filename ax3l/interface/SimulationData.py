"""Read the requested data page for a bound draft or image-analysis run."""

from uuid import UUID

from ax3l.activity.SimulationDataPages import (
    CONFIG_PAGES, RUN_PAGES, analysis_index_page, analysis_rules_page,
    config_page, data_json, draft_page, index_page, run_overview, run_page,
)
from ax3l.app.DbMgr import DbMgr
from ax3l.app.snakelab.ExperimentDb import ExperimentDb
from ax3l.constants.DChoice import REFERENCE_LABELS
from ax3l.interface.SnakeLab import SnakeLab


class SimulationData:
    def __init__(self, db: DbMgr):
        self._experiments = ExperimentDb(db)

    @staticmethod
    def _reject(reason: str) -> dict:
        return {"status": "rejected", "code": "invalid_data_page", "source_name": "SimulationData",
                "prompt": {"role": "user", "content": reason}}

    def read(self, payload: dict) -> dict:
        if (not isinstance(payload, dict) or set(payload) != {"draft_id", "url"}
                or not isinstance(payload["draft_id"], str) or not payload["draft_id"]
                or not isinstance(payload["url"], str)):
            return self._reject("Supply a bound draft and one data URL.")
        url = payload["url"]
        scopes = {label: role for role, label in REFERENCE_LABELS.items()}
        pages = {"/": ("", ""), "/draft": ("draft", "")}
        pages.update({f"/draft/{page}": ("draft", page) for page in CONFIG_PAGES})
        for scope in scopes:
            pages[f"/{scope}"] = (scope, "")
            pages.update({f"/{scope}/{page}": (scope, page) for page in RUN_PAGES})
        if url not in pages:
            return self._reject("Unknown data page. Read / and follow its links.")
        draft = self._experiments.draft(payload["draft_id"])
        if draft is None:
            return self._reject("This draft is unavailable.")
        scope, page = pages[url]
        if not scope:
            text = index_page(draft)
        elif scope == "draft":
            text = config_page(scope, page, draft.config) if page else draft_page(draft)
        else:
            analysis = self._experiments.analysis(draft.references[scopes[scope]])
            if analysis is None:
                raise RuntimeError("Reference metrics must finish before data lookup.")
            if not page:
                golden = (analysis if analysis.run_id == draft.golden_run_id else
                          self._experiments.analysis(draft.golden_run_id))
                if golden is None:
                    raise RuntimeError("Golden metrics must finish before data lookup.")
                text = run_overview(scope, draft, analysis, golden.metrics["high_score"])
            else:
                text = run_page(scope, page, analysis)
        return {"status": "ok", "page": text}

    def read_run(self, payload: dict) -> dict:
        """Read original chart settings without requiring the unfinished analysis."""
        if (not isinstance(payload, dict) or set(payload) != {"run_id", "url"}
                or not isinstance(payload["run_id"], str) or not isinstance(payload["url"], str)):
            return self._reject("Supply a bound analysis run and one data URL.")
        try:
            UUID(payload["run_id"])
        except ValueError:
            return self._reject("run_id must be a UUID.")
        url = payload["url"]
        if url in ("/", "/run"):
            return {"status": "ok", "page": analysis_index_page()}
        pages = {f"/run/{page}": page for page in (*CONFIG_PAGES, "config", "rules")}
        if url not in pages:
            return self._reject("Unknown analysis data page. Read /run and follow its links.")
        result = SnakeLab().get_run_result(payload["run_id"])
        if result is None or result["status"] != "completed":
            raise RuntimeError("Chart settings require a completed simulation.")
        config, page = result["config"], pages[url]
        if page == "config":
            text = data_json("run", config["seed"], dict(config=config))
        elif page == "rules":
            text = analysis_rules_page(config)
        else:
            text = config_page("run", page, config)
        return {"status": "ok", "page": text}
