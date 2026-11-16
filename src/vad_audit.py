"""Model-free audit: does Silero VAD (as used by faster-whisper) cut the start of dictated utterances?

For each session and padding value, an utterance counts as clipped if no VAD chunk starts within
TOL seconds of its start, i.e. its first word(s) never reach Whisper.

usage: python vad_audit.py <split> [--pads 400,1500]  -> results/<split>/vad_audit.jsonl
"""
import argparse, json
from pathlib import Path
import soundfile as sf
from faster_whisper.vad import get_speech_timestamps, VadOptions

ROOT = Path(__file__).resolve().parents[1]
TOL = 0.15


def clipped(x, segments, pad):
    iv = [(t["start"] / 16000, t["end"] / 16000) for t in get_speech_timestamps(x, VadOptions(speech_pad_ms=pad))]
    out = []
    for sg in segments:
        if sg["type"] != "speech":
            continue
        cov = [a for a, b in iv if b > sg["start"] and a < sg["end"]]
        if not cov or cov[0] > sg["start"] + TOL:
            out.append({"start": sg["start"], "lost_s": round((cov[0] - sg["start"]) if cov else sg["end"] - sg["start"], 2),
                        "words": [w for w, _ in sg["words"]], "tags": [t for _, t in sg["words"]]})
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("split"); ap.add_argument("--pads", default="400,1500")
    a = ap.parse_args()
    d = ROOT / "data/clinhallu" / a.split
    outp = ROOT / "results" / a.split / "vad_audit.jsonl"; outp.parent.mkdir(parents=True, exist_ok=True)
    from tqdm import tqdm
    with open(outp, "w") as f:
        for l in tqdm(open(d / "manifest.jsonl").readlines()):
            m = json.loads(l); x, _ = sf.read(d / f"{m['id']}.wav", dtype="float32")
            n = sum(sg["type"] == "speech" for sg in m["segments"])
            for pad in map(int, a.pads.split(",")):
                f.write(json.dumps({"id": m["id"], "seed": m["seed"], "gap": m["gap"], "kind": m["kind"], "voice": m["voice"],
                                    "pad": pad, "n_utt": n, "clipped": clipped(x, m["segments"], pad)}) + "\n")
