"""Aggregate results/<split>/*.jsonl.

- Adds text post-processing variants (postproc.FILTERS) as extra presets, re-scored from saved transcripts.
  Their timestamp-based gap metrics are NaN (text filters have no timestamps).
- Bootstrap 95% CIs over *scripts* (seeds), since sessions sharing a script are correlated.

usage: python aggregate.py <split> [--filters] [--csv out.csv]
"""
import argparse, json
from collections import Counter
from pathlib import Path
import numpy as np, pandas as pd
from score import score_session, drug_level
from postproc import FILTERS

ROOT = Path(__file__).resolve().parents[1]
CRIT = ["NEG", "DOSE", "UNIT", "LAT", "DRUG", "FREQ", "DX"]


def load(split, filters=False):
    man = {}
    for l in open(ROOT / "data/clinhallu" / split / "manifest.jsonl"):
        m = json.loads(l); man[m["id"]] = m
    ref_text = lambda m: " ".join(w for sg in m["segments"] if sg["type"] == "speech" for w, _ in sg["words"])
    rows = []
    for p in sorted((ROOT / "results" / split).glob("*.jsonl")):
        model, preset = p.stem.split("__")
        for l in open(p):
            r = json.loads(l); m = man[r["id"]]
            r.update(model=model, preset=preset, seed=m["seed"], **drug_level(ref_text(m), r["hyp"]))
            rows.append(r)
            if filters:
                for fname, f in FILTERS.items():
                    h = f(r["hyp"])
                    c = score_session(m["segments"], [(w, -1.0, -1.0) for w in h.split()])
                    c["ins_in_gap"] = np.nan; c["ins_medical_in_gap"] = np.nan
                    rows.append({**{k: r[k] for k in ("id", "kind", "gap", "voice")}, **c, "hyp": h,
                                 "model": model, "preset": f"{preset}+{fname}", "seed": m["seed"],
                                 **drug_level(ref_text(m), h)})
    return pd.DataFrame(rows)


def metrics(x):
    s = lambda c: x[c].sum()
    return {
        "WER%": 100 * (s("S") + s("D") + s("I")) / s("ref_words"),
        "ins/100w": 100 * s("I") / s("ref_words"),
        "del/100w": 100 * s("D") / s("ref_words"),
        "dup_sess%": 100 * (x.drug_dup > 0).mean(),
        "dup/100drugs": 100 * s("drug_dup") / max(s("drug_ref"), 1),
        "missing%": 100 * s("drug_missing") / max(s("drug_ref"), 1),
        "crit_err%": 100 * sum(s(f"crit_{t}_err") for t in CRIT) / max(sum(s(f"crit_{t}") for t in CRIT), 1),
        "NEG_err%": 100 * s("crit_NEG_err") / max(s("crit_NEG"), 1),
        "gapfab_sess%": 100 * (x.ins_in_gap > 0).mean() if x.ins_in_gap.notna().all() else np.nan,
    }


def summarize(df, by, ci=None, n_boot=1000, rng=np.random.default_rng(0)):
    out = []
    for key, x in df.groupby(by):
        row = dict(zip(by if isinstance(by, list) else [by], key if isinstance(key, tuple) else (key,)))
        row["n"] = len(x); row.update(metrics(x))
        if ci:
            seeds = x.seed.unique(); groups = {s: x[x.seed == s] for s in seeds}
            for m in ci:
                bs = [metrics(pd.concat([groups[s] for s in rng.choice(seeds, len(seeds))]))[m] for _ in range(n_boot)]
                row[f"{m}_lo"], row[f"{m}_hi"] = np.percentile(bs, [2.5, 97.5])
        out.append(row)
    return pd.DataFrame(out).set_index(by).round(2)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("split", nargs="?", default="pilot")
    ap.add_argument("--filters", action="store_true"); ap.add_argument("--csv")
    ap.add_argument("--ci", action="store_true", help="bootstrap CIs over scripts (slow)")
    a = ap.parse_args()
    df = load(a.split, a.filters)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300); pd.set_option("display.max_columns", 30)
    ci = ["WER%", "dup_sess%"] if a.ci else None
    print("== by model/preset"); t = summarize(df, ["model", "preset"], ci); print(t)
    print("\n== by model/preset/gap"); print(summarize(df, ["model", "preset", "gap"])[["n", "WER%", "ins/100w", "dup_sess%", "dup/100drugs", "gapfab_sess%"]])
    print("\n== by model/preset/kind (longest gap)"); print(summarize(df[df.gap == df.gap.max()], ["model", "preset", "kind"])[["n", "WER%", "dup_sess%", "dup/100drugs"]])
    raw = df[~df.preset.str.contains(r"\+")]
    fab = Counter(t for ts in raw.fab_tokens for t in ts)
    print("\n== most common inserted tokens:", fab.most_common(30))
    if a.csv: summarize(df, ["model", "preset", "gap"], ci).to_csv(a.csv)
