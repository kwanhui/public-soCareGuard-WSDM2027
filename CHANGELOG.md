# Changelog

## Unreleased (2026-09-07): five stakeholder review rounds

- Reports, fix logs and a summary under `docs/reviews/2026-09-07-stakeholder-rounds/`. In brief:
  per-request identity map and session tokens; escalation withholds the draft, flags included, and
  a supervisor releases it with a reason; vault keyed per entity with ambiguity-safe restoration
  and surrogate reuse within a session; enforceable never_leak patterns; offence, capacity and PPO
  polarity rules with a regression suite and scenario-level outbound tests; audience gate with
  external recipients winning and pack-specific statutory recipients; hospital, passport, bank,
  handle and vehicle recognisers; titled names; role words, scheme names and order acronyms never
  substituted; ledger rows carry recipients, actor attestation, pack hash, rules fired, build,
  audience and leak detail; retention sweep; fail-closed 503; OpenAI error envelope, /v1/models,
  /v1/packs, /v1/ledger, session purge. Panel: legend, plain-language flag cards with the judge's
  reason, per-flag overrides, rewrite acceptance, regenerate with a compare strip, same-session
  audience gate, escalation chip with supervisor release, replay of the recorded reply by default
  on shipped chips, integration snippet, operator docs.

## 2026-09-06

- `demo/record_video.py` rewritten to the lab house style: title and end cards, burned-in
  full-sentence captions, no audio, live waits trimmed to eight seconds with the measured
  latency stated, manifest, trim plan, cut summary and review frames. Final cut 2:31.
- Sanitiser fixes found by the takes: the instruction line before the first blank line is never
  generalised (`attribute_floor`); a NAME needs an uppercase letter; a leading verb such as
  "Attends" is trimmed from facility and school spans; adjacent identical generalised phrases
  collapse to one; the article before a generalised phrase is dropped ("at a cafe" becomes "at an
  employer", not "at a an employer"), including when a generalised attribute precedes it; a
  two-letter surname gets its derived restore form.
- The panel endpoint lists derived vault pairs; scenario fixtures re-recorded on the fixed code.

## demo-v1 (2026-09-05)

- Transparency panel at `/`: four columns with highlighted substitutions, flag cards with
  clause, evidence and rewrite, baseline contrast, override form, event stream; scenario chips.
- Sandbox mode with banner and per-address rate limit; `Dockerfile` for a Hugging Face Space
  with models warmed into the image; `docker-compose.yml` for an agency server.
- Public snapshot script and deploy-only workflow; `demo/record_video.py` (Playwright,
  text-to-speech, ffmpeg) produced a 154 s narrated video, stored in the paper repo
  (superseded by the captions-only cut, see Unreleased).

## screen-v1 (2026-09-05)

- Inbound conduct screen on the pseudonymised reply: clause-grounded LLM judge with verbatim
  evidence, confidence and rewrites; over-caution and invented-identifier rules; audience gate
  for disclosure categories; moderation baseline for contrast; ExpGuard wired (gated weights).
- Policy packs v1 with complete cross-cutting categories; I14 scoped to external audiences.
- Decisions pass / annotate / regenerate / escalate; escalations cannot be overridden.
- Screener metrics on the labelled drafts (F1, AUPRC, FPR, per label, baseline overlap) with a
  cross-provider judge check; all four scenarios pass every assertion with the live judge.

## proxy-v1 (2026-09-05)

- OpenAI-compatible FastAPI proxy with per-request policy pack, event stream in the response,
  override endpoint and ledger verification; LiteLLM Proxy guardrail class over the same core.
- Detection pipeline: Singapore recognisers, gazetteers, Presidio, GLiNER2-PII, cue-lexicon
  attributes; trust-ordered overlap resolution, name propagation, address merging.
- Generalisation rules per policy pack; type-consistent surrogates with token-level collision
  avoidance; AES-256-GCM SQLite vault; hash-chained JSONL ledger.
- Metrics: span P/R/F1 (exact and relaxed), leakage rate, recall by name origin, attribute
  recall, round-trip consistency/injectivity/fidelity, per-provider utility retention.
- Scenario replay drives the real guard; the four Use Case replies are recorded live.

## corpus-v1 (2026-09-05)

- 300 synthetic case notes with three-layer gold annotation, 600 labelled drafts, sweep report.
- Four scenario scripts, policy packs v0, conduct taxonomy v0.
