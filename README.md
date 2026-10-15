---
title: SoCareGuard
emoji: 🛡️
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Privacy and conduct guardrail proxy for social service LLMs
---

# SoCareGuard

> **Status:** public snapshot of the system demonstrated in the WSDM 2027 submission. Pinned versions in `requirements-lock.txt`.

An on-premise, OpenAI-compatible guardrail proxy that lets Singapore social service
agencies use commercial LLMs for drafting without sending client material across the
boundary in the clear, and that screens what comes back against a conduct taxonomy for
social-work practice. The conduct taxonomy is a draft adapted from published work and anchored on the
SASW Code of Professional Ethics, and it has not yet been reviewed by social-work practitioners.
The paper's title names the domain (a professional-ethics guardrail), and the artefact that this
repository implements is the conduct taxonomy and the screen built on it.

Outbound, the proxy detects Singapore PDPA identifiers (NRIC/FIN with checksum, postal
codes, HDB units, case references, multi-origin names), generalises sensitive attributes
and quasi-identifiers (disability status, domestic-violence disclosure, minor status,
protection-order status, school, estate) and substitutes reversible, format-preserving
surrogates held in an encrypted local vault. Inbound, it re-identifies locally, checks
for leakage, and screens the model's draft against the conduct taxonomy, with declarative
policy packs for disability, domestic violence, and youth offending. Every decision, and every
practitioner override with its reason, is written to an append-only audit ledger.

## Relation to existing tools

The reversible pseudonymisation loop, the OpenAI-compatible proxy, and the encrypted vault
are features that existing tools already provide. SoCareGuard is built as a
[LiteLLM](https://github.com/BerriAI/litellm) guardrail plugin over
[Presidio](https://github.com/microsoft/presidio) (which already ships `SG_NRIC_FIN`)
and [GLiNER](https://github.com/urchade/GLiNER). The conduct screener is a judge prompted with
a taxonomy whose categories derive from the SASW Code. ExpGuard (ICLR 2026) is the described
comparison and is wired as an optional comparator (see Conduct screen). The contribution of this
work is the inbound conduct screen, the generalisation of sensitive attributes as an operation
distinct from entity redaction, the Singapore quasi-identifier model, and the audit ledger.

## Companion Paper

- SoCareGuard: a privacy and professional-conduct guardrail proxy for commercial LLMs in social service practice. WSDM 2027 Demonstrations (under review).

## Install

```bash
git clone https://github.com/kwanhui/public-soCareGuard-WSDM2027.git
cd public-soCareGuard-WSDM2027
uv python install 3.12 && uv venv --python 3.12 .venv && source .venv/bin/activate
make install            # package + dev tools
make install-detect     # Presidio, spaCy (en_core_web_lg), GLiNER and GLiNER2-PII, for the sweep and the detectors
cp .env.example .env    # then add OPENAI_API_KEY and ANTHROPIC_API_KEY
```

## Run the proxy

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
`ledger`), so a client can show what left the premises and what came back. A request without
`X-SoCareGuard-Pack` runs the deployment's default pack (`SOCAREGUARD_DEFAULT_PACK`). Its body then
says `pack_defaulted: true`, and the response also carries the header
`X-SoCareGuard-Pack-Defaulted: true`, so a client that reads only the message content can still
detect that the default ran. Overrides go to
`POST /v1/override` with a reason, which the ledger records. An override must name flags raised on
that session, its `request_row_sha256` (when given) must name a ledger row of that session, and a
reason that contains an NRIC/FIN, a Singapore phone number or a case reference is refused with HTTP
400, as reasons are kept in the ledger as typed. When the session has a reply, the override must
also carry `draft_sha256`, the SHA-256 in hex of the text that the practitioner kept or applied,
so that a later case review can match the row against the document. A call without it is refused
with HTTP 400. The panel sends it on every override. The vault (SQLite, AES-256-GCM) and the ledger
live under `vault/` and are gitignored. By default the vault key is a file beside the vault
(`vault/socareguard.key`, mode 600). `SOCAREGUARD_VAULT_KEY` can point at a key file elsewhere,
such as a Docker secret, and `docker-compose.yml` carries that option as a commented alternative.

`/supervisor` is the supervisor view. It opens with the chain check of the record, that is, the
ledger (the rows in the record, the record fingerprint or head hash, any gap, and the fingerprint
that the server last logged), then lists the
withheld drafts that no supervisor has released yet (session id, policy pack, time, categories and
practitioner), then one period of escalations, releases, passages kept with a reason, rewrites used
and opened reviews, with filter chips for pack, category, actor, kind and dates, and the counts for
the period. The rows carry no note or reply text. `GET /v1/supervisor/summary` returns the same content as JSON and takes `since`,
`until`, `pack`, `category`, `actor`, `kind` and `limit`. A review link
(`POST /v1/sessions/{id}/review-token`) opens one session read-only in the panel for 30 minutes and
writes a `review_opened` row to the record. The link itself opens the GET routes of that session
and never a release, a passage kept with a reason (`POST /v1/override`) or a purge. A supervisor
who is signed in (the sandbox login or a supervisor key) sees the release form at the foot of the
review page of a withheld draft, and releases it there with a reason and a confirmation step. The
sign-in stands in for the practitioner's session token, the `withheld_released` row names the
supervisor (`admin (sandbox login)`, typed in, in the sandbox), and the draft leaves the queue. A
review link without a sign-in, or a practitioner's API key, releases nothing.

With `SOCAREGUARD_SUPERVISOR_KEYS` set, the view and the summary require a supervisor key
(`Authorization: Bearer <key>`, or the key typed into the sign-in form), and the record marks the
actor as checked by a person. Without keys, the sandbox signs a supervisor in with the user name
`admin` and the password `demo1234`, and the record keeps the actor as `admin (sandbox login)`,
typed in. This is a
simplistic authentication for demonstration purposes only, with a fixed shared credential and no
rate limiting or lockout, and it must be replaced with proper authentication (per-user credentials
or single sign-on, a supervisor role that the deployment checks, session expiry and audit) before
any production deployment. The login is off whenever `SOCAREGUARD_SUPERVISOR_KEYS` or `SOCAREGUARD_API_KEYS` is
set.

Every sandbox visitor shares that login, so the view that it opens is limited. The queue and the
period table list the action rows of every session, but a review link into a session that another
browser created returns only the content with stand-ins, that is, what left the premises, what the
model replied, the flags quoted with stand-ins, and the rows of the record. The restored draft and
the identity map open only for a session that this browser created (the panel keeps each session token in
`sessionStorage`) or under a supervisor key. A release from such a review therefore shows the
released draft with stand-ins, and the practitioner's panel shows the restored draft. `GET /v1/ledger` without a session still lists the
rows of all sessions only when API keys are configured and the call carries one.

Each ledger row records the transfer-basis statement that the deployer sets through
`SOCAREGUARD_TRANSFER_BASIS`. The sandbox uses the default statement, which says that the basis
is still to be asserted. The row does not establish a legal basis by itself. Each row also carries
its sequence number and the previous row's hash inside its own hash, and every append logs
`ledger head <sha> rows <n>` at INFO. `GET /v1/ledger/verify` recomputes the chain and the
sequence and returns `rows`, `head_sha256` and the first sequence gap, and with
`?expected_rows=<n>` it also reports a cut tail. The chain is tamper-evident against edits and
reordering. Anchoring the head hash outside the host is the deployer's step (ship the server
log). A party that can write the ledger file can still rewrite every row from some point
onwards, and only a comparison with the shipped head hash shows it.

In the terms of PDPC's Advisory Guidelines on Use of Personal Data in Generative AI, the agency that
runs the proxy is the System Deployer, SoCareGuard is a System Provider, and the provider of the
drafting model and the judge is a Model Provider, which PDPC's guidance treats as a data
intermediary at inference. Whether that status holds depends on the deployer's agreement with the
provider. The ledger is the kind of record of prompts and outputs that the guidelines ask a
deployer to keep (section 9.3), and `docs/metrics.md` reports the detection and redaction rates that
they ask a System Provider to document (section 8.3).

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

The primary deployment is an agency server. The proxy runs on a host that the agency
controls, started with `docker compose up` or with `python3 -m socareguard.proxy`, and
practitioners' tools point at it. Sensitive material, the vault, and the ledger remain on that
server, and only the pseudonymised payload reaches the model provider. This is the deployment
that the paper describes.

A fully local mode is available as an add-on. The same command runs on a practitioner's own
computer, as the detectors are CPU-only, the vault is a per-machine SQLite file, and the identity
mapping does not exist anywhere else. The trade-off is governance. Ledger rows (hashes and counts,
never identifiers) must be synced for an agency-level audit trail, and policy packs must be
distributed to each machine. This mode is documented as an option rather than the default. An
in-browser variant may be feasible for the outbound half with ONNX exports of the detector, but it
has not been built.

### Pipeline

On the outbound path, deterministic Singapore recognisers (NRIC/FIN with checksum, postal
sectors, HDB block and unit, phone, case references) and gazetteers (estates, schools,
facilities, ages) run first. Presidio (`SG_NRIC_FIN`, names) and GLiNER2-PII
(`fastino/gliner2-privacy-filter-PII-multi`) then add names, addresses, and zero-shot attribute
spans, and a cue lexicon adds clause-level disclosures. Overlaps are resolved by detector trust
(deterministic over model), then span type (direct over quasi), then score. Quasi-identifiers and
attributes are generalised by the pack's rules, whereas direct identifiers receive
type-consistent surrogates that never reuse a token of any original name.

On the inbound path, surrogates and generalised phrases are restored longest-first. The leak
check then flags any original echoed by the model, any invented direct identifier, and any
unrestored surrogate.

## Demo surface

`python3 -m socareguard.proxy` also serves the transparency panel at `/`. A result opens with a
banner that states the decision in one sentence (pass, flagged, regenerate or escalate), gives one
next step, and offers one button for it: copy the draft, go to the first flag, regenerate, or copy
the session id for a supervisor. The details (the policy pack, the counts, the privacy check, the
harm classifier shown for contrast, the actor) sit under "More about this result". The panel then
shows what you typed, what left the premises and what you see side by side, with stand-ins
(surrogates) and generalised details highlighted. What the model replied, with stand-ins, opens
with one click. Each flag is a card that leads with a plain-words headline, puts the clause, the
screen's own confidence and the measured precision on one line under it, and offers the rewrite
or keeping the passage with a reason that goes into the record. A release asks the supervisor to
confirm before it is sent. The record, the pack rules that fired and the event stream are
collapsed, each with a count. Each scenario loads with one click. The identity map that the panel
fetches decodes the practitioner's own note and never the withheld reply. The words that the panel
uses are listed in `docs/terminology.md`.
`SOCAREGUARD_SANDBOX=1` shows the synthetic-data banner, and `SOCAREGUARD_MAX_REQUESTS_PER_HOUR`
sets a per-address rate limit.

On an agency server, `docker compose up` starts one container with its state on a named volume
and its keys read from `.env`. For a hosted sandbox, the `Dockerfile` targets a Hugging Face Space
(Docker SDK, port 7860, with models warmed into the image), and the provider keys are held as
Space secrets rather than in the image. Local mode uses the same command on a practitioner's own
machine, as described under Deployment modes. The demo video was produced with separate recording
tooling that is not part of this repository.

## Conduct screen

The reply is screened before local re-identification, so the judge provider does not see an
original identifier either. Flags come from three sources.

The first is a clause-grounded judge (`socareguard/screen/judge.py`), an LLM prompted with the
pack's inbound categories, each quoting its SASW clause, together with the pack's setting rules.
The judge returns the category, a verbatim evidence span, a confidence, and, for annotate-level
flags, a minimal rewrite. By default the judge is `openai/gpt-4.1` at temperature 0
(`SOCAREGUARD_JUDGE_MODEL`), and claude-sonnet-5 provides the cross-provider check in the
evaluation.

The second is a set of deterministic rules (`screen/rules.py`), which cover crisis boilerplate in
a routine task (over-caution), invented identifiers from the leak check (I13), and the recipient
check. The recipient is resolved once per request as internal, care team or external (a header
value wins, then the instruction). The disclosure categories (I10, I14) fire only for a recipient
outside the case team. For the client's own care team (a day activity centre, a clinic, a school
counsellor) the screen's model reads I10 within the recipient's role, a draft reading of the SASW
Code's disclosure clause pending practitioner review, while a deterministic guard keeps I14 for any
youth document that names a protected young person to a recipient outside the agency.

The third is a generic baseline (`screen/baseline.py`), namely OpenAI moderation, which is
recorded as `baseline_flags` for contrast and is not used for the decision. ExpGuard (ICLR 2026)
is wired in `screen/expguard.py`, but its weights are gated on the Hugging Face Hub. To run it,
request access and set `HF_TOKEN`.

The decision is the highest default action among the flags in the pack (`pass`, `annotate`,
`regenerate`, or `escalate`). Escalations cannot be overridden by the practitioner. A supervisor
releases a withheld draft with a reason. Supervisor identity is self-asserted in the sandbox, and
with SOCAREGUARD_SUPERVISOR_KEYS set a supervisor key is required. A second release of the same
draft is recorded with a link to the earlier release row. Any other decision can be overridden with a
reason, which the ledger records. The policy packs are at v1. Every pack lists
the cross-cutting categories, the youth pack adds I14, and the disability and youth packs add I11.
The categories and packs are drafts that have not yet been reviewed by social-work practitioners
(see `policy-packs/README.md`). Each flag card shows the category's measured precision on the
labelled synthetic drafts at `results-v1.3` beside the screen model's own confidence, read from
`src/socareguard/proxy/screen_precision_v1_3.json` (derived from `docs/metrics/screen-v1.3-v1.1-drafts.json`).

```bash
python3 -m socareguard.eval screen                 # F1 / AUPRC / FPR on the 600 labelled drafts, plus the moderation baseline
python3 -m socareguard.eval screen --judge anthropic/claude-sonnet-5 --limit 60 --no-baseline --tag v1-claude
```

## Corpus and scenarios

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

The repository ships the synthetic notes and drafts with their labels (`corpus/notes`,
`corpus/drafts`), so `python3 -m socareguard.eval screen` recomputes the screen numbers from
the drafts. See `corpus/README.md` for provenance and the caveat that conduct labels are
generation-intent labels. The compliant drafts of corpus v1.1 are all internal summaries (for the
case file or a supervisor), so v1.1 does not test the audience gate against a compliant draft for an
external recipient. Corpus v1.2 adds 90 compliant external drafts (referral, school and
employer letters that stay within need-to-know), with v1.1 kept frozen. Scenario scripts live in `demo/sample-inputs/scenarios/`. Their model
replies are recorded live through the proxy (`source: recorded`, model and timestamp in the file).

## Metrics

```bash
python3 -m socareguard.eval detect            # entity P/R/F1, leakage rate, recall by name origin, attribute recall
python3 -m socareguard.eval roundtrip         # consistency, injectivity, surrogate fidelity, outbound leakage, latency
python3 -m socareguard.eval utility --limit 10   # per-provider utility retention, judged by the other provider
```

The round-trip injectivity counts a note as injective when no two people share a full name or a
short form. A surrogate surname that a household shares is by design and does not count against
it. Results are committed under `docs/metrics/` and summarised in `docs/metrics.md`. The reported
numbers were measured at tag `results-v1.3` on corpus v1.3 (the v1.1 notes and drafts, 90
compliant drafts written for an external reader and 30 written for the client's own care team), at
the code this snapshot carries. The earlier
`results-v1.1` values are kept in the same files and in the metrics page for comparison. On the 90
external drafts the screen flags 76. The reading of those flags is summarised in `docs/metrics.md`.

The gold identifiers in the corpus appear in the canonical formats of the corpus generator (for
example, an NRIC as `S1234567D`), because the generator and the recognisers share one identifier
module. The detection rows therefore measure canonical formats. A separate format-variant stress
set (spaced, hyphenated and lower-case identifiers, with and without a label, and in parentheses)
is reported with its own recall in `docs/metrics.md`. At OpenAI list
prices on 2026-09-27, one guarded draft costs approximately USD 0.006 (drafting with gpt-4.1-mini,
screening with gpt-4.1, moderation free), of which the judge accounts for most. The Cost
section of `docs/metrics.md` gives the breakdown.

## Roadmap

| Step | Deliverable | Status |
|---|---|---|
| 1 | Corpus with three-layer gold annotation; four scenario scripts; policy packs v0 | done, tag `corpus-v1` |
| 2 | Proxy core: detectors, generalisation, vault, ledger, metrics | done, tag `proxy-v1` |
| 3 | Conduct screen: clause-grounded judge, rules, baseline; policy packs v1 | done, tag `screen-v1` (reported results at `results-v1.3`) |
| 4 | Transparency panel, `docker compose`, hosted synthetic-only sandbox, video | done, tag `demo-v1` |
| 5 | Paper | submission due 2026-10-15, under review after that date |

## Development

```bash
make test     # pytest
make lint     # ruff check
make format   # ruff format
```

## Operating the proxy

Environment variables read at start-up (all optional):

| Variable | Default | What it does |
|---|---|---|
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | | provider keys for the drafting model, the judge and the moderation baseline |
| `SOCAREGUARD_DEFAULT_MODEL`, `SOCAREGUARD_MODELS` | `openai/gpt-4.1-mini`; `openai/gpt-4.1-mini,anthropic/claude-sonnet-5` | drafting models offered; an unknown model falls back to the default and the response says `model_defaulted` |
| `SOCAREGUARD_JUDGE_MODEL` | `openai/gpt-4.1` | the conduct judge |
| `SOCAREGUARD_DEFAULT_PACK` | `domestic-violence` | pack used when a request carries no `X-SoCareGuard-Pack` (the response says `pack_defaulted` and carries the header `X-SoCareGuard-Pack-Defaulted: true`) |
| `SOCAREGUARD_API_KEYS` | unset | comma-separated bearer keys. When set, every `/v1` route requires one and ledger actors are marked attested |
| `SOCAREGUARD_SUPERVISOR_KEYS` | unset | keys allowed to release a withheld draft (`GET /v1/sessions/{id}/withheld`) and to open the supervisor view (`/supervisor`). When set, the sandbox login is off |
| `SOCAREGUARD_TRANSFER_BASIS` | a statement that the basis is still to be asserted | the transfer-basis statement written to every request row |
| `SOCAREGUARD_SANDBOX` | `0` | banner, self-asserted actors, 24-hour retention |
| `SOCAREGUARD_MAX_REQUESTS_PER_HOUR` | `0` (unlimited, and the Space image sets 20) | per-address rate limit |
| `SOCAREGUARD_TRUST_PROXY` | `0` | honour `X-Forwarded-For`, `X-Forwarded-Proto` and `X-Forwarded-Host`, so the rate limit sees the client address and the panel's integration snippet shows the public `https` URL (set only behind a reverse proxy you control) |
| `SOCAREGUARD_RETENTION_HOURS` | `24` in sandbox, else `0` (`docker-compose.yml` sets `720`) | purge vault mappings older than this. `0` keeps them until `DELETE /v1/sessions/{id}`, and the proxy then logs a WARNING at start-up |
| `SOCAREGUARD_MAX_SESSIONS` | `500` | sessions kept in the session index. Beyond it the oldest session is closed and its mappings purged |
| `SOCAREGUARD_VAULT`, `SOCAREGUARD_LEDGER`, `SOCAREGUARD_VAULT_KEY` | `vault/socareguard.sqlite`, `vault/ledger.jsonl`, key file beside the vault (`vault/socareguard.key`) | where state lives. `SOCAREGUARD_VAULT_KEY` takes a path to a key file or the key itself (base64). The proxy refuses to mint a new key over an existing vault unless `SOCAREGUARD_VAULT_NEW_KEY=1` |
| `SOCAREGUARD_SCREEN` | `auto` | `off` disables the conduct screen (tests) |

Deploying for an agency: run `docker compose up` behind the agency's reverse proxy with TLS, set
`SOCAREGUARD_API_KEYS` (one key per client application) and `SOCAREGUARD_SUPERVISOR_KEYS`, put the
staff identity in `X-SoCareGuard-Actor` from the calling application (the ledger marks a key-backed
actor as attested), set `SOCAREGUARD_TRANSFER_BASIS` to the agency's contractual basis with the
provider, and back up `vault/socareguard.key` separately from the vault volume (without the key the
mappings are unreadable, but a snapshot of both makes them readable). The compose file keeps the key
on the vault volume by default, and its commented alternative mounts the key from a Docker secret
through `SOCAREGUARD_VAULT_KEY` instead. The compose file sets `SOCAREGUARD_RETENTION_HOURS=720`
(30 days), so the identity map is purged after 30 days unless the agency chooses otherwise. With
`0`, sessions and mappings are kept until `DELETE /v1/sessions/{id}`, and the proxy logs a WARNING
at start-up that says so. If a provider or the judge
fails, the request fails closed with HTTP 503 and nothing is drafted. The 503 body carries a short
error id, and the server log has the same id with the traceback at ERROR. Open sessions survive a
restart: the session index (the result, the token's hash, the pack, the withheld state and the
flags) is kept in the vault's SQLite file, with everything but the hash, the pack, the withheld state
and the flag labels encrypted under the vault key, so a supervisor can still open and release a
withheld draft after a deploy. Detection is not perfect:
column 2 of the panel is what left, and a practitioner should read it before relying on the guard.

Surrogates follow the household. People whose surname or father-name is the same in the note
receive one shared surrogate surname or father-name, so that a sentence such as "same surname as
the client" remains true, while a spouse with a different surname receives a different one. No two
people share a full name or a short form. A shared titled surname is marked when it could be either
of two people. For example, "Mdm Tan" written for one of two women in the same household is
restored to the surname, and the panel adds a card that says it could be either of two people.

Language that the practitioner wrote in the note may be echoed by the model without a flag. The
screen judges the draft in the context of the note, so deficit framing or a label that the draft
carries over from the note is not always flagged. The absence of a flag says nothing about the note
itself.

Endpoints: `POST /v1/chat/completions` (headers `X-SoCareGuard-Pack`, `X-SoCareGuard-Session`,
`X-SoCareGuard-Actor`, `X-SoCareGuard-Audience`), `GET /v1/models`, `GET /v1/packs`,
`GET /v1/packs/{id}`, `GET /v1/sessions/{id}` and `/panel` (require the session token returned
with the completion, or an API key), `GET /v1/sessions/{id}/withheld` (a supervisor key or a signed-in
supervisor, or in a deployment without keys the self-asserted supervisor role plus the session
token),
`DELETE /v1/sessions/{id}` (purge, ledgered), `GET /v1/ledger?session=`, `GET /supervisor`,
`GET /v1/supervisor/summary` and `POST /v1/sessions/{id}/review-token` (supervisor key, or the
sandbox login when no key is configured),
`GET /v1/ledger/verify?expected_rows=`, `GET /healthz` (also the container healthcheck). Errors use
the OpenAI `error` envelope, and a body that is not valid JSON or fails validation returns HTTP 400.

## Citation

To be added on acceptance.

## License

See [LICENSE](LICENSE).
