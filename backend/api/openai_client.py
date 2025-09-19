# backend/api/openai_client.py

import json
import requests
from django.conf import settings

# Optional: sanitize HTML before sending to the client
try:
    import bleach
except ImportError:
    bleach = None  # If bleach isn't installed, raw HTML is returned. Install it for safety.

class OpenAIError(Exception):
    pass

# Minimal safe allowlist for rich HTML (no scripts/styles)
_ALLOWED_TAGS = [
    "article", "section", "header", "footer",
    "h1", "h2", "h3", "h4", "p", "ul", "ol", "li",
    "strong", "em", "b", "i", "blockquote", "code", "pre",
    "hr", "br", "span", "details", "summary"
]
_ALLOWED_ATTRS = {
    "span": ["aria-label", "title"],
    "details": ["open"],
    "summary": []
}

def _sanitize_html(html: str) -> str:
    if not html:
        return ""
    if bleach is None:
        return html
    return bleach.clean(html, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, strip=True)

def generate_questions(interviewee, interviewer):
    api_key = settings.OPENAI_API_KEY
    model = (settings.OPENAI_MODEL or "gpt-4o-mini").strip()
    if not api_key:
        raise OpenAIError("OPENAI_API_KEY is not configured. Set it in backend/.env")

    # New system prompt: ask for a single HTML article with topics, subtopics, and prep tips.
    system = (
        "You are InterviewerLens, an interview-planning expert. "
        "Produce a SINGLE self-contained HTML article designed to be shown directly in a web page. "
        "Requirements:\n"
        "• Group content by clear interview TOPICS, with optional SUBTOPICS where useful.\n"
        "• For each topic, include detailed, specific questions and (when helpful) short follow-up probes.\n"
        "• End with a 'Prep Tips' section.\n"
        "• Use clear headings, lists, short paragraphs, and tasteful emojis (e.g., 🔍💡🧠⚙️📈). "
        "No external images/CSS/JS; no markdown—HTML only.\n"
        "Output JSON with a single key 'html' whose value is the HTML string. Example: {\"html\": \"<article>...\"}."
    )
    user = {"interviewee": interviewee, "interviewer": interviewer}

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user)},
        ],
        "response_format": {"type": "json_object"},
        # "temperature": 0.5,  # optional tweak
    }

    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=200)
        if resp.status_code == 404 and model.lower().startswith("gpt-5"):
            # Fallback if GPT-5 isn’t enabled
            body["model"] = "gpt-4o-mini"
            resp = requests.post(url, headers=headers, json=body, timeout=200)

        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.HTTPError as e:
        try:
            err = resp.json()
        except Exception:
            err = {"error": {"message": resp.text}}
        msg = err.get("error", {}).get("message") or str(e)
        raise OpenAIError(f"OpenAI HTTPError: {msg}") from e
    except requests.exceptions.Timeout as e:
        raise OpenAIError("OpenAI request timed out") from e
    except requests.exceptions.RequestException as e:
        raise OpenAIError(f"OpenAI network error: {e}") from e
    except Exception as e:
        raise OpenAIError(f"Unexpected error talking to OpenAI: {e}") from e

    content = data["choices"][0]["message"]["content"]
    try:
        parsed = json.loads(content)
    except Exception:
        parsed = {"html": content}

    html = parsed.get("html") or ""
    html = _sanitize_html(html)

    # Return new shape; your DRF view can just return this dict directly.
    return {"html": html}



# # backend/api/openai_client.py

# import json
# import requests
# from django.conf import settings

# class OpenAIError(Exception):
#     pass

# def generate_questions(interviewee, interviewer):
#     api_key = settings.OPENAI_API_KEY
#     model = (settings.OPENAI_MODEL or "gpt-4o-mini").strip()
#     if not api_key:
#         raise OpenAIError("OPENAI_API_KEY is not configured. Set it in backend/.env")

#     system = (
#         "You are InterviewerLens, an interview-planning expert. Given an interviewee profile "
#         "and an interviewer profile, predict detailed, specific interview questions the interviewer "
#         "is likely to ask. Group by topic; include technical depth, behavioral angles, and follow-ups. "
#         "Return concise JSON with two top-level arrays: 'questions' and 'tips'. Avoid markdown."
#     )
#     user = {"interviewee": interviewee, "interviewer": interviewer}

#     body = {
#         "model": model,
#         "messages": [
#             {"role": "system", "content": system},
#             {"role": "user", "content": json.dumps(user)},
#         ],
#         # "temperature": 0.3,
#         "response_format": {"type": "json_object"},
#     }

#     url = "https://api.openai.com/v1/chat/completions"
#     headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

#     try:
#         resp = requests.post(url, headers=headers, json=body, timeout=200)
#         if resp.status_code == 404 and model.lower().startswith("gpt-5"):
#             # Graceful fallback if GPT-5 isn’t enabled on the account
#             body["model"] = "gpt-4o-mini"
#             resp = requests.post(url, headers=headers, json=body, timeout=200)

#         resp.raise_for_status()
#         data = resp.json()
#     except requests.exceptions.HTTPError as e:
#         # Surface OpenAI error message if present
#         try:
#             err = resp.json()
#         except Exception:
#             err = {"error": {"message": resp.text}}
#         msg = err.get("error", {}).get("message") or str(e)
#         raise OpenAIError(f"OpenAI HTTPError: {msg}") from e
#     except requests.exceptions.Timeout as e:
#         raise OpenAIError("OpenAI request timed out") from e
#     except requests.exceptions.RequestException as e:
#         raise OpenAIError(f"OpenAI network error: {e}") from e
#     except Exception as e:
#         raise OpenAIError(f"Unexpected error talking to OpenAI: {e}") from e

#     content = data["choices"][0]["message"]["content"]
#     try:
#         parsed = json.loads(content)
#     except Exception:
#         parsed = {"questions": [content], "tips": []}

#     questions = [str(q) for q in (parsed.get("questions") or [])][:50]
#     tips = [str(t) for t in (parsed.get("tips") or [])][:50]
#     return {"questions": questions, "tips": tips}

