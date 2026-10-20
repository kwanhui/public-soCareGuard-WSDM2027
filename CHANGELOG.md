# Changelog

## 2026-10-20 (later): the sandbox against the paper's account

- The screen's model is a provider outside the premises, and it read the practitioner's
  instruction as typed, so a client's name in the instruction line reached it. It now reads the
  instruction as it left, with stand-ins, as it already read the note and the draft.
- A replayed reply is screened against the pseudonymised note that its model was given when it
  was recorded (the scenario's `send` event), not against this request's outbound text, which can
  differ after a later change to the outbound rules. What left the premises still shows this
  request's own text, and the screen event says `note_source: recorded`. Use Case 3 was the case
  in point: its reply was recorded when the instruction line still left as "an employer
  supervisor" and the age as "29". On the live screen, eight runs on the code of the morning's
  release raised I10 in none, and sixteen runs after this change raised it in ten (I3, for the
  added word "moderate", in nine; one run raised no flag). At the release used for the
  demonstration video (space-2026-09-28-2), eight runs raised I10 in eight.
- Use Case 3 says that the screen flagged I10 in the recorded demonstration of 2026-09-28 and that
  its flags can differ between runs, and a replay shows the two cards of that run (I10 and I3,
  transcribed from the video) as a labelled reference beside the live result.
- Use Case 4 keeps a reply from each provider. The anthropic/claude-sonnet-5 reply was recorded on
  2026-10-20 with one live call through the guard; it does not mention the self-harm history, and
  the scenario card says so. The panel lists each recording with its model and date under
  "Recorded reply from", and a request takes `replay_model` to choose one. A replay names the
  recording's model in the record, since no provider is called.
- Only a signed-in supervisor releases a withheld draft. The practitioner's panel has no release
  form: it shows the session id and points to the supervisor view, where the review page carries
  the release. A typed-in supervisor id with the practitioner's session token no longer releases
  anything in the sandbox. Where keys are set, a supervisor key still does.
- The banner opens with the decision's name (Pass, Flagged (annotate), Regenerate, Escalate), and
  a flag card's pill names its default action.
- `/packs/{id}` shows a policy pack as its YAML file and `/ledger/check` shows the chain check of
  the record, each with a link back to the panel and to its JSON route. The footer and "Open the
  pack" link to them. `/v1/packs`, `/v1/packs/{id}` and `/v1/ledger/verify` are unchanged.
- "Use this from your own application" adds a curl line for `/v1/packs` and one for a replay with
  `replay_scenario`.
- The review page no longer repeats the practitioner's line that there is no release on the panel,
  since the review page is where the release is. While a replay runs, the status line says that
  the recorded reply is replayed (usually 3 to 9 seconds on the Space, longer for the first request
  after it wakes) and no longer that the model provider is called.

## 2026-10-20: supervisor sign-in inside the Space page's frame

- The Hugging Face Space page shows the app in a frame from another site, where the browser
  dropped the `SameSite=Strict` supervisor cookie and the sign-in form came back with no message.
  Over https the cookie is now `SameSite=None; Secure; Partitioned`, and over plain http
  `SameSite=Lax`. Sign-out clears it with the same attributes. `SOCAREGUARD_COOKIE_SECURE`
  (`auto`, `1`, `0`) overrides the choice.
- An origin check replaces the protection that `SameSite=Strict` gave: the sign-in and sign-out
  forms, and every request that changes state with the cookie and no `Authorization` header
  (including the release of a withheld draft, a GET that writes a ledger row), are refused with 403
  when their `Origin` (or else `Referer`) is another site. `SOCAREGUARD_ALLOWED_ORIGINS` lists
  further origins to accept.
- The sign-in redirects to `/supervisor?signin=1`. Arriving there without a sign-in shows a message
  that the browser did not keep the cookie, with a link to open the supervisor view in a new tab.
  In a frame, the sign-in page and the supervisor view show that link, and a review link opens in
  the same frame, where the cookie is kept. The queue hint then says that the review page opens in this
  frame, not in a new tab.

## Unreleased (round 6, 2026-09-28)

### Supervisor view

- `GET /supervisor` shows the ledger chain check (rows, head hash, first gap, and the head hash
  that the server last logged), the withheld drafts that no supervisor has released yet, filter
  chips for pack, category, actor, kind and dates, one period of escalations, releases, overrides,
  accepted rewrites and opened reviews, and the counts for the period. `GET /v1/supervisor/summary`
  returns the same content as JSON. The rows carry no note or reply text.
- With `SOCAREGUARD_SUPERVISOR_KEYS` set, both need a supervisor key. Without keys, a sandbox login
  (`admin` / `demo1234`, in `proxy/demo_login.py`) opens them and the ledger records the actor as
  `admin (sandbox login)`. The login is for demonstration only and must be replaced with proper
  authentication before any production deployment, as the module, the route, the form and the
  README state.
- `POST /v1/sessions/{id}/review-token` issues a read-only review token for 30 minutes and writes a
  `review_opened` ledger row. The token opens the session's GET routes only. On its own it returns
  the pseudonymised view (no re-identified reply, no replacement map, flags quoted with stand-ins,
  no detection event, generalisation rule ids only). The session's own token or a supervisor key opens the
  full view.
- The panel keeps each session token in `sessionStorage`, opens `/?session=<id>&review=<token>`
  read-only with its controls disabled, and links to the supervisor view from the footer
  (`#supervisor-link`).
- `Ledger.rows_since` reads one period in one pass, and `review_opened` is one of the action kinds.
  The session index gains a `review_tokens` table (token hashes only).

## Unreleased (2026-09-27)

- With `SOCAREGUARD_TRUST_PROXY=1`, the panel's integration snippet uses the scheme and host
  forwarded by the reverse proxy, so it shows the public `https` URL.
- Without API keys, releasing a withheld draft also requires the session token.
- The sandbox banner and the README state that the conduct taxonomy is a draft that has not yet
  been reviewed by social-work practitioners.

### Results on corpus v1.1 (tag `results-v1.1`)

Every evaluation the paper reports was re-run on the amended corpus v1.1 with the code of commit
ddd838a, with the settings of the v1 runs: detection (full, without GLiNER2-PII, recognisers
only), round trip, the conduct screen (GPT-4.1 at temperature 0, threshold sweep, moderation
baseline at 0.3), the second judge (Claude Sonnet 5 on the first 60 drafts per pack) and utility
(10 notes per pack, GPT-4.1-mini and Claude Sonnet 5 as provider and judge). The plain `v1.1`
detection and round-trip files are replaced (the earlier ones used the code before the leak fix
and the corpus before the FSC renames). The `v1.1-code4868da4` files and every v1 file are
unchanged. `docs/metrics.md` now reports v1.1 and ends with a table of the paper's v1 numbers
beside the v1.1 values.

### Names inside a kept attribute clause reached the provider

Rounds 4 and 5 of the stakeholder review (d351ac1, 680e9a4) kept the sentence of a long offence,
disability, diagnosis or protection-order clause and replaced only the words naming the
condition. The sanitiser still removed the names inside such a clause from substitution, on the
assumption that the whole clause would be replaced, so those names went to the provider as
written. On corpus v1.1 the round-trip evaluation found 291 of 2,970 gold direct strings in the
outbound text, and the live `/v1/chat/completions` path had the same leak for every audience
setting. The recorded UC3 payload carried the client's given name.

- Names inside a clause that keeps its wording now receive surrogates with the other names,
  longest first, are substituted inside the clause's outbound text, and are stored in the vault,
  so a reply that uses them restores.
- The long-clause rewrite replaces the whole phrase that names the condition, offence or order,
  with its article and modifiers ("seated in a power wheelchair" becomes "seated in a mobility
  aid", not "seated in a power a physical disability"). Qualifiers that change what a sentence
  asserts ("alleged", "suspected") are kept. When no clean rewrite exists (a verb such as
  "caught vaping", an adjective before a noun), the clause becomes the whole-clause statement.
  Protection-order clauses name any order type as "protection order" and drop its dates.
- The filter that discards a facility or school hit without a capital letter no longer applies to
  employers, so a generic employer such as "a shipyard" is detected again. Round 4 had added it,
  and employer recall on v1.1 had fallen from 0.80 to 0.16.
- Regression tests cover a name inside each kind of kept clause, through the sanitiser and
  through the proxy endpoint for each audience setting, the ungrammatical rewrites, and a
  lower-case employer.
- Scenario replay: the UC2 and UC3 outbound payloads change, so their `send` events were
  re-derived in replay mode without a model call. UC2 hash `fc45194b…` becomes `6ac57dab…`
  (the husband's full name now has a surrogate, which changes the surrogate draw), and UC3 hash
  `fe91e789…` becomes `9ed9c5f8…` (the client's given name inside the diagnosis clause is now
  substituted, and "the cafe" is generalised as an employer). The recorded UC2 reply was not
  regenerated. Its surrogate names and case reference were mapped to the new ones by literal
  substitution. UC1 and UC4 payloads are byte-identical.

### Corpus v1.1: invented institution names

An audit found that the synthetic corpus named real Singapore institutions although the corpus
README described them as fictional. Six school stems in the identifier pool belong to current MOE
schools, one shelter name is a real family-violence shelter, and the v1 notes also carried a real
youth-services organisation and a real family service centre from an earlier version of the
pool. The UC1 scenario placed its fictional young offender at one of these schools.

All of them are now invented names, checked against MOE's school list on data.gov.sg and by web
search. A day activity centre that shared its name with a special education school was renamed
as well. Pool sizes and order are unchanged, so seeded draws select the same entries.

- The notes were rewritten with recomputed gold offsets. They are identical to a fresh injection
  from the v1 templates with the v1 pools after the same renames. Seeds, labels and span counts
  do not change.
- The drafts were edited by literal substitution and were not regenerated. One draft that named
  a real school on its own now names an invented one, and a placeholder address now uses
  `example.org`.
- Estates, streets, public bodies, the public hospitals, IMH, the polyclinics and the Singapore
  Boys' Home are real and were kept. `corpus/README.md` lists them.
- Four notes named an FSC by its town ("Tampines FSC" twice, "Ang Mo Kio FSC", "Queenstown
  FSC"), which matches the informal name of a real centre. They now read "Harbourlight FSC",
  "Meadowvale FSC" and "Riverbend FSC", names from the invented FSC pool that match no FSC
  operator on the MSF and ICA lists or in a web search. The gold span becomes a FACILITY span
  over the whole name in place of the ESTATE span over the town (ESTATE 309, FACILITY 294), the
  six drafts that repeat these names were edited the same way, and three sweep candidates had
  their offsets moved. v1.1 had not yet been reported, so it was amended in place.
- `configs/corpus-v1.1.yaml` records the version, and `configs/corpus-v1.yaml` is unchanged.
- The UC1 scenario, the escalation fixture and the tests use the new school name. Every
  scenario's outbound payload is byte-identical to the recorded one, so the recorded payload
  hashes stand.
- Detection and round-trip metrics were re-run on v1.1 and written beside the v1 results. Files
  with the `v1.1-code4868da4` suffix use the code of commit 4868da4, which produced the v1
  results. That code reproduces every v1 number exactly on the v1 notes. On v1.1 it finds one
  more third-party name, so full-pipeline leakage is 27 of 2,970 direct spans (0.91%) rather
  than 28 (0.94%), and consistency is 296 of 300 notes rather than 295. The ablation rows do not
  change. Files with the plain `v1.1` suffix use the current code.
- The current code does not reproduce the v1 numbers on the v1 notes. On v1 it gives leakage of
  39 of 2,970 (1.31%) and leaves 291 gold direct strings in the round-trip outbound text rather
  than 2. This drift predates the renaming and needs its own investigation.
- The v1 result files, `docs/metrics.md` and the screen and utility results are unchanged. The
  screen and utility numbers were measured on the v1 text.

## 2026-09-07: revisions after internal testing

These changes follow five rounds of internal testing with simulated stakeholder personas.

### Proxy, vault and ledger

- The identity map is kept per request, and the session routes require a session token.
- An escalation withholds the draft, including its flags, and a supervisor can release it with a
  reason.
- The vault is keyed per entity. Restoration is safe when surrogates are ambiguous, and a
  surrogate is reused within a session.
- `never_leak` patterns are enforced.
- Polarity rules for offence, capacity and PPO status, with a regression suite and
  scenario-level outbound tests.
- The audience gate lets external recipients take precedence and knows each pack's statutory
  recipients.
- New recognisers for hospitals, passports, bank accounts, handles and vehicles. Titled names are
  detected.
- Role words, scheme names and order acronyms are never substituted.
- Ledger rows record the recipients, actor attestation, pack hash, rules fired, build, audience
  and leak detail.
- A retention sweep purges old mappings.
- A provider or judge failure fails closed with HTTP 503.
- Errors use the OpenAI error envelope. New endpoints are `/v1/models`, `/v1/packs`,
  `/v1/ledger` and session purge.

### Panel

- A legend, and plain-language flag cards that show the judge's reason.
- Per-flag overrides, rewrite acceptance, and regeneration with a comparison strip.
- The audience gate can be tried again within the same session.
- An escalation chip with supervisor release.
- The shipped chips replay the recorded reply by default.
- An integration snippet and operator documentation.

## 2026-09-06

- The demo video was re-cut with title and end cards, burned-in full-sentence captions, no
  audio, and live waits trimmed to eight seconds with the measured latency stated. The final cut
  is 2:31. The recording tooling is separate and is not part of this repository.
- Sanitiser fixes found during the recording takes:
  - The instruction line before the first blank line is never generalised (`attribute_floor`).
  - A NAME needs an uppercase letter.
  - A leading verb such as "Attends" is trimmed from facility and school spans.
  - Adjacent identical generalised phrases collapse to one.
  - The article before a generalised phrase is dropped ("at a cafe" becomes "at an employer",
    not "at a an employer"), including when a generalised attribute precedes it.
  - A two-letter surname gets its derived restore form.
- The panel endpoint lists derived vault pairs. The scenario fixtures were re-recorded on the
  fixed code.

## demo-v1 (2026-09-05)

- Transparency panel at `/` with four columns and highlighted substitutions, flag cards with
  clause, evidence and rewrite, the baseline for contrast, an override form, the event stream,
  and scenario chips.
- Sandbox mode with a banner and a per-address rate limit.
- A `Dockerfile` for a Hugging Face Space with models warmed into the image, and a
  `docker-compose.yml` for an agency server.
- A first narrated demo video (154 s), later superseded by the captions-only cut.

## screen-v1 (2026-09-05)

- Inbound conduct screen on the pseudonymised reply. A clause-grounded LLM judge returns
  verbatim evidence, a confidence and rewrites.
- Over-caution and invented-identifier rules, and an audience gate for the disclosure categories.
- A moderation baseline for contrast. ExpGuard is wired in, but its weights are gated.
- Policy packs v1 with complete cross-cutting categories. I14 is scoped to external audiences.
- Decisions are pass, annotate, regenerate or escalate. Escalations cannot be overridden.
- Screener metrics on the labelled drafts (F1, AUPRC, FPR, per label, baseline overlap) with a
  cross-provider judge check. All four scenarios pass every assertion with the live judge.

## proxy-v1 (2026-09-05)

- OpenAI-compatible FastAPI proxy with a per-request policy pack, the event stream in the
  response, an override endpoint and ledger verification.
- A LiteLLM Proxy guardrail class over the same core.
- Detection with Singapore recognisers, gazetteers, Presidio, GLiNER2-PII and cue-lexicon
  attributes, followed by trust-ordered overlap resolution, name propagation and address merging.
- Generalisation rules per policy pack, and type-consistent surrogates with token-level
  collision avoidance.
- An AES-256-GCM SQLite vault and a hash-chained JSONL ledger.
- Metrics for span P/R/F1 (exact and relaxed), leakage rate, recall by name origin, attribute
  recall, round-trip consistency, injectivity and fidelity, and per-provider utility retention.
- Scenario replay drives the real guard, and the four Use Case replies are recorded live.

## corpus-v1 (2026-09-05)

- 300 synthetic case notes with three-layer gold annotation, 600 labelled drafts, sweep report.
- Four scenario scripts, policy packs v0, conduct taxonomy v0.
