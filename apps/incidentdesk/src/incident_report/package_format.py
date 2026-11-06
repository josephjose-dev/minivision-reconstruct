"""Shared export errors and metadata limit, independent of report presentation."""

# Project engineering bound for metadata only; original videos are streamed by verification.
MAX_MANIFEST_BYTES = 1024 * 1024


class PackageRefused(ValueError):
    """Readable export refusal without local paths or underlying DB/storage diagnostics."""


class VerificationRefused(ValueError):
    """Readable integrity or archive portability refusal."""
