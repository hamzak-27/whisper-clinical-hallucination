"""Build ClinHallu audio sessions: TTS sentences joined by controlled gaps.

Gap fillers: silence | room (low-level pink noise) | esc:<category> (real ESC-50 clips) | alarm (IEC-style tones).
Writes data/clinhallu/<split>/<id>.wav and a manifest.jsonl with sentence + gap intervals and word tags.
"""
import argparse, json, random
from pathlib import Path
import numpy as np, pandas as pd, soundfile as sf
from scipy.signal import resample_poly
from scripts_gen import make_dictation, sentence_text, word_tags

ROOT = Path(__file__).resolve().parents[1]
SR = 16000
ESC_DIR = next((ROOT / "data/raw/esc50").glob("ESC-50*"), None)
CLINICAL_ESC = ["coughing", "breathing", "sneezing", "keyboard_typing", "clock_tick",
                "door_wood_knock", "footsteps", "mouse_click", "drinking_sipping", "snoring"]
VOICES = ["am_michael", "af_heart", "am_adam", "af_bella", "bm_george", "bf_emma", "am_eric", "af_nicole"]

_tts = None
from functools import lru_cache
@lru_cache(maxsize=4096)
def tts(text, voice, speed):
    global _tts
    if _tts is None:
        from kokoro_onnx import Kokoro
        _tts = Kokoro(str(ROOT / "models/kokoro/kokoro-v1.0.onnx"), str(ROOT / "models/kokoro/voices-v1.0.bin"))
    a, sr = _tts.create(text, voice=voice, speed=speed, lang="en-us" if voice[0] == "a" else "en-gb")
    return resample_poly(a, 2, 3).astype(np.float32)  # 24k -> 16k


def pink(n, rng, level_db=-55):
    w = np.fft.rfft(rng.standard_normal(n)); f = np.arange(len(w)); f[0] = 1
    x = np.fft.irfft(w / np.sqrt(f), n)
    return (x / (np.abs(x).max() + 1e-9) * 10 ** (level_db / 20)).astype(np.float32)


def alarm(n, rng):
    """IEC 60601-1-8-like medium-priority burst: 3 pulses of a 5-harmonic tone, repeating."""
    t = np.arange(n) / SR; f0 = rng.choice([440, 523, 660])
    tone = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in range(1, 6))
    period = 3.0; ph = t % period
    gate = ((ph < 0.2) | ((ph > 0.4) & (ph < 0.6)) | ((ph > 0.8) & (ph < 1.0)))
    return (0.05 * tone * gate).astype(np.float32)


_esc_meta = None
def esc_clip(cat, n, rng):
    global _esc_meta
    if _esc_meta is None:
        _esc_meta = pd.read_csv(ESC_DIR / "meta/esc50.csv")
    files = _esc_meta[_esc_meta.category == cat].filename.tolist()
    out = np.zeros(0, np.float32)
    while len(out) < n:
        x, sr = sf.read(ESC_DIR / "audio" / rng.choice(files), dtype="float32")
        if sr != SR: x = resample_poly(x, SR, sr).astype(np.float32)
        out = np.concatenate([out, x])
    x = out[:n]
    return x / (np.abs(x).max() + 1e-9) * 10 ** (rng.uniform(-30, -15) / 20)


def filler(kind, n, rng):
    base = pink(n, rng)
    if kind == "silence": return np.zeros(n, np.float32)
    if kind == "room": return base
    if kind == "alarm": return base + alarm(n, rng)
    if kind.startswith("esc:"): return base + esc_clip(kind[4:], n, rng)
    raise ValueError(kind)


def build_session(seed, gap_s, kind, voice, speed):
    rng = np.random.default_rng(seed); sents = make_dictation(seed)
    audio, segs, t = [], [], 0.0
    lead = int(0.5 * SR); audio.append(pink(lead, rng)); t += 0.5
    for i, s in enumerate(sents):
        a = tts(sentence_text(s), voice, speed)
        segs.append({"type": "speech", "start": t, "end": t + len(a) / SR, "words": word_tags(s)})
        audio.append(a); t += len(a) / SR
        g = gap_s if i < len(sents) - 1 else max(gap_s, 2.0)  # trailing non-speech too
        n = int(g * SR); audio.append(filler(kind, n, rng) if g > 0 else np.zeros(0, np.float32))
        if g > 0: segs.append({"type": "gap", "start": t, "end": t + g, "kind": kind})
        t += g
    return np.concatenate(audio), segs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="pilot")
    ap.add_argument("--n", type=int, default=20, help="dictations per condition")
    ap.add_argument("--gaps", default="0.5,5,15")
    ap.add_argument("--kinds", default="silence,room,alarm," + ",".join("esc:" + c for c in CLINICAL_ESC))
    ap.add_argument("--seed0", type=int, default=1000)
    a = ap.parse_args()
    out = ROOT / "data/clinhallu" / a.split; out.mkdir(parents=True, exist_ok=True)
    man = open(out / "manifest.jsonl", "w")
    from tqdm import tqdm
    jobs = [(g, k, i) for g in map(float, a.gaps.split(",")) for k in a.kinds.split(",") for i in range(a.n)]
    for g, k, i in tqdm(jobs):
        seed = a.seed0 + i  # same text across conditions -> paired comparison
        r = random.Random(seed); voice = r.choice(VOICES); speed = r.choice([0.9, 1.0, 1.1])
        x, segs = build_session(seed, g, k, voice, speed)
        uid = f"{k.replace(':', '-')}_g{g:g}_{seed}"
        sf.write(out / f"{uid}.wav", x, SR, subtype="PCM_16")
        man.write(json.dumps({"id": uid, "seed": seed, "gap": g, "kind": k, "voice": voice, "speed": speed,
                              "dur": len(x) / SR, "segments": segs}) + "\n")
    man.close()


if __name__ == "__main__":
    main()
