"""Present prepared experiment values through editable Markdown templates."""

from ax3l.activity.SimulationDataValues import (
    CONFIG_PAGES, RUN_PAGES, config_values, draft_values, overview_values,
    parameter_rules, reference_groups, run_values, scoped_values,
)
from ax3l.entities.ConfigurationDraft import ConfigurationDraft
from ax3l.entities.SimulationAnalysis import SimulationAnalysis
from ax3l.presentation.snakelab.Templates import templates


def data_json(scope: str, seed: int, data: dict) -> str:
    return templates.render("pages/values.md.jinja", data=scoped_values(scope, seed, data))


def analysis_index_page() -> str:
    return templates.render("pages/analysis_index.md.jinja", pages=("config", *CONFIG_PAGES, "rules"))


def analysis_rules_page(config: dict) -> str:
    return templates.render("pages/rules.md.jinja", seed=config["seed"], parameters=parameter_rules())


def index_page(draft: ConfigurationDraft) -> str:
    return templates.render("pages/references.md.jinja", groups=reference_groups(draft))


def draft_page(draft: ConfigurationDraft) -> str:
    return templates.render("pages/draft.md.jinja", data=draft_values(draft), pages=CONFIG_PAGES)


def config_page(scope: str, page: str, config: dict) -> str:
    return templates.render(f"pages/config/{page}.md.jinja", data=config_values(scope, page, config))


def run_overview(scope: str, draft: ConfigurationDraft, analysis: SimulationAnalysis, target: int) -> str:
    pages = tuple(page for page in RUN_PAGES if page != "notes" or analysis.summary)
    return templates.render("pages/run.md.jinja", data=overview_values(scope, draft, analysis, target), pages=pages)


def run_page(scope: str, page: str, analysis: SimulationAnalysis) -> str:
    if page in CONFIG_PAGES:
        return config_page(scope, page, analysis.config)
    return templates.render(f"pages/run/{page}.md.jinja", data=run_values(scope, page, analysis))
