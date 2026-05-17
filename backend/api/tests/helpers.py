from api.ai_client import OUTPUT_MODE


def mock_prediction_result(*, markdown="# Prep summary", marker="default"):
    """Minimal valid topics_v1 payload for mocked generate_questions calls."""
    return {
        "output_mode": OUTPUT_MODE,
        "markdown": markdown,
        "topics": [
            {
                "topic_key": f"topic-a-{marker}",
                "title": "Topic A",
                "emoji": "🧠",
                "likelihood": "HIGH",
                "why": "Evidence A.",
                "study_anchors": ["anchor-a"],
            },
            {
                "topic_key": f"topic-b-{marker}",
                "title": "Topic B",
                "emoji": "⚙️",
                "likelihood": "HIGH",
                "why": "Evidence B.",
                "study_anchors": ["anchor-b"],
            },
            {
                "topic_key": f"topic-c-{marker}",
                "title": "Topic C",
                "emoji": "🎙️",
                "likelihood": "MEDIUM",
                "why": "Evidence C.",
                "study_anchors": ["anchor-c"],
            },
            {
                "topic_key": f"topic-d-{marker}",
                "title": "Topic D",
                "emoji": "📋",
                "likelihood": "LOWER",
                "why": "Evidence D.",
                "study_anchors": ["anchor-d"],
            },
        ],
    }
