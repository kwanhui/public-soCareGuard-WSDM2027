// Applying a flag's suggested rewrite to the draft in column 4. Kept apart from panel.js so
// that the tests can run it under node without a page.
//
// The rewrite replaces the flagged text where it stands. A sentence of the rewrite that the
// draft already says elsewhere is left out, so accepting a rewrite does not repeat a point.
// When the flagged text cannot be found in the draft, nothing is changed: the panel shows the
// rewrite for the practitioner to place by hand, and never appends it.
(function (root) {
  // A judge quote may be elided ("... "), joined with ";" or quoted. Each piece is matched on its own.
  function pieces(evidence) {
    return String(evidence || "").split(/\s*(?:\.\.\.|…|;\s+")\s*/).map((p) => p.replace(/^["“”']+|["“”']+$/g, "").trim()).filter((p) => p.length >= 12);
  }
  const STOP = new Set("a an and are as at be been by for from has have he her his in is it its of on or she that the their they this to was were will with".split(" "));
  const words = (s) => (String(s).toLowerCase().match(/[a-z0-9']+/g) || []).filter((w) => w.length > 1 && !STOP.has(w));
  const sentences = (s) => (String(s).match(/[^.!?\n]+[.!?]*/g) || []).map((x) => x.trim()).filter(Boolean);
  // A rewrite sentence is already in the draft when a draft sentence carries at least 80% of
  // its content words (and it has at least four).
  function alreadySaid(sentence, rest) {
    const w = words(sentence);
    if (w.length < 4) return false;
    return sentences(rest).some((t) => { const have = new Set(words(t)); return w.filter((x) => have.has(x)).length >= 0.8 * w.length; });
  }

  // Returns {text, status, dropped}. status is "whole" (the rewrite is a full draft and
  // replaces it), "replaced" (in place), or "not_found" (text unchanged).
  function applyRewrite(plain, evidence, rewrite) {
    plain = String(plain || ""); rewrite = String(rewrite || "");
    if (!rewrite) return {text: plain, status: "not_found", dropped: []};
    if (rewrite.length > 0.6 * plain.length || /^\s*(subject|dear)\b/i.test(rewrite)) return {text: rewrite, status: "whole", dropped: []};
    let found = plain.includes(evidence) && String(evidence).length >= 2 ? [evidence] : pieces(evidence).filter((p) => plain.includes(p));
    if (!found.length) return {text: plain, status: "not_found", dropped: []};
    // A full-sentence rewrite of a phrase replaces the sentence that holds the phrase, so the
    // rewrite does not land inside a sentence ("has a Priya has a ...").
    if (found.length === 1 && /[.!?]\s*$/.test(rewrite) && !/[.!?]\s*$/.test(found[0])) {
      const at = plain.indexOf(found[0]);
      const head = plain.slice(0, at), tail = plain.slice(at + found[0].length);
      const start = Math.max(head.search(/[^.!?\n]*$/), 0);
      const m = tail.match(/^[^.!?\n]*[.!?]?/);
      const whole = plain.slice(start, at + found[0].length + (m ? m[0].length : 0)).trim();
      if (whole) found = [whole];
    }
    // what the draft says outside the flagged text
    let rest = plain;
    found.forEach((frag) => { rest = rest.split(frag).join(" "); });
    const keep = [], dropped = [];
    sentences(rewrite).forEach((s) => (alreadySaid(s, rest) ? dropped : keep).push(s));
    const insert = keep.join(" ");
    let text = plain;
    // the first located fragment becomes the rewrite; every other located fragment is removed
    found.forEach((frag, k) => { text = text.split(frag).join(k === 0 ? insert : ""); });
    text = text.replace(/[ \t]{2,}/g, " ").replace(/[ \t]+([.,;])/g, "$1").replace(/[ \t]+\n/g, "\n");
    return {text, status: "replaced", dropped, inserted: insert};
  }

  const api = {applyRewrite, pieces};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SoCareGuardRewrite = api;
})(typeof window !== "undefined" ? window : this);
