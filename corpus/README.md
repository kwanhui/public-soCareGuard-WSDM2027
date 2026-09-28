# SoCareGuard synthetic corpus (v1.1)

Synthetic Singapore social-work case notes with exact gold spans, built to evaluate the
outbound detectors and the inbound conduct screen. **No real case material was used at any
stage.** Every person, identity number, address, phone number, school and case reference is
generated, and every school, shelter and service centre is invented. Estates and towns are real
Singapore place names because they are the quasi-identifiers under test.

## Layers

| Layer | Command | Output | What it adds |
|---|---|---|---|
| 1 Narrative | `python3 -m socareguard.corpus generate` | `templates/*.jsonl` | An LLM writes the note in a practitioner's voice with typed placeholders (`{{CLIENT_NAME}}`, `{{NRIC}}`, `{{ATTR:dv_disclosure=...}}`, `{{CS:malay=...}}`). Never invents an identifier. |
| 2 Injection | `python3 -m socareguard.corpus inject` | `notes/*.jsonl` | Deterministic substitution of Singapore-format surrogates. Exact character offsets become gold spans typed `DIRECT` / `QUASI` / `ATTRIBUTE` (TAB convention). Name spans carry an origin tag. |
| 3 Drafts | `python3 -m socareguard.corpus drafts` | `drafts/*.jsonl` | For each note, one compliant model draft and one instructed to exhibit a single labelled conduct failure (`I1` to `I14`, `OVER_CAUTION`). |
| Sweep | `python3 -m socareguard.corpus sweep` | `sweep-report.md` | Off-the-shelf detectors (Presidio, GLiNER) flag anything outside a gold span so spontaneous identifiers are caught, plus a fixed 30-note manual audit checklist. |

Configuration is `configs/corpus-v1.yaml` (seed, counts, model, code-switch share, name-origin
mix). The config is append-only once results are reported against it. Corpus v1.1
(`configs/corpus-v1.1.yaml`, 2026-09-27) is v1 with real private institution names replaced by
invented ones. Seeds, templates, labels and span counts are unchanged. The layer-2 notes equal a
re-run of `inject` on the v1 templates with the v1 identifier pools after the same renames,
except for the four notes that named an FSC by its town (see below).
Hospital, polyclinic, FSC and youth-home pools in `identifiers.py` were made fictional after v1
was injected, so `inject` at the current commit does not reproduce the v1 or v1.1 notes.

## What is real and what is fictional

The real names are HDB town names, postal sectors and street names, so that an address is
internally consistent. Public bodies are also real (MSF, MOE, ComCare, HDB, Youth Court, the
Singapore Boys' Home, ITE College Central, East and West), as are the public hospitals and
polyclinics that appear in the notes: Changi General Hospital, Khoo Teck Puat Hospital, Ng Teng
Fong General Hospital, the Institute of Mental Health (IMH), and Bedok, Jurong and Yishun
Polyclinics.

Everything else is fictional. This covers all people, NRIC/FIN numbers (valid check letters,
random bodies), phone numbers, block and unit numbers, and all case reference formats
(`YC/2026/0412`, `FSC-2026-0288` and the like follow no real scheme). Schools, polytechnics,
shelters, family service centres, day activity centres and youth homes other than the Singapore
Boys' Home are invented, and employers are generic descriptions ("a logistics firm in Tuas") that
name no company. School stems were checked against MOE's school list on data.gov.sg in September
2026. Shelter and centre names were checked by web search.

Four notes placed an FSC by its town ("Tampines FSC", "Ang Mo Kio FSC", "Queenstown FSC")
because the template wrote `{{ESTATE}} FSC`, which matches the informal name of a real centre.
In v1.1 these read "Harbourlight FSC" (disability-001, youth-offending-022), "Meadowvale FSC"
(disability-066) and "Riverbend FSC" (disability-089), names from the invented FSC pool, and
their gold span is a FACILITY span over the whole name instead of an ESTATE span over the town.
The same literal rename was applied to the six drafts that repeat them. These four notes no
longer equal a re-injection of their templates, which still read `{{ESTATE}} FSC`.

## Labels are generation-intent labels

The conduct label on a layer-3 draft records the instruction the generator received, not an
expert judgement of the text it produced. Some "violating" drafts will be milder than intended
and some "clean" drafts will contain an unintended failure. Screener metrics computed against
these labels are therefore a demonstration of behaviour on scripted material, not validated
accuracy. Expert double-rating is left to future work.

## Known limitations

- Generation and drafting use one provider (OpenAI). Detection uses non-LLM models (Presidio,
  GLiNER), so there is no generator/detector circularity, but the drafts still share a writing
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

In v1.1 the four town-named FSCs are FACILITY spans, so ESTATE is 309 and FACILITY 294. Every
other count, and the QUASI total of 1,203, is unchanged.

### Sweep and audit

Presidio (`en_core_web_lg`) and GLiNER (`urchade/gliner_multi_pii-v1`)
flagged 121 detections outside gold spans in 84 of 300 notes.
Every candidate was reviewed: all are detector false positives on agency acronyms, role words,
language names and generic organisation phrases, and none is an invented person, identifier,
school or address. A manual read of the fixed 30-note audit sample with gold spans masked found
no direct identifier outside a span. It did find the model writing the client's age as a plain
number beside the `{{AGE}}` placeholder in 2 of 30 notes. That pattern was added to the
validator, and the 12 affected notes corpus-wide were regenerated with their drafts. Earlier
validator additions from the same pass: placeholder keys written as field labels (3 notes) and
empty code-switch fragments (2 notes). Residual rate of unlabelled direct identifiers on the
audited sample: 0 of 30.

Corpus v1.2 (`configs/corpus-v1.2.yaml`) appends 90 compliant drafts for an external reader, 30 per pack (referral notes, and school and employer letters that stay within need-to-know), each written from an existing v1.1 note by the same drafting model and prompt. They are in `corpus/drafts/<pack>-external-v1.2.jsonl`, described in `corpus/drafts/README-v1.2.md`, and leave the v1.1 files unchanged. Like the v1.1 drafts, they are the unguarded drafter output on synthetic notes, so they carry the synthetic names and NRICs of those notes by construction.

Corpus v1.3 (`configs/corpus-v1.3.yaml`) appends 30 compliant drafts for the client's own care team, 10 per pack: a note to the day activity centre or the client's clinic (disability), to the shelter caseworker or the client's polyclinic doctor (domestic violence), and to the school counsellor or the co-case agency worker (youth offending). Each instruction records the consent for that specific disclosure and asks for functional needs, appointments and arrangements only, never a diagnosis or the history of the case. Every address block resolves to care-team under `resolve_audience`. The drafts are in `corpus/drafts/<pack>-careteam-v1.3.jsonl`, described in `corpus/drafts/README-v1.3.md`, and leave the v1.1 and v1.2 files unchanged. Like the earlier drafts, they are the unguarded drafter output on synthetic notes and carry synthetic names and NRICs by construction.
