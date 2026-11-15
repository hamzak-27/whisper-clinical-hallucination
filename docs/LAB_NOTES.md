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
