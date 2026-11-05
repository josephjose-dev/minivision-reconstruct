"""Reconstruction settings do not initialize AI or network clients."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ReconstructionSettings:
    enabled: bool = False
    evidence_exports_root: Path | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "ReconstructionSettings":
        values = os.environ if env is None else env
        flag = values.get("INCIDENTDESK_RECONSTRUCTION", "").lower().strip()
        if flag not in ("", "0", "false", "1", "true"):
            raise ValueError("INCIDENTDESK_RECONSTRUCTION must be true or false")
        root = values.get("INCIDENTDESK_EVIDENCE_EXPORTS_ROOT", "").strip()
        return cls(flag in ("1", "true"), Path(root) if root else None)
