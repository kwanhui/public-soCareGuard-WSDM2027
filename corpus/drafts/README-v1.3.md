# Corpus v1.3: compliant drafts for the client's care team

Corpus v1.3 is corpus v1.2 with 30 compliant layer-3 drafts appended, 10 per pack, each written for one of the client's own care-team providers. The screen reads I10 within a care-team recipient's role (a draft reading of SASW A.6.d pending practitioner review), but only 3 of the 90 v1.2 external drafts name such a recipient, all of them youth-offending school letters. The care-team tier therefore had almost no compliant drafts to be measured against, and the v1.3 drafts provide them.

## What was added

| Pack | Task | Recipient named in the "To:" line | Drafts | File |
|---|---|---|---|---|
| disability | `dac_support_note` | Day Activity Centre staff | 5 | `disability-careteam-v1.3.jsonl` |
| disability | `clinic_handover` | the client's clinic | 5 | `disability-careteam-v1.3.jsonl` |
| domestic-violence | `shelter_note` | Shelter caseworker | 5 | `domestic-violence-careteam-v1.3.jsonl` |
| domestic-violence | `polyclinic_followup` | the client's polyclinic doctor | 5 | `domestic-violence-careteam-v1.3.jsonl` |
| youth-offending | `school_counsellor_note` | School counsellor | 5 | `youth-offending-careteam-v1.3.jsonl` |
| youth-offending | `cocase_note` | Co-case agency worker | 5 | `youth-offending-careteam-v1.3.jsonl` |

Each draft comes from an existing v1.1 note, and no note is used twice within a pack (a note may also carry a v1.2 draft). Each task draws from the notes whose text fits its recipient: a note that mentions a day activity centre for the centre note, a clinic, hospital or medical social worker for the clinic handover, a shelter for the shelter note, a polyclinic or clinic for the follow-up note, and a school for the school counsellor note. The co-case note can come from any youth-offending note. The patterns are `_CARETEAM_NEEDS` in `src/socareguard/corpus/drafts.py`, and the draw is seeded (`configs/corpus-v1.3.yaml`).

## The instructions

Every instruction does three things (`TASKS` in `src/socareguard/corpus/drafts.py`). First, it records consent for the specific purpose, in the worker's voice: "The client agreed that I may tell the centre what support is needed on the bus and at the centre", or, for a young person, "The young person and the parent agreed that I may tell the school counsellor what support is needed at school and which appointments affect attendance". Second, it asks for need-to-know content only, that is, functional needs, appointments and practical arrangements, and it excludes a diagnosis, the offence and the history of the case. Third, it fixes the first line of the note ("To: Day Activity Centre staff", "To: the client's polyclinic doctor"), so that the address block names the recipient.

The drafts were written by the same drafting model and prompt as the v1.1 and v1.2 compliant drafts: `gpt-4.1-mini` at temperature 0.7, the v1.1 compliant system prompt, and the same "Case note ... Task ..." layout. Every row carries label `NONE`, `audience: "care-team"` and `recipient_kind: "care-team"`. As in v1.1 and v1.2, the label is a generation-intent label: it records the instruction that the drafter received, not an expert judgement of the note. Some drafts may go beyond the instruction. For example, the clinic handover from `disability-009` names the hospital at which the client's appointments are held, which can itself suggest a diagnosis.

The drafts are the unguarded drafter output on synthetic notes, as the v1.1 and v1.2 drafts are. The notes were sent to the drafting model without the outbound guard, so a note can carry the synthetic client's full name and NRIC as written in the source note. These names and NRICs are synthetic by construction, since the note generator wrote them and none was taken from a real record.

## Recipient kind

`recipient_kind` was written by `scripts/label_recipient_kind.py`, which now covers the v1.3 files as well as the v1.2 files. It reads the address block (the lines before the "Re:" line) with `resolve_audience` from `src/socareguard/screen/rules.py`, the function that the proxy uses. All 30 address blocks resolve to care-team, and so does each task instruction on its own. Re-running the script leaves the v1.2 files unchanged.

## Files that did not change

No v1.1 or v1.2 note, draft file or configuration was changed. The v1.3 configuration is `configs/corpus-v1.3.yaml`, and the drafts were produced by

```
python3 -m socareguard.corpus drafts-careteam --config configs/corpus-v1.3.yaml
```

Before the run, the estimate was USD 0.016 at list prices (16,967 input tokens counted with o200k_base, 200 output tokens per call assumed). The 30 notes came to 3,552 output tokens, or about USD 0.013 in total.

## Checks

The new drafts were scanned for the real institution names that v1.1 replaced, for private repository names and paths, for email addresses other than at example.org, and for titled names that do not occur in the source note. None was found. `tests/test_corpus_v13.py` repeats these checks on every test run, together with the counts per pack and task, the labels and audiences, the care-team reading of every address block, and the reproducibility of the draw.

## Use in the screen evaluation

`python3 -m socareguard.eval screen` does not yet accept `--corpus v1.3`. Scoring these drafts needs the screen loader to append the care-team files and to read their `recipient_kind`, which is a separate change to `src/socareguard/eval/`.
