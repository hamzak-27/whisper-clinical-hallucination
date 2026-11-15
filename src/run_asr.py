"""Run faster-whisper over a ClinHallu split with a decoding preset; write per-session hyps + scores."""
import argparse, json, time
from pathlib import Path
import numpy as np, soundfile as sf
from faster_whisper import WhisperModel
from score import score_session

ROOT = Path(__file__).resolve().parents[1]
PRESETS = {
    # openai-whisper-like defaults: condition on previous text, temperature fallback
    "default": dict(beam_size=5, condition_on_previous_text=True),
    "no_prev": dict(beam_size=5, condition_on_previous_text=False),
    "no_prev_t0": dict(beam_size=5, condition_on_previous_text=False, temperature=0.0),
    "vad": dict(beam_size=5, condition_on_previous_text=True, vad_filter=True),
    "vad_no_prev": dict(beam_size=5, condition_on_previous_text=False, vad_filter=True),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="pilot"); ap.add_argument("--model", default="small")
    ap.add_argument("--preset", default="default"); ap.add_argument("--device", default="cpu")
    ap.add_argument("--compute", default="int8"); ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    d = ROOT / "data/clinhallu" / a.split
    man = [json.loads(l) for l in open(d / "manifest.jsonl")]
    if a.limit: man = man[: a.limit]
    m = WhisperModel(a.model, device=a.device, compute_type=a.compute)
    outp = ROOT / "results" / a.split / f"{a.model.replace('/', '_')}__{a.preset}.jsonl"
    outp.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if outp.exists(): done = {json.loads(l)["id"] for l in open(outp)}
    f = open(outp, "a")
    from tqdm import tqdm
    for r in tqdm([r for r in man if r["id"] not in done]):
        x, _ = sf.read(d / f"{r['id']}.wav", dtype="float32")
        t0 = time.time()
        segs, _ = m.transcribe(x, language="en", word_timestamps=True, **PRESETS[a.preset])
        words, texts = [], []
        for s in segs:
            texts.append(s.text.strip())
            words += [(w.word, w.start, w.end) for w in (s.words or [])]
        c = score_session(r["segments"], words)
        f.write(json.dumps({"id": r["id"], "kind": r["kind"], "gap": r["gap"], "voice": r["voice"],
                            "hyp": " ".join(texts), "rtf": (time.time() - t0) / r["dur"], **c}) + "\n"); f.flush()


if __name__ == "__main__":
    main()
