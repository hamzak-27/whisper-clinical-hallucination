# Lab notes

## 2026-11-15: Pilot 0 (isolated synthetic noise)
- faster-whisper base and small (int8, CPU) on 20 s of synthetic 960 Hz beeps and on 20 s of room noise produced **empty output**. A 10 s mid-sentence pause with silence, room noise or beeps produced **no fabrication**.
- Conclusion: isolated synthetic noise is not a meaningful trigger. Move to long-form sessions, real noise, and context.

## 2026-11-15: Pilot 1 (ClinHallu pilot split, 104 sessions = 4 scripts × 13 gap kinds × gaps {1 s, 12 s})
Run status: base/default finished (104 sessions). small/default was partial (65/104) because the system stopped the job when memory ran low. no_prev presets were not run.

| model/preset | n | WER % | sessions with gap fabrication % |
|---|---|---|---|
| base / default | 104 | 12.7 | 39.4 |
| small / default | 65 (partial) | 8.3 | 10.8 |

**Main qualitative finding: medication-order duplication.** On long pauses inside a dictation, Whisper does not write the generic "Thank you for watching". It **copies a medication order from earlier in the context into the pause**. Example (small, default decoding, 12 s *digital silence* gaps, seed 1001):

- Reference contains "Patient takes azithromycin 250 milligrams every morning" **once**.
- The hypothesis contains it **5 times**. It also **replaces** the spoken order "Started on ondansetron eight milligrams three times daily" with the azithromycin line, so one order is dropped and another is fabricated in its place.
- Seed 1002 (base): "Resume montelukast 10 milligrams every 8 hours" is duplicated into the trailing gap. The same thing happens with sneezing, sipping and snoring fillers.

Why this matters: the fabricated content is **clinically plausible**. It is a duplicate drug order taken from the patient's own record, so a reviewer cannot spot it as "weird text" the way they would spot YouTube outro phrases. Likely mechanism: `condition_on_previous_text=True` plus the 30 s windowing.

Caveats:
- n = 4 scripts. This is only an existence proof, not a rate estimate.
- The DRUG error rate (60–73%) is mostly **spelling** ("Montalucas", "asethromycin"), and possibly also Kokoro mispronouncing drug names. Since fixed: drug-level metrics now use fuzzy matching, so spelling errors are counted separately from wrong, missing or duplicated orders.
- Gap fabrication at 1 s gaps is partly word-timestamp spill-over. Report gaps of 5 s or more as primary.


## 2026-11-15: Pilot 1 complete (default vs `condition_on_previous_text=False`)
All 4 runs × 104 sessions. "dup order" = a dictated drug appears more often in the transcript than in the script (fuzzy-matched, so misspellings don't count).

| model / preset | WER % | sessions with duplicated order (12 s gaps) | dup orders / 100 dictated (12 s) | insertions / 100 words (1 s → 12 s gaps) |
|---|---|---|---|---|
| base / default | 12.7 | **34.6%** | 12.1 | 3.4 → 7.6 |
| base / no_prev | 12.2 | **0%** | 0 | 2.9 → 5.5 |
| small / default | 11.9 | **21.2%** | 17.6 | 0.5 → 11.4 |
| small / no_prev | 8.9 | **0%** | 0 | 1.1 → 5.5 |

- **Duplicated medication orders come entirely from previous-text conditioning.** With conditioning off, they drop to zero in both models, and small's WER improves (11.9 → 8.9).
- No duplicates occur at 1 s gaps under either preset. The effect needs long pauses.
- **Residual insertions remain** (about 5.5 / 100 words at 12 s gaps vs 1–3 at 1 s). Examples: fragments of misrecognized drug names ("furos mined", "Onden-Cetron"), repeats at 30 s window boundaries ("three times daily. daily."), and short fillers ("You", "mmmm", "patients").
- **Metric issue found:** the timestamp-based "gap fabrication" count overestimates under no_prev. Misrecognized *real* words get timestamps that drift into the gap and are counted as fabricated. Fix: count only true insertions (not substitutions), with a tolerance at gap edges, and store word timestamps in the results so this can be recomputed without re-running ASR.
- No negation errors in any run. Missing drugs (12–24%) are the same across presets, so they reflect drug-name recognition or TTS pronunciation, not hallucination.

## 2026-11-15: Large models (Kaggle T4, fp16): large-v3 and large-v3-turbo
Same pilot split, rebuilt on Kaggle from the same seeds (104 sessions per run). Metrics here don't depend on timestamps, so they compare fairly with the CPU runs.

**12 s pauses:**

| model / preset | WER % | ins / 100 words | sessions with duplicated order | dup orders / 100 dictated | allergy statements lost |
|---|---|---|---|---|---|
| base / default | 15.1 | 7.6 | 34.6% | 12.1 | 0/26 |
| base / no_prev | 13.3 | 5.5 | 0% | 0 | 0/26 |
| small / default | 18.5 | 11.4 | 21.2% | 17.6 | 4/26 |
| small / no_prev | 11.7 | 5.5 | 0% | 0 | 2/26 |
| large-v3-turbo / default | 26.7 | 21.9 | 19.2% | 11.0 | 0/26 |
| large-v3-turbo / no_prev | **5.6** | **1.6** | 0% | 0 | 0/26 |
| large-v3 / default | **30.0** | **26.8** | **50.0%** | **52.2** | **4/26** |
| large-v3 / no_prev | 5.4 | 2.8 | 0% | 0 | 0/26 |

**1 s pauses:** large-v3 default has 1.7% WER and 0 duplicated orders. Same model and same scripts; only the pause length changes.

Findings:
- **The best model is the worst on long pauses.** large-v3 is the most accurate at 1 s pauses (1.7% WER) and the worst at 12 s pauses (30% WER, half of the sessions with duplicated orders).
- **Duplicated orders come entirely from previous-text conditioning.** In all 4 models they drop to 0 when it is off. large-v3 WER at 12 s goes 30.0 → 5.4.
- **Repetition loops delete real content.** Worst case (large-v3, room tone, seed 1002): "Resume Montelukast 10 mg every 8 hours" is repeated 13 times, and the spoken "Allergic to sulfa drugs which causes hives" is **missing**. All 4 large-v3 allergy losses happen this way.
- **Invented clinical instructions** (large-v3 default, silence, seed 1001): "…Stop at a hospital and come back every two weeks." This was never dictated. Also "Increase insulin 10 units every morning" was duplicated.
- Even with no_prev, large-v3 adds "Thank you for watching." in the trailing pause (room tone, seed 1002). The classic hallucination remains, but it is rare.
- Noise type: room tone (18 duplicated orders) and breathing (17) are worst for large-v3 default; mouse clicks (0) are least harmful. With n = 4 per cell, this ranking is not reliable yet.
- Stricter timestamp metric (GPU runs only), sessions with invented words inside pauses, default → no_prev: large-v3 58% → 31%, turbo 48% → 6%.

Caveats and detector notes:
- **High variance across scripts.** Duplicated orders for large-v3 default by script: 0 / 17 / 26 / 52. Four scripts are not enough; the next step is a larger split.
- Drug-mention detector false positive: "tug of **war and**" → *warfarin*. **No model invented a new drug name** in this pilot. The 0.27 "novel" figure for large-v3 is this artifact.
- An earlier allergy check counted "sulfa" → "sulfur" as a loss. Recounted with prefix matching; the table uses the corrected numbers.

## 2026-11-15: Text post-processing filters on the pilot (no extra GPU)
`boh` removes stock phrases ("thank you for watching"…), using a small hand-made list in the spirit of Barański et al., not their released list. `dedup` drops a sentence that repeats one of the previous 3.

12 s pauses:

| model / preset | WER % | sessions with duplicated order | dup orders / 100 dictated |
|---|---|---|---|
| large-v3 / default | 30.0 | 50% | 52.2 |
| large-v3 / default + boh | 29.6 | 50% | 52.2 |
| large-v3 / default + dedup | 11.9 | 19% | 9.3 |
| large-v3 / no_prev | 5.4 | 0% | 0 |
| large-v3 / no_prev + boh + dedup | 5.0 | 0% | 0 |
| turbo / default + dedup | 20.0 | 4% | 1.7 |
| turbo / no_prev | 5.6 | 0% | 0 |

- Stock-phrase filtering barely helps here. These hallucinations are clinical content, not YouTube phrases.
- De-duplication helps but leaves large-v3 at 19% of sessions. The repeats are not always adjacent or identical (spelling varies), and it cannot bring back content the loop already deleted.
- No filter matches simply turning off previous-text conditioning. At 1 s pauses all variants are unchanged (large-v3 ≈ 1.7% WER), so the filters cost nothing there.
