from local_inference_v4 import infer


def _extract_subject(text):
    import re

    text = str(text).lower().replace("ё", "е")

    matches = list(re.finditer(
        r"(сервер|устройство)\s+([а-яa-z0-9_-]+)",
        text,
    ))

    if not matches:
        return None

    match = matches[-1]
    return f"{match.group(1)} {match.group(2)}"


def infer_rule_state(rule, state):
    try:
        result = infer(rule, state)

        if result is None:
            return None

        rule_subject = _extract_subject(rule)
        state_subject = _extract_subject(state)

        # Если состояние явно относится к другому объекту,
        # правило к нему не применяется.
        if state_subject and rule_subject != state_subject:
            return None

        result["subject"] = rule_subject
        return result

    except Exception:
        return None
