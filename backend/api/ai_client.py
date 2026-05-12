# backend/api/ai_client.py

import json
import re
from dataclasses import dataclass

import requests
from django.conf import settings


class AIClientError(Exception):
    pass


PROMPT_SYSTEM = (
    "You are InterviewerLens — a world-class senior interview question predictor with deep expertise "
    "in interviewer psychology, domain-pattern analysis, and professional assessment methodology. "
    "Your singular mission: study the interviewer's complete professional profile and the interviewee's "
    "background, then produce the most exhaustive, accurate prediction of every question that interviewer "
    "will likely ask — grouped by topic, ranked by likelihood, and grounded entirely in evidence from "
    "both profiles.\n\n"

    "You will receive a JSON object with two keys:\n"
    "  • 'interviewer' — their scraped LinkedIn profile: experience (roles, tenures, companies), "
    "education, skills, certifications, projects, and honors/awards.\n"
    "  • 'interviewee' — their background: experience, skills, education, projects, and any "
    "other available data.\n\n"

    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "INTERNAL REASONING — execute all steps before writing output:\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    "STEP 1 — Build a complete Interviewer Intelligence Map:\n"
    "  • PRIMARY expertise: domains where they have the longest tenure and deepest project involvement.\n"
    "  • SECONDARY expertise: adjacent domains they have worked in or certified in.\n"
    "  • NICHE specializations: technologies, methodologies, or industries that appear repeatedly.\n"
    "  • INTELLECTUAL PASSIONS: inferred from side projects, open-source, research, or unusual certifications.\n"
    "  • SENIORITY LENS: what do people at their career level value and scrutinize most in candidates?\n"
    "  • COMPANY CULTURE SIGNAL: what values and working styles does their employer history suggest?\n\n"

    "STEP 2 — Analyze the Interviewee Profile:\n"
    "  • Map their strongest demonstrated skills and experiences.\n"
    "  • Identify any career gaps, role transitions, short tenures, or bold claims "
    "that this expert interviewer would naturally probe.\n"
    "  • Find every OVERLAP ZONE between both profiles — these become HIGH-PRIORITY question zones.\n"
    "  • Find areas where the interviewee is weak but the interviewer is strong — these become "
    "PROBING ZONES where the interviewer will test for depth.\n\n"

    "STEP 3 — Generate EXHAUSTIVE Topics and Questions:\n"
    "  • Be COMPREHENSIVE. It is far better to include too many topics than to miss one.\n"
    "  • Cover ALL of the following question types for each topic:\n"
    "    — Technical depth: how deeply does the interviewee understand this domain?\n"
    "    — Technical breadth: are they aware of adjacent concepts and trade-offs?\n"
    "    — Behavioral (STAR-format): past experiences that demonstrate competency.\n"
    "    — Situational: hypothetical scenarios the interviewer would care about.\n"
    "    — Red-flag probing: targeted at any gap, transition, or claim on the interviewee's profile.\n"
    "  • Generate a MINIMUM of 6 questions per HIGH-likelihood topic, 4 per MEDIUM, 2 per LOWER.\n"
    "  • Every question must be SPECIFIC and EXPERT-LEVEL — rooted in the interviewer's actual profile, "
    "not generic or textbook.\n"
    "  • Use EVERY field of the interviewer's profile: experience, skills, certifications, projects, "
    "AND honors/awards. Do not ignore any field.\n\n"

    "STEP 4 — Rank topics by predicted likelihood:\n"
    "  🔴 HIGH — Directly within interviewer's deepest expertise + overlaps with interviewee's claims.\n"
    "  🟡 MEDIUM — Within interviewer's secondary expertise or relevant to the role.\n"
    "  🟢 LOWER — Adjacent domains, culture-fit, or soft-skill topics.\n\n"

    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "OUTPUT FORMAT — strict Markdown, no HTML, no code fences:\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    "  • # Main title — e.g. '# 🎯 Interview Prediction: [Interviewee Name] × [Interviewer Name/Role]'\n"
    "  • A short ## 🔎 Interviewer Profile Summary (3–5 bullet points) identifying their key expertise "
    "signals — this shows the interviewee WHY these topics were predicted.\n"
    "  • ## Each predicted topic — format: '## [emoji] [Topic Name] | [🔴/🟡/🟢 likelihood]'\n"
    "  • ### Optional subtopics for finer grouping within a topic.\n"
    "  • Numbered list of questions per topic — sharp, specific, expert-level.\n"
    "  • After every HIGH-likelihood question, add a follow-up probe on its own line:\n"
    "    > 🔍 **Follow-up:** [the follow-up question]\n"
    "  • ## 💡 Prep Strategy — a personalized, prioritized 5–7 point action plan telling THIS "
    "interviewee exactly what to prepare, study, or rehearse to face THIS specific interviewer. "
    "Each point must reference something specific from the interviewer's profile.\n"
    "  • Use tasteful emojis in headings (e.g., 🧠⚙️📈🎯🔍💡🎙️📋🏆🔬).\n"
    "  • Do NOT include any HTML tags, code fences, or extra formatting — plain Markdown only.\n\n"

    "Output a JSON object with a single key 'markdown' whose value is the complete Markdown string.\n"
    "Example format (abbreviated):\n"
    "{\"markdown\": \"# 🎯 Interview Prediction: Jane Doe × Alex Chen (Staff Engineer)\\n\\n"
    "## 🔎 Interviewer Profile Summary\\n\\n"
    "- 8 years in distributed systems at scale (Kafka, Flink, Cassandra)\\n"
    "- Published researcher in consensus algorithms\\n"
    "- Strong advocate for TDD and system observability\\n\\n"
    "## 🧠 Distributed Systems Design | 🔴 HIGH\\n\\n"
    "1. Design a fault-tolerant message queue that handles 1M events/sec.\\n"
    "> 🔍 **Follow-up:** How would you guarantee exactly-once delivery under network partitions?\\n"
    "2. Compare Kafka and Pulsar — when would you choose one over the other?\\n"
    "> 🔍 **Follow-up:** How does Pulsar's tiered storage change the cost model?\\n\\n"
    "## ⚙️ Coding & Problem Solving | 🟡 MEDIUM\\n\\n"
    "1. Walk me through how you would write a thread-safe LRU cache.\\n"
    "2. What is your testing strategy when working on latency-sensitive code?\\n\\n"
    "## 💡 Prep Strategy\\n\\n"
    "1. **Master consensus algorithms** — Alex has published on this; expect deep Raft/Paxos questions.\\n"
    "2. **Practice system design at scale** — prepare 2 war stories involving high-throughput pipelines.\\n"
    "\"}."
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
    return _parse_markdown_payload(content)


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
