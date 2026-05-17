import re

from django.utils.text import slugify

from .models import PredictionTopic

LIKELIHOOD_ALIASES = {
    "HIGH": PredictionTopic.LIKELIHOOD_HIGH,
    "MEDIUM": PredictionTopic.LIKELIHOOD_MEDIUM,
    "LOWER": PredictionTopic.LIKELIHOOD_LOWER,
    "LOW": PredictionTopic.LIKELIHOOD_LOWER,
}


def _normalize_likelihood(raw: str) -> str:
    text = re.sub(r"[^\w\s]", "", str(raw or "").upper())
    for token in text.split():
        if token in LIKELIHOOD_ALIASES:
            return LIKELIHOOD_ALIASES[token]
    if "HIGH" in text:
        return PredictionTopic.LIKELIHOOD_HIGH
    if "MEDIUM" in text or "MED" in text:
        return PredictionTopic.LIKELIHOOD_MEDIUM
    return PredictionTopic.LIKELIHOOD_LOWER


def _unique_topic_key(prediction_id: int, title: str, index: int) -> str:
    base = slugify(title) or f"topic-{index + 1}"
    candidate = base[:110]
    if not PredictionTopic.objects.filter(prediction_id=prediction_id, topic_key=candidate).exists():
        return candidate
    suffix = 2
    while True:
        alt = f"{base[:100]}-{suffix}"
        if not PredictionTopic.objects.filter(prediction_id=prediction_id, topic_key=alt).exists():
            return alt
        suffix += 1


def replace_prediction_topics(prediction, topics_payload):
    """
    Replace all topics for a prediction from the AI topics list.
    Returns the created PredictionTopic queryset values as dicts.
    """
    topics_payload = topics_payload if isinstance(topics_payload, list) else []
    PredictionTopic.objects.filter(prediction=prediction).delete()

    created = []
    for index, item in enumerate(topics_payload):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        topic_key = str(item.get("topic_key") or "").strip()
        if not topic_key:
            topic_key = _unique_topic_key(prediction.id, title, index)
        else:
            topic_key = slugify(topic_key)[:120] or _unique_topic_key(prediction.id, title, index)

        anchors = item.get("study_anchors") or []
        if isinstance(anchors, str):
            anchors = [anchors]
        if not isinstance(anchors, list):
            anchors = []
        anchors = [str(a).strip() for a in anchors if str(a).strip()][:8]

        row = PredictionTopic.objects.create(
            prediction=prediction,
            topic_key=topic_key,
            title=title[:255],
            emoji=str(item.get("emoji") or "").strip()[:16],
            likelihood=_normalize_likelihood(item.get("likelihood")),
            why=str(item.get("why") or "").strip(),
            study_anchors=anchors,
            sort_order=int(item.get("sort_order") if item.get("sort_order") is not None else index),
        )
        created.append(row)
    return [serialize_prediction_topic(row) for row in created]


def serialize_prediction_topic(topic):
    return {
        "id": topic.id,
        "topic_key": topic.topic_key,
        "title": topic.title,
        "emoji": topic.emoji,
        "likelihood": topic.likelihood,
        "why": topic.why,
        "study_anchors": topic.study_anchors or [],
        "sort_order": topic.sort_order,
    }


def topics_for_prediction(prediction):
    if prediction is None:
        return []
    rows = prediction.topics.order_by("sort_order", "id")
    return [serialize_prediction_topic(row) for row in rows]
