# MIG-05 report version and package smoke

Status: prepared for Claude; NOT RUN by Codex. Part A implemented only. Package steps
remain pending the card's hash-cycle/determinism and legal-link clarification.
Use a clearly labelled synthetic report with cited parties, fines and officer decisions.
Do not use real/NDA footage or make a model call for this check.

1. Open the report with a valid share session. In the review workspace, add an override
   with an explanation, approve version 1, and record the version and approval timestamp.
2. Open `/reports/<run_id>?version=1`, then its Print report link. Confirm the URL ends
   `/print?version=1`, and the header identifies version 1 and the same approval timestamp.
   Compare parties, Fault Status words and colour, violations, fine/points/impound values,
   source/item references, storyline, view/time citations, AI originals and officer overrides.
3. Use browser print preview to save an A4 PDF. Inspect EVERY page: table rows and Arabic
   text readable, no clipped columns, fines with source/item visible, citations readable,
   no player/decision controls. PDF is browser output; no server PDF library is introduced.
4. Start version 2, add a different override, inspect its draft print page ('Draft, not
   approved'), approve it. Reopen version 1 screen and print: original decisions and
   approval timestamp unchanged. Its print link must still select version 1.
5. Pending Parts B/D: download approved version 1 and version 2 packages through the same
   share session; a draft and missing/mismatched evidence must be refused before streaming.
   Repeat a build and compare ZIP bytes. Confirm one build audit entry per successful build.
6. Pending Parts B/C/E: copy a ZIP into a clean folder and run
   `python -m incident_report.package verify <zip>` in the app environment. Open extracted
   report offline; verify originals and manifest hashes/sizes. Confirm no machine-local
   paths, secrets or active network resources. Check reconstruction only in its labelled
   proposal appendix when enabled; repeat with flag off and an interior view.
7. Pending verifier: tamper a byte, add/remove a payload file, and introduce a traversal
   member in separate copies; each must fail with a readable reason.

Record browser/PDF results and any package-contract exception in the independent review.
