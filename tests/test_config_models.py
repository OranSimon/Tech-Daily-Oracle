from __future__ import annotations

from pathlib import Path

import pytest
from state import RawEvent


def _raw_event() -> RawEvent:
    return RawEvent(
        source_name="Fixture",
        source_type="rss",
        raw_title="OpenAI and Nvidia launch GPU benchmark",
        raw_url="https://example.com/benchmark",
        raw_content="OpenAI and Nvidia announced an inference benchmark for GPUs.",
        published_at="2026-07-02T00:00:00+00:00",
        fetched_at="2026-07-02T00:00:00+00:00",
        metadata={"priority": 1, "feed_source_type": "company"},
    )


def test_normalization_config_loads_compatible_defaults(recwarn: pytest.WarningsRecorder) -> None:
    from config_models import load_normalization_config

    config = load_normalization_config()

    assert "ai_models" in config.topic_keywords
    assert "OpenAI" in config.company_keywords
    assert "GPT" in config.topic_keywords["ai_models"]
    assert "OpenAI" in config.company_keywords["OpenAI"]
    assert config.topic_groups["core_tech_topics"] == [
        "ai_models",
        "ai_agents",
        "embodied_ai_robotics",
        "ai_infrastructure",
        "semiconductors",
        "startups_unicorns",
        "papers_research",
    ]
    assert config.topic_groups["cross_domain_topics"] == [
        "science_breakthrough",
        "health_biotech",
        "astronomy_space",
        "materials_science",
        "global_events",
    ]
    assert config.topic_groups["high_priority_topics"] == [
        "ai_models",
        "embodied_ai_robotics",
        "ai_infrastructure",
        "semiconductors",
        "papers_research",
        "startups_unicorns",
    ]
    assert not recwarn


def test_normalization_config_default_path_is_externalized() -> None:
    from config_models import DEFAULT_NORMALIZATION_CONFIG_PATH, load_normalization_config

    assert DEFAULT_NORMALIZATION_CONFIG_PATH.name == "normalization_rules.yml"
    assert DEFAULT_NORMALIZATION_CONFIG_PATH.exists()
    assert "ai_models" in load_normalization_config(DEFAULT_NORMALIZATION_CONFIG_PATH).topic_keywords


def test_normalize_sources_does_not_duplicate_authoritative_keyword_tables() -> None:
    source = Path("scripts/normalize_sources.py").read_text(encoding="utf-8")

    assert "TOPIC_KEYWORDS" not in source
    assert "COMPANY_KEYWORDS" not in source
    assert "_CORE_TECH_TOPICS" not in source
    assert "_CROSS_DOMAIN_TOPICS" not in source


def test_normalization_config_missing_external_file_falls_back_to_legacy_defaults(tmp_path: Path) -> None:
    from config_models import load_normalization_config

    config = load_normalization_config(tmp_path / "missing.yml", allow_missing=True)

    assert "GPT" in config.topic_keywords["ai_models"]
    assert "OpenAI" in config.company_keywords["OpenAI"]


def test_normalization_config_rejects_duplicate_yaml_keys(tmp_path: Path) -> None:
    from config_models import ConfigValidationError, load_normalization_config

    config_path = tmp_path / "normalization.yml"
    config_path.write_text(
        """
topic_keywords:
  ai_models:
    - GPT
  ai_models:
    - Claude
company_keywords:
  OpenAI:
    - OpenAI
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigValidationError, match="duplicate key"):
        load_normalization_config(config_path)


def test_normalization_config_requires_sections_and_non_empty_company_aliases(tmp_path: Path) -> None:
    from config_models import ConfigValidationError, load_normalization_config

    missing_section = tmp_path / "missing-section.yml"
    missing_section.write_text(
        """
topic_keywords:
  ai_models:
    - GPT
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigValidationError, match="company_keywords"):
        load_normalization_config(missing_section)

    empty_aliases = tmp_path / "empty-aliases.yml"
    empty_aliases.write_text(
        """
topic_keywords:
  ai_models:
    - GPT
company_keywords:
  OpenAI: []
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigValidationError, match="company_keywords.OpenAI"):
        load_normalization_config(empty_aliases)


def test_normalization_config_rejects_duplicate_company_aliases() -> None:
    from config_models import ConfigValidationError, NormalizationConfig

    with pytest.raises(ConfigValidationError, match="duplicate company alias"):
        NormalizationConfig.from_mapping(
            {
                "topic_keywords": {"ai_models": ["GPT"]},
                "company_keywords": {
                    "OpenAI": ["Shared"],
                    "OtherAI": ["shared"],
                },
            }
        )


def test_normalization_config_can_load_external_yaml(tmp_path: Path) -> None:
    from config_models import ConfigRuntimeWarning, load_normalization_config

    config_path = tmp_path / "normalization.yml"
    config_path.write_text(
        """
topic_keywords:
  custom_topic:
    - CustomKeyword
company_keywords:
  CustomCo:
    - CustomAlias
""",
        encoding="utf-8",
    )

    with pytest.warns(ConfigRuntimeWarning, match="topic_groups.*missing"):
        config = load_normalization_config(config_path)

    assert config.topic_keywords == {"custom_topic": ["CustomKeyword"]}
    assert config.company_keywords == {"CustomCo": ["CustomAlias"]}
    assert config.topic_groups == {
        "core_tech_topics": [],
        "cross_domain_topics": [],
        "high_priority_topics": [],
    }


def test_normalization_config_reports_missing_topic_groups_to_diagnostics(tmp_path: Path) -> None:
    from config_models import ConfigDiagnostics, ConfigRuntimeWarning, load_normalization_config

    config_path = tmp_path / "normalization.yml"
    config_path.write_text(
        """
topic_keywords:
  ai_models:
    - GPT
company_keywords:
  OpenAI:
    - OpenAI
""",
        encoding="utf-8",
    )
    diagnostics = ConfigDiagnostics()

    with pytest.warns(ConfigRuntimeWarning, match="legacy-compatible groups were derived"):
        config = load_normalization_config(config_path, diagnostics=diagnostics)

    assert config.topic_groups["core_tech_topics"] == ["ai_models"]
    assert len(diagnostics.warnings) == 1
    assert diagnostics.warnings[0].field == "topic_groups"
    assert "scoring behavior may differ" in diagnostics.warnings[0].message


def test_normalization_config_strict_topic_groups_rejects_missing_topic_groups(tmp_path: Path) -> None:
    from config_models import ConfigValidationError, load_normalization_config

    config_path = tmp_path / "normalization.yml"
    config_path.write_text(
        """
topic_keywords:
  ai_models:
    - GPT
company_keywords:
  OpenAI:
    - OpenAI
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigValidationError, match="topic_groups"):
        load_normalization_config(config_path, strict_topic_groups=True)


def test_normalization_config_loads_topic_groups_from_yaml(tmp_path: Path) -> None:
    from config_models import load_normalization_config

    config_path = tmp_path / "normalization.yml"
    config_path.write_text(
        """
topic_keywords:
  ai_models:
    - GPT
  science_breakthrough:
    - molecule
company_keywords:
  OpenAI:
    - OpenAI
topic_groups:
  core_tech_topics:
    - ai_models
  cross_domain_topics:
    - science_breakthrough
  high_priority_topics:
    - ai_models
""",
        encoding="utf-8",
    )

    config = load_normalization_config(config_path)

    assert config.topic_groups["core_tech_topics"] == ["ai_models"]
    assert config.topic_groups["cross_domain_topics"] == ["science_breakthrough"]
    assert config.topic_groups["high_priority_topics"] == ["ai_models"]


def test_normalization_config_rejects_topic_group_references_missing_topics(tmp_path: Path) -> None:
    from config_models import ConfigValidationError, load_normalization_config

    config_path = tmp_path / "normalization.yml"
    config_path.write_text(
        """
topic_keywords:
  ai_models:
    - GPT
company_keywords:
  OpenAI:
    - OpenAI
topic_groups:
  core_tech_topics:
    - missing_topic
  cross_domain_topics:
    - ai_models
  high_priority_topics:
    - ai_models
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigValidationError, match="missing_topic"):
        load_normalization_config(config_path)


def test_normalization_config_rejects_duplicate_topic_group_members(tmp_path: Path) -> None:
    from config_models import ConfigValidationError, load_normalization_config

    config_path = tmp_path / "normalization.yml"
    config_path.write_text(
        """
topic_keywords:
  ai_models:
    - GPT
company_keywords:
  OpenAI:
    - OpenAI
topic_groups:
  core_tech_topics:
    - ai_models
    - ai_models
  cross_domain_topics:
    - ai_models
  high_priority_topics:
    - ai_models
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigValidationError, match="duplicate topic group member"):
        load_normalization_config(config_path)


def test_normalization_config_rejects_empty_required_topic_group(tmp_path: Path) -> None:
    from config_models import ConfigValidationError, load_normalization_config

    config_path = tmp_path / "normalization.yml"
    config_path.write_text(
        """
topic_keywords:
  ai_models:
    - GPT
company_keywords:
  OpenAI:
    - OpenAI
topic_groups:
  core_tech_topics: []
  cross_domain_topics:
    - ai_models
  high_priority_topics:
    - ai_models
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigValidationError, match="core_tech_topics"):
        load_normalization_config(config_path)


def test_normalization_uses_loaded_domain_config_without_changing_defaults() -> None:
    from normalize_sources import normalize_events

    event = normalize_events([_raw_event()], run_date="2026-07-02")[0]

    assert "ai_models" in event.topics
    assert "OpenAI" in event.companies
    assert "Nvidia" in event.companies


def test_normalization_config_exposes_default_scoring_policy() -> None:
    from config_models import load_normalization_config

    from tech_daily.config.normalization_policy import SourceReliabilityPolicy

    config = load_normalization_config()

    assert config.scoring_policy.baseline_importance == 0.3
    assert config.scoring_policy.source_priority_weight == 0.1
    assert config.scoring_policy.company_boost == 0.2
    assert config.scoring_policy.high_priority_topic_boost == 0.1
    assert config.scoring_policy.cross_domain_boost == 0.15
    assert config.scoring_policy.hn_social_heat_thresholds == {500: 0.3, 200: 0.2, 100: 0.1}
    assert isinstance(config.scoring_policy.source_reliability_policy, SourceReliabilityPolicy)
    assert config.scoring_policy.source_reliability_policy.source_reliability_by_priority == {
        1: 0.95,
        2: 0.75,
        3: 0.55,
        4: 0.35,
        5: 0.15,
    }
    assert config.scoring_policy.source_reliability_policy.paper_reliability == 0.90
    assert config.scoring_policy.source_reliability_policy.github_reliability == 0.85
    assert config.scoring_policy.source_reliability_policy.default_reliability == 0.50
    assert [rule.event_type for rule in config.scoring_policy.event_type_rules] == [
        "funding",
        "layoffs",
        "earnings",
        "product_launch",
        "policy",
    ]


def test_normalization_scoring_policy_accepts_direct_reliability_constructor_fields() -> None:
    from tech_daily.config.normalization_policy import NormalizationScoringPolicy

    policy = NormalizationScoringPolicy(default_reliability=0.4)

    assert policy.default_reliability == 0.4
    assert policy.source_reliability_policy.default_reliability == 0.4


def test_normalization_accepts_injected_domain_config() -> None:
    from config_models import NormalizationConfig
    from normalize_sources import normalize_events

    config = NormalizationConfig(
        topic_keywords={"custom_topic": ["NeedleTerm"]},
        company_keywords={"CustomCo": ["NeedleCorp"]},
    )
    raw = RawEvent(
        source_name="Fixture",
        source_type="rss",
        raw_title="NeedleCorp ships NeedleTerm",
        raw_url="https://example.com/custom",
        raw_content="NeedleCorp released a NeedleTerm system.",
        published_at="2026-07-02T00:00:00+00:00",
        fetched_at="2026-07-02T00:00:00+00:00",
        metadata={"priority": 1, "feed_source_type": "company"},
    )

    event = normalize_events([raw], run_date="2026-07-02", config=config)[0]

    assert event.topics == ["custom_topic"]
    assert event.companies == ["CustomCo"]
