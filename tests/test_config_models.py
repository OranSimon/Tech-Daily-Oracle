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


def test_normalization_config_loads_compatible_defaults() -> None:
    from config_models import load_normalization_config

    config = load_normalization_config()

    assert "ai_models" in config.topic_keywords
    assert "OpenAI" in config.company_keywords
    assert "GPT" in config.topic_keywords["ai_models"]
    assert "OpenAI" in config.company_keywords["OpenAI"]


def test_normalization_config_default_path_is_externalized() -> None:
    from config_models import DEFAULT_NORMALIZATION_CONFIG_PATH, load_normalization_config

    assert DEFAULT_NORMALIZATION_CONFIG_PATH.name == "normalization_rules.yml"
    assert DEFAULT_NORMALIZATION_CONFIG_PATH.exists()
    assert "ai_models" in load_normalization_config(DEFAULT_NORMALIZATION_CONFIG_PATH).topic_keywords


def test_normalization_config_missing_external_file_falls_back_to_legacy_defaults(tmp_path: Path) -> None:
    from config_models import load_normalization_config

    config = load_normalization_config(tmp_path / "missing.yml", allow_missing=True)

    assert "GPT" in config.topic_keywords["ai_models"]
    assert "OpenAI" in config.company_keywords["OpenAI"]


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
    from config_models import load_normalization_config

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

    config = load_normalization_config(config_path)

    assert config.topic_keywords == {"custom_topic": ["CustomKeyword"]}
    assert config.company_keywords == {"CustomCo": ["CustomAlias"]}


def test_normalization_uses_loaded_domain_config_without_changing_defaults() -> None:
    from normalize_sources import normalize_events

    event = normalize_events([_raw_event()], run_date="2026-07-02")[0]

    assert "ai_models" in event.topics
    assert "OpenAI" in event.companies
    assert "Nvidia" in event.companies


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
