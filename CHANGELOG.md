# Changelog

## demo-v1 (2026-09-05)

- Transparency panel at `/`: four columns with highlighted substitutions, flag cards with
  clause, evidence and rewrite, baseline contrast, override form, event stream; scenario chips.
- Sandbox mode with banner and per-address rate limit; `Dockerfile` for a Hugging Face Space
  with models warmed into the image; `docker-compose.yml` for an agency server.
- Public snapshot script and deploy-only workflow; `demo/record_video.py` (Playwright,
  text-to-speech, ffmpeg) produced a 154 s narrated video, stored in the paper repo.

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
