"""Local-only, content-addressed evidence proposals; no producer runtime imports."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue


class ImportDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    import_id: str
    provenance_state: Literal["verified", "incomplete_provenance", "rejected"]
    issues: tuple[str, ...]
    records: tuple[dict[str, JsonValue], ...] = ()


def inspect_bundle(directory: Path) -> ImportDecision:
    """Inspect without executing input or making external calls."""
    return ImportDecision(import_id="", provenance_state="rejected", issues=("unsupported contract",))
