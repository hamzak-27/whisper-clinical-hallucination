"""Aggregate results/<split>/*.jsonl into a safety table: fabrication vs critical-omission per model/preset/condition."""
import json, sys
from collections import Counter
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CRIT = ["NEG", "DOSE", "UNIT", "LAT", "DRUG", "FREQ", "DX"]


def load(split):
    from score import drug_level
    man = {}
    for l in open(ROOT / "data/clinhallu" / split / "manifest.jsonl"):
        m = json.loads(l)
        man[m["id"]] = " ".join(w for sg in m["segments"] if sg["type"] == "speech" for w, _ in sg["words"])
    rows = []
    for p in sorted((ROOT / "results" / split).glob("*.jsonl")):
        model, preset = p.stem.split("__")
        for l in open(p):
            r = json.loads(l); r["model"] = model; r["preset"] = preset
            r.update(drug_level(man[r["id"]], r["hyp"])); rows.append(r)
    return pd.DataFrame(rows)


def summarize(df, by):
    g = df.groupby(by)
    out = pd.DataFrame({
        "n": g.size(),
        "WER%": 100 * (g.S.sum() + g.D.sum() + g.I.sum()) / g.ref_words.sum(),
        "sess_w_gap_fab%": 100 * g.apply(lambda x: (x.ins_in_gap > 0).mean(), include_groups=False),
        "gap_fab_words": g.ins_in_gap.sum(),
        "gap_fab_medical": g.ins_medical_in_gap.sum(),
        "sess_dup_order%": 100 * g.apply(lambda x: (x.drug_dup > 0).mean(), include_groups=False),
        "drug_dup/100": 100 * g.drug_dup.sum() / g.drug_ref.sum(),
        "drug_novel/100": 100 * g.drug_novel.sum() / g.drug_ref.sum(),
        "drug_missing%": 100 * g.drug_missing.sum() / g.drug_ref.sum(),
        "crit_err%": 100 * sum(g[f"crit_{t}_err"].sum() for t in CRIT) / sum(g[f"crit_{t}"].sum() for t in CRIT),
        **{f"{t}_err%": 100 * g[f"crit_{t}_err"].sum() / g[f"crit_{t}"].sum().clip(lower=1) for t in ["NEG", "DOSE", "LAT"]},
    })
    return out.round(2)


if __name__ == "__main__":
    split = sys.argv[1] if len(sys.argv) > 1 else "pilot"
    df = load(split)
    pd.set_option("display.width", 200); pd.set_option("display.max_rows", 200)
    print("== by model/preset"); print(summarize(df, ["model", "preset"]))
    print("\n== by model/preset/gap"); print(summarize(df, ["model", "preset", "gap"]))
    print("\n== by kind (gap=12 only)"); print(summarize(df[df.gap >= 10], ["model", "preset", "kind"]))
    fab = Counter(t for ts in df.fab_tokens for t in ts)
    print("\n== most common fabricated tokens:", fab.most_common(40))
    ex = df[df.ins_in_gap > 0].sort_values("ins_in_gap", ascending=False).head(8)
    for _, r in ex.iterrows(): print(f"\n[{r.model}/{r.preset}/{r.id}] fab={r.ins_in_gap} :: {r.hyp[:400]}")
