# Silence Is Not Safe: Whisper Hallucinations in Clinical Dictation

> 🚧 Work in progress. These are early pilot numbers and will change.

Whisper sometimes writes text that nobody said ([Koenecke et al., 2024](https://arxiv.org/abs/2402.08021)). In a medical note, that can mean an invented drug or dose in a patient record. This repo is a small, controlled benchmark for measuring that in synthetic clinical dictation.

## Early findings (pilot)

When a dictation has long pauses (12 s of silence, room tone, a cough…), Whisper's default decoding **copies earlier medication orders into the pause**:

```
Spoken (once):   "Resume montelukast 10 mg every 8 hours."  ...  "Allergic to sulfa drugs which causes hives."
Whisper large-v3: "Resume Montelukast 10 mg every 8 hours." × 13      ← allergy statement is gone
```

| Whisper model | WER, 1 s pauses | WER, 12 s pauses | sessions with a duplicated drug order (12 s) | same, `condition_on_previous_text=False` |
|---|---|---|---|---|
| base | 10.2% | 15.1% | 35% | **0%** |
| small | 5.3% | 18.5% | 21% | **0%** |
| large-v3-turbo | 4.8% | 26.7% | 19% | **0%** |
| large-v3 | **1.7%** | **30.0%** | **50%** | **0%** |

- The most accurate model is the most affected.
- Turning off previous-text conditioning removes the duplicated orders in every model (large-v3 at 12 s pauses: 30% → 5.4% WER).

Pilot size: 4 scripts × 26 conditions, so treat the percentages as rough. Details: [`docs/LAB_NOTES.md`](docs/LAB_NOTES.md).

## How it works

- **Scripts:** templated dictations, with drugs, doses, negations and left/right tagged per word
- **Audio:** Kokoro TTS voices, with pauses filled by silence, room tone, alarms, or real sounds from ESC-50 (cough, breathing, keyboard…)
- **Scoring:** WER, words invented during pauses, errors on safety-critical words, and duplicated / missing / invented drug orders

## Run it

```bash
pip install faster-whisper jiwer kokoro-onnx soundfile pandas scipy tqdm
# put kokoro-v1.0.onnx + voices-v1.0.bin in models/kokoro/ and ESC-50 in data/raw/esc50/
cd src
python build_audio.py --split pilot --n 4 --gaps 1,12
python run_asr.py --split pilot --model small --preset default
python aggregate.py pilot
```

Large models on a GPU (Kaggle or Colab): [`notebooks/gpu_large_eval.ipynb`](notebooks/gpu_large_eval.ipynb)

## License

Code: MIT. ESC-50 audio is CC BY-NC 3.0 (non-commercial use).
