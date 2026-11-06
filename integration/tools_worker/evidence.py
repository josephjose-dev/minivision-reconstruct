"""Resolve producer manifest input before invoking workflows that trust its paths."""

import json
from pathlib import PurePosixPath

from minivision_reconstruct.domain.models import EvidenceManifest, FrameRate
from minivision_reconstruct.evidence.integrity import sha256_file
from minivision_reconstruct.video.reader import read_frame_at


def load_evidence(root, case_id, select_case):
    case = select_case(root, case_id)
    manifest = EvidenceManifest(
        **json.loads((case / "metadata/evidence_manifest.json").read_bytes())
    )
    declared = manifest.preserved_relative_path
    path = PurePosixPath(declared)
    if (
        manifest.case_id != case_id
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in declared
        or not path.parts
        or path.parts[0] != case_id
    ):
        raise ValueError("Invalid preserved input")
    video = root / declared
    if (
        not video.resolve(strict=True).is_relative_to(case)
        or sha256_file(video) != manifest.preserved_sha256
    ):
        raise ValueError("Invalid preserved input")
    return case, manifest, video


def source_frame(manifest, video, frame_number):
    rate = (
        None
        if manifest.frame_rate_numerator is None
        or manifest.frame_rate_denominator is None
        else FrameRate(manifest.frame_rate_numerator, manifest.frame_rate_denominator)
    )
    return read_frame_at(video, rate, frame_number)
