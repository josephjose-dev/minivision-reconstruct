// Freeze the request until its result is confirmed. Retrying never creates a new intent.
function copyFields(fields) {
  const copy = new FormData();
  for (const [key, value] of fields.entries()) copy.append(key, value);
  return copy;
}
export class PendingWrite {
  constructor(fetcher = globalThis.fetch) { this.fetcher = fetcher; this.current = null; }
  get pending() { return this.current !== null; }
  async start(url, fields) {
    if (this.pending) throw new Error("An unconfirmed action is pending. Retry it before starting another write.");
    const frozen = copyFields(fields);
    if (!frozen.get("action_id")) frozen.set("action_id", crypto.randomUUID());
    this.current = {url, fields: frozen, attempts: 0};
    return this.retry();
  }
  async retry() {
    if (!this.pending) throw new Error("No pending action to retry.");
    const retry = this.current.attempts++ > 0;
    const response = await this.fetcher(this.current.url, {
      method: "POST", body: copyFields(this.current.fields), credentials: "same-origin",
      headers: {"Accept": "application/json", ...(retry ? {"X-Native-Retry": "1"} : {})}
    });
    let data = null;
    try { data = await response.json(); }
    catch { if (response.ok) throw new Error("Result was not confirmed. Retry the pending action."); }
    if (data?.detail?.write_state === "refused") data = data.detail;
    if (response.ok || data?.write_state === "refused") this.current = null;
    return {response, data};
  }
}
