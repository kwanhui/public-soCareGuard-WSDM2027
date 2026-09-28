# Corpus v1.2: compliant drafts for an external reader

Corpus v1.2 is corpus v1.1 with 90 compliant layer-3 drafts appended, 30 per pack. In v1.1, every compliant draft is an internal case summary for the supervising social worker, and every referral draft carries a labelled failure (I10, I13 or I14). The audience gate, which scores the disclosure categories I10 and I14 only when the instruction names an external reader, was therefore never tested against a compliant draft written for someone outside the case team. The v1.2 drafts provide that test.

## What was added

| Pack | Referral notes | School letters | Employer letters | File |
|---|---|---|---|---|
| disability | 15 | 0 | 15 | `disability-external-v1.2.jsonl` |
| domestic-violence | 10 | 10 | 10 | `domestic-violence-external-v1.2.jsonl` |
| youth-offending | 15 | 15 | 0 | `youth-offending-external-v1.2.jsonl` |

Each draft comes from an existing v1.1 note, and no note is used twice within a pack. A school letter is drawn from the notes that name a school and an employer letter from the notes that name an employer. Because the disability notes name no school and only one youth note names an employer, the mix differs by pack. Referral notes use the same instruction as the v1.1 referral drafts ("Draft a referral note (about 100 words) to another agency ..."). For the school and employer letters, the instruction states that the client or parent has consented and asks the drafter to share only what the recipient needs to know (`TASKS` in `src/socareguard/corpus/drafts.py`).

The drafts were written by the same drafting model and prompt as the v1.1 compliant drafts: `gpt-4.1-mini` at temperature 0.7, the v1.1 compliant system prompt, and the same "Case note ... Task ..." layout. Every row carries label `NONE` and `audience: "external"`. As in v1.1, the label is a generation-intent label: it records the instruction that the drafter received, not an expert judgement of the letter.

The drafts are the unguarded drafter output on synthetic notes, as the v1.1 drafts are. The notes were sent to the drafting model without the outbound guard, so a letter can carry the synthetic client's full name and NRIC as written in the note. These names and NRICs are synthetic by construction, since the note generator wrote them and none was taken from a real record. Removing them would defeat the corpus's purpose, which is to measure how often the conduct screen flags a compliant letter as written.

## Files that did not change

No v1.1 note, v1.1 draft file (`<pack>.jsonl`) or line of `configs/corpus-v1.1.yaml` was changed. The v1.2 configuration is `configs/corpus-v1.2.yaml`, and the drafts were produced by

```
python3 -m socareguard.corpus drafts-external --config configs/corpus-v1.2.yaml
```

Before the run, the estimate was USD 0.05 at list prices (45,413 input tokens counted with o200k_base, 200 output tokens per call assumed). The 90 letters came to 12,240 output tokens, or about USD 0.04 in total.

## Checks

The new drafts were scanned for the real institution names that v1.1 replaced, for email addresses, and for titled names that do not occur in the source note. None was found. `tests/test_corpus_v12.py` repeats these checks on every test run, together with the counts, labels and audiences above.

## Use in the screen evaluation

`python3 -m socareguard.eval screen --corpus v1.2 --tag v1.2` scores the 600 v1.1 drafts and the 90 external drafts together. For the compliant drafts, it reports the false-positive rate with and without the audience gate, separately for internal and external drafts. This run belongs to the v1.2 re-measurement and has not been run yet.
