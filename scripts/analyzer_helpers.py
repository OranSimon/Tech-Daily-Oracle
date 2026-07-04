"""Small helpers shared by migrated analyzer modules."""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T")


def schema_to_dataclass(schema: BaseModel, dataclass_type: type[T], **overrides: object) -> T:
    data = schema.model_dump()
    data.update(overrides)
    return dataclass_type(**data)
