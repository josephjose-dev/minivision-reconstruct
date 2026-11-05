# MIG-04 display-only reconstruction cross-check

The review page projects comparisons from each current immutable import and the saved
OverviewFacts for the SHA-bound view. Nothing is persisted, no migration or dependency
is added, and no network/model request is made. Only the web presentation reads this
projection. INCIDENTDESK_RECONSTRUCTION remains default off. Print excludes both the
collapsed block and neutral disagreement notice.

## State mapping

| Producer field | Saved video-analysis field | Result |
| --- | --- | --- |
| Effective collision_candidate source_time/frame, with current same-view track mappings | contact_observed interval | inclusive containment: agree; outside: disagree_time with signed difference to nearest boundary |
| Same effective candidate | typed contact timestamp, when no interval | saved adjacent presentation timestamps define half-open source-frame intervals; frame equality agrees; no frame mapping cannot compare |
| No collision candidate | contact_observed / typed contact | tracker_miss, unless assessment says obscured/cannot assess |
| Any missing_inputs | saved facts retained | reconstruction_unavailable, never tracker_miss |
| Candidate and same-view mappings | no_contact_observed | model_miss |
| Rejected, quarantined, needs-review or unknown corrected time | any | cannot_compare |
| Two distinct reviewer-mapped tracks | one unambiguous matching typed contact's subject/other_party codes | unordered equality: agree/disagree_parties; missing/ambiguous codes: cannot_compare |
| Cited first/last seen and latest stop/start | motion_state_before_contact at its own timestamp | moving/moving, stopped/(stopped_in_lane or parked_at_kerb); reversing/unknown cannot_compare |
| Unresolved movement transition | any motion fact | cannot_compare; never bridge the unknown interval |
| First seen at/after its own cited contact; calibration/timestamp missing flags | same-party contact citations; recovery notes unchanged | lacks pre-contact context; never use another pair's contact |

Track associations come only from the latest mapping on the current attached import,
same view and still-valid party code. Prior associations need re-confirmation. Unknown
clocks are irrelevant to comparison: no cross-view comparison occurs. Source times
stay native and never borrow reviewer alignment offsets.

The existing importer timestamp/frame projection is reused. Modified events resolve
only through MIG-03 effective citations; no old frame substitutes for unknown corrected
time. Autoescaping stays enabled; no imported string becomes markup.

## Verification and review

New tests construct labelled synthetic saved OverviewFacts, never purported Gemini output.
All six unchanged MIG-02 exports are exercised. Normal-crossing's missing-input state is
kept separate from a negative or tracker miss. Tests cover timing, parties, motion,
context, unknown/rejected/quarantined evidence, camera isolation, current/stale mappings,
source-frame containment, socket-denied rendering, escaping and byte-identical full
print HTML with nonempty fault findings and a sourced fine row.

Native Standards and Spec reviewers found false video citation ownership, quarantine
leakage, uncertainty precedence, missing context and unknown movement barriers; red
regressions were added and fixes made. Final party-specific contact regression also
prevents unrelated earlier collisions triggering missing-context warnings. These
checks are preparation, not Claude acceptance. Gate logs and full result are in the
donor .agent_bridge/results/MIG-04-CROSS-CHECK.md. Claude browser checklist:
integration/smoke/MIG-04-CROSS-CHECK.md.

## Alternative found / limitations

There is no server PDF endpoint or byte-renderer in this app: /print returns HTML for
the browser's print/save-PDF workflow. Automated evidence is byte-identical print HTML,
not actual browser PDF-byte equality. Claude must verify the saved PDF/pages manually;
no PDF-byte claim is made. A dedicated deterministic PDF renderer would be a separate
scope/dependency decision, not a silent addition to this card.

A typed citation structure could replace the compact display-only video_times tuple
in a later refactor. This card keeps the existing native citation style and regression
tests enforce source ownership. Unknown transitions conservatively block the whole
track's motion comparison rather than invent their corrected time bounds.

## Tell the collaborator

No producer change required. Existing event, movement, source timestamp and review
exports are read as written. Reconstruction stays a proposal and a reviewer cross-check;
producer confirmation never changes Fault Status, fines, storyline, summary, Q&A or PDF.
No merge, push or tag by Codex. Independent Claude critical review remains required.
