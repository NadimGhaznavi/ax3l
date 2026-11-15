"""Read only the requested page of a bound draft's saved experiment data."""

from ax3l.activity.SimulationDataPages import (
    CONFIG_PAGES, RUN_PAGES, config_page, draft_page, index_page, run_overview, run_page,
)
from ax3l.app.DbMgr import DbMgr
from ax3l.app.snakelab.ExperimentDb import ExperimentDb
from ax3l.constants.DChoice import REFERENCE_LABELS


class SimulationData:
    def __init__(self, db: DbMgr):
        self._experiments = ExperimentDb(db)

    def read(self, payload: dict) -> dict:
        def reject(reason):
            return {"status": "rejected", "code": "invalid_data_page", "source_name": "SimulationData",
                    "prompt": {"role": "user", "content": reason}}

        if (not isinstance(payload, dict) or set(payload) != {"draft_id", "url"}
                or not isinstance(payload["draft_id"], str) or not payload["draft_id"]
                or not isinstance(payload["url"], str)):
            return reject("Supply a bound draft and one data URL.")
        url = payload["url"]
        scopes = {label: role for role, label in REFERENCE_LABELS.items()}
        pages = {"/": ("", ""), "/draft": ("draft", "")}
        pages.update({f"/draft/{page}": ("draft", page) for page in CONFIG_PAGES})
        for scope in scopes:
            pages[f"/{scope}"] = (scope, "")
            pages.update({f"/{scope}/{page}": (scope, page) for page in RUN_PAGES})
        if url not in pages:
            return reject("Unknown data page. Read / and follow its links.")
        draft = self._experiments.draft(payload["draft_id"])
        if draft is None:
            return reject("This draft is unavailable.")
        scope, page = pages[url]
        if not scope:
            text = index_page(draft)
        elif scope == "draft":
            text = config_page(scope, page, draft.config) if page else draft_page(draft)
        else:
            analysis = self._experiments.analysis(draft.references[scopes[scope]])
            if analysis is None:
                raise RuntimeError("Reference analysis must finish before data lookup.")
            if not page:
                golden = (analysis if analysis.run_id == draft.golden_run_id else
                          self._experiments.analysis(draft.golden_run_id))
                if golden is None:
                    raise RuntimeError("Golden analysis must finish before data lookup.")
                text = run_overview(scope, draft, analysis, golden.metrics["high_score"])
            else:
                text = run_page(scope, page, analysis)
        return {"status": "ok", "page": text}
