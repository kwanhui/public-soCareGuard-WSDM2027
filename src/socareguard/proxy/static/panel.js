(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const KEPT_TITLE = "A detail that the policy packs leave as written, such as a public body or the recipient named in the instruction line, or one that this policy pack has no rule for";
  const TYPE_LABEL = {DIRECT: "identifier", QUASI: "detail that identifies someone when combined", ATTRIBUTE: "sensitive detail", KEPT: "kept as typed", evidence: "flagged text"};
  // The key above the columns; its first line names the technical term once, in parentheses.
  const LEGEND_LABEL = {DIRECT: "identifier, replaced by a stand-in", QUASI: "details that identify someone when combined (quasi-identifiers), generalised", ATTRIBUTE: "sensitive detail, generalised"};
  // One label per decision (docs/terminology.md). The four decisions are the paper's pass,
  // annotate, regenerate and escalate; "flagged" is the panel's word for the second, and its label
  // names the decision in parentheses.
  const DECISION_LABEL = {pass: "Pass", annotate: "Flagged (annotate)", regenerate: "Regenerate", escalate: "Escalate"};
  const DECISION_WORD = Object.fromEntries(Object.entries(DECISION_LABEL).map(([k, v]) => [k, v.toLowerCase()]));
  const DECISIONS = {
    pass: `${DECISION_LABEL.pass}: the screen raised no flag, so the draft in What you see is ready to use.`,
    annotate: `${DECISION_LABEL.annotate}: the draft can be used once each flag is dealt with. Use the rewrite, or keep the passage with a reason that goes into the record.`,
    regenerate: `${DECISION_LABEL.regenerate}: the screen asks for a new draft. Regenerate it, or keep each flagged passage with a reason.`,
    escalate: `${DECISION_LABEL.escalate}: the draft is withheld from this screen until a supervisor signs in, reviews it and releases it with a reason. It cannot be kept with a reason here.`,
  };
  // The result banner: one line saying what to do next and one filled button per decision.
  const BANNER = {
    pass: {next: "Nothing to flag. Copy the draft.", action: "Copy the draft"},
    annotate: {next: "Read each flag, then use the rewrite or keep the passage with a reason.", action: "Go to the first flag"},
    regenerate: {next: "Regenerate with the flags as instructions.", action: "Regenerate"},
    escalate: {next: "Give the session id to your supervisor, who signs in at the supervisor view to review and release it.", action: "Copy the session id"},
  };
  // The banner's title opens with the decision's label, so the decision is named as in the paper.
  function bannerTitle(sg) {
    const n = sg.flags.length, flags = `${n} flag${n === 1 ? "" : "s"}`;
    const label = DECISION_LABEL[sg.decision] || sg.decision;
    if (sg.decision === "pass") return `${label}. The draft passed the screen.`;
    if (sg.decision === "annotate") return `${label}. The screen raised ${flags} on this draft.`;
    if (sg.decision === "regenerate") return `${label}. The screen raised ${flags} that need a new draft.`;
    return `${label}. ` + (sg.withheld ? "The draft is withheld until a supervisor signs in and releases it." : `The screen raised ${flags} that only a supervisor can clear.`);
  }
  // A flag's default action from the policy pack, as the card's pill shows it.
  const SEVERITY_WORD = {annotate: `${DECISION_WORD.annotate}: read and decide`, regenerate: "regenerate: needs a new draft", escalate: "escalate: supervisor only"};
  // Headlines for flags that are not taxonomy categories.
  const PLAIN = {UNRESTORED: "A stand-in came back changed and was not restored"};
  const plainOf = (f) => ((window.TAXONOMY || {})[f.label] || {}).plain || PLAIN[f.label] || f.name || f.label;
  const recipientWord = (a) => String(a || "").replace("-", " ");
  const FLAG_LEGEND = "Clause codes refer to the SASW Code or to the statute named on the card. DV-n and similar codes are pack rules. Precision is measured on synthetic drafts (v1.3). Confidence is the screen's own estimate. Wording that the note itself uses may be echoed without a flag.";
  const BASELINE_CAPTION = "generic harm classifier, shown for contrast";
  let current = null;      // the run shown in the columns
  let runs = {};           // {internal, external} for the recipient check
  let loadedScenario = null;
  let compareWith = null;  // the internal instruction of a two-recipient scenario
  let reviewMode = false;  // a supervisor's read-only review page, where the release form is

  // ---------- scenario chips ----------
  // The pack hint says where the selector's value came from, so a pack set by a scenario never
  // carries over to the practitioner's own note without a visible line saying so.
  function packHint(text) { const h = $("pack-hint"); if (h) h.textContent = text; }
  function clearScenario() {
    document.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
    $("scenario-summary").hidden = true;
    if (loadedScenario) packHint(`Kept from the scenario: ${$("pack").value}. Check that it fits your note.`);
    loadedScenario = null; compareWith = null;
    $("replay-row").hidden = true; $("replay").checked = false;
    syncReplay();
  }
  document.querySelectorAll(".chip").forEach((b) => b.addEventListener("click", () => {
    const s = window.SCENARIOS.find((x) => x.id === b.dataset.scenario);
    if (!s) return;
    document.querySelectorAll(".chip").forEach((c) => c.classList.toggle("active", c === b));
    $("pack").value = s.pack; $("instruction").value = s.instruction; $("note").value = s.note;
    packHint(`Set by the scenario: ${s.pack}.`);
    loadedScenario = s;
    compareWith = s.compare_instruction || null;
    const sum = $("scenario-summary");
    sum.hidden = false;
    sum.textContent = (compareWith ? "Two runs of the same note in one session: first for the case file, then for the external recipient. " : "") + (s.summary || s.title);
    $("status").textContent = "Loaded: " + s.title;
    $("error").hidden = true;
    $("replay-row").hidden = !s.has_recording;
    $("replay").checked = !!s.has_recording;  // the recorded reply by default; untick for a live reply
    const recs = s.recordings || [];
    $("replay-model").innerHTML = recs.map((r) => `<option value="${esc(r.model)}">${esc(r.model)}, recorded ${esc(r.recorded_on)}</option>`).join("");
    $("replay-model-field").hidden = !recs.length;
    syncReplay();
    $("audience").value = "auto";
    syncSnippet();
  }));
  // In a replay no model provider is called: the reply comes from the recording chosen here, so
  // the drafting model selector does not apply until the box is unticked.
  function syncReplay() {
    const on = $("replay").checked && !!loadedScenario;
    $("model").disabled = on;
    $("replay-model").disabled = !on;
  }
  $("replay").addEventListener("change", syncReplay);
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
  $("pack").addEventListener("change", () => { syncSnippet(); packHint(`Chosen by you: ${$("pack").value}.`); }); $("actor").addEventListener("input", syncSnippet); syncSnippet();

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
  // A judge quote may be elided ("... "), joined with ";" or truncated. Each piece is matched on
  // its own. When none matches, the first sentence is matched loosely, and then each piece on its
  // first forty characters.
  const pieces = window.SoCareGuardRewrite.pieces;  // static/rewrite.js
  // When no piece matches exactly, the first sentence of the evidence is matched with any run of
  // spaces, line breaks or markdown marks between its words, ignoring case.
  function firstSentence(evidence) {
    const s = String(evidence || "").replace(/^\s*["“”']+/, "").split(/\s*(?:\.\.\.|…)\s*/)[0];
    const m = s.match(/^.*?[.!?:](?=\s|$)/);
    return (m ? m[0] : s).replace(/["“”']+$/, "").replace(/[.!?:]+$/, "").trim();
  }
  function looseFind(text, phrase) {
    const words = phrase.split(/\s+/).filter(Boolean).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    if (words.length < 3) return [];
    const m = new RegExp(words.join("[\\s*_#>]+"), "i").exec(text);
    return m ? [[m.index, m.index + m[0].length]] : [];
  }
  function markAll(text, needles, cls) {
    const spans = [];
    for (const n of needles) {
      if (!n.text || n.text.length < 2) continue;
      const cands = n.fuzzy ? pieces(n.text) : [n.text];
      let hits = [];
      for (const c of cands) hits = hits.concat(findAll(text, c, !n.fuzzy));
      if (!hits.length && n.fuzzy) hits = looseFind(text, firstSentence(n.text));
      if (!hits.length && n.fuzzy) for (const c of cands) if (c.length > 40) hits = hits.concat(findAll(text, c.slice(0, 40)));
      for (const [s, e] of hits) spans.push({start: s, end: e, label: n.label, title: n.title});
    }
    spans.sort((a, b) => a.start - b.start || (b.end - b.start) - (a.end - a.start));
    return highlight(text, spans, cls);
  }
  function md(h) {
    return h.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>").replace(/^(#{1,4})\s+(.+)$/gm, "<strong>$2</strong>");
  }
  function ruleTitle(r) {
    if (r.kind === "kept") return `${TYPE_LABEL.KEPT}: this ${r.category.replace("ATTR:", "").toLowerCase()} left as typed`;
    const what = r.kind === "generalised" ? "generalised" : r.kind === "derived" ? "another form of a stand-in" : "replaced by a stand-in";
    return `${TYPE_LABEL[r.type] || r.type} (${r.category.replace("ATTR:", "").toLowerCase()}): ${what}${r.rule ? " by rule " + r.rule : ""}`;
  }
  const cls = (r) => (r.kind === "kept" ? "KEPT" : r.type);
  const utc = (ts) => new Date(ts * 1000).toISOString().replace("T", " ").slice(0, 19) + " UTC";
  // The record marks a staff id as checked only when the request carried a configured key; an
  // unchecked id carries the ledger's "(self-asserted)" suffix, which the panel shows as "typed in".
  // A name that already ends in parentheses ("admin (sandbox login)") takes the qualifier inside
  // them: "admin (sandbox login, typed in)", never two pairs in a row.
  function actorLabel(actor, attested) {
    const base = String(actor || "unattributed").replace(/\s*\(self-asserted[^)]*\)\s*$/, "");
    const att = attested != null ? !!attested : !/\(self-asserted/.test(actor || "");
    const how = att ? "checked by a person" : "typed in";
    return /\)$/.test(base) ? `${base.slice(0, -1)}, ${how})` : `${base} (${how})`;
  }
  function unrestoredWords(leak) {
    const all = [].concat(leak.unrestored || [], leak.partial || []);
    return all.filter((w, k) => w && all.indexOf(w) === k).sort((a, b) => b.length - a.length);
  }
  function precisionText(label) {
    const p = ((window.PRECISION || {}).categories || {})[label];
    return p ? `measured precision on synthetic drafts ${p.precision.toFixed(2)} (${window.PRECISION.version})` : "";
  }

  // ---------- session tokens kept for this browser tab ----------
  // Each result's session token is kept in sessionStorage as {session id: token}, so a supervisor
  // review link opened in this browser shows the full view of the sessions this browser created.
  const TOKENS_KEY = "socareguard.sessionTokens";
  function readTokens() {
    try { return JSON.parse(sessionStorage.getItem(TOKENS_KEY) || "{}") || {}; } catch (e) { return {}; }
  }
  function keepToken(session, token) {
    if (!session || !token) return;
    try { const t = readTokens(); t[session] = token; sessionStorage.setItem(TOKENS_KEY, JSON.stringify(t)); } catch (e) { /* storage off: the review opens with stand-ins only */ }
  }

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
    if (opts.replay) { body.replay_scenario = opts.replay; if ($("replay-model").value) body.replay_model = $("replay-model").value; }
    const headers = authHeaders({"X-SoCareGuard-Pack": $("pack").value});
    if (opts.session) headers["X-SoCareGuard-Session"] = opts.session;
    const aud = opts.audience || $("audience").value;
    if (aud && aud !== "auto") headers["X-SoCareGuard-Audience"] = aud;
    const r = await fetch("/v1/chat/completions", {method: "POST", headers, body: JSON.stringify(body)});
    const data = await r.json();
    if (!r.ok) throw new Error((data.error && data.error.message) || data.detail || r.statusText);
    const sg = data.socareguard;
    keepToken(sg.session, sg.session_token);
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
        $("status").textContent = "Run 1 of 2 (for the case file): detecting, replacing, calling the model provider, screening… usually 5 to 20 seconds each on this sandbox.";
        runs.internal = await guarded(compareWith, note, {audience: "internal"});
      }
      $("status").textContent = (compareWith && !extraInstruction ? "Run 2 of 2 (for the external recipient): " : "") + (replay
        ? "Detecting, replacing, replaying the recorded reply, screening… usually 3 to 9 seconds on this sandbox, and longer for the first request after it wakes."
        : "Detecting, replacing, calling the model provider, screening… usually 5 to 20 seconds on this sandbox.");
      const prior = extraInstruction && current ? current : null;
      const ext = await guarded(instruction, note, {replay, session: runs.internal ? runs.internal.sg.session : (prior ? prior.sg.session : null), audience: runs.internal ? "external" : null});
      if (prior) { runs = {list: [{key: "first", label: "First draft", run: prior}, {key: "revised", label: "Revised draft (shown below)", run: ext}], head: "Regenerated in the same session (same stand-ins) with the flags as instructions."}; ext.regenerated = true; }
      else runs.external = ext;
      show(ext);
      renderCompare();
      res.hidden = false; res.removeAttribute("aria-busy");
      scrollAffordance();
      const rec = ext.sg.recording;
      $("status").textContent = `Done in ${ext.sg.latency_s} s${ext.sg.replayed ? ` (recorded reply from ${rec && rec.model ? rec.model : "the model"}${rec && rec.recorded_on ? `, recorded ${rec.recorded_on}` : ""}, replayed; the guard and the screen ran live${rec && rec.screened_with_recorded_note ? ", and the screen read the reply against the note that its model was given" : ""})` : ""}. Session ${ext.sg.session}.`;
      res.scrollIntoView({behavior: "smooth", block: "start"});
    } catch (e) {
      $("status").textContent = "";
      const err = $("error");
      err.hidden = false;
      err.innerHTML = `<strong>The request did not complete.</strong> ${esc(e.message)}<br><span class="muted">Nothing was drafted. Adjust the note or try again. The previous result has been cleared.</span>`;
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
    // Stand-ins left whole or in part: one list for What you see, the legend, the privacy segment
    // and the UNRESTORED card, so the counts agree.
    const unrestored = unrestoredWords(leak);

    $("col-typed").innerHTML = (run.regenerated ? `<em class="muted">Instruction revised by the panel for the regeneration:</em>\n` : "") + markAll(typed, shown.map((r) => ({text: r.original, label: cls(r), title: ruleTitle(r)})));
    $("col-out").innerHTML = markAll(send.outbound_text || "", shown.map((r) => ({text: r.outbound, label: cls(r), title: ruleTitle(r)})));
    const evidRaw = sg.flags.map((f) => ({text: unrestore(f.evidence, panel), label: "evidence", title: f.name || f.label, fuzzy: true}));
    $("col-back").innerHTML = sg.withheld ? `<span class="withheld">${esc(recv.text || "")}</span>` : markAll(recv.text || "", evidRaw, "evidence");
    // What you see: flagged text, generalised phrases that cannot come back or came back, unrestored fragments
    const seenMarks = sg.flags.map((f) => ({text: f.evidence, label: "evidence", title: f.name || f.label, fuzzy: true}));
    shown.filter((r) => r.kind === "generalised" && r.outbound && r.outbound.length > 3).forEach((r) => seenMarks.push({text: r.outbound, label: cls(r), title: `generalised on the way out and not restorable. The record says: ${r.original}`}));
    // A generalised phrase (a never-leak placeholder included) that the model repeated exactly is
    // restored to the record's wording, and is marked so that it does not read as the model's own.
    shown.filter((r) => r.kind === "generalised" && r.outbound && (recv.text || "").includes(r.outbound) && r.original)
      .forEach((r) => seenMarks.push({text: r.original, label: `${cls(r)} restored`, title: /\.never_leak$/.test(r.rule || "") ? "withheld outbound, restored here" : "generalised outbound, restored here"}));
    unrestored.forEach((u) => seenMarks.push({text: u, label: "unrestored", title: "part of a stand-in that the model reformatted. Check it against the case record before use."}));
    (run.applied || []).forEach((t) => seenMarks.push({text: t, label: "rewrite", title: "rewrite used"}));
    $("col-seen").innerHTML = sg.withheld
      ? `<span class="withheld">${esc(data.choices[0].message.content)}</span>`
      : markAll(data.choices[0].message.content, seenMarks);
    scrollAffordance();

    const restoredN = sg.withheld ? 0 : $("col-seen").querySelectorAll("mark.restored").length;
    const located = new Set(Array.from($("col-seen").querySelectorAll("mark.evidence")).map((m) => m.title)).size;
    const counts = {DIRECT: 0, QUASI: 0, ATTRIBUTE: 0, KEPT: 0};
    shown.forEach((r) => { counts[cls(r)] = (counts[cls(r)] || 0) + 1; });
    $("legend").innerHTML = ["DIRECT", "QUASI", "ATTRIBUTE"].map((t) => `<span class="key"><mark class="${t}">&nbsp;&nbsp;&nbsp;</mark> ${LEGEND_LABEL[t]}: ${counts[t] || 0}</span>`).join("") +
      (counts.KEPT ? `<span class="key" id="legend-kept" title="${KEPT_TITLE}"><mark class="KEPT">&nbsp;&nbsp;&nbsp;</mark> ${TYPE_LABEL.KEPT}: ${counts.KEPT}</span>` : "") +
      (sg.withheld ? `<span class="key"><mark class="evidence">text</mark> flagged text: withheld with the draft</span>` :
        `<span class="key"><mark class="evidence">text</mark> flagged text: ${located} of ${sg.flags.length} flag${sg.flags.length === 1 ? "" : "s"} located${located < sg.flags.length ? " (the flag card below quotes the full text)" : ""}${(run.applied || []).length ? `, ${run.applied.length} rewritten` : ""}</span>`) +
      (restoredN ? `<span class="key" id="legend-restored"><mark class="restored">text</mark> restored from the record: ${restoredN}</span>` : "") +
      (unrestored.length ? `<span class="key" id="legend-unrestored"><mark class="unrestored">text</mark> stand-in not restored: ${unrestored.length}</span>` : "");

    const d = $("decision"); d.className = "decision " + sg.decision;
    const privacyOk = !!leak.passed;
    const invented = leak.n_invented || 0;
    const baseline = screen.baseline_flags && screen.baseline_flags.length ? screen.baseline_flags.join(", ") : "none";
    const baselineName = screen.baseline_model ? "harm classifier" : "harm classifier (not run)";
    const unrestoredTip = unrestored.length ? ` title="not restored: ${esc(unrestored.join(", "))}"` : "";
    const overridden = Object.keys(run.overrides).length;
    const banner = BANNER[sg.decision] || BANNER.annotate;
    $("decision-title").textContent = bannerTitle(sg);
    $("decision-next").textContent = banner.next;
    const action = $("decision-action");
    action.textContent = banner.action; action.hidden = false; action.disabled = false;
    $("decision-action-status").textContent = "";
    // What needs checking before use, shown without opening "More".
    const warns = [];
    if (!privacyOk) warns.push(`Check before use: ${leak.n_echoed || 0} original detail${(leak.n_echoed || 0) === 1 ? "" : "s"} came back from the model provider and ${unrestored.length} stand-in${unrestored.length === 1 ? " was" : "s were"} not restored (marked in What you see).`);
    if (sg.pack_defaulted) warns.push("No policy pack was named on the request, so the deployment default ran.");
    $("decision-warn").hidden = !warns.length; $("decision-warn").textContent = warns.join(" ");
    $("decision-facts").innerHTML = [
      `<span class="seg head">Decision: ${esc(DECISION_WORD[sg.decision] || sg.decision)}${sg.withheld ? " · draft withheld" : ""}${overridden ? ` · ${overridden} flag${overridden === 1 ? "" : "s"} kept with a reason by ${esc(sg.actor)}` : ""}</span>`,
      `<span class="seg${sg.pack_defaulted ? " warn" : ""}" id="pack-seg"${sg.pack_defaulted ? ' title="No pack was named on the request, so the deployment default ran."' : ""}>pack: ${esc(sg.pack)}${sg.pack_defaulted ? " (default)" : ""}</span>`,
      `<span class="seg">${sub.n_spans || 0} identifiers replaced by stand-ins · ${gen ? gen.rules.length : 0} generalised${sub.n_kept ? ` · ${sub.n_kept} kept as typed` : ""}</span>`,
      `<span class="seg ${privacyOk ? "ok" : "bad"}"${unrestoredTip}>${privacyOk ? "nothing original came back, every stand-in restored" : `privacy check: ${leak.n_echoed || 0} original echoed, ${unrestored.length} stand-in${unrestored.length === 1 ? "" : "s"} not restored (marked in What you see)`}</span>`,
      invented ? `<span class="seg warn">${invented} identifier${invented === 1 ? "" : "s"} invented by the model (I13)</span>` : "",
      (reid.ambiguous_generalised || []).length ? `<span class="seg muted" title="${esc(reid.ambiguous_generalised.join(" | "))}">${reid.ambiguous_generalised.length} generalised phrase${reid.ambiguous_generalised.length === 1 ? "" : "s"} left as is (shared by two originals)</span>` : "",
      `<span class="seg ${sg.flags.length ? "warn" : "ok"}" title="Disclosure flags depend on the recipient. Auto reads the recipient from your instruction, and the Recipient field above sets it.">screen: ${sg.flags.length} flag${sg.flags.length === 1 ? "" : "s"}${screen.audience ? ` (recipient: ${esc(recipientWord(screen.audience))}${$("audience").value === "auto" ? ", read from the instruction" : ""})` : ""}</span>`,
      `<span class="seg muted" id="baseline-seg">${esc(baselineName)}: ${esc(baseline)} <span class="segcap">(${BASELINE_CAPTION})</span></span>`,
      `<span class="seg muted">actor: ${esc(actorLabel(sg.ledger_row.actor, sg.ledger_row.actor_attested))}</span>`,
    ].filter(Boolean).join("");
    $("ledgersum").textContent = `Record: actor: ${actorLabel(sg.ledger_row.actor, sg.ledger_row.actor_attested)} · transfer basis: ${sg.ledger_row.transfer_basis || "not recorded"}`;
    $("glossary").textContent = DECISIONS[sg.decision] || "";

    // flag cards: a plain-words headline, the clause and both numbers on one line under it, and
    // one main button (the rewrite when there is one, else keeping the passage with a reason)
    const version = (window.PRECISION || {}).version || "";
    $("flags").innerHTML = (sg.flags.length ? `<p class="flaglegend" id="flag-legend">${esc(FLAG_LEGEND)}</p>` : "") + sg.flags.map((f, i) => {
      const cat = (window.TAXONOMY || {})[f.label] || {};
      const canOverride = f.severity !== "escalate";
      const ov = run.overrides[f.label];
      // An unrestored stand-in is an invented name or place in the draft: shown at Major
      // severity, with every unrestored string listed.
      const isUnrestored = f.label === "UNRESTORED";
      const nums = [f.confidence != null ? `the screen's own confidence ${f.confidence.toFixed(2)}` : "", precisionText(f.label)].filter(Boolean).join("; ");
      return `
      <div class="flag ${f.severity}${isUnrestored ? " major" : ""}" data-flag="${esc(f.label)}" id="flag-${i}" tabindex="-1">
        <div class="flaghead">
          <h3>${esc(plainOf(f))}</h3>
          <span class="pill ${isUnrestored ? "major" : f.severity}">${isUnrestored ? "major: replace before use" : esc(SEVERITY_WORD[f.severity] || f.severity)}</span>
        </div>
        <p class="flag-meta">
          <span class="badge" title="${esc(cat.name || "category of the draft taxonomy")}">${esc(f.label)}</span>
          <span class="clause" title="${esc(cat.clause_text || "")}">${/^[A-D]\.\d/.test(f.clause) ? "SASW Code clause " + esc(f.clause) : esc(f.clause)}</span>
          ${nums ? `<span class="clause" title="The screen's own confidence is the model's score for this flag. Measured precision is the share of this category's flags that matched the label on 600 labelled synthetic drafts (results-${esc(version)}, docs/metrics.md).">${esc(nums)}</span>` : ""}
          <span class="draftnote">Draft taxonomy, not yet practitioner-reviewed</span>
        </p>
        ${f.reason ? `<p class="why">${esc(f.reason)}</p>` : ""}
        ${isUnrestored && unrestored.length ? `<div class="unrestored-list"><span class="cap">Not restored in What you see (${unrestored.length})</span><ul>${unrestored.map((u) => `<li><mark class="unrestored">${esc(u)}</mark></li>`).join("")}</ul>Replace each from the case record before using the draft.</div>` : ""}
        <div class="evidence"><span class="cap">Flagged text</span>${esc(f.evidence)}</div>
        ${f.rewrite ? `<div class="rewrite"><span class="cap">Suggested rewrite</span>${esc(f.rewrite)}<div class="rowbtn"><button type="button" class="btn-card accept" data-i="${i}">Use this rewrite</button><span class="status" id="accept-${i}"></span></div><p class="flag-note">Using it changes the draft in What you see, and your choice goes into the record.</p><div class="manual-rewrite" id="manual-${i}" hidden></div></div>` : ""}
        ${canOverride && !sg.withheld ? `<form class="flag-override${f.rewrite ? " demoted" : ""}" data-i="${i}" ${ov ? "hidden" : ""}><details>
          <summary class="${f.rewrite ? "btn-quiet" : "btn-card"}">Keep with a reason</summary>
          <label>Keep the passage despite this flag. Your reason goes into the record beside it, as typed and on this server only. Do not put client details in it.
            <textarea rows="2" required placeholder="Reason for keeping the passage"></textarea></label>
          <button type="submit" class="secondary small">Keep and record the reason</button>
        </details></form>` : ""}
        <div class="flagstate" id="flagstate-${i}">${ov ? esc(ov) : ""}</div>
      </div>`; }).join("");
    document.querySelectorAll("button.accept").forEach((b) => b.addEventListener("click", () => acceptRewrite(+b.dataset.i)));
    document.querySelectorAll("form.flag-override").forEach((f) => f.addEventListener("submit", (ev) => { ev.preventDefault(); overrideFlag(+f.dataset.i, f); }));

    const note = $("escalate-note");
    if (sg.withheld || sg.decision === "escalate") {
      note.hidden = false;
      note.innerHTML = `<p><strong>Sent to a supervisor.</strong> ${sg.withheld ? "The draft is kept on this server and is not shown here until a supervisor releases it." : "This flag cannot be kept with a reason here."} The escalation is in the record below.</p>` +
        `<div class="sessionid" id="escalate-session"><span>Session id</span><code id="esc-session">${esc(sg.session)}</code><button type="button" class="secondary small" id="copy-session">Copy</button><span id="copy-status" class="status" role="status"></span></div>` +
        (sg.withheld && !reviewMode ? `<p id="escalate-next">Only a signed-in supervisor can release it. Your supervisor signs in at the <a href="/supervisor" id="escalate-supervisor-link">supervisor view</a>, opens this session from the queue under "Needs your release", reviews it and releases it with a reason. There is no release on this panel.</p>` : "");
      $("copy-session").addEventListener("click", async () => { $("copy-status").textContent = await copyText(sg.session, $("esc-session")); });
      // The release form is shown only on a supervisor's review page (readOnly), after sign-in.
      $("release").hidden = true; $("released").hidden = true; $("release-status").textContent = ""; $("release-prior").hidden = true;
      $("release-confirm").hidden = true;
    } else { note.hidden = true; $("release").hidden = true; }
    const regen = $("regenerate");
    regen.hidden = sg.decision !== "annotate" || sg.withheld;
    $("closing").hidden = sg.flags.length > 0 || sg.withheld;
    renderRecordedRef(run);

    renderLedger([{label: "this request", row: sg.ledger_row}].concat(run.extraRows || []));
    $("ledger-details").open = !!(run.extraRows && run.extraRows.length);
    renderRules(panel, sg);
    $("events").textContent = JSON.stringify(sg.events.map((e) => { const c = Object.assign({}, e); delete c.outbound_text; delete c.text; return c; }), null, 1);
    $("events-tag").textContent = `${sg.events.length} event${sg.events.length === 1 ? "" : "s"}`;
  }

  // The screen's verdict in a recorded run of the scenario (UC3), shown beside a replay as a
  // labelled reference. It is a record of that run, never this run's result.
  function renderRecordedRef(run) {
    const box = $("recorded-ref");
    const ref = run.sg.replayed && loadedScenario && loadedScenario.recorded_screen;
    if (!ref || !(ref.flags || []).length) { box.hidden = true; box.innerHTML = ""; return; }
    const now = new Set(run.sg.flags.map((f) => f.label));
    const missing = ref.flags.filter((f) => !now.has(f.label)).map((f) => f.label);
    box.hidden = false;
    box.innerHTML = `<span class="cap">For reference: the recorded run of ${esc(ref.recorded_on)}</span>` +
      `<p>${esc(ref.what)} The screen's decision there was ${esc(DECISION_WORD[ref.decision] || ref.decision)}, with these flags:</p><ul>` +
      ref.flags.map((f) => `<li><span class="badge">${esc(f.label)}</span> ${esc(plainOf(f))}, SASW Code clause ${esc(f.clause)}, the screen's own confidence ${Number(f.confidence).toFixed(2)}. Flagged text: “${esc(String(f.evidence).replace(/[.]\s*$/, ""))}”${f.rewrite ? `. Suggested rewrite: “${esc(String(f.rewrite).replace(/[.]\s*$/, ""))}”` : ""}.</li>`).join("") +
      `</ul><p class="hint">This is a record of that run, not the result of this request. The screen runs live here and its flags can differ between runs${missing.length ? `: this run did not raise ${esc(missing.join(" or "))}` : ""}.</p>`;
  }

  // Copy to the clipboard; without clipboard access, select the text for Ctrl+C.
  async function copyText(text, el) {
    try { await navigator.clipboard.writeText(text); return "Copied."; }
    catch (e) {
      if (!el) return "Copying is blocked in this browser.";
      const r = document.createRange(); r.selectNodeContents(el); const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(r);
      return "Selected; press Ctrl+C.";
    }
  }
  $("decision-action").addEventListener("click", async () => {
    if (!current) return;
    const k = current.sg.decision, st = $("decision-action-status");
    if (k === "annotate") {
      const card = document.querySelector("#flags .flag");
      if (card) { card.scrollIntoView({behavior: "smooth", block: "start"}); card.focus({preventScroll: true}); }
      return;
    }
    if (k === "regenerate") { $("regenerate").click(); return; }
    if (k === "escalate" && current.released) { st.textContent = await copyText($("released-text").textContent, $("released-text")); return; }
    if (k === "escalate") { st.textContent = await copyText(current.sg.session, $("esc-session")); return; }
    st.textContent = await copyText($("col-seen").textContent, $("col-seen"));
  });

  function scrollAffordance() {
    document.querySelectorAll(".columns article").forEach((a) => {
      const pre = a.querySelector("pre"); let btn = a.querySelector("button.more");
      if (!btn) { const hint = a.querySelector(".hint"); btn = document.createElement("button"); btn.type = "button"; btn.className = "secondary small more"; hint.parentNode.insertBefore(btn, hint); }
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
    if (runs.internal) return [{key: "internal", label: "For the case file", run: runs.internal}, {key: "external", label: "For the employer", run: runs.external}];
    return null;
  }
  function renderCompare() {
    const c = $("compare");
    const list = compareList();
    if (!list) { c.hidden = true; return; }
    const line = (item) => {
      const r = item.run;
      const flags = r.sg.flags.length ? r.sg.flags.map((f) => `${f.label} (${plainOf(f)}, ${f.clause})`).join("; ") : "no flag";
      return `<div class="cmp ${r.sg.decision}"><span class="cmplabel">${esc(item.label.replace(" (shown below)", ""))}</span><span class="cmpinstr">“${esc(r.instruction)}”</span><span class="cmpres">${esc(DECISION_WORD[r.sg.decision] || r.sg.decision)} · ${esc(flags)}</span><button type="button" class="secondary small showrun" data-run="${item.key}" ${current === r ? "disabled" : ""}>${current === r ? "Shown below" : "Show this run"}</button></div>`;
    };
    c.hidden = false;
    c.innerHTML = `<div class="cmphead">${esc(runs.head || "Recipient check: the same note, in one session with the same stand-ins, screened for two recipients. Disclosure flags (I10, I14) apply only to a recipient outside the agency.")}</div>` + list.map(line).join("");
    const rows = list.map((it) => ({label: it.label.replace(" (shown below)", ""), row: it.run.sg.ledger_row}));
    c.querySelectorAll("button.showrun").forEach((b) => b.addEventListener("click", () => { const it = list.find((x) => x.key === b.dataset.run); show(it.run); scrollAffordance(); renderCompare(); }));
    renderLedger(rows.concat(current.extraRows || []));
  }

  const LEDGER_KEYS = [["ts", "Time"], ["decision", "Decision"], ["actor", "Actor"], ["actor_attested", "Checked by a person"], ["pack", "Policy pack"], ["recipients", "Recipients of what left the premises"], ["transfer_basis", "Transfer basis"], ["replayed_reply", "Recorded reply replayed"], ["payload_sha256", "Hash of what left"], ["n_identifiers_substituted", "Identifiers replaced by stand-ins"], ["n_generalised", "Generalised"], ["leakcheck_passed", "Privacy check passed"], ["n_invented", "Invented by the model"], ["flags", "Flags"], ["withheld", "Draft withheld"], ["override_reason", "Reason"], ["request_row_sha256", "Refers to the request row"], ["prior_release_row_sha256", "Earlier release rows"], ["seq", "Row number"], ["prev_sha256", "Previous row hash"], ["row_sha256", "This row hash"]];
  // Row kinds in words; the ledger's own names stay in the data.
  const ROW_DECISION = {pass: DECISION_WORD.pass, annotate: DECISION_WORD.annotate, regenerate: DECISION_WORD.regenerate, escalate: DECISION_WORD.escalate, override: "kept with a reason", rewrite_accepted: "rewrite used", withheld_released: "supervisor release", review_opened: "review opened", session_purged: "session purged"};
  const short = (h) => (typeof h === "string" && /^[0-9a-f]{64}$/.test(h)) ? `<span title="${h}">${h.slice(0, 16)}…</span>` : esc(h);
  function renderLedger(items) {
    const n = items.filter((x) => x && x.row).length;
    $("ledger-tag").textContent = `${n} row${n === 1 ? "" : "s"}`;
    chainTag(n);
    $("ledger").innerHTML = items.filter((x) => x && x.row).map(({label, row}) => `<div class="rowlabel">${esc(label)}${row.actor ? ` · actor: ${esc(actorLabel(row.actor, row.actor_attested))}` : ""}</div><table class="row"><tbody>` + LEDGER_KEYS.filter(([k]) => row[k] !== undefined && row[k] !== null).map(([k, lab]) => {
      let v = row[k];
      if (k === "ts") v = esc(utc(v));
      else if (k === "actor") v = esc(actorLabel(v, row.actor_attested));
      else if (k === "decision") v = esc(ROW_DECISION[v] || v);
      else if (k === "recipients") v = esc(v.map((x) => `${x.role}: ${x.model}`).join(" · "));
      else if (Array.isArray(v)) v = v.every((x) => typeof x === "string" && /^[0-9a-f]{64}$/.test(x)) ? v.map(short).join(", ") : esc(v.join(", "));
      else if (typeof v === "boolean") v = v ? "yes" : "no";
      else v = short(v);
      return `<tr><th>${esc(lab)}</th><td>${v}</td></tr>`; }).join("") + `</tbody></table>`).join("");
  }
  // The status tag of the record's summary: the rows shown here, and the chain check when this
  // browser may call it.
  let chainSeq = 0;
  async function chainTag(n) {
    const mine = ++chainSeq;
    try {
      const r = await fetch("/v1/ledger/verify", {headers: authHeaders()});
      if (!r.ok || mine !== chainSeq) return;
      const v = await r.json();
      $("ledger-tag").textContent = `${n} row${n === 1 ? "" : "s"}, ${v.ok ? "record not altered, no gaps" : "record altered or with a gap"}`;
    } catch (e) { /* the tag keeps the row count */ }
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
    $("rules-tag").textContent = `${fired.length} rule${fired.length === 1 ? "" : "s"} fired`;
    $("rules").innerHTML = (fired.length ? `<p>Generalised by the <strong>${esc(sg.pack)}</strong> pack (rule id · what you typed → what left):</p><ul>` +
      fired.map((r) => `<li><code>${esc(r.rule || "default")}</code> · <mark class="${r.type}">${esc(r.original)}</mark> → <em>${esc(r.outbound || "(removed)")}</em></li>`).join("") + "</ul>" : "<p>No generalisation rule fired on this note.</p>") +
      (kept.length ? `<p>Details detected but <strong>kept as typed</strong> (a public body, the recipient named in the instruction line, or a detail that this policy pack has no rule for): ${kept.map((r) => `<mark class="KEPT">${esc(r.original)}</mark>`).join(", ")}. If one of them should be generalised, switch pack or add a rule to the YAML.</p>` : "") +
      `<p>${sur.length} identifier${sur.length === 1 ? "" : "s"} replaced by stand-ins of the same shape (same script and format, a different person). <a href="/packs/${esc(sg.pack)}" target="_blank" rel="noopener">Open the pack</a>.</p>`;
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
      current.overrides[f.label] = `Kept by ${actorLabel(data.ledger_row.actor, data.ledger_row.actor_attested)}: ${reason} (record row ${data.ledger_row_sha256.slice(0, 12)}…)`;
      render(current);
      addLedgerRow(`kept with a reason: ${f.label}`, data.ledger_row);
    } catch (e) { form.querySelector("button").disabled = false; $(`flagstate-${i}`).textContent = "Refused: " + e.message; }
  }
  async function acceptRewrite(i) {
    const f = current.sg.flags[i];
    if (!f || !f.rewrite) return;
    const seenPre = $("col-seen");
    const out = window.SoCareGuardRewrite.applyRewrite(seenPre.textContent, f.evidence, f.rewrite);
    if (out.status === "not_found") {
      // Nothing is appended: the practitioner places the rewrite by hand.
      const box = $(`manual-${i}`);
      box.hidden = false;
      box.innerHTML = `<span class="cap">Place this rewrite yourself</span><pre>${esc(f.rewrite)}</pre>`;
      $(`accept-${i}`).textContent = "The flagged text is not verbatim in What you see, so nothing was changed or recorded. Copy the rewrite below into the draft where it belongs.";
      return;
    }
    current.data.choices[0].message.content = out.text;
    if (out.status === "whole" || out.inserted) current.applied = (current.applied || []).concat([out.status === "whole" ? f.rewrite : out.inserted]);
    render(current);
    const m = seenPre.querySelector("mark.rewrite");
    if (m) { seenPre.classList.add("expanded"); m.scrollIntoView({behavior: "smooth", block: "center"}); }
    const n = out.dropped.length;
    const left = n ? ` ${n} sentence${n === 1 ? "" : "s"} of the rewrite ${n === 1 ? "was" : "were"} left out because the draft already says ${n === 1 ? "it" : "them"}.` : "";
    try {
      const data = await ledgerWrite("rewrite_accepted", [f.label], "suggested rewrite applied in the panel");
      $(`accept-${i}`).textContent = (out.status === "whole" ? "The rewrite replaced the whole draft in What you see and went into the record." : "Used in place in What you see and recorded.") + left;
      $(`flagstate-${i}`).textContent = "Rewrite used.";
      addLedgerRow(`rewrite used: ${f.label}`, data.ledger_row);
    } catch (e) { $(`accept-${i}`).textContent = "Used in What you see, but it could not be recorded: " + e.message; }
  }
  // The release asks for a confirmation first: the submit button shows #release-confirm, and
  // "Yes, release it" submits the form again with the confirmation given.
  let releaseConfirmed = false;
  $("release-confirm-yes").addEventListener("click", () => { releaseConfirmed = true; $("release-confirm").hidden = true; $("release-form").requestSubmit(); });
  $("release-confirm-no").addEventListener("click", () => { $("release-confirm").hidden = true; $("release-form").querySelector("button[type=submit]").focus(); });
  $("release-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (!current || !current.sg.withheld) return;
    if (!releaseConfirmed) {
      $("release-confirm-who").textContent = $("release-actor").value.trim();
      $("release-confirm").hidden = false;
      $("release-status").textContent = "";
      $("release-confirm-yes").focus();
      return;
    }
    const btn = ev.target.querySelector("button[type=submit]"); btn.disabled = true;
    try {
      // The supervisor's sign-in (the cookie, or a supervisor key) is what the server checks; the
      // session token is sent only when this browser has it, for the restored view of the draft.
      const extra = {"X-SoCareGuard-Actor": $("release-actor").value.trim()};
      if (current.sg.session_token) extra["X-SoCareGuard-Session-Token"] = current.sg.session_token;
      const h = authHeaders(extra);
      const r = await fetch(`/v1/sessions/${current.sg.session}/withheld?reason=${encodeURIComponent($("release-reason").value)}`, {headers: h});
      const data = await r.json();
      if (!r.ok) throw new Error((data.error && data.error.message) || data.detail || r.statusText);
      $("released").hidden = false;
      $("released-text").innerHTML = markAll(data.reply, (data.flags || []).map((f) => ({text: f.evidence, label: "evidence", title: f.name || f.label, fuzzy: true})), "evidence");
      $("released-text").classList.add("expanded");
      $("released-note").hidden = data.view !== "pseudonymised";
      $("release-status").textContent = `Released and recorded (row ${data.ledger_row.row_sha256.slice(0, 12)}…).`;
      const prior = data.prior_releases || [];
      $("release-prior").hidden = !prior.length;
      $("release-prior").textContent = prior.map((x) => `Released earlier by ${actorLabel(x.actor, x.actor_attested)}, ${x.ts ? utc(x.ts) : "time not recorded"}.`).join(" ");
      current.released = {by: data.ledger_row.actor, flags: data.flags || []};
      const head = $("decision").querySelector(".seg.head");
      if (head) head.innerHTML += ` · released to ${esc(data.ledger_row.actor)}`;
      $("decision-title").textContent = `The draft was released to ${actorLabel(data.ledger_row.actor, data.ledger_row.actor_attested)} and recorded.`;
      $("decision-next").textContent = "The released draft is shown below the release form.";
      $("decision-action").textContent = "Copy the released draft";
      (data.flags || []).forEach((f, i) => {
        const card = document.querySelector(`.flag[data-flag="${f.label}"]`);
        if (!card) return;
        const ev = card.querySelector(".evidence"); if (ev) ev.innerHTML = `<span class="cap">Flagged text (supervisor view)</span>${esc(f.evidence)}`;
        if (f.rewrite && !card.querySelector(".rewrite")) ev.insertAdjacentHTML("afterend", `<div class="rewrite"><span class="cap">Suggested rewrite (supervisor view)</span>${esc(f.rewrite)}</div>`);
      });
      addLedgerRow("supervisor release", data.ledger_row);
    } catch (e) { $("release-status").textContent = "Refused: " + e.message; }
    finally { btn.disabled = false; releaseConfirmed = false; }  // a supervisor may record a second release (a handoff or a correction)
  });
  // ---------- read-only review (a supervisor's review link: /?session=<id>&review=<token>) ----------
  const REVIEW_ROW_LABELS = {override: "kept with a reason", rewrite_accepted: "rewrite used", withheld_released: "supervisor release", review_opened: "review opened", session_purged: "session purged"};
  function rebuildTyped(outText, replacements) {
    let t = outText;
    for (const r of replacements.filter((x) => x.kind !== "derived" && x.original && x.outbound && x.original !== x.outbound).sort((a, b) => b.outbound.length - a.outbound.length)) {
      t = t.split(r.outbound).join(r.original);
    }
    return t;
  }
  async function openReview(session, review) {
    const own = readTokens()[session];
    const headers = {"X-SoCareGuard-Review-Token": review};
    if (own) headers["X-SoCareGuard-Session-Token"] = own;
    const get = async (url) => {
      const r = await fetch(url, {headers});
      const d = await r.json();
      if (!r.ok) throw new Error((d.error && d.error.message) || d.detail || r.statusText);
      return d;
    };
    const id = encodeURIComponent(session);
    const s = await get(`/v1/sessions/${id}`);
    const p = await get(`/v1/sessions/${id}/panel`);
    const l = await get(`/v1/ledger?session=${id}&limit=500`);
    const full = s.view === "full";
    const replacements = full ? p.replacements : (p.marks || []).map((m) => Object.assign({original: ""}, m));
    const row = s.ledger_row || {};
    const sg = {session, session_token: own || "", pack: s.pack, pack_defaulted: false, actor: row.actor, decision: s.decision, withheld: s.withheld,
      flags: s.flags, events: s.events, ledger_row: row, ledger_row_sha256: row.row_sha256, replayed: !!row.replayed_reply};
    const send = s.events.find((e) => e.kind === "send") || {};
    const extraRows = (l.rows || []).filter((r) => r.row_sha256 !== row.row_sha256 && r.decision !== "escalate" && REVIEW_ROW_LABELS[r.decision])
      .map((r) => ({label: REVIEW_ROW_LABELS[r.decision], row: r}));
    const run = {data: {choices: [{message: {content: full ? (s.reply || "") : ""}}]}, sg, panel: {replacements}, instruction: "",
      typed: full ? rebuildTyped(send.outbound_text || "", replacements) : "", overrides: {}, extraRows};
    runs = {};
    reviewMode = true;
    show(run);
    readOnly(session, full);
  }
  function readOnly(session, full) {
    const note = $("review-note");
    note.hidden = false;
    note.textContent = full
      ? `Read-only review of session ${session}. Nothing on this page can be changed. What you typed is rebuilt from what left the premises and the identity map.`
      : `Read-only review of session ${session}, with stand-ins only. This browser did not create the session, so what was typed and the restored draft are not shown.`;
    document.querySelector("section.compose").hidden = true;
    if (!full) {
      ["col-typed", "col-seen"].forEach((c) => { $(c).innerHTML = ""; $(c).closest("article").hidden = true; });
      $("closing").hidden = true;
      $("glossary").textContent = "";
      $("col-back-details").open = true;  // the reply with stand-ins is what this view can show
    }
    // A signed-in supervisor (the page is told by the server) may release a withheld draft here.
    const sup = window.SOCAREGUARD_SUPERVISOR;
    const canRelease = !!(sup && current && current.sg.withheld);
    $("decision-next").textContent = canRelease
      ? "This is a read-only review. As a signed-in supervisor you can release the withheld draft with a reason, below the flags."
      : "This is a read-only review. Nothing here can be changed.";
    $("decision-action").hidden = true;
    $("release").hidden = !canRelease;
    $("regenerate").hidden = true;
    document.querySelectorAll("form.flag-override").forEach((f) => { f.hidden = true; });
    document.querySelectorAll("#result button:not(.more), #result input, #result textarea, #result select, #compose button, #compose input, #compose select, #compose textarea")
      .forEach((el) => { if (!(canRelease && el.closest("#release"))) el.disabled = true; });
    if (canRelease) {
      const who = $("release-signed-in");
      who.hidden = false;
      who.textContent = `Signed in as ${actorLabel(sup.actor, sup.attested)}. The release goes into the record under this name, and the draft leaves the queue in the supervisor view.`;
      $("release-actor").value = sup.actor;
      $("release-actor").readOnly = true;
    }
    $("result").hidden = false; $("result").removeAttribute("aria-busy");
    $("ledger-details").open = true;
    scrollAffordance();
  }
  const reviewParams = new URLSearchParams(window.location.search);
  if (reviewParams.get("session") && reviewParams.get("review")) {
    openReview(reviewParams.get("session"), reviewParams.get("review")).catch((e) => {
      const err = $("error");
      err.hidden = false;
      err.innerHTML = `<strong>The review link did not open.</strong> ${esc(e.message)}<br><span class="muted">A review link lasts 30 minutes. Ask for a new one from the supervisor view.</span>`;
    });
  }

  $("regenerate").addEventListener("click", () => {
    if (!current) return;
    const asks = current.sg.flags.map((f) => `avoid ${(f.name || f.label).toLowerCase()}${f.rewrite ? ` (for example: "${f.rewrite}")` : ""}`);
    submit(current.instruction + "\n\nRevise the draft to " + asks.join("; ") + ". Do not add any detail that is not in the note.");
  });
})();
