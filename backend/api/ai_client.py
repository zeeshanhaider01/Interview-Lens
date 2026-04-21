# backend/api/ai_client.py

import json
from dataclasses import dataclass

import requests
from django.conf import settings

# Optional: sanitize HTML before sending to the client
try:
    import bleach
except ImportError:
    bleach = None  # If bleach isn't installed, raw HTML is returned. Install it for safety.


class AIClientError(Exception):
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


PROMPT_SYSTEM = (
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


def _parse_html_payload(content):
    try:
        parsed = json.loads(content)
    except Exception:
        parsed = {"html": content}

    html = parsed.get("html") or ""
    return {"html": _sanitize_html(html)}


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
    return _parse_html_payload(content)


def _generate_with_anthropic(config, user_payload):
    body = {
        "model": config.model,
        "max_tokens": 4000,
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
    return _parse_html_payload(content)


PROVIDER_HANDLERS = {
    "openai": _generate_with_openai,
    "anthropic": _generate_with_anthropic,
}


def generate_questions(interviewee, interviewer):
    config = _resolve_provider_config()
    user_payload = {"interviewee": interviewee, "interviewer": interviewer}
    handler = PROVIDER_HANDLERS.get(config.provider)
    if handler is None:
        raise AIClientError(f"Unsupported AI provider '{config.provider}'")
    return handler(config, user_payload)
