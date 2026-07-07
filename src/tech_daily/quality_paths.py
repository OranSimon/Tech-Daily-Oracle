"""Print quality paths from pyproject for local and CI use."""

from __future__ import annotations

import tomllib
from pathlib import Path


def iter_quality_paths(pyproject_path: str | Path = "pyproject.toml") -> list[str]:
    config = tomllib.loads(Path(pyproject_path).read_text(encoding="utf-8"))
    return list(config["tool"]["tech_daily"]["quality"]["stable_paths"])


def main() -> None:
    for path in iter_quality_paths():
        print(path)


if __name__ == "__main__":
    main()
