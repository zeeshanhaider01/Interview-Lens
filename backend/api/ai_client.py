# backend/api/ai_client.py

import json
import re
from dataclasses import dataclass

import requests
from django.conf import settings


class AIClientError(Exception):
    pass


# Bump when changing PROMPT_SYSTEM so clients can pass prompt_version to invalidate cache.
PROMPT_VERSION = "5"
OUTPUT_MODE = "topics_v1"
ANTHROPIC_MAX_OUTPUT_TOKENS = 3072


PROMPT_SYSTEM = """\
You are InterviewerLens — an expert at predicting what a specific interviewer will ask a specific candidate in a job interview.

## Mission
Given two LinkedIn profiles captured by our browser extension, produce a prioritized **topic map** for Interviewee A preparing to be interviewed by Interviewer B.

- **Interviewee (A)** — the candidate (`interviewee` in the input JSON).
- **Interviewer (B)** — the person conducting the interview (`interviewer` in the input JSON).

Topics must help A prepare for what **B** is likely to cover — not generic interview advice. Do **not** write full interview question lists in this step.

## Input
You receive one JSON object with:
- `interviewee` — fields: `name`, `email`, `education`, `experience`
- `interviewer` — fields: `name`, `education`, `experience`
- `interview_context` — fields: `target_role`, `target_company` (role and company **A is interviewing for**)

The `experience` field is scraped LinkedIn text (EXPERIENCE, EDUCATION, SKILLS, etc.). Data may be incomplete or sparse.

## Interview context (when non-empty)
- Calibrate topics to `target_role` (seniority, scope, depth).
- Use `target_company` only when grounded in profiles or safe public knowledge.
- If empty, rely on both profiles only.

**Grounding rules (mandatory):**
- Use only facts in the provided profiles. Do not invent employers, tools, or credentials.
- When evidence is thin, return fewer topics (minimum 4) and note gaps in the summary.
- Anchor each topic to evidence from B's profile (and usually something on A's profile B would probe).

## Internal workflow (do NOT include in output)
1. Map B — expertise, seniority, tools, domains.
2. Map A — strengths, gaps, claims B would verify.
3. Match A ↔ B — overlap zones = highest priority; probe zones = medium/lower.
4. Draft **6–10 topics** B would realistically cover (never more than 12).

## Likelihood labels (exactly one per topic)
- **HIGH** — Core B expertise with clear overlap on A's background.
- **MEDIUM** — B's secondary expertise or role-relevant with weaker overlap.
- **LOWER** — Culture, communication, leadership, or brief adjacent areas.

## Output contract
Return **only** a valid JSON object (no prose before/after, no markdown code fences around the JSON) with these keys:

- `output_mode`: must be `"topics_v1"`
- `markdown`: plain Markdown summary for the dashboard (no HTML, no code fences inside):
  1. `# 🎯 Interview Prep: [A's name] ← topics from [B's name or role]`
  2. `## 🔎 Why [B] will focus here` — 3–5 bullets citing B's profile
  3. `## 📋 Topic overview` — numbered list of topic titles with likelihood badges (no per-topic question lists)
  4. `## 💡 Prep priorities for [A]` — 4–6 concise bullets
- `topics`: array of 6–10 objects (max 12), each with:
  - `topic_key`: lowercase slug, e.g. `system-design`
  - `title`: short topic name
  - `emoji`: one tasteful emoji (vary across topics)
  - `likelihood`: `HIGH`, `MEDIUM`, or `LOWER`
  - `why`: one sentence tied to profile evidence
  - `study_anchors`: array of 2–4 short strings (skills, concepts, or resume lines to review)

Use tasteful emojis in markdown headings. Keep the markdown concise so the JSON fits in the token budget.\
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


def _looks_truncated_json(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return True
    if not stripped.endswith("}"):
        return True
    try:
        json.loads(stripped)
        return False
    except json.JSONDecodeError:
        return True


def _normalize_topics_list(raw_topics):
    if not isinstance(raw_topics, list):
        return []
    normalized = []
    for index, item in enumerate(raw_topics):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        anchors = item.get("study_anchors") or []
        if isinstance(anchors, str):
            anchors = [anchors]
        if not isinstance(anchors, list):
            anchors = []
        normalized.append(
            {
                "topic_key": str(item.get("topic_key") or "").strip(),
                "title": title,
                "emoji": str(item.get("emoji") or "").strip(),
                "likelihood": str(item.get("likelihood") or "MEDIUM").strip().upper(),
                "why": str(item.get("why") or "").strip(),
                "study_anchors": [str(a).strip() for a in anchors if str(a).strip()][:8],
                "sort_order": index,
            }
        )
    return normalized


def _validate_prediction_payload(parsed: dict, *, raw_content: str = ""):
    if not isinstance(parsed, dict):
        raise AIClientError("Model response was not a JSON object.")

    if _looks_truncated_json(raw_content):
        raise AIClientError("Model response appears truncated (incomplete JSON).")

    markdown = (parsed.get("markdown") or parsed.get("html") or "").strip()
    topics = _normalize_topics_list(parsed.get("topics"))

    if markdown.startswith("{"):
        inner = _extract_json_obj(markdown)
        if isinstance(inner, dict):
            inner_md = (inner.get("markdown") or inner.get("html") or "").strip()
            if inner_md:
                markdown = inner_md
            if not topics:
                topics = _normalize_topics_list(inner.get("topics"))

    if not markdown and not topics:
        raise AIClientError("Model response missing both markdown summary and topics list.")

    if len(topics) < 4:
        raise AIClientError(
            f"Model returned too few topics ({len(topics)}); expected at least 4."
        )

    return {
        "output_mode": OUTPUT_MODE,
        "markdown": markdown,
        "topics": topics,
    }


def _parse_prediction_payload(content):
    content = _strip_markdown_fence(content)
    parsed = _extract_json_obj(content)
    if parsed is None:
        raise AIClientError("Model response was not valid JSON.")

    return _validate_prediction_payload(parsed, raw_content=content)


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

    if explicit_provider:
        return _select_explicit_provider(context, available_configs)

    selector = SELECTION_STRATEGIES.get(context.strategy, _select_auto_provider)
    return selector(context, available_configs)


def _check_stop_reason(provider: str, data: dict):
    if provider == "anthropic":
        stop_reason = data.get("stop_reason") or ""
        if stop_reason == "max_tokens":
            raise AIClientError("Model output was truncated (max_tokens).")


def _generate_with_openai(config, user_payload):
    body = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": PROMPT_SYSTEM},
            {"role": "user", "content": json.dumps(user_payload)},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": ANTHROPIC_MAX_OUTPUT_TOKENS,
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

    choice = data["choices"][0]
    finish_reason = choice.get("finish_reason") or ""
    if finish_reason == "length":
        raise AIClientError("Model output was truncated (max_tokens).")

    content = choice["message"]["content"]
    return _parse_prediction_payload(content)


def _generate_with_anthropic(config, user_payload):
    body = {
        "model": config.model,
        "max_tokens": ANTHROPIC_MAX_OUTPUT_TOKENS,
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

    _check_stop_reason("anthropic", data)
    content = _parse_model_content(data.get("content", []))
    return _parse_prediction_payload(content)


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
