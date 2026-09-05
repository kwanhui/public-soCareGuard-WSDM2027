# SoCareGuard synthetic corpus (v1)

Synthetic Singapore social-work case notes with exact gold spans, built to evaluate the
outbound detectors and the inbound conduct screen. **No real case material was used at any
stage.** Every person, identity number, address, phone number, school and case reference is
generated; estates and towns are real Singapore place names because they are the
quasi-identifiers under test.

## Layers

| Layer | Command | Output | What it adds |
|---|---|---|---|
| 1 Narrative | `python3 -m socareguard.corpus generate` | `templates/*.jsonl` | An LLM writes the note in a practitioner's voice with typed placeholders (`{{CLIENT_NAME}}`, `{{NRIC}}`, `{{ATTR:dv_disclosure=...}}`, `{{CS:malay=...}}`). Never invents an identifier. |
| 2 Injection | `python3 -m socareguard.corpus inject` | `notes/*.jsonl` | Deterministic substitution of Singapore-format surrogates. Exact character offsets become gold spans typed `DIRECT` / `QUASI` / `ATTRIBUTE` (TAB convention). Name spans carry an origin tag. |
| 3 Drafts | `python3 -m socareguard.corpus drafts` | `drafts/*.jsonl` | For each note, one compliant model draft and one instructed to exhibit a single labelled conduct failure (`I1` to `I14`, `OVER_CAUTION`). |
| Sweep | `python3 -m socareguard.corpus sweep` | `sweep-report.md` | Off-the-shelf detectors (Presidio, GLiNER) flag anything outside a gold span so spontaneous identifiers are caught, plus a fixed 30-note manual audit checklist. |

Configuration is `configs/corpus-v1.yaml` (seed, counts, model, code-switch share, name-origin
mix). The config is append-only once results are reported against it.

## What is real and what is fictional

- **Real**: HDB town names, postal sectors and street names (so an address is internally
  consistent), public bodies (MSF, MOE, ComCare, IMH, Youth Court), a few hospital and FSC names.
- **Fictional**: all people, NRIC/FIN numbers (valid check letters, random bodies), phone
  numbers, block and unit numbers, school names, shelters, day activity centres, and all case
  reference formats (`YC/2026/0412`, `FSC-2026-0288` and the like follow no real scheme).

## Labels are generation-intent labels

The conduct label on a layer-3 draft records the instruction the generator received, not an
expert judgement of the text it produced. Some "violating" drafts will be milder than intended
and some "clean" drafts will contain an unintended failure. Screener metrics computed against
these labels are therefore a demonstration of behaviour on scripted material, not validated
accuracy. Expert double-rating is deferred to the follow-on grant.

## Known limitations

- Generation and drafting use one provider (OpenAI); detection uses non-LLM models (Presidio,
  GLiNER) so there is no generator/detector circularity, but the drafts still share a house
  style with the notes.
- The generator occasionally invents an identifier in free text despite instructions. The
  sweep and the audit sample estimate the residual rate; notes with an unresolved spontaneous
  identifier are regenerated, never left with an unlabelled span.
- Dates of contact and durations are not annotated in v1; the sweep ignores Presidio's `DATE_TIME`
  detections for that reason.
- Code-switched fragments are the model's rendering of Singlish, Malay, Mandarin and Tamil, not
  transcripts of speakers.

## Statistics

From `python3 -m socareguard.corpus stats`.

### Corpus v1 (generated 2026-09-05, `configs/corpus-v1.yaml`, gpt-5-mini for notes, gpt-4.1-mini for drafts)

| | |
|---|---|
| Notes | 300 (100 per pack) |
| Gold spans | 4874: DIRECT 2970, QUASI 1203, ATTRIBUTE 701 |
| Name spans by origin | chinese 428, eurasian 385, indian 456, malay 413, western 420 |
| Attribute spans by key | capacity 78, diagnosis 76, disability 100, dv_disclosure 100, minor 100, offence 100, ppo 79, safety_plan 68 |
| Notes with a code-switched fragment | 58 (malay 7, mandarin 4, singlish 67, tamil 6) |
| Drafts | 600: 300 compliant (`NONE`) and 300 single-failure, 6 to 8 per label per pack (`I14` youth-offending only, `I11` not in domestic violence) |

| Category | Spans |
|---|---|
| ADDRESS | 114 |
| AGE | 301 |
| ATTRIBUTE | 701 |
| CASE_REF | 214 |
| DOB | 101 |
| EMPLOYER | 100 |
| ESTATE | 313 |
| FACILITY | 290 |
| NAME | 1409 |
| NRIC | 302 |
| PHONE | 137 |
| SCHOOL | 199 |
| THIRD_PARTY_NAME | 693 |

**Sweep and audit.** Presidio (`en_core_web_lg`) and GLiNER (`urchade/gliner_multi_pii-v1`)
flagged 121 detections outside gold spans in 84 of 300 notes.
Every candidate was reviewed: all are detector false positives on agency acronyms, role words,
language names and generic organisation phrases, and none is an invented person, identifier,
school or address. A manual read of the fixed 30-note audit sample with gold spans masked found
no direct identifier outside a span. It did find the model writing the client's age as a plain
number beside the `{{AGE}}` placeholder in 2 of 30 notes; that pattern was added to the
validator and the 12 affected notes corpus-wide were regenerated with their drafts. Earlier
validator additions from the same pass: placeholder keys written as field labels (3 notes) and
empty code-switch fragments (2 notes). Residual rate of unlabelled direct identifiers on the
audited sample: 0 of 30.
