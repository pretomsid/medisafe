"""Match Bangladeshi generic names (MedEx / generic.csv) to DDInter drug names.

MedEx usually writes the salt ("Amlodipine Besilate", "Warfarin Sodium") and sometimes the
British/INN name ("Paracetamol", "Salbutamol"). DDInter uses the base name, often the US name
("Acetaminophen", "Albuterol"). resolve() tries, in order:
  1. the whole name,
  2. the name without (...) / [...] notes,
  3. the name without salt / hydrate words,
  4. known spelling variants (INN <-> US name, both directions),
  5. the first word (only if it is a long, exact DDInter name).
It returns None when nothing matches; the caller must then treat the drug as "no data".
Only the standard library is used, so the Flask backend can import this file too.
"""
import re

SALT_WORDS = {
    "hydrochloride", "hcl", "dihydrochloride", "hydrobromide", "sodium", "potassium", "calcium",
    "magnesium", "sulfate", "sulphate", "acetate", "fumarate", "maleate", "propionate", "besilate",
    "besylate", "mesylate", "mesilate", "tartrate", "bitartrate", "citrate", "phosphate", "succinate",
    "gluconate", "bromide", "chloride", "nitrate", "carbonate", "hydroxide", "furoate", "dipropionate",
    "valerate", "acetonide", "monohydrate", "dihydrate", "trihydrate", "hemihydrate", "anhydrous",
    "disodium", "trometamol", "tromethamine", "hyclate", "lactate", "pamoate", "embonate", "palmitate",
    "decanoate", "enanthate", "xinafoate", "bromide", "oxalate", "stearate", "estolate", "ethylsuccinate",
    "arginine", "erbumine", "tert-butylamine", "medoxomil", "base", "usp", "bp",
}

# Same drug, different spelling. DDInter mixes INN and US names, so every group is tried both ways;
# resolve() keeps whichever spelling DDInter actually uses.
SYNONYM_GROUPS = [
    ("paracetamol", "acetaminophen"),
    ("aspirin", "acetylsalicylic acid"),
    ("salbutamol", "albuterol"),
    ("levosalbutamol", "levalbuterol"),
    ("adrenaline", "epinephrine"),
    ("noradrenaline", "norepinephrine"),
    ("frusemide", "furosemide"),
    ("glibenclamide", "glyburide"),
    ("lignocaine", "lidocaine"),
    ("thyroxine", "levothyroxine"),
    ("aciclovir", "acyclovir"),
    ("valaciclovir", "valacyclovir"),
    ("ciclosporin", "cyclosporine", "cyclosporin"),
    ("rifampicin", "rifampin"),
    ("vitamin d3", "cholecalciferol", "colecalciferol"),
    ("vitamin d2", "ergocalciferol"),
    ("vitamin c", "ascorbic acid"),
    ("vitamin a", "retinol"),
    ("vitamin e", "tocopherol"),
    ("vitamin b1", "thiamine"),
    ("vitamin b6", "pyridoxine"),
    ("vitamin b12", "cyanocobalamin"),
    ("pethidine", "meperidine"),
    ("hyoscine", "scopolamine"),
    ("chlorphenamine", "chlorpheniramine"),
    ("cefalexin", "cephalexin"),
    ("cefradine", "cephradine"),
    ("amoxycillin", "amoxicillin"),
    ("sodium valproate", "valproate", "divalproex", "valproic acid"),
    ("glyceryl trinitrate", "nitroglycerin"),
    ("mesalazine", "mesalamine"),
    ("sulphasalazine", "sulfasalazine"),
    ("sulphamethoxazole", "sulfamethoxazole"),
    ("ethinyl estradiol", "ethinylestradiol"),
    ("oestradiol", "estradiol"),
    ("dicycloverine", "dicyclomine"),
    ("clomifene", "clomiphene"),
    ("benzhexol", "trihexyphenidyl"),
    ("dothiepin", "dosulepin"),
    ("torasemide", "torsemide"),
    ("busulphan", "busulfan"),
    ("amfetamine", "amphetamine"),
    ("methylthioninium chloride", "methylene blue"),
    ("aluminium hydroxide", "aluminum hydroxide"),
    ("phenoxymethyl penicillin", "phenoxymethylpenicillin", "penicillin v"),
    ("benzyl penicillin", "benzylpenicillin", "penicillin g"),
    ("ferrous sulfate", "ferrous sulphate", "ferrous sulfate anhydrous"),
    ("zinc sulphate", "zinc sulfate"),
    ("metamizole", "dipyrone"),
    ("doxophylline", "doxofylline"),
    ("phytomenadione", "phytonadione", "vitamin k1"),
]
SYNONYMS = {}
for _group in SYNONYM_GROUPS:
    for _name in _group:
        SYNONYMS.setdefault(_name, [])
        SYNONYMS[_name] += [n for n in _group if n != _name]

HYDRATE_WORDS = {"monohydrate", "dihydrate", "trihydrate", "hemihydrate", "anhydrous", "usp", "bp"}

_PAREN = re.compile(r"[\(\[].*?[\)\]]")
_SPACE = re.compile(r"\s+")


def normalize(name):
    """Lower-case, unify dashes and spaces: ' Warfarin  Sodium ' -> 'warfarin sodium'."""
    text = (name or "").casefold().replace("–", "-").replace("’", "'")
    return _SPACE.sub(" ", text).strip()


def candidates(name):
    """Possible DDInter spellings for one active ingredient, best first."""
    full = normalize(name)
    no_hydrate = " ".join(w for w in full.split() if w not in HYDRATE_WORDS)
    # keep a route note such as "(topical)" but drop salt words: DDInter lists "Diclofenac (topical)"
    with_route = " ".join(w for w in full.split() if w not in SALT_WORDS)
    plain = normalize(_PAREN.sub(" ", full))
    base = " ".join(w for w in plain.split() if w not in SALT_WORDS)
    out = []
    for n in (full, no_hydrate, with_route, plain, base):
        out.append(n)
        out += SYNONYMS.get(n, [])
    if base:
        first = base.split()[0]
        if len(first) >= 6:
            out += [first] + SYNONYMS.get(first, [])
    seen, result = set(), []
    for c in out:
        if c and c not in seen:
            seen.add(c)
            result.append(c)
    return result


def resolve(name, known):
    """First candidate that is in `known` (a set of normalized DDInter names), else None."""
    return next((c for c in candidates(name) if c in known), None)


def split_ingredients(generic):
    """'Paracetamol + Caffeine' -> ['Paracetamol', 'Caffeine'] (same rule as the backend)."""
    return [x.strip() for x in (generic or "").split("+") if x.strip()]


def pair_key(a, b):
    """Order-independent key for two normalized DDInter names (A+B == B+A)."""
    x, y = sorted([a, b])
    return f"{x}|{y}"
