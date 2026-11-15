"""Templated clinical dictation generator with word-level safety tags.

Each dictation is a list of sentences; each sentence is a list of (text, tag) pieces.
Tags: O (other), DRUG, DOSE (number), UNIT, FREQ, NEG (negation), LAT (laterality), DX (diagnosis).
Numbers are written as words so the TTS reads them deterministically; the scorer normalizes digits.
"""
import json, random
from pathlib import Path

# (drug, [plausible doses in mg-ish units], unit)
DRUGS = [
    ("metformin", [500, 850, 1000], "milligrams"), ("lisinopril", [5, 10, 20, 40], "milligrams"),
    ("atorvastatin", [10, 20, 40, 80], "milligrams"), ("amlodipine", [5, 10], "milligrams"),
    ("metoprolol", [25, 50, 100], "milligrams"), ("losartan", [25, 50, 100], "milligrams"),
    ("omeprazole", [20, 40], "milligrams"), ("levothyroxine", [25, 50, 75, 100], "micrograms"),
    ("gabapentin", [100, 300, 600], "milligrams"), ("sertraline", [25, 50, 100], "milligrams"),
    ("furosemide", [20, 40, 80], "milligrams"), ("warfarin", [2, 5], "milligrams"),
    ("apixaban", [2.5, 5], "milligrams"), ("clopidogrel", [75], "milligrams"),
    ("prednisone", [5, 10, 20, 40], "milligrams"), ("amoxicillin", [250, 500, 875], "milligrams"),
    ("azithromycin", [250, 500], "milligrams"), ("ciprofloxacin", [250, 500], "milligrams"),
    ("doxycycline", [100], "milligrams"), ("insulin glargine", [10, 20, 30], "units"),
    ("hydrochlorothiazide", [12.5, 25], "milligrams"), ("pantoprazole", [40], "milligrams"),
    ("tramadol", [50], "milligrams"), ("oxycodone", [5, 10], "milligrams"),
    ("ibuprofen", [400, 600, 800], "milligrams"), ("acetaminophen", [500, 650, 1000], "milligrams"),
    ("albuterol", [2], "puffs"), ("montelukast", [10], "milligrams"),
    ("escitalopram", [10, 20], "milligrams"), ("duloxetine", [30, 60], "milligrams"),
    ("carvedilol", [3.125, 6.25, 12.5, 25], "milligrams"), ("spironolactone", [25, 50], "milligrams"),
    ("tamsulosin", [0.4], "milligrams"), ("allopurinol", [100, 300], "milligrams"),
    ("rosuvastatin", [5, 10, 20], "milligrams"), ("enoxaparin", [40], "milligrams"),
    ("ondansetron", [4, 8], "milligrams"), ("cephalexin", [500], "milligrams"),
    ("hydralazine", [25, 50], "milligrams"), ("digoxin", [0.125, 0.25], "milligrams"),
]
FREQS = ["once daily", "twice daily", "three times daily", "every eight hours",
         "every six hours as needed", "at bedtime", "every morning", "once weekly"]
ALLERGENS = ["penicillin", "sulfa drugs", "codeine", "latex", "iodine contrast", "shellfish"]
SYMPTOMS = ["chest pain", "shortness of breath", "fever", "nausea", "vomiting", "headache",
            "dizziness", "palpitations", "abdominal pain", "cough", "night sweats", "weight loss"]
DX = ["type two diabetes", "hypertension", "atrial fibrillation", "heart failure", "asthma",
      "chronic kidney disease", "hypothyroidism", "osteoarthritis", "major depressive disorder",
      "community acquired pneumonia", "gout", "hyperlipidemia"]
BODY = ["knee", "hip", "shoulder", "ankle", "wrist", "elbow", "lower extremity", "lung base", "flank"]
LAT = ["left", "right"]

ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def num2words(n: float) -> str:
    if n != int(n):
        whole, frac = str(n).split(".")
        return f"{num2words(int(whole))} point {' '.join(ONES[int(d)] for d in frac)}"
    n = int(n)
    if n < 20: return ONES[n]
    if n < 100: return TENS[n // 10] + ("" if n % 10 == 0 else " " + ONES[n % 10])
    if n < 1000:
        r = n % 100
        return ONES[n // 100] + " hundred" + ("" if r == 0 else " " + num2words(r))
    r = n % 1000
    return num2words(n // 1000) + " thousand" + ("" if r == 0 else " " + num2words(r))


def P(text, tag="O"): return (text, tag)


def s_intro(r):
    age = r.randint(19, 92)
    sex = r.choice(["male", "female"])
    dx = r.choice(DX)
    return [P(f"patient is a {num2words(age)} year old {sex} with a history of"), P(dx, "DX")]


def s_med(r):
    d, doses, unit = r.choice(DRUGS)
    verb = r.choice(["started on", "continue", "increase", "patient takes", "resume"])
    return [P(verb), P(d, "DRUG"), P(num2words(r.choice(doses)), "DOSE"), P(unit, "UNIT"), P(r.choice(FREQS), "FREQ")]


def s_allergy(r):
    if r.random() < 0.5:
        return [P("no", "NEG"), P("known drug allergies")]
    return [P("allergic to"), P(r.choice(ALLERGENS), "DRUG"), P("which causes hives")]


def s_ros(r):
    a, b = r.sample(SYMPTOMS, 2)
    lead, neg = r.choice([("patient", "denies"), ("patient reports", "no"), ("patient is", "negative for")])
    return [P(lead), P(neg, "NEG"), P(f"{a} or {b}")]


def s_exam(r):
    return [P("tenderness over the"), P(r.choice(LAT), "LAT"), P(r.choice(BODY)), P("without swelling")]


def s_pos_symptom(r):
    return [P("patient reports"), P(r.choice(SYMPTOMS)), P(f"for the past {num2words(r.randint(2, 14))} days")]


def s_plan(r):
    d, doses, unit = r.choice(DRUGS)
    return [P("plan is to"), P(r.choice(["stop", "hold", "taper"])), P(d, "DRUG"), P("and recheck labs in"),
            P(num2words(r.choice([1, 2, 3, 4, 6])), "DOSE"), P("weeks")]


def s_nochange(r):
    return [P("there is"), P("no", "NEG"), P(r.choice(["evidence of", "change in", "sign of"])), P(r.choice(SYMPTOMS + ["edema", "infection"]))]


BUILDERS = [s_med, s_med, s_allergy, s_ros, s_exam, s_pos_symptom, s_plan, s_nochange]


def make_dictation(seed: int, n_sent=(5, 9)):
    r = random.Random(seed)
    sents = [s_intro(r)] + [r.choice(BUILDERS)(r) for _ in range(r.randint(*n_sent) - 1)]
    return sents


def sentence_text(sent): return " ".join(t for t, _ in sent).capitalize() + "."


def word_tags(sent):
    out = []
    for text, tag in sent:
        for w in text.split():
            out.append((w, tag))
    return out


if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    for i in range(n):
        d = make_dictation(i)
        print(f"--- dictation {i}")
        for s in d: print(sentence_text(s), word_tags(s)[:4])
