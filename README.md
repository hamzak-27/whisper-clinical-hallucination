# Silence Is Not Safe: Whisper Hallucinations in Clinical Dictation

> 🚧 Work in progress. These are early pilot numbers and will change.

Whisper sometimes writes text that nobody said ([Koenecke et al., 2024](https://arxiv.org/abs/2402.08021)). In a medical note, that can mean an invented drug or dose in a patient record. This repo is a small, controlled benchmark for measuring that in synthetic clinical dictation.

## Early finding: duplicated medication orders

When a dictation has long pauses, Whisper (base and small) sometimes **copies an earlier medication order into the pause**, even when the pause is pure silence:

```
Spoken (once):   "Patient takes azithromycin 250 milligrams every morning."
Whisper-small:   ...Patient takes Azithromycin 250 milligrams every morning.
                    Patient takes Azithromycin 250 milligrams every morning.   ← not spoken
                    Patient takes Azithromycin 250 milligrams every morning.   ← not spoken
```

A repeated drug order looks plausible, so it is much harder to catch than generic hallucinated text. Pilot size: 4 scripts × 26 conditions. Details are in [`docs/LAB_NOTES.md`](docs/LAB_NOTES.md).

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

Large models on a Colab GPU: [`notebooks/colab_large_eval.ipynb`](notebooks/colab_large_eval.ipynb)

## License

Code: MIT. ESC-50 audio is CC BY-NC 3.0 (non-commercial use).
