(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  let current = null;

  document.querySelectorAll(".chip").forEach((b) => b.addEventListener("click", () => {
    const s = window.SCENARIOS.find((x) => x.id === b.dataset.scenario);
    if (!s) return;
    $("pack").value = s.pack; $("instruction").value = s.instruction; $("note").value = s.note;
    $("status").textContent = "Loaded " + s.title;
  }));

  function highlight(text, spans, cls) {
    // spans: [{start,end,label}] on this text; non-overlapping, sorted
    let out = "", pos = 0;
    for (const sp of spans) {
      if (sp.start < pos) continue;
      out += esc(text.slice(pos, sp.start)) + `<mark class="${cls || sp.label}" title="${esc(sp.title || sp.label)}">` + esc(text.slice(sp.start, sp.end)) + "</mark>";
      pos = sp.end;
    }
    return out + esc(text.slice(pos));
  }

  function markAll(text, needles, cls) {
    const spans = [];
    for (const n of needles) {
      if (!n.text || n.text.length < 2) continue;
      let i = text.indexOf(n.text);
      while (i >= 0) { spans.push({start: i, end: i + n.text.length, label: n.label, title: n.title}); i = text.indexOf(n.text, i + n.text.length); }
    }
    spans.sort((a, b) => a.start - b.start);
    return highlight(text, spans, cls);
  }

  $("compose").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    $("send").disabled = true; $("status").textContent = "Detecting, substituting, calling the model, screening…";
    const body = {model: $("model").value, messages: [{role: "user", content: $("instruction").value + "\n\n" + $("note").value}]};
    try {
      const r = await fetch("/v1/chat/completions", {method: "POST", headers: {"Content-Type": "application/json", "X-SoCareGuard-Pack": $("pack").value}, body: JSON.stringify(body)});
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || r.statusText);
      const sg = data.socareguard;
      const panel = await (await fetch(`/v1/sessions/${sg.session}/panel`)).json();
      current = {sg, panel, pack: $("pack").value};
      render(data, sg, panel);
      $("status").textContent = `Done in ${sg.latency_s}s. Ledger row ${sg.ledger_row_sha256.slice(0, 12)}…`;
    } catch (e) {
      $("status").textContent = "Error: " + e.message;
    } finally { $("send").disabled = false; }
  });

  function render(data, sg, panel) {
    $("result").hidden = false;
    const send = sg.events.find((e) => e.kind === "send");
    const recv = sg.events.find((e) => e.kind === "receive");
    const typed = $("instruction").value + "\n\n" + $("note").value;
    const typedMarks = panel.replacements.map((r) => ({text: r.original, label: r.type, title: `${r.category} → ${r.kind}`}));
    $("col-typed").innerHTML = markAll(typed, typedMarks);
    const outMarks = panel.replacements.map((r) => ({text: r.outbound, label: r.type, title: `${r.category}: ${r.kind}`}));
    $("col-out").innerHTML = markAll(send.outbound_text || "", outMarks);
    const evid = sg.flags.map((f) => ({text: f.evidence, label: "evidence", title: f.label}));
    $("col-back").innerHTML = markAll(recv.text || "", evid, "evidence");
    const restoredEvid = sg.flags.map((f) => ({text: panelRestore(f.evidence, panel), label: "evidence", title: f.label}));
    $("col-seen").innerHTML = markAll(data.choices[0].message.content, restoredEvid, "evidence");
    const d = $("decision"); d.className = "decision " + sg.decision;
    const leak = sg.events.find((e) => e.kind === "leakcheck");
    const sub = sg.events.find((e) => e.kind === "substitute");
    const gen = sg.events.find((e) => e.kind === "generalise");
    d.textContent = `Decision: ${sg.decision.toUpperCase()} · ${sub ? sub.n_spans : 0} identifiers substituted · ${gen ? gen.rules.length : 0} generalised · leak check ${leak && leak.passed ? "passed" : "FAILED"} · ${sg.flags.length} conduct flag${sg.flags.length === 1 ? "" : "s"}`;
    const screen = sg.events.find((e) => e.kind === "screen");
    const baseline = screen && screen.baseline_flags && screen.baseline_flags.length ? screen.baseline_flags.join(", ") : "none";
    $("flags").innerHTML = sg.flags.map((f) => `
      <div class="flag ${f.severity}">
        <h3>${esc(f.label)} · ${esc(f.severity)}</h3>
        <p class="clause">SASW clause ${esc(f.clause)}</p>
        <div class="evidence">${esc(panelRestore(f.evidence, panel))}</div>
        ${f.rewrite ? `<div class="rewrite"><strong>Suggested rewrite:</strong> ${esc(panelRestore(f.rewrite, panel))}</div>` : ""}
      </div>`).join("") + `<div class="baseline">Generic harm classifier on the same reply: ${esc(baseline)}.</div>`;
    const overridable = sg.flags.length && sg.decision !== "escalate";
    $("override").hidden = !overridable; $("override-status").textContent = "";
    $("events").textContent = JSON.stringify(sg.events.map((e) => { const c = Object.assign({}, e); delete c.outbound_text; delete c.text; return c; }), null, 1);
  }

  function panelRestore(text, panel) {
    let t = text || "";
    for (const r of [...panel.replacements].sort((a, b) => b.outbound.length - a.outbound.length)) {
      if (r.outbound && r.outbound.length > 1) t = t.split(r.outbound).join(r.original);
    }
    return t;
  }

  $("override-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (!current) return;
    const r = await fetch("/v1/override", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({session: current.sg.session, pack: current.pack, by: "practitioner", flag_labels: current.sg.flags.map((f) => f.label), reason: $("override-reason").value})});
    const data = await r.json();
    $("override-status").textContent = r.ok ? `Override recorded. Ledger row ${data.ledger_row_sha256.slice(0, 12)}…` : "Refused: " + (data.detail || r.statusText);
  });
})();
