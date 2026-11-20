"""Free prescription reader, part 2: OCR text -> medicines, by matching words against the medicine catalog.

OCR itself runs in the user's browser (Tesseract.js), so no paid API and no key are needed, and the photo never
leaves the device. This module only receives the recognised *text* and finds catalog brand names in it.
It works well on printed prescriptions; handwriting is unreliable, so every result is shown for review."""
import difflib
import re

# Words that are also brand names in the catalog or are common prescription words: never match these alone
STOP = {"tablet", "tablets", "capsule", "capsules", "syrup", "daily", "after", "before", "with", "take", "name",
        "date", "once", "twice", "dose", "days", "week", "weeks", "meal", "meals", "night", "morning", "patient",
        "doctor", "advice", "water", "fever", "pain", "cold", "drops", "cream", "ointment", "injection", "tabs",
        "this", "that", "from", "have", "years", "year", "male", "female", "weight", "phone", "address", "hospital",
        "clinic", "chamber", "signature", "regd", "mbbs", "nutrition", "diet", "follow", "review", "visit", "test"}
STRENGTH = re.compile(r"(\d+(?:\.\d+)?)\s*(mg|mcg|µg|g|ml|iu)\b", re.I)
FREQ = re.compile(r"\b\d\s*[+\-]\s*\d\s*[+\-]\s*\d(?:\s*[+\-]\s*\d)?\b|\b(?:bd|bid|tds|tid|qid|od|sos|stat|hs)\b|"
                  r"\b(?:once|twice|thrice)\s+(?:a\s+)?daily\b", re.I)
DOSE = re.compile(r"\b(\d+(?:\.\d+)?|half|one|two)\s*(tab(?:let)?s?|cap(?:sule)?s?|ml|tsp|drops?)\b", re.I)
DURATION = re.compile(r"\b(?:for\s+)?(\d+)\s*(days?|weeks?|months?)\b", re.I)
WORD = re.compile(r"[A-Za-z][A-Za-z0-9\-]{2,}")


def find_medicines(text, brands, limit=30):
    """text: OCR output. brands: {lowercase brand: canonical brand}. Returns a list of medicine dicts."""
    found, seen = [], set()
    by_first = {}
    for low in brands:
        by_first.setdefault(low[:1], []).append(low)
    for line in (text or "").splitlines():
        words = [w.lower() for w in WORD.findall(line)]
        hits = []
        for i, w in enumerate(words):
            if i + 1 < len(words) and f"{w} {words[i + 1]}" in brands:     # two-word brands, e.g. "Ace Plus"
                hits.append((f"{w} {words[i + 1]}", False))
            elif len(w) >= 4 and w not in STOP and w in brands:
                hits.append((w, False))
            elif len(w) >= 5 and w not in STOP and w[:1] in by_first:       # OCR typo: Seclo -> Sec1o
                cand = [b for b in by_first[w[:1]] if abs(len(b) - len(w)) <= 2 and " " not in b]
                m = difflib.get_close_matches(w, cand, n=1, cutoff=0.88)
                if m:
                    hits.append((m[0], True))
        for low, fuzzy in hits:
            if low in seen:
                continue
            seen.add(low)
            strength = STRENGTH.search(line)
            freq = FREQ.search(line)
            dose = DOSE.search(line)
            dur = DURATION.search(line)
            found.append({"name": brands[low],
                          "strength": f"{strength.group(1)} {strength.group(2).lower()}" if strength else None,
                          "dose": dose.group(0) if dose else None,
                          "frequency": freq.group(0) if freq else None,
                          "duration": dur.group(0) if dur else None,
                          "uncertain": True if fuzzy else False})
            if len(found) >= limit:
                return found
    return found
