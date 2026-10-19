from local_inference_v4 import infer, extract_subject


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



def rule_subject(text):
    """Return the explicit target object named by a rule, if any."""
    return _extract_subject(text)


def state_subject(text):
    """Return a state subject independently of whether its rule fires."""
    try:
        subject = extract_subject(text)
        return subject or _extract_subject(text)
    except Exception:
        return _extract_subject(text)

def infer_rule_state(rule, state):
    try:
        result = infer(rule, state)

        if result is None:
            return None

        rule_subject = _extract_subject(rule)
        state_subject_value = state_subject(state)

        # Если состояние явно относится к другому объекту,
        # правило к нему не применяется.
        if state_subject_value and rule_subject != state_subject_value:
            return None

        result["subject"] = rule_subject
        return result

    except Exception:
        return None
