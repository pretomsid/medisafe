"""Prescription reader: a photo or PDF of a prescription -> structured medicines (Claude vision).

Needs ANTHROPIC_API_KEY. Without it, extraction is reported as "unavailable" and everything else keeps working.
The result is only a *suggestion*: the user reviews it before anything is added to their medication list."""
import base64
import json
import os

MODEL = os.environ.get("PRESCRIPTION_MODEL", "claude-opus-5-5")
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # API limit per image

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
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def extract(data: bytes, ext: str) -> dict:
    """Returns {"status": "ok"|"unavailable"|"error"|"not_prescription", "message": str, ...fields}."""
    if not available():
        return {"status": "unavailable",
                "message": "Automatic reading is not enabled on this server (no ANTHROPIC_API_KEY). Add medicines manually."}
    ext = ext.lower()
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
        return {"status": "error", "message": "Could not read this file automatically right now. Add the medicines manually."}
    if not out.get("is_prescription"):
        return {"status": "not_prescription", "message": "This file does not look like a prescription.", "medicines": []}
    meds = [m for m in out.get("medicines", []) if (m.get("name") or "").strip()][:30]
    return {"status": "ok", "message": "", "doctor": out.get("doctor_name"), "date": out.get("prescription_date"),
            "diagnosis": out.get("diagnosis"), "medicines": meds}
