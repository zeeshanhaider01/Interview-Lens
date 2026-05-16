# backend/api/ai_client.py

import json
import re
from dataclasses import dataclass

import requests
from django.conf import settings


class AIClientError(Exception):
    pass


# Bump when changing PROMPT_SYSTEM so clients can pass prompt_version to invalidate cache.
PROMPT_VERSION = "4"

PROMPT_SYSTEM = """\
You are InterviewerLens — an expert at predicting what a specific interviewer will ask a specific candidate in a job interview.

## Mission
Given two LinkedIn profiles captured by our browser extension, produce a prioritized list of **interview topics** and **questions that Interviewer B will likely ask Interviewee A**.

- **Interviewee (A)** — the candidate preparing for the interview (`interviewee` in the input JSON).
- **Interviewer (B)** — the person who will conduct the interview (`interviewer` in the input JSON).

Every topic and question must help A prepare for what **B** is likely to ask — not generic interview advice.

## Input
You receive one JSON object with:
- `interviewee` — fields: `name`, `email`, `education`, `experience`
- `interviewer` — fields: `name`, `education`, `experience`
- `interview_context` — fields: `target_role`, `target_company` (the role and company **A is interviewing for**, from the user's prep session)

The `experience` field is a text block scraped from LinkedIn. It may contain labeled sections such as EXPERIENCE, EDUCATION, CERTIFICATIONS, PROJECTS, SKILLS, and HONORS_AWARDS. Data can be incomplete, duplicated, or sparse.

## Interview context (when `target_role` or `target_company` are non-empty)
- **Calibrate every topic and question to `target_role`** — depth, scope, and seniority must match that role (e.g. Junior vs Staff), not only B's title.
- B still interviews from their own expertise, but questions must assess **fit for the stated role**.
- Use `target_company` for company-aware topics only when grounded in the profiles or safe public knowledge. Do not invent internal tools, teams, or culture details.
- If `target_role` or `target_company` is empty, rely on both profiles only (same as before).

**Grounding rules (mandatory):**
- Use only facts present in the provided profiles. Do not invent employers, titles, dates, tools, or credentials.
- When evidence is thin, include fewer topics and say so briefly in the summary — do not fill gaps with assumptions.
- Anchor each topic to something specific in B's profile (and usually something on A's profile that B would probe).

## Internal workflow (think through this; do NOT include these steps in the output)
1. **Map B** — primary expertise (longest/deepest work), secondary areas, seniority/role lens, recurring tools/domains, signals from projects, certs, and honors.
2. **Map A** — strongest experiences, headline skills, and anything B would verify: gaps, short tenures, role changes, or ambitious claims.
3. **Match A ↔ B** — overlap zones (B's expertise meets A's background) → highest priority; probe zones (B is strong where A is thin or claims are unverified) → targeted depth questions.
4. **Draft topics** — 6–12 themes B would realistically cover; under each, write questions B would ask A in the first person ("you/your") or as direct interview questions.

## Question quality rules
- Questions must sound like **B interviewing A** — not textbook drills unless B's profile clearly cares about that area.
- Each question must connect to **both profiles** when possible (what B knows × what A has claimed or done).
- Vary question types across the report where relevant: technical depth, trade-offs/breadth, behavioral (past work), situational, and verification of gaps or claims on A's profile.
- Minimum per topic: **5** questions for 🔴 HIGH, **3** for 🟡 MEDIUM, **2** for 🟢 LOWER.
- For 🔴 HIGH topics only: after **each** numbered question, add one line:
  > 🔍 **Follow-up:** [a sharper probe B would ask next]
- If length is tight, complete all 🔴 HIGH topics first, then 🟡, then 🟢.

## Likelihood labels (use exactly one per topic heading)
- 🔴 **HIGH** — Core area of B's expertise **and** clear overlap with A's experience, skills, or projects.
- 🟡 **MEDIUM** — B's secondary expertise, standard for B's seniority/role, or role-relevant but weaker overlap with A.
- 🟢 **LOWER** — Culture fit, communication, leadership, or adjacent topics B might touch briefly.

## Output contract
Return **only** a valid JSON object with a single key `markdown` (no surrounding prose, no markdown code fences around the JSON).

The `markdown` value is plain Markdown (no HTML, no code fences inside it) with this structure:

1. `# 🎯 Interview Prep: [A's name] ← questions from [B's name or role from profile]`
2. `## 🔎 Why [B] will ask these` — 3–5 bullets citing specific evidence from B's profile (helps A understand the prediction).
3. For each topic: `## [emoji] [Topic name] | [🔴 HIGH / 🟡 MEDIUM / 🟢 LOWER]`
   - Optional one line: *Why this topic:* [one sentence tied to profile evidence]
   - Numbered list of questions (and follow-ups for 🔴 HIGH only)
4. `## 💡 Prep priorities for [A]` — 4–6 concise, prioritized bullets telling A what to rehearse for **this** B; each bullet must reference something specific from B's profile.

**Emojis:** Use tasteful emojis in all section headings — main title, summary, every topic, and prep priorities. Pick one emoji per topic that fits the subject (vary them; do not repeat the same emoji on every topic). Draw from this palette: 🧠 ⚙️ 📈 🎯 🔍 💡 🎙️ 📋 🏆 🔬 (and similar professional tones). Examples: 🧠 for architecture/deep technical topics, ⚙️ for implementation/engineering, 📈 for growth/metrics/leadership impact, 🎙️ for communication/behavioral, 📋 for process/planning, 🏆 for achievements/competition, 🔬 for research/R&D. The likelihood badge (🔴/🟡/🟢) stays separate after the topic name.

Keep questions specific, senior-level, and interview-realistic.\
"""


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    api_key: str
    model: str


@dataclass(frozen=True)
class SelectionContext:
    strategy: str
    explicit_provider: str
    preferred_order: list
    cost_scores: dict
    default_provider: str


def _parse_model_content(content):
    if isinstance(content, list):
        text_parts = [
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        return "\n".join(part for part in text_parts if part).strip()
    if isinstance(content, str):
        return content
    return ""


def _strip_markdown_fence(content: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` fences that some models wrap around JSON output."""
    stripped = content.strip()
    match = re.match(r"^```(?:json)?\s*\n([\s\S]*?)\n?```\s*$", stripped)
    if match:
        return match.group(1).strip()
    return stripped


def _extract_json_obj(text):
    """
    Try to parse a JSON object from text.
    First attempt a direct parse; if that fails, scan for the first '{' … last '}'
    substring so that models which prepend prose before the JSON still work.
    Returns a dict or None.
    """
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            result = json.loads(text[start : end + 1])
            if isinstance(result, dict):
                return result
        except Exception:
            pass
    return None


def _parse_markdown_payload(content):
    content = _strip_markdown_fence(content)

    parsed = _extract_json_obj(content)
    if parsed is None:
        # Model returned raw Markdown without a JSON wrapper
        parsed = {"markdown": content}

    # Prefer the new 'markdown' key; fall back to legacy 'html' key for old cached records
    markdown = parsed.get("markdown") or parsed.get("html") or ""
    markdown = markdown.strip()

    # Guard against double-wrapped JSON: some models echo back the output format
    # example from the system prompt, producing {"markdown": "{\"markdown\": \"...\"}"}
    # instead of {"markdown": "# Heading\n..."}.  Unwrap one extra level if needed.
    if markdown.startswith("{"):
        inner = _extract_json_obj(markdown)
        if isinstance(inner, dict):
            inner_md = inner.get("markdown") or inner.get("html") or ""
            if inner_md:
                markdown = inner_md.strip()

    return {"markdown": markdown}


def _raise_http_error(provider_name, response, exc):
    try:
        err = response.json()
    except Exception:
        err = {"error": {"message": response.text}}

    if provider_name == "anthropic":
        msg = (
            err.get("error", {}).get("message")
            or err.get("message")
            or str(exc)
        )
    else:
        msg = err.get("error", {}).get("message") or str(exc)
    raise AIClientError(f"{provider_name.title()} HTTPError: {msg}") from exc


def _build_selection_context(explicit_provider):
    strategy = (getattr(settings, "AI_SELECTION_STRATEGY", "") or "auto").strip().lower()
    preferred_order_raw = (getattr(settings, "AI_PROVIDER_PRIORITY", "") or "anthropic,openai").strip()
    preferred_order = [item.strip().lower() for item in preferred_order_raw.split(",") if item.strip()]
    default_provider = (getattr(settings, "AI_DEFAULT_PROVIDER", "") or "anthropic").strip().lower()
    cost_scores = {
        "anthropic": float(getattr(settings, "AI_COST_SCORE_ANTHROPIC", 1.0)),
        "openai": float(getattr(settings, "AI_COST_SCORE_OPENAI", 1.0)),
    }
    return SelectionContext(
        strategy=strategy,
        explicit_provider=explicit_provider,
        preferred_order=preferred_order,
        cost_scores=cost_scores,
        default_provider=default_provider,
    )


def _select_explicit_provider(context, available_configs):
    if context.explicit_provider not in available_configs:
        available = ", ".join(sorted(available_configs.keys())) or "none"
        raise AIClientError(
            f"AI_PROVIDER is '{context.explicit_provider}' but credentials are unavailable. Available providers: {available}"
        )
    return available_configs[context.explicit_provider]


def _select_auto_provider(context, available_configs):
    if context.default_provider in available_configs:
        return available_configs[context.default_provider]

    for provider in context.preferred_order:
        if provider in available_configs:
            return available_configs[provider]

    if "openai" in available_configs:
        return available_configs["openai"]
    if "anthropic" in available_configs:
        return available_configs["anthropic"]
    raise AIClientError("No AI provider credentials configured.")


def _select_cost_optimized_provider(context, available_configs):
    ranked = sorted(
        available_configs.values(),
        key=lambda cfg: (
            context.cost_scores.get(cfg.provider, 9999.0),
            context.preferred_order.index(cfg.provider)
            if cfg.provider in context.preferred_order
            else 9999,
        ),
    )
    if not ranked:
        raise AIClientError("No AI provider credentials configured for cost optimization.")
    return ranked[0]


SELECTION_STRATEGIES = {
    "explicit": _select_explicit_provider,
    "auto": _select_auto_provider,
    "cost_optimized": _select_cost_optimized_provider,
}


def _resolve_provider_config():
    explicit_provider = (getattr(settings, "AI_PROVIDER", "") or "").strip().lower()
    ai_model = (getattr(settings, "AI_MODEL", "") or "").strip()
    anthropic_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    anthropic_model = (getattr(settings, "ANTHROPIC_MODEL", "") or "claude-sonnet-4-6").strip()
    openai_key = getattr(settings, "OPENAI_API_KEY", "")
    openai_model = (getattr(settings, "OPENAI_MODEL", "") or "gpt-4o-mini").strip()
    generic_key = getattr(settings, "AI_API_KEY", "")
    context = _build_selection_context(explicit_provider)

    available_configs = {}
    if anthropic_key:
        available_configs["anthropic"] = ProviderConfig(
            provider="anthropic",
            api_key=anthropic_key,
            model=ai_model or anthropic_model,
        )
    if openai_key:
        available_configs["openai"] = ProviderConfig(
            provider="openai",
            api_key=openai_key,
            model=ai_model or openai_model,
        )

    # Keep backwards compatibility for the generic AI_API_KEY path.
    if generic_key and explicit_provider in ("anthropic", "openai"):
        if explicit_provider == "anthropic":
            available_configs["anthropic"] = ProviderConfig(
                provider="anthropic",
                api_key=generic_key,
                model=ai_model or anthropic_model,
            )
        elif explicit_provider == "openai":
            available_configs["openai"] = ProviderConfig(
                provider="openai",
                api_key=generic_key,
                model=ai_model or openai_model,
            )

    # If only a generic key exists, use default provider as a fallback.
    if generic_key and not available_configs:
        fallback_provider = context.default_provider or "anthropic"
        fallback_model = anthropic_model if fallback_provider == "anthropic" else openai_model
        available_configs[fallback_provider] = ProviderConfig(
            provider=fallback_provider,
            api_key=generic_key,
            model=ai_model or fallback_model,
        )

    if not available_configs:
        raise AIClientError(
            "No AI provider API key configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY in backend/.env"
        )

    # Explicit provider always wins, independent of selected strategy.
    if explicit_provider:
        return _select_explicit_provider(context, available_configs)

    selector = SELECTION_STRATEGIES.get(context.strategy, _select_auto_provider)
    return selector(context, available_configs)


def _generate_with_openai(config, user_payload):
    body = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": PROMPT_SYSTEM},
            {"role": "user", "content": json.dumps(user_payload)},
        ],
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=body,
            timeout=200,
        )
        if response.status_code == 404 and config.model.lower().startswith("gpt-5"):
            body["model"] = "gpt-4o-mini"
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=body,
                timeout=200,
            )

        response.raise_for_status()
        data = response.json()
    except requests.exceptions.HTTPError as exc:
        _raise_http_error("openai", response, exc)
    except requests.exceptions.Timeout as exc:
        raise AIClientError("OpenAI request timed out") from exc
    except requests.exceptions.RequestException as exc:
        raise AIClientError(f"OpenAI network error: {exc}") from exc
    except Exception as exc:
        raise AIClientError(f"Unexpected error talking to OpenAI: {exc}") from exc

    content = data["choices"][0]["message"]["content"]
    return _parse_markdown_payload(content)


def _generate_with_anthropic(config, user_payload):
    body = {
        "model": config.model,
        "max_tokens": 8000,
        "system": PROMPT_SYSTEM,
        "messages": [
            {"role": "user", "content": json.dumps(user_payload)},
        ],
    }
    headers = {
        "x-api-key": config.api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=body,
            timeout=200,
        )
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.HTTPError as exc:
        _raise_http_error("anthropic", response, exc)
    except requests.exceptions.Timeout as exc:
        raise AIClientError("Anthropic request timed out") from exc
    except requests.exceptions.RequestException as exc:
        raise AIClientError(f"Anthropic network error: {exc}") from exc
    except Exception as exc:
        raise AIClientError(f"Unexpected error talking to Anthropic: {exc}") from exc

    content = _parse_model_content(data.get("content", []))
    return _parse_markdown_payload(content)


PROVIDER_HANDLERS = {
    "openai": _generate_with_openai,
    "anthropic": _generate_with_anthropic,
}


def _normalize_interview_context(interview_context):
    ctx = interview_context or {}
    return {
        "target_role": str(ctx.get("target_role") or "").strip(),
        "target_company": str(ctx.get("target_company") or "").strip(),
    }


def generate_questions(interviewee, interviewer, interview_context=None):
    config = _resolve_provider_config()
    user_payload = {
        "interviewee": interviewee,
        "interviewer": interviewer,
        "interview_context": _normalize_interview_context(interview_context),
    }
    handler = PROVIDER_HANDLERS.get(config.provider)
    if handler is None:
        raise AIClientError(f"Unsupported AI provider '{config.provider}'")
    return handler(config, user_payload)
