"use strict";
const form = document.getElementById("replay-write");
const base = form.dataset.base;
const selection = document.getElementById("replay-selection");
const status = document.getElementById("replay-save-status");
const host = document.getElementById("native-replay-host");
// The collaborator's built module and styles are served byte-for-byte by our app.
const {default: mount} = await import(`${base}/assets/workspace.js`);
let dispose = null;
let busy = false;
function query() { return new URLSearchParams(new FormData(selection)); }
function setRevision(name, value) {
  const select = selection.elements.namedItem(name);
  if (![...select.options].some(option => option.value === value)) select.add(new Option(value, value));
  select.value = value;
}
function open(seek = null, preserve = false) {
  if (dispose) dispose();
  if (!preserve) delete host.querySelector(".replay-root").dataset.workspace;
  const params = query();
  const data = {bundle_url: `${base}/bundle?${params}`, video_url: `${base}/video?${params}`,
    frame_url: `${base}/frame/`, reviewer: form.elements.namedItem("reviewer").value, seek};
  dispose = mount({parentElement: host, data, setStateValue() {},
    setTriggerValue: (action, value) => { void save(action, value); }});
  form.elements.namedItem("reviewer").oninput = () => { data.reviewer = form.elements.namedItem("reviewer").value; };
}
async function save(action, value = {}) {
  if (busy) { status.textContent = "Wait for the current save to finish."; return; }
  if (!form.reportValidity()) return;
  busy = true;
  status.textContent = "Saving producer revision…";
  try {
    const fields = new FormData(form);
    for (const [name, entry] of new FormData(selection)) fields.set(name, entry);
    fields.set("action", action);
    fields.set("action_id", value.action_id || crypto.randomUUID());
    if (value.document) fields.set("document", JSON.stringify(value.document));
    fields.set("source_frame", String(value.source_frame ?? host.querySelector(".replay-root").dataset.sourceFrame ?? 0));
    const response = await fetch(base, {method: "POST", body: fields, credentials: "same-origin"});
    if (!response.ok) throw new Error("Save was not confirmed. Check the selected inputs and inspect saved revisions before retrying.");
    const result = await response.json();
    if (result.category === "scene") { setRevision("scene_revision", result.revision); open(null, true); }
    if (result.category === "marker") { setRevision("marker_revision", result.revision); open(null, true); }
    if (result.category === "review") setRevision("review_revision", result.revision);
    if (result.snapshot) {
      const link = document.getElementById("snapshot-download");
      link.href = `${base}/snapshot/${encodeURIComponent(result.snapshot)}`; link.hidden = false;
    }
    status.textContent = `Saved ${result.revision || result.export || result.snapshot}. Open saved selections to refresh the incident tables.`;
  } catch (error) { status.textContent = error.message; }
  finally { busy = false; }
}
form.addEventListener("submit", event => { event.preventDefault(); void save(event.submitter.value); });
for (const button of document.querySelectorAll(".native-seek")) button.addEventListener("click", () => open({source_frame: Number(button.dataset.frame), track_id: null, action_id: crypto.randomUUID()}, true));
open();
