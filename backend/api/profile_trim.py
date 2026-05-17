"""Trim scraped profile text before sending to the AI provider."""

DEFAULT_MAX_FIELD_CHARS = {
    "experience": 10_000,
    "education": 2_000,
}

DEFAULT_MAX_FIELD_CHARS_FALLBACK = 1_500


def trim_profile_field(text: str, field_name: str = "") -> str:
    """Truncate a single profile text field with a clean boundary when possible."""
    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned

    limit = DEFAULT_MAX_FIELD_CHARS.get(
        (field_name or "").lower(),
        DEFAULT_MAX_FIELD_CHARS_FALLBACK,
    )
    if len(cleaned) <= limit:
        return cleaned

    truncated = cleaned[:limit]
    last_break = truncated.rfind("\n")
    if last_break > limit * 0.7:
        truncated = truncated[:last_break]
    return f"{truncated.rstrip()}\n\n[Profile trimmed for length]"


def trim_predict_person(person: dict) -> dict:
    """Return a copy of interviewee/interviewer payload with trimmed text fields."""
    if not isinstance(person, dict):
        return person
    trimmed = dict(person)
    for field in ("experience", "education"):
        if field in trimmed:
            trimmed[field] = trim_profile_field(str(trimmed.get(field) or ""), field)
    return trimmed
