---
title: SoCareGuard
emoji: 🛡️
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Privacy and professional-conduct guardrail proxy for social service practice (synthetic sandbox)
---

# SoCareGuard

> **Status:** in-progress (build step 4 of 5: demo surface done; paper next)

An on-premise, OpenAI-compatible guardrail proxy that lets Singapore social service
agencies use commercial LLMs for drafting without sending client material across the
boundary in the clear, and that screens what comes back against the profession's own
code of conduct.

Outbound, the proxy detects Singapore PDPA identifiers (NRIC/FIN with checksum, postal
codes, HDB units, case references, multi-origin names), generalises sensitive attributes
and quasi-identifiers (disability status, domestic-violence disclosure, minor status,
protection-order status, school, estate) and substitutes reversible, format-preserving
surrogates held in an encrypted local vault. Inbound, it re-identifies locally, checks
for leakage, and screens the model's draft against a professional-conduct taxonomy
anchored on the SASW Code of Professional Ethics, with declarative policy packs for
disability, domestic violence and youth offending. Every decision, and every
practitioner override with its reason, is written to an append-only audit ledger.

**What is and is not ours.** The reversible pseudonymisation loop, the OpenAI-compatible
proxy and the encrypted vault are commodity features; SoCareGuard is built as a
[LiteLLM](https://github.com/BerriAI/litellm) guardrail plugin over
[Presidio](https://github.com/microsoft/presidio) (which already ships `SG_NRIC_FIN`)
and [GLiNER](https://github.com/urchade/GLiNER), and the conduct screener builds on
ExpGuard (ICLR 2026). The contribution is the inbound conduct screen, the
sensitive-attribute generalisation as an operation distinct from entity redaction, the
Singapore quasi-identifier model, and the accountability ledger.

## Companion Paper

- SoCareGuard: a privacy and professional-conduct guardrail proxy for commercial LLMs in social service practice. WSDM 2027 Demonstrations (under review).

## Install

```bash
git clone https://github.com/kwanhui/public-soCareGuard-WSDM2027.git
cd public-soCareGuard-WSDM2027
uv python install 3.12 && uv venv --python 3.12 .venv && source .venv/bin/activate
make install            # package + dev tools
make install-detect     # Presidio, spaCy (en_core_web_lg) and GLiNER, for the sweep and the detectors
cp .env.example .env    # then add OPENAI_API_KEY and ANTHROPIC_API_KEY
```

## Run the proxy (build step 2)

```bash
python3 -m socareguard.proxy --port 8080          # OpenAI-compatible endpoint on localhost
```

Point any OpenAI client at it and add one header naming the policy pack:

```bash
curl -s http://127.0.0.1:8080/v1/chat/completions \
  -H 'Content-Type: application/json' -H 'X-SoCareGuard-Pack: domestic-violence' \
  -d '{"model": "openai/gpt-4.1-mini", "messages": [{"role": "user", "content": "Summarise: Client Tan Wei Ming, NRIC S1234567D, ..."}]}'
```

The reply is a standard chat completion whose `socareguard` field carries the event stream
(`detect`, `generalise`, `substitute`, `send`, `receive`, `reidentify`, `leakcheck`, `action`,
`ledger`), so a client can show what left the premises and what came back. Overrides go to
`POST /v1/override` with a reason, which the ledger records; `GET /v1/ledger/verify` recomputes
the hash chain. The vault (SQLite, AES-256-GCM, key file with mode 600) and the ledger live under
`vault/` and are gitignored.

To run inside a LiteLLM Proxy instead, register the guardrail class:

```yaml
guardrails:
  - guardrail_name: socareguard
    litellm_params:
      guardrail: socareguard.proxy.litellm_guardrail.SoCareGuardrail
      mode: [pre_call, post_call]
      default_on: true
```

### Deployment modes

- **Agency server (primary).** The proxy runs on a host the agency controls (docker compose in
  build step 4, or `python3 -m socareguard.proxy` on a server). Practitioners' tools point at it.
  Sensitive material, the vault and the ledger stay on that server; only the pseudonymised payload
  reaches the model provider. This is the deployment the paper describes.
- **Fully local (add-on).** The same command runs on a practitioner's own computer: the detectors
  are CPU-only, the vault is a per-machine SQLite file, and the identity mapping never exists
  anywhere else. Governance is the trade-off: ledger rows (hashes and counts, never identifiers)
  must be synced for an agency-level audit trail, and policy packs distributed. Documented as an
  option, not the default. An in-browser variant is feasible for the outbound half with ONNX
  exports of the detector but is not built.

### Pipeline

Outbound: deterministic Singapore recognisers (NRIC/FIN with checksum, postal sectors, HDB
block and unit, phone, case references) and gazetteers (estates, schools, facilities, ages)
run first; Presidio (`SG_NRIC_FIN`, names) and GLiNER2-PII (`fastino/gliner2-privacy-filter-PII-multi`)
add names, addresses and zero-shot attribute spans; a cue lexicon adds clause-level disclosures.
Overlaps resolve by detector trust (deterministic over model), then span type (direct over quasi),
then score. Quasi-identifiers and attributes are generalised by the pack's rules; direct
identifiers get type-consistent surrogates that never reuse a token of any original name.

Inbound: surrogates and generalised phrases are restored longest-first; the leak check flags any
original echoed by the model, any invented direct identifier, and any unrestored surrogate.

## Demo surface (build step 4)

`python3 -m socareguard.proxy` also serves the **transparency panel** at `/`: four columns
(what you typed, what left the premises, what came back, what you see) with substitutions and
generalisations highlighted, the conduct flags with clause, evidence and rewrite, the generic
classifier's verdict for contrast, an override form that records the reason, and the event
stream. The four scenarios load with one click. `SOCAREGUARD_SANDBOX=1` shows the synthetic-data
banner and `SOCAREGUARD_MAX_REQUESTS_PER_HOUR` rate-limits by address.

- **Agency server:** `docker compose up` (one container, state on a named volume, keys from `.env`).
- **Hosted sandbox:** the `Dockerfile` targets a Hugging Face Space (Docker SDK, port 7860, models
  warmed into the image). `scripts/make_public_snapshot.sh` builds the allowlisted public
  reproducibility snapshot (`public-SoCareGuard-WSDM2027`), and the deploy-only workflow
  `.github/workflows/deploy-hf.yml` pushes that snapshot to the Space. Provider keys are Space
  secrets, never in the image.
- **Local mode:** the same command on a practitioner's own machine; see Deployment modes.
- **Video:** `demo/record_video.py` drives the panel through the four scenarios with Playwright,
  narrates with text-to-speech and encodes with ffmpeg; the finished video lives in the paper repo.

## Conduct screen (build step 3)

The reply is screened before local re-identification, so the judge provider never sees an
original identifier either. Three sources of flags:

- **Clause-grounded judge** (`socareguard/screen/judge.py`): an LLM prompted with the pack's
  inbound categories, each quoting its SASW clause, plus the pack's setting rules. It returns
  the category, a verbatim evidence span, a confidence and, for annotate-level flags, a minimal
  rewrite. Default `openai/gpt-4.1` at temperature 0 (`SOCAREGUARD_JUDGE_MODEL`); claude-sonnet-5
  is the cross-provider check in the evaluation.
- **Deterministic rules** (`screen/rules.py`): crisis boilerplate in a routine task (over-caution),
  invented identifiers from the leak check (I13), and an audience gate: disclosure categories
  (I10, I14) can only fire when the instruction names a recipient outside the case team.
- **Generic baseline** (`screen/baseline.py`): OpenAI moderation, recorded as `baseline_flags` for
  contrast, never used for the decision. ExpGuard (ICLR 2026) is wired in `screen/expguard.py`
  but its weights are gated on the Hub; request access and set `HF_TOKEN` to run it.

Decision = the highest default action among the flags in the pack (`pass`, `annotate`,
`regenerate`, `escalate`). Escalations cannot be overridden; anything else can, with a reason
that the ledger records. Policy packs are at v1: every pack lists the cross-cutting categories,
the youth pack adds I14, the disability and youth packs add I11.

```bash
python3 -m socareguard.eval screen                 # F1 / AUPRC / FPR on the 600 labelled drafts, plus the moderation baseline
python3 -m socareguard.eval screen --judge anthropic/claude-sonnet-5 --limit 60 --no-baseline --tag v1-claude
```

## Corpus and scenarios (build step 1)

```bash
python3 -m socareguard.corpus generate      # layer 1: LLM-written notes with typed placeholders
python3 -m socareguard.corpus inject        # layer 2: Singapore surrogates + exact gold spans
python3 -m socareguard.corpus drafts        # layer 3: compliant and labelled-failure model drafts
python3 -m socareguard.corpus sweep         # spontaneous-entity sweep + 30-note audit checklist
python3 -m socareguard.corpus stats

python3 -m socareguard.scenarios validate   # the four Use Case scripts
python3 -m socareguard.scenarios run --proxy   # replay them through the real guard
python3 -m socareguard.scenarios record uc2-domestic-violence   # re-record the model reply live
```

See `corpus/README.md` for provenance and the caveat that conduct labels are generation-intent
labels. Scenario scripts live in `demo/sample-inputs/scenarios/`; their model replies are
recorded live through the proxy (`source: recorded`, model and timestamp in the file).

## Metrics

```bash
python3 -m socareguard.eval detect            # entity P/R/F1, leakage rate, recall by name origin, attribute recall
python3 -m socareguard.eval roundtrip         # consistency, injectivity, surrogate fidelity, outbound leakage, latency
python3 -m socareguard.eval utility --limit 10   # per-provider utility retention, judged by the other provider
```

Results are committed under `docs/metrics/` and summarised in `docs/metrics.md`.

## Roadmap

| Step | Deliverable | Status |
|---|---|---|
| 1 | Corpus with three-layer gold annotation; four scenario scripts; policy packs v0 | done, tag `corpus-v1` |
| 2 | Proxy core: detectors, generalisation, vault, ledger, metrics | done, tag `proxy-v1` |
| 3 | Conduct screen: clause-grounded judge, rules, baseline; policy packs v1 | done, tag `screen-v1` |
| 4 | Transparency panel, `docker compose`, hosted synthetic-only sandbox, video | done, tag `demo-v1` (Space deployment is the PI's step) |
| 5 | Paper | |

## Development

```bash
make test     # pytest
make lint     # ruff check
make format   # ruff format
```

## Citation

To be added on acceptance.

## License

See [LICENSE](LICENSE).
