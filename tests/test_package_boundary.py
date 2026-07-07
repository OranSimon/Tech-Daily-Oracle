from __future__ import annotations

import ast
from pathlib import Path

ALLOWED_BARE_SCRIPT_IMPORTS = {
    Path("src/tech_daily/cli/run_daily.py"): {"state"},
    # Transitional adapter: these are the existing legacy script delegates only.
    Path("src/tech_daily/pipeline/actions.py"): {
        "analyze_companies",
        "analyze_github_projects",
        "analyze_macro_impact",
        "analyze_market_signals",
        "analyze_papers",
        "analyze_social_signals",
        "analyze_topics",
        "analyze_trending",
        "collect_market_data",
        "collect_sources",
        "collect_trending",
        "generate_report",
        "normalize_sources",
        "publish_notion",
        "state",
        "update_predictions",
    },
    Path("src/tech_daily/pipeline/daily.py"): {"state"},
    Path("src/tech_daily/pipeline/state.py"): {"state"},
    Path("src/tech_daily/llm/client.py"): {"claude_client"},
    Path("src/tech_daily/reports/daily.py"): {"state"},
    Path("src/tech_daily/web_search/client.py"): {"claude_client"},
}

BARE_SCRIPT_MODULES = {
    "analyze_companies",
    "analyze_github_projects",
    "analyze_macro_impact",
    "analyze_market_signals",
    "analyze_papers",
    "analyze_social_signals",
    "analyze_topics",
    "analyze_trending",
    "claude_client",
    "collect_market_data",
    "collect_sources",
    "collect_trending",
    "generate_report",
    "normalize_sources",
    "publish_notion",
    "state",
    "update_predictions",
    "web_search_client",
}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".", maxsplit=1)[0])
    return modules


def test_package_modules_do_not_add_new_bare_script_imports() -> None:
    offenders: list[str] = []
    for path in sorted(Path("src/tech_daily").rglob("*.py")):
        allowed = ALLOWED_BARE_SCRIPT_IMPORTS.get(path, set())
        forbidden = (_imported_modules(path) & BARE_SCRIPT_MODULES) - allowed
        for module in sorted(forbidden):
            offenders.append(f"{path}: imports bare script module {module!r}")

    assert offenders == []
