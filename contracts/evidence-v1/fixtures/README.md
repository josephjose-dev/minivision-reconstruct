# MIG-02 fixtures

Producer source: `c66000af37099e39920ff0e8ac621ce5be09090d`; generated from its
unchanged worker in the approved integration checkout `5f6327a`. Scripted scenes,
no real people or NDA footage. The worker was run in WSL using the existing locked
Linux environment; no Chromium install or Canvas export was needed. Configs are
`configs/movement.json` and `configs/incident.json`, copied unchanged in each run.
No detector/model was used; tracks come from the scripted producer fixture.

The actual generation commands and tool paths are recorded in the donor ticket
result (`.agent_bridge/results/MIG-02-EVIDENCE-IMPORTER.md`). Reproduction from the
repository root, after setting the machine-specific tool paths from CLAUDE.local.md:

```bash
export PYTHONPATH=src
"$WORKER_PYTHON" scripts/create_incident_fixture.py --cases-root ../cases \
  --case-prefix mig02 --seeds 1 --scenarios rear_end occluded_impact near_miss_crossing normal_crossing \
  --pixel-noise-sigma 0 --ffmpeg "$FFMPEG" --ffprobe "$FFPROBE"
"$WORKER_PYTHON" integration/generate_mig02_fixture.py
```

Then run `apps/incidentdesk/.venv/Scripts/python integration/mig02_fixture.py` on
Windows. The packaging script copies only JSON/JSONL bytes, excludes truth labels,
and adds view/run bindings. Three immutable revisions on each nonempty case record
confirm, reject, then modify of its single candidate. Each revision is a complete
snapshot. The modify adds 0.001 s, intentionally not a source timestamp. The normal
crossing case has an empty candidate list. Producer creation times and video bytes
may vary across reruns; the checked-in `bundle.json` files freeze the actual hashes.

Every included artifact digest is listed in its `bundle.json`; `SHA256SUMS.json`
additionally pins every included byte including the envelopes. Git attributes keep
fixture bytes unchanged across Windows/Linux checkouts.

These **real producer exports are intentionally incomplete JSON-only packages**:
reconstruction manifests reference omitted replay MP4s, movement manifests reference
omitted CSVs, and preserved-original metadata names video digests. Missing evidence
and floating-point timestamp inconsistencies are reported, not patched. All records
are quarantined, never affirmative. Producer `lost` states survive. Synthetic
negative/completion variations are built separately by
`apps/incidentdesk/tests/evidence_import_fixtures.py`; those are labelled handmade
and never claimed to be unchanged producer output.
