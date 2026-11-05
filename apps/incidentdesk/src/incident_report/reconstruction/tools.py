"""Tool routes are fixed; case selection stays in the collaborator's dropdown."""

TOOLS = (("Track review", "tracks"), ("Calibration", "calibration"), ("Reconstruction replay", "replay"))


def tool_links() -> tuple[tuple[str, str], ...]:
    return tuple((label, f"/reconstruct/{slug}/") for label, slug in TOOLS)


def unavailable(tool: str) -> str:
    if tool not in {slug for _, slug in TOOLS}:
        raise ValueError("Unknown reconstruction tool")
    return "Reconstruction tools are not running. Start the local tools and Caddy proxy, then open this address through Caddy."
