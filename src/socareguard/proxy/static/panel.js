(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const TYPE_LABEL = {DIRECT: "direct identifier", QUASI: "quasi-identifier", ATTRIBUTE: "sensitive attribute", KEPT: "kept as typed (no rule in this pack)", evidence: "flagged text"};
  const DECISIONS = {
    pass: "PASS: no conduct flag. The draft in column 4 is ready to use.",
    annotate: "ANNOTATE: use the draft, but read the flag first; apply the rewrite or record a reason to keep it.",
    regenerate: "REGENERATE: the draft should be redrafted; regenerate it, or record a reason per flag to keep it.",
    escalate: "ESCALATE: withheld from this screen and routed to supervisory review; it cannot be overridden here.",
  };
  let current = null;      // the run shown in the columns
  let runs = {};           // {internal, external} for the audience gate
  let loadedScenario = null;
  let compareWith = null;  // internal-audience instruction for the audience-gate chip

  // ---------- scenario chips ----------
  function clearScenario() {
    document.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
    $("scenario-summary").hidden = true;
    loadedScenario = null; compareWith = null;
    $("replay-row").hidden = true; $("replay").checked = false;
  }
  document.querySelectorAll(".chip").forEach((b) => b.addEventListener("click", () => {
    const s = window.SCENARIOS.find((x) => x.id === b.dataset.scenario);
    if (!s) return;
    document.querySelectorAll(".chip").forEach((c) => c.classList.toggle("active", c === b));
    $("pack").value = s.pack; $("instruction").value = s.instruction; $("note").value = s.note;
    loadedScenario = s;
    compareWith = s.compare_instruction || null;
    const sum = $("scenario-summary");
    sum.hidden = false;
    sum.textContent = (compareWith ? "Two runs of the same note in one session: first for the case file, then for the external recipient. " : "") + (s.summary || s.title);
    $("status").textContent = "Loaded: " + s.title;
    $("error").hidden = true;
    $("replay-row").hidden = !s.has_recording;
    $("replay").checked = !!s.has_recording;  // the paper's account by default; untick for a live reply
    $("audience").value = "auto";
    syncSnippet();
  }));
  ["instruction", "note"].forEach((id) => $(id).addEventListener("input", () => {
    if (loadedScenario && ($("instruction").value !== loadedScenario.instruction || $("note").value !== loadedScenario.note)) {
      clearScenario();
      $("status").textContent = "Your own note. The scenario context above no longer applies.";
    }
  }));
  function syncSnippet() {
    const el = $("snippet-pack"); if (el) el.textContent = $("pack").value;
    const a = $("snippet-actor"); if (a) a.textContent = $("actor").value.trim() || "sw-042";
  }
  $("pack").addEventListener("change", syncSnippet); $("actor").addEventListener("input", syncSnippet); syncSnippet();

  // ---------- highlighting ----------
  function highlight(text, spans, cls) {
    let out = "", pos = 0;
    for (const sp of spans) {
      if (sp.start < pos) continue;
      out += md(esc(text.slice(pos, sp.start))) + `<mark class="${cls || sp.label}" title="${esc(sp.title || sp.label)}">` + esc(text.slice(sp.start, sp.end)) + "</mark>";
      pos = sp.end;
    }
    return out + md(esc(text.slice(pos)));
  }
  const isWord = (ch) => /[A-Za-z0-9]/.test(ch || "");
  function findAll(text, needle, whole) {
    const hits = [];
    let i = text.indexOf(needle);
    while (i >= 0) {
      const ok = !whole || (!isWord(text[i - 1]) && !isWord(text[i + needle.length]));
      if (ok) hits.push([i, i + needle.length]);
      i = text.indexOf(needle, i + needle.length);
    }
    return hits;
  }
  // A judge quote may be elided ("... "), joined with ";" or truncated; each piece is matched on
  // its own, and a piece that still misses is matched on its first forty characters.
  function pieces(evidence) {
    return String(evidence || "").split(/\s*(?:\.\.\.|…|;\s+")\s*/).map((p) => p.replace(/^["“”']+|["“”']+$/g, "").trim()).filter((p) => p.length >= 12);
  }
  function markAll(text, needles, cls) {
    const spans = [];
    for (const n of needles) {
      if (!n.text || n.text.length < 2) continue;
      const cands = n.fuzzy ? pieces(n.text) : [n.text];
      for (const c of cands) {
        let hits = findAll(text, c, !n.fuzzy);
        if (!hits.length && n.fuzzy && c.length > 40) hits = findAll(text, c.slice(0, 40));
        for (const [s, e] of hits) spans.push({start: s, end: e, label: n.label, title: n.title});
      }
    }
    spans.sort((a, b) => a.start - b.start || (b.end - b.start) - (a.end - a.start));
    return highlight(text, spans, cls);
  }
  function md(h) {
    return h.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>").replace(/^(#{1,4})\s+(.+)$/gm, "<strong>$2</strong>");
  }
  function ruleTitle(r) {
    if (r.kind === "kept") return `${TYPE_LABEL.KEPT}: this ${r.category.replace("ATTR:", "").toLowerCase()} left as typed`;
    const what = r.kind === "generalised" ? "generalised" : r.kind === "derived" ? "derived form of a surrogate" : "replaced by a surrogate";
    return `${TYPE_LABEL[r.type] || r.type} (${r.category.replace("ATTR:", "").toLowerCase()}): ${what}${r.rule ? " by rule " + r.rule : ""}`;
  }
  const cls = (r) => (r.kind === "kept" ? "KEPT" : r.type);

  // ---------- requests ----------
  function authHeaders(extra) {
    const h = {"Content-Type": "application/json"};
    if ($("actor").value.trim()) h["X-SoCareGuard-Actor"] = $("actor").value.trim();
    const key = window.SOCAREGUARD_AUTH ? ($("apikey") || {}).value : "";
    if (key) h["Authorization"] = "Bearer " + key;
    return Object.assign(h, extra || {});  // a caller's header (the supervisor id) wins
  }
  async function sha256(text) {
    const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");
  }
  async function guarded(instruction, note, opts) {
    opts = opts || {};
    const body = {model: $("model").value, messages: [{role: "user", content: instruction + "\n\n" + note}]};
    if (opts.replay) body.replay_scenario = opts.replay;
    const headers = authHeaders({"X-SoCareGuard-Pack": $("pack").value});
    if (opts.session) headers["X-SoCareGuard-Session"] = opts.session;
    const aud = opts.audience || $("audience").value;
    if (aud && aud !== "auto") headers["X-SoCareGuard-Audience"] = aud;
    const r = await fetch("/v1/chat/completions", {method: "POST", headers, body: JSON.stringify(body)});
    const data = await r.json();
    if (!r.ok) throw new Error((data.error && data.error.message) || data.detail || r.statusText);
    const sg = data.socareguard;
    const panel = await (await fetch(`/v1/sessions/${sg.session}/panel`, {headers: authHeaders({"X-SoCareGuard-Session-Token": sg.session_token})})).json();
    return {data, sg, panel, instruction, typed: instruction + "\n\n" + note, overrides: {}};
  }

  $("compose").addEventListener("submit", (ev) => { ev.preventDefault(); submit(); });
  async function submit(extraInstruction) {
    const res = $("result");
    res.hidden = true; res.setAttribute("aria-busy", "true");
    $("error").hidden = true;
    $("send").disabled = true;
    const instruction = extraInstruction || $("instruction").value, note = $("note").value;
    const replay = ($("replay").checked && loadedScenario && !extraInstruction) ? loadedScenario.id : null;
    try {
      runs = {};
      if (compareWith && !extraInstruction) {
        $("status").textContent = "Run 1 of 2 (internal audience): detecting, substituting, calling the model, screening… usually 5 to 20 seconds each on this sandbox.";
        runs.internal = await guarded(compareWith, note, {audience: "internal"});
      }
      $("status").textContent = (compareWith && !extraInstruction ? "Run 2 of 2 (external audience): " : "") + "Detecting, substituting, calling the model, screening… usually 5 to 20 seconds on this sandbox.";
      const prior = extraInstruction && current ? current : null;
      const ext = await guarded(instruction, note, {replay, session: runs.internal ? runs.internal.sg.session : (prior ? prior.sg.session : null), audience: runs.internal ? "external" : null});
      if (prior) { runs = {list: [{key: "first", label: "First draft", run: prior}, {key: "revised", label: "Revised draft (shown below)", run: ext}], head: "Regenerated in the same session (same surrogates) with the flags as instructions."}; ext.regenerated = true; }
      else runs.external = ext;
      show(ext);
      renderCompare();
      res.hidden = false; res.removeAttribute("aria-busy");
      scrollAffordance();
      $("status").textContent = `Done in ${ext.sg.latency_s} s${ext.sg.replayed ? " (recorded model reply replayed; the guard ran live)" : ""}. Session ${ext.sg.session}.`;
      res.scrollIntoView({behavior: "smooth", block: "start"});
    } catch (e) {
      $("status").textContent = "";
      const err = $("error");
      err.hidden = false;
      err.innerHTML = `<strong>The request did not complete.</strong> ${esc(e.message)}<br><span class="muted">Nothing was drafted. Adjust the note or try again; the previous result has been cleared.</span>`;
    } finally { $("send").disabled = false; }
  }

  // ---------- rendering ----------
  function show(run) { current = run; render(run); }

  function render(run) {
    const {data, sg, panel, typed} = run;
    const send = sg.events.find((e) => e.kind === "send") || {};
    const recv = sg.events.find((e) => e.kind === "receive") || {};
    const leak = sg.events.find((e) => e.kind === "leakcheck") || {};
    const reid = sg.events.find((e) => e.kind === "reidentify") || {};
    const sub = sg.events.find((e) => e.kind === "substitute") || {};
    const gen = sg.events.find((e) => e.kind === "generalise");
    const screen = sg.events.find((e) => e.kind === "screen") || {};
    const shown = panel.replacements.filter((r) => r.kind !== "derived");

    $("col-typed").innerHTML = (run.regenerated ? `<em class="muted">Instruction revised by the panel for the regeneration:</em>\n` : "") + markAll(typed, shown.map((r) => ({text: r.original, label: cls(r), title: ruleTitle(r)})));
    $("col-out").innerHTML = markAll(send.outbound_text || "", shown.map((r) => ({text: r.outbound, label: cls(r), title: ruleTitle(r)})));
    const evidRaw = sg.flags.map((f) => ({text: unrestore(f.evidence, panel), label: "evidence", title: f.name || f.label, fuzzy: true}));
    $("col-back").innerHTML = sg.withheld ? `<span class="withheld">${esc(recv.text || "")}</span>` : markAll(recv.text || "", evidRaw, "evidence");
    // column 4: flagged text, generalised phrases that cannot come back, unrestored fragments
    const seenMarks = sg.flags.map((f) => ({text: f.evidence, label: "evidence", title: f.name || f.label, fuzzy: true}));
    shown.filter((r) => r.kind === "generalised" && r.outbound && r.outbound.length > 3).forEach((r) => seenMarks.push({text: r.outbound, label: cls(r), title: `generalised on the way out and not restorable; the record says: ${r.original}`}));
    (leak.unrestored || []).forEach((u) => seenMarks.push({text: u, label: "unrestored", title: "a surrogate fragment the model reformatted; check against the record before use"}));
    (run.applied || []).forEach((t) => seenMarks.push({text: t, label: "rewrite", title: "applied rewrite"}));
    $("col-seen").innerHTML = sg.withheld
      ? `<span class="withheld">${esc(data.choices[0].message.content)}</span>`
      : markAll(data.choices[0].message.content, seenMarks);
    scrollAffordance();

    const counts = {DIRECT: 0, QUASI: 0, ATTRIBUTE: 0, KEPT: 0};
    shown.forEach((r) => { counts[cls(r)] = (counts[cls(r)] || 0) + 1; });
    $("legend").innerHTML = ["DIRECT", "QUASI", "ATTRIBUTE"].map((t) => `<span class="key"><mark class="${t}">&nbsp;&nbsp;&nbsp;</mark> ${TYPE_LABEL[t]}: ${counts[t] || 0}</span>`).join("") +
      (counts.KEPT ? `<span class="key"><mark class="KEPT">&nbsp;&nbsp;&nbsp;</mark> ${TYPE_LABEL.KEPT}: ${counts.KEPT}</span>` : "") +
      (sg.withheld ? `<span class="key"><mark class="evidence">text</mark> flagged text: withheld with the draft</span>` :
        `<span class="key"><mark class="evidence">text</mark> flagged text: ${$("col-seen").querySelectorAll("mark.evidence").length} of ${sg.flags.length} flag${sg.flags.length === 1 ? "" : "s"} located${(run.applied || []).length ? `, ${run.applied.length} rewritten` : ""}</span>`) +
      ((leak.unrestored || []).length ? `<span class="key"><mark class="unrestored">text</mark> unrestored fragment: ${leak.unrestored.length}</span>` : "");

    const d = $("decision"); d.className = "decision " + sg.decision;
    const privacyOk = !!leak.passed;
    const invented = leak.n_invented || 0;
    const baseline = screen.baseline_flags && screen.baseline_flags.length ? screen.baseline_flags.join(", ") : "none";
    const baselineName = screen.baseline_model ? "OpenAI moderation" : "harm classifier (not run)";
    const unrestoredTip = (leak.unrestored || []).length ? ` title="unrestored: ${esc(leak.unrestored.join(", "))}"` : "";
    const overridden = Object.keys(run.overrides).length;
    d.innerHTML = [
      `<span class="seg head">Decision: ${esc(sg.decision.toUpperCase())}${sg.withheld ? " · draft withheld" : ""}${overridden ? ` · ${overridden} flag${overridden === 1 ? "" : "s"} overridden by ${esc(sg.actor)}` : ""}</span>`,
      `<span class="seg">${sub.n_spans || 0} identifiers substituted · ${gen ? gen.rules.length : 0} generalised${sub.n_kept ? ` · ${sub.n_kept} kept as typed` : ""}</span>`,
      `<span class="seg ${privacyOk ? "ok" : "bad"}"${unrestoredTip}>${privacyOk ? "nothing original came back, every surrogate restored" : `privacy check: ${leak.n_echoed || 0} original echoed, ${leak.n_unrestored || 0} surrogate fragment${leak.n_unrestored === 1 ? "" : "s"} unrestored (marked in column 4)`}</span>`,
      invented ? `<span class="seg warn">${invented} identifier${invented === 1 ? "" : "s"} invented by the model (I13)</span>` : "",
      (reid.ambiguous_generalised || []).length ? `<span class="seg muted" title="${esc(reid.ambiguous_generalised.join(" | "))}">${reid.ambiguous_generalised.length} generalised phrase${reid.ambiguous_generalised.length === 1 ? "" : "s"} left as is (shared by two originals)</span>` : "",
      `<span class="seg ${sg.flags.length ? "warn" : "ok"}" title="Disclosure categories apply to an external audience. Auto reads the audience from your instruction; the selector above overrides it.">conduct screen: ${sg.flags.length} flag${sg.flags.length === 1 ? "" : "s"}${screen.audience ? ` (${screen.audience} audience${$("audience").value === "auto" ? ", read from the instruction" : ""})` : ""}</span>`,
      `<span class="seg muted" title="What a generic safety filter says about the same reply, for contrast">${esc(baselineName)}: ${esc(baseline)}</span>`,
    ].filter(Boolean).join("");
    $("glossary").textContent = DECISIONS[sg.decision] || "";

    // flag cards, each with its own override
    $("flags").innerHTML = sg.flags.map((f, i) => {
      const name = f.name || (window.TAXONOMY[f.label] || {}).name || f.label;
      const canOverride = f.severity !== "escalate";
      const ov = run.overrides[f.label];
      return `
      <div class="flag ${f.severity}" data-flag="${esc(f.label)}">
        <div class="flaghead">
          <h3>${esc(name)}</h3>
          <span class="pill ${f.severity}">${esc(f.severity)}</span>
          <span class="badge" title="taxonomy category">${esc(f.label)}</span>
          <span class="clause" title="${esc((window.TAXONOMY[f.label] || {}).clause_text || "")}">${/^[A-D]\.\d/.test(f.clause) ? "SASW Code clause " + esc(f.clause) : esc(f.clause)}</span>
          ${f.confidence != null ? `<span class="clause">judge confidence ${Math.round(f.confidence * 100)}%</span>` : ""}
        </div>
        ${f.reason ? `<p class="why">${esc(f.reason)}</p>` : ""}
        <div class="evidence"><span class="cap">Flagged text</span>${esc(f.evidence)}</div>
        ${f.rewrite ? `<div class="rewrite"><span class="cap">Suggested rewrite</span>${esc(f.rewrite)}<div class="rowbtn"><button type="button" class="secondary small accept" data-i="${i}">Use this rewrite</button><span class="status" id="accept-${i}"></span></div></div>` : ""}
        ${canOverride && !sg.withheld ? `<form class="flag-override" data-i="${i}" ${ov ? "hidden" : ""}>
          <label>Keep the draft despite this flag. Your reason is written to the ledger beside it, as typed and on this server only; do not put client details in it.
            <textarea rows="2" required placeholder="Reason for keeping it"></textarea></label>
          <button type="submit" class="secondary small">Record reason and keep</button>
        </form>` : ""}
        <div class="flagstate" id="flagstate-${i}">${ov ? esc(ov) : ""}</div>
      </div>`; }).join("");
    document.querySelectorAll("button.accept").forEach((b) => b.addEventListener("click", () => acceptRewrite(+b.dataset.i)));
    document.querySelectorAll("form.flag-override").forEach((f) => f.addEventListener("submit", (ev) => { ev.preventDefault(); overrideFlag(+f.dataset.i, f); }));

    const note = $("escalate-note");
    if (sg.withheld || sg.decision === "escalate") {
      note.hidden = false;
      note.innerHTML = `<strong>Escalated to supervisory review.</strong> ${sg.withheld ? "The draft is withheld from this screen and retained on this server for a supervisor to release." : "This flag cannot be overridden by the practitioner."} The escalation is in the ledger row below.`;
      $("release").hidden = !sg.withheld; $("released").hidden = true; $("release-status").textContent = "";
    } else { note.hidden = true; $("release").hidden = true; }
    const regen = $("regenerate");
    regen.hidden = !(sg.decision === "regenerate" || sg.decision === "annotate") || sg.withheld;
    $("closing").hidden = sg.flags.length > 0 || sg.withheld;

    renderLedger([{label: "this request", row: sg.ledger_row}].concat(run.extraRows || []));
    $("ledger-details").open = !!(run.extraRows && run.extraRows.length);
    renderRules(panel, sg);
    $("events").textContent = JSON.stringify(sg.events.map((e) => { const c = Object.assign({}, e); delete c.outbound_text; delete c.text; return c; }), null, 1);
  }

  function scrollAffordance() {
    document.querySelectorAll(".columns article").forEach((a) => {
      const pre = a.querySelector("pre"); let btn = a.querySelector(".more");
      if (!btn) { btn = document.createElement("button"); btn.type = "button"; btn.className = "secondary small more"; a.insertBefore(btn, a.querySelector(".hint")); }
      pre.classList.remove("expanded");
      const over = pre.scrollHeight > pre.clientHeight + 4;
      btn.hidden = !over;
      btn.textContent = "Show the full text";
      btn.onclick = () => { const x = pre.classList.toggle("expanded"); btn.textContent = x ? "Show less" : "Show the full text"; };
      a.classList.toggle("clipped", over);
    });
  }

  function compareList() {
    if (runs.list) return runs.list;
    if (runs.internal) return [{key: "internal", label: "Internal (case file)", run: runs.internal}, {key: "external", label: "External (employer)", run: runs.external}];
    return null;
  }
  function renderCompare() {
    const c = $("compare");
    const list = compareList();
    if (!list) { c.hidden = true; return; }
    const line = (item) => {
      const r = item.run;
      const flags = r.sg.flags.length ? r.sg.flags.map((f) => `${f.label} (${f.name || ""}, ${f.clause})`).join("; ") : "no conduct flag";
      return `<div class="cmp ${r.sg.decision}"><span class="cmplabel">${esc(item.label.replace(" (shown below)", ""))}</span><span class="cmpinstr">“${esc(r.instruction)}”</span><span class="cmpres">${esc(r.sg.decision.toUpperCase())} · ${esc(flags)}</span><button type="button" class="secondary small showrun" data-run="${item.key}" ${current === r ? "disabled" : ""}>${current === r ? "Shown below" : "Show this run"}</button></div>`;
    };
    c.hidden = false;
    c.innerHTML = `<div class="cmphead">${esc(runs.head || "Audience gate: the same note, one session (same surrogates), screened for two recipients. Disclosure categories (I10, I14) apply only to an external audience.")}</div>` + list.map(line).join("");
    const rows = list.map((it) => ({label: it.label.replace(" (shown below)", ""), row: it.run.sg.ledger_row}));
    c.querySelectorAll("button.showrun").forEach((b) => b.addEventListener("click", () => { const it = list.find((x) => x.key === b.dataset.run); show(it.run); scrollAffordance(); renderCompare(); }));
    renderLedger(rows.concat(current.extraRows || []));
  }

  const LEDGER_KEYS = [["ts", "Time"], ["decision", "Decision"], ["actor", "Actor"], ["actor_attested", "Actor attested"], ["pack", "Policy pack"], ["recipients", "Recipients of the pseudonymised text"], ["transfer_basis", "Transfer basis"], ["replayed_reply", "Recorded reply replayed"], ["payload_sha256", "Payload hash"], ["n_identifiers_substituted", "Identifiers substituted"], ["n_generalised", "Generalised"], ["leakcheck_passed", "Privacy check passed"], ["n_invented", "Invented by the model"], ["flags", "Flags"], ["withheld", "Draft withheld"], ["override_reason", "Reason"], ["request_row_sha256", "Refers to request row"], ["prev_sha256", "Previous row hash"], ["row_sha256", "This row hash"]];
  const short = (h) => (typeof h === "string" && /^[0-9a-f]{64}$/.test(h)) ? `<span title="${h}">${h.slice(0, 16)}…</span>` : esc(h);
  function renderLedger(items) {
    $("ledger").innerHTML = items.filter((x) => x && x.row).map(({label, row}) => `<div class="rowlabel">${esc(label)}</div><table class="row"><tbody>` + LEDGER_KEYS.filter(([k]) => row[k] !== undefined && row[k] !== null).map(([k, lab]) => {
      let v = row[k];
      if (k === "ts") v = esc(new Date(v * 1000).toISOString().replace("T", " ").slice(0, 19) + " UTC");
      else if (k === "recipients") v = esc(v.map((x) => `${x.role}: ${x.model}`).join(" · "));
      else if (Array.isArray(v)) v = esc(v.join(", "));
      else if (typeof v === "boolean") v = v ? "yes" : "no";
      else v = short(v);
      return `<tr><th>${esc(lab)}</th><td>${v}</td></tr>`; }).join("") + `</tbody></table>`).join("");
  }
  function addLedgerRow(label, row) {
    current.extraRows = (current.extraRows || []).concat([{label, row}]);
    const list = compareList();
    const base = list ? list.map((it) => ({label: it.label.replace(" (shown below)", ""), row: it.run.sg.ledger_row})) : [{label: "this request", row: current.sg.ledger_row}];
    renderLedger(base.concat(current.extraRows));
    $("ledger-details").open = true;
  }

  function renderRules(panel, sg) {
    const fired = panel.replacements.filter((r) => r.kind === "generalised");
    const kept = panel.replacements.filter((r) => r.kind === "kept");
    const sur = panel.replacements.filter((r) => r.kind === "surrogate");
    $("rules").innerHTML = (fired.length ? `<p>Generalised by the <strong>${esc(sg.pack)}</strong> pack (rule id · what you typed → what left):</p><ul>` +
      fired.map((r) => `<li><code>${esc(r.rule || "default")}</code> · <mark class="${r.type}">${esc(r.original)}</mark> → <em>${esc(r.outbound || "(removed)")}</em></li>`).join("") + "</ul>" : "<p>No generalisation rule fired on this note.</p>") +
      (kept.length ? `<p>Sensitive attributes detected but <strong>kept as typed</strong> because this pack has no rule for them: ${kept.map((r) => `<mark class="KEPT">${esc(r.original)}</mark>`).join(", ")}. Switch pack or add a rule to the YAML.</p>` : "") +
      `<p>${sur.length} direct identifier${sur.length === 1 ? "" : "s"} replaced by format-preserving surrogates (same script, same shape, different person). <a href="/v1/packs/${esc(sg.pack)}" target="_blank" rel="noopener">Open the pack</a>.</p>`;
  }

  function unrestore(text, panel) {
    let t = text || "";
    for (const r of [...panel.replacements].sort((a, b) => b.original.length - a.original.length)) {
      if (r.original && r.original.length > 1 && r.outbound) t = t.split(r.original).join(r.outbound);
    }
    return t;
  }

  // ---------- override, rewrite, regenerate ----------
  async function ledgerWrite(kind, labels, reason) {
    const draft_sha256 = await sha256($("col-seen").textContent);
    const r = await fetch("/v1/override", {method: "POST", headers: authHeaders({"X-SoCareGuard-Session-Token": current.sg.session_token}),
      body: JSON.stringify({session: current.sg.session, pack: current.sg.pack, flag_labels: labels, reason, kind, request_row_sha256: current.sg.ledger_row_sha256, draft_sha256})});
    const data = await r.json();
    if (!r.ok) throw new Error((data.error && data.error.message) || data.detail || r.statusText);
    return data;
  }
  async function overrideFlag(i, form) {
    const f = current.sg.flags[i]; const reason = form.querySelector("textarea").value;
    form.querySelector("button").disabled = true;
    try {
      const data = await ledgerWrite("override", [f.label], reason);
      current.overrides[f.label] = `Kept by ${data.ledger_row.actor}: ${reason} (ledger row ${data.ledger_row_sha256.slice(0, 12)}…)`;
      render(current);
      addLedgerRow(`override of ${f.label}`, data.ledger_row);
    } catch (e) { form.querySelector("button").disabled = false; $(`flagstate-${i}`).textContent = "Refused: " + e.message; }
  }
  async function acceptRewrite(i) {
    const f = current.sg.flags[i];
    if (!f || !f.rewrite) return;
    const seenPre = $("col-seen");
    let plain = seenPre.textContent;
    const whole = f.rewrite.length > 0.6 * plain.length || /^\s*(subject|dear)\b/i.test(f.rewrite);
    const found = whole ? [plain] : (plain.includes(f.evidence) ? [f.evidence] : pieces(f.evidence).filter((p) => plain.includes(p)));
    if (!found.length) { $(`accept-${i}`).textContent = "The flagged text is not verbatim in column 4, so nothing was changed or recorded; paste the rewrite yourself."; return; }
    if (whole) plain = f.rewrite;  // the judge rewrote the whole draft, so it replaces the whole draft
    else {
      // the first located fragment becomes the rewrite; every other located fragment is removed
      found.forEach((frag, k) => { plain = plain.split(frag).join(k === 0 ? f.rewrite : ""); });
      plain = plain.replace(/[ \t]{2,}/g, " ").replace(/\s+([.,;])/g, "$1");
    }
    current.data.choices[0].message.content = plain;
    current.applied = (current.applied || []).concat([f.rewrite]);
    render(current);
    const m = seenPre.querySelector("mark.rewrite");
    if (m) { seenPre.classList.add("expanded"); m.scrollIntoView({behavior: "smooth", block: "center"}); }
    try {
      const data = await ledgerWrite("rewrite_accepted", [f.label], "suggested rewrite applied in the panel");
      $(`accept-${i}`).textContent = whole ? "The rewrite replaced the whole draft in column 4 and was recorded in the ledger." : "Applied in column 4 and recorded in the ledger.";
      $(`flagstate-${i}`).textContent = "Rewrite applied.";
      addLedgerRow(`rewrite accepted for ${f.label}`, data.ledger_row);
    } catch (e) { $(`accept-${i}`).textContent = "Applied in column 4, but could not be recorded: " + e.message; }
  }
  $("release-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (!current || !current.sg.withheld) return;
    const btn = ev.target.querySelector("button"); btn.disabled = true;
    try {
      const h = authHeaders({"X-SoCareGuard-Role": "supervisor", "X-SoCareGuard-Actor": $("release-actor").value.trim()});
      const r = await fetch(`/v1/sessions/${current.sg.session}/withheld?reason=${encodeURIComponent($("release-reason").value)}`, {headers: h});
      const data = await r.json();
      if (!r.ok) throw new Error((data.error && data.error.message) || data.detail || r.statusText);
      $("released").hidden = false;
      $("released-text").innerHTML = markAll(data.reply, (data.flags || []).map((f) => ({text: f.evidence, label: "evidence", title: f.name || f.label, fuzzy: true})), "evidence");
      $("released-text").classList.add("expanded");
      $("release-status").textContent = `Released and recorded (row ${data.ledger_row.row_sha256.slice(0, 12)}…).`;
      current.released = {by: data.ledger_row.actor, flags: data.flags || []};
      const head = $("decision").querySelector(".seg.head");
      if (head) head.innerHTML += ` · released to ${esc(data.ledger_row.actor)}`;
      (data.flags || []).forEach((f, i) => {
        const card = document.querySelector(`.flag[data-flag="${f.label}"]`);
        if (!card) return;
        const ev = card.querySelector(".evidence"); if (ev) ev.innerHTML = `<span class="cap">Flagged text (supervisor view)</span>${esc(f.evidence)}`;
        if (f.rewrite && !card.querySelector(".rewrite")) ev.insertAdjacentHTML("afterend", `<div class="rewrite"><span class="cap">Suggested rewrite (supervisor view)</span>${esc(f.rewrite)}</div>`);
      });
      addLedgerRow("supervisor release", data.ledger_row);
    } catch (e) { $("release-status").textContent = "Refused: " + e.message; btn.disabled = false; }
  });
  $("regenerate").addEventListener("click", () => {
    if (!current) return;
    const asks = current.sg.flags.map((f) => `avoid ${(f.name || f.label).toLowerCase()}${f.rewrite ? ` (for example: "${f.rewrite}")` : ""}`);
    submit(current.instruction + "\n\nRevise the draft to " + asks.join("; ") + ". Do not add any detail that is not in the note.");
  });
})();
