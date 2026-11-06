import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";

const source = await readFile(new URL("../../apps/incidentdesk/src/incident_report/web/static/js/pending-write.js", import.meta.url));
const {PendingWrite} = await import("data:text/javascript;base64," + source.toString("base64"));
const sent = [];
const pending = new PendingWrite(async (url, options) => {
  sent.push({url, entries: [...options.body.entries()]});
  return new Response(JSON.stringify(sent.length === 1 ? {detail: "Unconfirmed"} : {revision: "revision-001"}), {status: sent.length === 1 ? 503 : 200});
});
const fields = new FormData();
fields.set("action", "marker_save"); fields.set("document", "original");
await pending.start("/reports/synthetic/tools/attached/replay", fields);
assert.equal(pending.pending, true);
fields.set("document", "edited after timeout");
await assert.rejects(() => pending.start("/reports/synthetic/tools/attached/replay", fields), /pending/i);
const confirmed = await pending.retry();
assert.equal(confirmed.response.status, 200);
assert.deepEqual(sent[1], sent[0]);
assert.equal(pending.pending, false);
assert.ok(new Map(sent[0].entries).get("action_id"));
await pending.start("/reports/synthetic/tools/attached/replay", new FormData());
assert.notEqual(new Map(sent[2].entries).get("action_id"), new Map(sent[0].entries).get("action_id"));
console.log("PASS: unconfirmed retry preserves action ID and exact payload; confirmation releases it");
const refused = new PendingWrite(async () => new Response(JSON.stringify({error: "Invalid input", write_state: "refused"}), {status: 422}));
await refused.start("/write", new FormData());
assert.equal(refused.pending, false, "a confirmed refusal must permit a corrected intent");
console.log("PASS: confirmed non-mutating refusal releases the pending intent");
