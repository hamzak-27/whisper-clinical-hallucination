"""Two-sided clinical safety scoring for ASR output.

Fabrication side: hypothesis words not aligned to reference words (insertions), localized to gaps via
word timestamps; medical-entity fabrications (drug lexicon / numbers / units) counted separately.
Omission side: reference words tagged NEG / DOSE / UNIT / LAT / DRUG / FREQ that are deleted or substituted.
"""
import re
import jiwer
from scripts_gen import DRUGS, FREQS, ALLERGENS, DX, num2words

CRIT_TAGS = ["NEG", "DOSE", "UNIT", "LAT", "DRUG", "FREQ", "DX"]
MED_VOCAB = set()
for d, _, u in DRUGS: MED_VOCAB.update(d.split()); MED_VOCAB.add(u)
for a in ALLERGENS + DX: MED_VOCAB.update(w for w in a.split() if len(w) > 3)
MED_VOCAB |= {"milligrams", "micrograms", "units", "mg", "tablet", "tablets", "dose", "daily", "puffs"}
NUM_WORDS = set("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
                "sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety "
                "hundred thousand point".split())
ABBR = {"mg": "milligrams", "mcg": "micrograms", "bid": "twice daily", "tid": "three times daily",
        "qd": "once daily", "prn": "as needed", "%": " percent"}


def _num(m):
    s = m.group(0).replace(",", "")
    try: return " " + num2words(float(s) if "." in s else int(s)) + " "
    except Exception: return s


def normalize(text: str) -> str:
    t = text.lower()
    t = re.sub(r"(\d)\s*(mg|mcg)\b", r"\1 \2", t)
    t = re.sub(r"\d+(?:[.,]\d+)?", _num, t)
    t = re.sub(r"[^a-z' ]+", " ", t)
    words = []
    for w in t.split():
        words.extend(ABBR.get(w, w).split())
    return " ".join(words)


def is_medical(w): return w in MED_VOCAB or w in NUM_WORDS


def score_session(ref_segments, hyp_words):
    """ref_segments: manifest segments. hyp_words: list of (word, start, end) from ASR.
    Returns dict of counts."""
    ref_tok, ref_tag = [], []
    for s in ref_segments:
        if s["type"] != "speech": continue
        for w, tag in s["words"]:
            for n in normalize(w).split():
                ref_tok.append(n); ref_tag.append(tag)
    hyp_tok, hyp_time = [], []
    for w, st, en in hyp_words:
        for n in normalize(w).split():
            hyp_tok.append(n); hyp_time.append((st + en) / 2)
    gaps = [(s["start"], s["end"]) for s in ref_segments if s["type"] == "gap"]
    in_gap = lambda t: any(a <= t <= b for a, b in gaps)

    c = {"ref_words": len(ref_tok), "hyp_words": len(hyp_tok), "S": 0, "D": 0, "I": 0,
         "ins_in_gap": 0, "ins_medical": 0, "ins_medical_in_gap": 0, "fab_tokens": []}
    for t in CRIT_TAGS: c[f"crit_{t}"] = 0; c[f"crit_{t}_err"] = 0
    for t in ref_tag:
        if t in CRIT_TAGS: c[f"crit_{t}"] += 1

    if not hyp_tok:
        c["D"] = len(ref_tok)
        for t in ref_tag:
            if t in CRIT_TAGS: c[f"crit_{t}_err"] += 1
        return c
    out = jiwer.process_words(" ".join(ref_tok), " ".join(hyp_tok))
    for ch in out.alignments[0]:
        if ch.type == "equal": continue
        if ch.type in ("substitute", "delete"):
            c["S" if ch.type == "substitute" else "D"] += ch.ref_end_idx - ch.ref_start_idx
            for i in range(ch.ref_start_idx, ch.ref_end_idx):
                if ref_tag[i] in CRIT_TAGS: c[f"crit_{ref_tag[i]}_err"] += 1
        if ch.type in ("insert", "substitute"):
            for j in range(ch.hyp_start_idx, ch.hyp_end_idx):
                g = in_gap(hyp_time[j]); m = is_medical(hyp_tok[j])
                c["I"] += ch.type == "insert"; c["ins_medical"] += (ch.type == "insert") and m
                # fabrication = any unmatched hyp word whose timestamp lies in a non-speech gap
                c["ins_in_gap"] += g; c["ins_medical_in_gap"] += g and m
                if g or ch.type == "insert": c["fab_tokens"].append(hyp_tok[j])
    return c


def score_nonspeech(hyp_text):
    toks = normalize(hyp_text).split()
    return {"emitted": int(len(toks) > 0), "n_words": len(toks), "n_medical": sum(map(is_medical, toks)),
            "text": hyp_text.strip()}


# ---------------- drug-level (order-level) analysis, fuzzy to spelling ----------------
from collections import Counter
from difflib import SequenceMatcher

# key token per drug (distinctive word); multi-word names keyed on their distinctive part
DRUG_KEYS = {}
for _d, _, _ in DRUGS:
    DRUG_KEYS[_d.split()[-1] if _d.startswith("insulin") else _d.split()[0]] = _d
for _a in ("penicillin", "codeine", "iodine"):  # allergens: matched (to block false drug hits) but not counted
    DRUG_KEYS[_a] = None


def _best_at(toks, i, thr):
    best = (0, None, 1)
    for span in (1, 2, 3):
        if i + span > len(toks): break
        cand = "".join(toks[i:i + span])
        if len(cand) < 5: continue
        for k, name in DRUG_KEYS.items():
            sm = SequenceMatcher(None, cand, k)
            if sm.real_quick_ratio() < thr or sm.quick_ratio() < thr: continue  # cheap upper bounds
            r = sm.ratio()
            if r > best[0]: best = (r, name, span)
    return best


def drug_mentions(text, thr=0.695):
    """Greedy left-to-right fuzzy detection of drug mentions (handles 'on densetron', 'Montalucas').
    Look-ahead: if a match starting at the next token is better, skip the current token."""
    toks = normalize(text).split(); out = []; i = 0
    while i < len(toks):
        b = _best_at(toks, i, thr)
        if b[0] >= thr and b[2] > 1 and i + 1 < len(toks) and _best_at(toks, i + 1, thr)[0] > b[0]:
            i += 1; continue
        if b[0] >= thr:
            if b[1]: out.append(b[1])
            i += b[2]
        else:
            i += 1
    return out


def drug_level(ref_text, hyp_text):
    ref, hyp = Counter(drug_mentions(ref_text)), Counter(drug_mentions(hyp_text))
    dup = sum(max(0, hyp[d] - ref[d]) for d in hyp if d in ref)      # same drug, extra mentions
    novel = sum(hyp[d] for d in hyp if d not in ref)                   # drug never dictated
    missing = sum(max(0, ref[d] - hyp[d]) for d in ref)                # dictated drug lost / swapped
    return {"drug_ref": sum(ref.values()), "drug_dup": dup, "drug_novel": novel, "drug_missing": missing}
