"""Prescription reader: a photo or PDF of a prescription -> structured medicines.

Engines, tried in this order (all optional; each needs its own key):
  1. GEMINI_API_KEY    : Google Gemini vision. Free tier available (aistudio.google.com/apikey, no card needed).
  2. ANTHROPIC_API_KEY : Claude vision (paid).
With neither key, extraction is "unavailable" on the server and the browser falls back to free in-browser OCR
(Tesseract.js) plus catalog matching (text_match.py). Everything else keeps working.
The result is only a *suggestion*: the user reviews it before anything is added to their medication list."""
import base64
import json
import os

MODEL = os.environ.get("PRESCRIPTION_MODEL", "claude-opus-5-5")
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # Claude limit per image

SYSTEM = """You read photos and PDFs of medical prescriptions (often from Bangladesh, printed or handwritten, English and/or Bangla).
Extract only what is actually written. Never guess or invent a medicine, dose or date.
- If a word is illegible or you are unsure, keep your best reading but set "uncertain" to true for that medicine.
- Keep brand names exactly as written (e.g. "Napa", "Seclo 20", "Ace Plus").
- "frequency" is how often to take it as written (e.g. "1+0+1", "twice daily", "after meals", "SOS").
- "dose" is the amount per intake (e.g. "1 tablet", "5 ml").
- If the document is not a prescription (for example a lab report), set is_prescription to false and leave medicines empty.
- Dates must be YYYY-MM-DD, or null if not written."""

SCHEMA = {
    "type": "object",
    "properties": {
        "is_prescription": {"type": "boolean"},
        "doctor_name": {"type": ["string", "null"]},
        "prescription_date": {"type": ["string", "null"]},
        "diagnosis": {"type": ["string", "null"]},
        "medicines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "strength": {"type": ["string", "null"]},
                    "dose": {"type": ["string", "null"]},
                    "frequency": {"type": ["string", "null"]},
                    "duration": {"type": ["string", "null"]},
                    "uncertain": {"type": "boolean"},
                },
                "required": ["name", "strength", "dose", "frequency", "duration", "uncertain"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["is_prescription", "doctor_name", "prescription_date", "diagnosis", "medicines"],
    "additionalProperties": False,
}

MEDIA = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}


def available():
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"))


def extract(data: bytes, ext: str) -> dict:
    """Returns {"status": "ok"|"unavailable"|"error"|"not_prescription", "message": str, ...fields}."""
    if not available():
        return {"status": "unavailable",
                "message": "No server-side reader is configured. The photo can be read free in your browser instead."}
    if os.environ.get("GEMINI_API_KEY"):
        return _gemini(data, ext.lower())
    return _claude(data, ext.lower())


def _finish(out):
    if not out.get("is_prescription"):
        return {"status": "not_prescription", "message": "This file does not look like a prescription.", "medicines": []}
    meds = [m for m in out.get("medicines", []) if (m.get("name") or "").strip()][:30]
    for m in meds:
        m["uncertain"] = bool(m.get("uncertain"))
    return {"status": "ok", "message": "", "doctor": out.get("doctor_name"), "date": out.get("prescription_date"),
            "diagnosis": out.get("diagnosis"), "medicines": meds}


def _gemini(data, ext):
    """Gemini vision over plain REST (no extra SDK). The JSON shape is described in the prompt."""
    import requests
    mime = "application/pdf" if ext == "pdf" else MEDIA.get(ext, "image/jpeg")
    prompt = (SYSTEM + "\n\nReturn ONLY JSON with exactly these keys: is_prescription (bool), doctor_name (string|null), "
              "prescription_date (string|null), diagnosis (string|null), medicines (array of objects with name, strength, "
              "dose, frequency, duration (each string|null) and uncertain (bool)).")
    body = {"contents": [{"parts": [{"inline_data": {"mime_type": mime, "data": base64.standard_b64encode(data).decode()}},
                                    {"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    try:
        r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                          headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"},
                          json=body, timeout=45)
        r.raise_for_status()
        out = json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
    except Exception:
        return {"status": "error", "message": "Could not read this file automatically right now."}
    return _finish(out)


def _claude(data, ext):
    if ext != "pdf" and len(data) > MAX_IMAGE_BYTES:
        return {"status": "error", "message": "The image is larger than 5 MB, so it could not be read automatically. "
                                              "Upload a smaller photo, or add the medicines manually."}
    b64 = base64.standard_b64encode(data).decode()
    if ext == "pdf":
        block = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}
    else:
        block = {"type": "image", "source": {"type": "base64", "media_type": MEDIA.get(ext, "image/jpeg"), "data": b64}}
    try:
        import anthropic
        client = anthropic.Anthropic(timeout=50.0, max_retries=1)
        resp = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": [block, {"type": "text", "text": "Extract this prescription."}]}],
        )
        if resp.stop_reason == "refusal":
            return {"status": "error", "message": "The document could not be processed automatically."}
        raw = next((b.text for b in resp.content if b.type == "text"), "")
        out = json.loads(raw)
    except Exception:
        return {"status": "error", "message": "Could not read this file automatically right now."}
    return _finish(out)
