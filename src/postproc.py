"""Cheap text-level mitigations applied after decoding (no extra GPU time).

- boh:   remove known stock hallucination phrases. This is a small hand-made list in the spirit of the
         Bag-of-Hallucinations of Barański et al. (2025), not their released list.
- dedup: collapse consecutive (and near-consecutive) repeats of the same sentence.
         Risk: it also removes a sentence that really was dictated twice; the benchmark measures that.
"""
import re

BOH = [
    "thank you for watching", "thanks for watching", "please subscribe", "like and subscribe",
    "subtitles by", "subtitles by the amara org community", "transcribed by", "see you next time",
    "see you in the next video", "i'll see you next time", "bye bye", "thank you so much for watching",
    "please like and subscribe", "don't forget to subscribe", "thank you very much", "thank you",
]
_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _norm(s): return re.sub(r"[^a-z0-9 ]+", "", s.lower()).strip()


def boh(text: str) -> str:
    keep = []
    for sent in _SPLIT.split(text.strip()):
        n = _norm(sent)
        if n and any(n == b or n == b + " " + b for b in BOH):
            continue
        for b in sorted(BOH, key=len, reverse=True):  # trailing stock phrase glued onto a real sentence
            if len(b.split()) >= 3 and n.endswith(" " + b):
                sent = re.sub(r"(?i)[\s,]*" + r"\W*".join(map(re.escape, b.split())) + r"\W*$", ".", sent)
                break
        keep.append(sent)
    return " ".join(keep)


def dedup(text: str, window: int = 3) -> str:
    """Drop a sentence if an identical (normalized) sentence occurred within the previous `window` sentences."""
    out, recent = [], []
    for sent in _SPLIT.split(text.strip()):
        n = _norm(sent)
        if n and n in recent:
            continue
        out.append(sent); recent = (recent + [n])[-window:]
    return " ".join(out)


FILTERS = {"boh": boh, "dedup": dedup, "boh+dedup": lambda t: dedup(boh(t))}

if __name__ == "__main__":
    t = ("Resume Montelukas 10 mg every 8 hours. Patient denies chest pain. Resume Montelukas 10 mg every 8 hours. "
         "Resume Montelukas 10 mg every 8 hours. Allergic to sulfur drugs which causes hives Thank you for watching. Thank you.")
    for k, f in FILTERS.items(): print(k, "=>", f(t))
