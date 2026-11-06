import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {test} from "node:test";

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

// R3-1: a browser's fetch throws "Illegal invocation" when called with a foreign `this`.
test("R3-1: default fetcher works when fetch rejects a foreign this", async () => {
  const realFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = function browserLikeFetch(url, options) {
    if (this !== undefined && this !== globalThis) throw new TypeError("Failed to execute 'fetch' on 'Window': Illegal invocation");
    calls.push(url);
    return Promise.resolve(new Response(JSON.stringify({revision: "revision-001"}), {status: 200}));
  };
  try {
    const result = await new PendingWrite().start("/write", new FormData());
    assert.equal(result.response.status, 200);
    assert.deepEqual(calls, ["/write"]);
  } finally { globalThis.fetch = realFetch; }
});

// R3-2: a throw before any response keeps the action pending but tells the user nothing was sent.
test("R3-2: a thrown fetch keeps the action pending and says it was not sent", async () => {
  let attempts = 0;
  const sentIds = [];
  const pending = new PendingWrite(async (url, options) => {
    attempts++;
    if (attempts === 1) throw new TypeError("Failed to fetch");
    sentIds.push(options.body.get("action_id"));
    return new Response(JSON.stringify({revision: "revision-001"}), {status: 200});
  });
  const fields = new FormData();
  fields.set("action_id", "action-fixed-1");
  await assert.rejects(() => pending.start("/write", fields), error => {
    assert.match(error.message, /not sent/i);
    assert.match(error.message, /retry/i);
    assert.match(error.message, /same action ID/i);
    return true;
  });
  assert.equal(pending.pending, true, "stays pending so Retry is offered");
  const confirmed = await pending.retry();
  assert.equal(confirmed.response.status, 200);
  assert.deepEqual(sentIds, ["action-fixed-1"]);
  assert.equal(pending.pending, false);
});
