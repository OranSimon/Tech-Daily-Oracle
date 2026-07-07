from __future__ import annotations

import ast
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest


def test_pyproject_declares_src_package_discovery() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["tool"]["setuptools"]["package-dir"] == {"": "src"}
    assert pyproject["tool"]["setuptools"]["packages"]["find"]["where"] == ["src"]
    assert "src" in pyproject["tool"]["pytest"]["ini_options"]["pythonpath"]


def test_tech_daily_cli_facade_imports_existing_daily_runner() -> None:
    from tech_daily.cli.run_daily import run_daily

    assert callable(run_daily)


def test_script_and_package_daily_cli_help_expose_same_options() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(["src", "scripts", env.get("PYTHONPATH", "")])

    script_result = subprocess.run(
        [sys.executable, "scripts/run_daily.py", "--help"],
        check=False,
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
    )
    package_result = subprocess.run(
        [sys.executable, "-m", "tech_daily.cli.run_daily", "--help"],
        check=False,
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
    )

    assert script_result.returncode == 0
    assert package_result.returncode == 0
    for option in ["--date", "--force"]:
        assert option in script_result.stdout
        assert option in package_result.stdout


def test_daily_arg_parser_parses_existing_options() -> None:
    from tech_daily.cli.daily_parser import build_daily_arg_parser

    parser = build_daily_arg_parser()

    defaults = parser.parse_args([])
    forced = parser.parse_args(["--date", "2026-07-02", "--force"])

    assert defaults.date is None
    assert defaults.force is False
    assert forced.date == "2026-07-02"
    assert forced.force is True


def test_daily_arg_parser_rejects_unknown_args() -> None:
    from tech_daily.cli.daily_parser import build_daily_arg_parser

    parser = build_daily_arg_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--unknown"])

    assert exc_info.value.code == 2


def test_script_and_package_entrypoints_use_shared_daily_parser() -> None:
    script_source = Path("scripts/run_daily.py").read_text(encoding="utf-8")
    package_source = Path("src/tech_daily/cli/run_daily.py").read_text(encoding="utf-8")

    assert "build_daily_arg_parser" in package_source
    assert "from tech_daily.cli.run_daily import main, run_daily" in script_source
    assert "argparse.ArgumentParser" not in script_source
    assert "argparse.ArgumentParser" not in package_source


def test_script_run_daily_is_thin_package_wrapper() -> None:
    source = Path("scripts/run_daily.py").read_text(encoding="utf-8")

    assert "from tech_daily.cli.run_daily import main, run_daily" in source
    assert "TechDailyState(" not in source
    assert "execute_daily_pipeline(" not in source


def test_script_daily_entrypoint_preserves_existing_skip_behavior() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(["src", "scripts", env.get("PYTHONPATH", "")])

    result = subprocess.run(
        [sys.executable, "scripts/run_daily.py", "--date", "2026-07-02"],
        check=False,
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Report for 2026-07-02 already exists" in result.stdout


def test_module_daily_entrypoint_preserves_existing_skip_behavior() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(["src", "scripts", env.get("PYTHONPATH", "")])

    result = subprocess.run(
        [sys.executable, "-m", "tech_daily.cli.run_daily", "--date", "2026-07-02"],
        check=False,
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Report for 2026-07-02 already exists" in result.stdout


def test_run_context_available_from_package_and_script_wrapper() -> None:
    from run_context import AppConfig as ScriptAppConfig
    from run_context import RunContext as ScriptRunContext

    from tech_daily.runtime.run_context import AppConfig, RunContext

    assert ScriptAppConfig is AppConfig
    assert ScriptRunContext is RunContext


def test_run_logging_available_from_package_and_script_wrapper() -> None:
    from run_logging import RunLogEvent as ScriptRunLogEvent
    from run_logging import RunLogger as ScriptRunLogger

    from tech_daily.runtime.run_logging import RunLogEvent, RunLogger

    assert ScriptRunLogEvent is RunLogEvent
    assert ScriptRunLogger is RunLogger


def test_pipeline_step_available_from_package_and_script_wrapper() -> None:
    from pipeline_step import PipelineStep as ScriptPipelineStep
    from pipeline_step import PipelineStepResult as ScriptPipelineStepResult
    from pipeline_step import log_step_summary as script_log_step_summary
    from pipeline_step import run_recorded_step as script_run_recorded_step
    from pipeline_step import run_step as script_run_step
    from pipeline_step import summarize_step_results as script_summarize_step_results

    from tech_daily.pipeline.step import (
        PipelineStep,
        PipelineStepResult,
        log_step_summary,
        run_recorded_step,
        run_step,
        summarize_step_results,
    )

    assert ScriptPipelineStep is PipelineStep
    assert ScriptPipelineStepResult is PipelineStepResult
    assert script_log_step_summary is log_step_summary
    assert script_run_recorded_step is run_recorded_step
    assert script_run_step is run_step
    assert script_summarize_step_results is summarize_step_results


def test_pipeline_policy_available_from_package_and_script_wrapper() -> None:
    from pipeline_policy import DAILY_STEP_POLICIES as script_policies
    from pipeline_policy import StepId as ScriptStepId
    from pipeline_policy import get_daily_step_policy as script_get_policy

    from tech_daily.pipeline.policy import DAILY_STEP_POLICIES, StepId, get_daily_step_policy

    assert ScriptStepId is StepId
    assert script_policies is DAILY_STEP_POLICIES
    assert script_get_policy is get_daily_step_policy


def test_pipeline_policy_imports_under_package_only_pythonpath() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"

    result = subprocess.run(
        [sys.executable, "-c", "import tech_daily.pipeline.policy"],
        check=False,
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_daily_pipeline_imports_under_package_only_pythonpath() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"

    result = subprocess.run(
        [sys.executable, "-c", "import tech_daily.pipeline.daily"],
        check=False,
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_package_owned_modules_import_under_package_only_pythonpath() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    command = """
mods = [
    'tech_daily.reports.daily',
    'tech_daily.storage.events',
    'tech_daily.storage.event_payloads',
    'tech_daily.storage._shared',
]
for mod in mods:
    __import__(mod)
    print(f'OK {mod}')
"""

    result = subprocess.run(
        [sys.executable, "-c", command],
        check=False,
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "OK tech_daily.reports.daily",
        "OK tech_daily.storage.events",
        "OK tech_daily.storage.event_payloads",
        "OK tech_daily.storage._shared",
    ]


def test_pipeline_state_available_from_package_and_script_wrapper() -> None:
    from pipeline_state import CollectionState as ScriptCollectionState
    from pipeline_state import get_collection_state as script_get_collection_state

    from tech_daily.pipeline.state import CollectionState, get_collection_state

    assert ScriptCollectionState is CollectionState
    assert script_get_collection_state is get_collection_state


def test_llm_boundary_available_from_package_and_script_wrappers() -> None:
    from llm_client import ClaudeLLMClient as ScriptClaudeLLMClient
    from llm_client import LLMClient as ScriptLLMClient
    from llm_schemas import TopicSummaryResponse as ScriptTopicSummaryResponse
    from prompt_runner import PromptRunner as ScriptPromptRunner
    from prompt_runner import PromptRunnerError as ScriptPromptRunnerError

    from tech_daily.llm.client import ClaudeLLMClient, LLMClient
    from tech_daily.llm.prompt_runner import PromptRunner, PromptRunnerError
    from tech_daily.llm.schemas import TopicSummaryResponse

    assert ScriptClaudeLLMClient is ClaudeLLMClient
    assert ScriptLLMClient is LLMClient
    assert ScriptPromptRunner is PromptRunner
    assert ScriptPromptRunnerError is PromptRunnerError
    assert ScriptTopicSummaryResponse is TopicSummaryResponse


def test_pipeline_state_exports_remain_available_from_package_facade() -> None:
    from tech_daily.pipeline import CollectionState, CorpusState, PredictionState, ReportInputState
    from tech_daily.pipeline.state import (
        CollectionState as PackageCollectionState,
    )
    from tech_daily.pipeline.state import (
        CorpusState as PackageCorpusState,
    )
    from tech_daily.pipeline.state import (
        PredictionState as PackagePredictionState,
    )
    from tech_daily.pipeline.state import (
        ReportInputState as PackageReportInputState,
    )

    assert CollectionState is PackageCollectionState
    assert CorpusState is PackageCorpusState
    assert PredictionState is PackagePredictionState
    assert ReportInputState is PackageReportInputState


def test_daily_report_generation_available_from_package_and_script_wrapper() -> None:
    from generate_report import generate_daily_report_from_input as script_generate_from_input

    from tech_daily.reports.daily import generate_daily_report_from_input

    assert script_generate_from_input is generate_daily_report_from_input


def test_daily_report_wrapper_stub_preserves_typed_report_entrypoints() -> None:
    stub_source = Path("scripts/generate_report.pyi").read_text(encoding="utf-8")

    assert "def generate_daily_report(" in stub_source
    assert "def generate_daily_report_from_input(" in stub_source
    assert "-> str" in stub_source


def test_daily_report_helpers_remain_available_from_script_wrapper() -> None:
    from generate_report import (
        DEFAULT_DAILY_MODEL as script_default_daily_model,
    )
    from generate_report import ROOT as script_root
    from generate_report import (
        _build_report_payload as script_build_report_payload,
    )
    from generate_report import _load_config as script_load_config
    from generate_report import _load_preferences as script_load_preferences
    from generate_report import (
        _previous_reports_summary_from_input as script_previous_reports_summary_from_input,
    )
    from generate_report import _safe_dict as script_safe_dict

    from tech_daily.reports import daily as daily_report

    assert script_default_daily_model == daily_report.DEFAULT_DAILY_MODEL
    assert script_root == daily_report.ROOT
    assert script_load_config is daily_report._load_config
    assert script_load_preferences is daily_report._load_preferences
    assert script_build_report_payload is daily_report._build_report_payload
    assert script_previous_reports_summary_from_input is daily_report._previous_reports_summary_from_input
    assert script_safe_dict is daily_report._safe_dict


def test_daily_report_star_import_preserves_legacy_public_surface() -> None:
    namespace: dict[str, object] = {}

    exec("from generate_report import *", {}, namespace)

    from tech_daily.reports import daily as daily_report

    assert namespace["DEFAULT_DAILY_MODEL"] == daily_report.DEFAULT_DAILY_MODEL
    assert namespace["ROOT"] == daily_report.ROOT
    assert namespace["PromptRunner"] is daily_report.PromptRunner
    assert namespace["ReportInputState"] is daily_report.ReportInputState
    assert namespace["TechDailyState"] is daily_report.TechDailyState
    assert namespace["Any"] is daily_report.Any
    assert namespace["dataclasses"] is daily_report.dataclasses
    assert namespace["json"] is daily_report.json
    assert namespace["os"] is daily_report.os
    assert namespace["yaml"] is daily_report.yaml
    assert namespace["generate_daily_report"] is daily_report.generate_daily_report
    assert namespace["generate_daily_report_from_input"] is daily_report.generate_daily_report_from_input
    assert namespace["build_daily_report_payload_from_input"] is daily_report.build_daily_report_payload_from_input


def test_daily_report_legacy_public_names_remain_available_on_generate_report_module() -> None:
    import generate_report

    from tech_daily.reports import daily as daily_report

    assert generate_report.ROOT == daily_report.ROOT
    assert generate_report.TechDailyState is daily_report.TechDailyState


def test_daily_report_loaders_preserve_raw_yaml_payloads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tech_daily.reports import daily as daily_report

    config_path = tmp_path / "config.yml"
    prefs_path = tmp_path / "data" / "user_preferences.yml"
    prefs_path.parent.mkdir(parents=True)
    config_path.write_text("- alpha\n- beta\n", encoding="utf-8")
    prefs_path.write_text("false\n", encoding="utf-8")
    monkeypatch.setattr(daily_report, "ROOT_DIR", tmp_path)

    assert daily_report._load_config() == ["alpha", "beta"]
    assert daily_report._load_preferences() is False


def test_daily_pipeline_available_from_package_and_script_wrapper() -> None:
    from daily_pipeline import DailyPipelineRuntime as ScriptDailyPipelineRuntime
    from daily_pipeline import execute_daily_pipeline as script_execute_daily_pipeline

    from tech_daily.pipeline.daily import DailyPipelineRuntime, execute_daily_pipeline

    assert ScriptDailyPipelineRuntime is DailyPipelineRuntime
    assert script_execute_daily_pipeline is execute_daily_pipeline


def test_daily_step_actions_available_from_package_and_script_wrapper() -> None:
    from daily_step_actions import load_historical_context_action as script_load_historical_context_action

    from tech_daily.pipeline.actions import load_historical_context_action

    assert script_load_historical_context_action is load_historical_context_action


def test_storage_io_available_from_package_and_script_wrapper() -> None:
    from storage_io import append_jsonl_rows_safely as script_append_jsonl_rows_safely
    from storage_io import atomic_replace as script_atomic_replace
    from storage_io import atomic_write_jsonl as script_atomic_write_jsonl
    from storage_io import atomic_write_text as script_atomic_write_text
    from storage_io import quarantine_jsonl_row as script_quarantine_jsonl_row

    from tech_daily.storage.io import (
        append_jsonl_rows_safely,
        atomic_replace,
        atomic_write_jsonl,
        atomic_write_text,
        quarantine_jsonl_row,
    )

    assert script_append_jsonl_rows_safely is append_jsonl_rows_safely
    assert script_atomic_replace is atomic_replace
    assert script_atomic_write_jsonl is atomic_write_jsonl
    assert script_atomic_write_text is atomic_write_text
    assert script_quarantine_jsonl_row is quarantine_jsonl_row


def test_storage_validation_available_from_package_and_script_wrapper() -> None:
    from storage_validation import StorageDiagnostics as ScriptStorageDiagnostics
    from storage_validation import StorageWarning as ScriptStorageWarning
    from storage_validation import migrate_collector_telemetry_row as script_migrate_collector_telemetry_row
    from storage_validation import validate_collector_telemetry_row as script_validate_collector_telemetry_row
    from storage_validation import validate_open_prediction_row as script_validate_open_prediction_row

    from tech_daily.storage.validation import (
        StorageDiagnostics,
        StorageWarning,
        migrate_collector_telemetry_row,
        validate_collector_telemetry_row,
        validate_open_prediction_row,
    )

    assert ScriptStorageDiagnostics is StorageDiagnostics
    assert ScriptStorageWarning is StorageWarning
    assert script_migrate_collector_telemetry_row is migrate_collector_telemetry_row
    assert script_validate_collector_telemetry_row is validate_collector_telemetry_row
    assert script_validate_open_prediction_row is validate_open_prediction_row


def test_storage_context_available_from_package_and_script_storage_facade(tmp_path: Path) -> None:
    import storage

    from tech_daily.storage.context import StorageContext

    assert storage.StorageContext is StorageContext

    context = StorageContext.from_root(tmp_path)

    assert context.daily_report_path("2026-07-02") == tmp_path / "reports" / "daily" / "2026-07-02.md"
    assert context.prediction_log_path() == tmp_path / "data" / "prediction_log.jsonl"
    assert context.collector_telemetry_path() == tmp_path / "data" / "collector_runs.jsonl"


def test_storage_artifact_modules_available_from_package_and_script_facade() -> None:
    import storage

    from tech_daily.storage.events import append_events
    from tech_daily.storage.predictions import load_open_predictions
    from tech_daily.storage.reports import save_daily_report
    from tech_daily.storage.telemetry import load_collector_telemetry

    assert callable(append_events)
    assert callable(load_open_predictions)
    assert callable(save_daily_report)
    assert callable(load_collector_telemetry)
    assert callable(storage.append_events)
    assert callable(storage.load_open_predictions)
    assert callable(storage.save_predictions)
    assert callable(storage.save_daily_report)
    assert callable(storage.load_collector_telemetry)
    assert callable(storage.save_collector_telemetry)


def test_low_risk_consumers_prefer_package_foundation_imports() -> None:
    daily_pipeline = Path("src/tech_daily/pipeline/daily.py").read_text(encoding="utf-8")
    daily_step_actions = Path("src/tech_daily/pipeline/actions.py").read_text(encoding="utf-8")
    daily_pipeline_wrapper = Path("scripts/daily_pipeline.py").read_text(encoding="utf-8")
    daily_step_actions_wrapper = Path("scripts/daily_step_actions.py").read_text(encoding="utf-8")
    package_run_daily = Path("src/tech_daily/cli/run_daily.py").read_text(encoding="utf-8")
    script_run_daily = Path("scripts/run_daily.py").read_text(encoding="utf-8")
    storage = Path("scripts/storage.py").read_text(encoding="utf-8")
    diagnose_collectors = Path("scripts/diagnose_collectors.py").read_text(encoding="utf-8")

    assert "from tech_daily.pipeline.step import" in daily_pipeline
    assert "from tech_daily.runtime.run_context import" in daily_pipeline
    assert "from tech_daily.runtime.run_logging import" in daily_pipeline
    assert "from pipeline_step import" not in daily_pipeline
    assert "from run_context import" not in daily_pipeline
    assert "from run_logging import" not in daily_pipeline

    assert "from tech_daily.runtime.run_context import" in daily_step_actions
    assert "from run_context import" not in daily_step_actions

    assert "from tech_daily.pipeline.daily import *" in daily_pipeline_wrapper
    assert "from tech_daily.pipeline.actions import *" in daily_step_actions_wrapper

    assert "from tech_daily.runtime.run_context import" in package_run_daily
    assert "from tech_daily.runtime.run_logging import" in package_run_daily
    assert "from tech_daily.pipeline.daily import DailyPipelineRuntime, execute_daily_pipeline" in package_run_daily
    assert "from daily_pipeline import" not in package_run_daily
    assert "from run_context import" not in package_run_daily
    assert "from run_logging import" not in package_run_daily

    assert "from tech_daily.cli.run_daily import main, run_daily" in script_run_daily
    assert "TechDailyState(" not in script_run_daily
    assert "execute_daily_pipeline(" not in script_run_daily

    assert "from tech_daily.storage.io import" in storage
    assert "from tech_daily.storage.validation import" in storage
    assert "from storage_io import" not in storage
    assert "from storage_validation import" not in storage

    assert "from tech_daily.storage.validation import StorageDiagnostics" in diagnose_collectors
    assert "from storage_validation import" not in diagnose_collectors


def test_package_modules_do_not_import_legacy_script_modules() -> None:
    forbidden_modules = {
        "state",
        "storage",
        "run_daily",
        "daily_pipeline",
        "daily_step_actions",
        "pipeline_state",
        "pipeline_policy",
    }
    transitional_allowlist = {
        ("state", Path("src/tech_daily/cli/run_daily.py")): "runtime",
        ("state", Path("src/tech_daily/pipeline/actions.py")): "type_checking",
        ("state", Path("src/tech_daily/pipeline/daily.py")): "type_checking",
        ("state", Path("src/tech_daily/pipeline/state.py")): "runtime",
        ("state", Path("src/tech_daily/reports/daily.py")): "type_checking",
    }

    def assert_legacy_reference_allowed(path: Path, legacy_import: str, *, inside_type_checking: bool) -> None:
        allowance = transitional_allowlist.get((legacy_import, path))
        if allowance == "runtime":
            return
        if allowance == "type_checking" and inside_type_checking:
            return
        pytest.fail(f"{path} imports legacy script module via {legacy_import!r}")

    def collect_importlib_aliases(module: ast.Module) -> tuple[set[str], set[str]]:
        importlib_module_names = {"importlib"}
        import_module_names: set[str] = set()
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "importlib":
                        importlib_module_names.add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == "importlib":
                for alias in node.names:
                    if alias.name == "import_module":
                        import_module_names.add(alias.asname or alias.name)
        return importlib_module_names, import_module_names

    def is_dynamic_import_call(
        node: ast.Call,
        *,
        importlib_module_names: set[str],
        import_module_names: set[str],
    ) -> bool:
        if isinstance(node.func, ast.Name):
            return node.func.id == "__import__" or node.func.id in import_module_names
        return (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "import_module"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in importlib_module_names
        )

    def visit(
        node: ast.AST,
        path: Path,
        *,
        importlib_module_names: set[str],
        import_module_names: set[str],
        inside_type_checking: bool = False,
    ) -> None:
        legacy_import: str | None = None
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_name = alias.name.split(".")[0]
                if module_name in forbidden_modules:
                    legacy_import = module_name
                    break
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            module_name = node.module.split(".")[0]
            if module_name in forbidden_modules:
                legacy_import = module_name
        elif (
            isinstance(node, ast.Call)
            and is_dynamic_import_call(
                node,
                importlib_module_names=importlib_module_names,
                import_module_names=import_module_names,
            )
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and node.args[0].value in forbidden_modules
        ):
            legacy_import = node.args[0].value

        if legacy_import:
            assert_legacy_reference_allowed(path, legacy_import, inside_type_checking=inside_type_checking)

        if isinstance(node, ast.If):
            is_type_checking_block = isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING"
            for child in node.body:
                visit(
                    child,
                    path,
                    importlib_module_names=importlib_module_names,
                    import_module_names=import_module_names,
                    inside_type_checking=inside_type_checking or is_type_checking_block,
                )
            for child in node.orelse:
                visit(
                    child,
                    path,
                    importlib_module_names=importlib_module_names,
                    import_module_names=import_module_names,
                    inside_type_checking=inside_type_checking,
                )
            return

        for child in ast.iter_child_nodes(node):
            visit(
                child,
                path,
                importlib_module_names=importlib_module_names,
                import_module_names=import_module_names,
                inside_type_checking=inside_type_checking,
            )

    for path in sorted(Path("src/tech_daily").rglob("*.py")):
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        importlib_module_names, import_module_names = collect_importlib_aliases(module)
        visit(
            module,
            path,
            importlib_module_names=importlib_module_names,
            import_module_names=import_module_names,
        )


def test_storage_submodules_do_not_import_private_helpers_from_package_init() -> None:
    storage_submodules = [
        path for path in Path("src/tech_daily/storage").glob("*.py") if path.name not in {"__init__.py", "_shared.py"}
    ]

    for path in storage_submodules:
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(module):
            if isinstance(node, ast.ImportFrom) and node.module == "tech_daily.storage":
                imported_names = {alias.name for alias in node.names}
                private_names = {name for name in imported_names if name.startswith("_")}
                assert not private_names, f"{path} imports private helpers from package __init__: {private_names}"


def test_sys_path_mutation_stays_on_explicit_transition_allowlist() -> None:
    allowed = {
        Path("scripts/run_daily.py"),
        Path("src/tech_daily/cli/run_daily.py"),
        Path("scripts/run_context.py"),
        Path("scripts/run_logging.py"),
        Path("scripts/pipeline_policy.py"),
        Path("scripts/pipeline_state.py"),
        Path("scripts/pipeline_step.py"),
        Path("scripts/daily_pipeline.py"),
        Path("scripts/daily_step_actions.py"),
        Path("scripts/llm_client.py"),
        Path("scripts/llm_schemas.py"),
        Path("scripts/storage.py"),
        Path("scripts/storage_io.py"),
        Path("scripts/storage_validation.py"),
        Path("scripts/prompt_runner.py"),
        Path("scripts/run_weekly_review.py"),
        Path("scripts/run_monthly_review.py"),
        Path("scripts/normalize_sources.py"),
        Path("scripts/generate_report.py"),
    }
    offenders: list[Path] = []
    for root in [Path("scripts"), Path("src/tech_daily")]:
        for path in sorted(root.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            if ("sys.path.insert" in text or "sys.path.append" in text) and path not in allowed:
                offenders.append(path)

    assert offenders == []
