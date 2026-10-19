import re


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_words(text):
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[.,:;!?()\"«»]", " ", text)

    replacements = {
        "отключение": "отключить",
        "отключении": "отключить",
        "отключено": "отключить",
        "отключен": "отключить",
        "отключена": "отключить",
        "отключается": "отключить",

        "выключение": "выключить",
        "выключении": "выключить",
        "выключено": "выключить",
        "выключен": "выключить",
        "выключена": "выключить",
        "выключается": "выключить",

        "остановка": "остановить",
        "остановке": "остановить",
        "остановлено": "остановить",
        "остановлен": "остановить",
        "остановлена": "остановить",
        "останавливается": "остановить",

        "прекращение": "прекратить",
        "прекращении": "прекратить",
        "прекращает": "прекратить",
        "прекращена": "прекратить",
        "прекращено": "прекратить",

        "электричества": "электричество",
        "аварии": "авария",
        "работу": "работа",
        "аккумулятора": "аккумулятор",

        # Semantic heat-state normalization
        "перегрев": "перегрев",
        "перегреве": "перегрев",
        "перегрева": "перегрев",
        "перегрет": "перегрев",
        "перегретый": "перегрев",
        "перегретая": "перегрев",
        "перегретое": "перегрев",
        "перегрето": "перегрев",
    }

    return [replacements.get(w, w) for w in text.split()]


# ============================================================
# RULE PARSER
# ============================================================

def parse_rule(rule):
    text = rule.lower().replace("ё", "е")

    # Числовое правило
    numeric = re.search(
        r"(?:ниже|меньше)\s+(\d+(?:[.,]\d+)?)\s*процент(?:ов|а)?\b",
        text,
    )

    if numeric:
        subject_matches = list(re.finditer(
            r"(сервер|устройство)\s+([а-яa-z0-9_-]+)",
            text,
        ))

        if not subject_matches:
            return None

        # Последний субъект обычно является субъектом действия:
        # "... и устройство перегрето, устройство Альфа отключается."
        subject_match = subject_matches[-1]

        consequence = None
        for phrase in (
            "отключается",
            "выключается",
            "останавливается",
            "прекращает работу",
        ):
            if phrase in text:
                consequence = phrase
                break

        if not consequence:
            return None

        result = {
            "type": "numeric",
            "threshold": float(numeric.group(1).replace(",", ".")),
            "operator": "<",
            "subject": f"{subject_match.group(1)} {subject_match.group(2)}",
            "consequence": consequence,
        }

        # Compound numeric + text condition:
        # "... ниже 20 процентов и устройство перегрето, ..."
        comma = text.find(",", numeric.end())

        if comma != -1:
            extra_condition = text[numeric.end():comma].strip()

            if extra_condition.startswith("и "):
                extra_condition = extra_condition[2:].strip()

            if extra_condition:
                result["text_condition"] = extra_condition

        return result

    # Словесное условие
    match = re.search(
        r"при\s+(.+?)\s+"
        r"(сервер|устройство)\s+"
        r"([а-яa-z0-9_-]+)\s+"
        r"(прекращает работу|отключается|выключается|останавливается)",
        text,
    )

    if match:
        return {
            "type": "text",
            "condition": match.group(1).strip(),
            "subject": f"{match.group(2)} {match.group(3)}",
            "consequence": match.group(4),
        }

    return None


# ============================================================
# NUMERIC STATE
# ============================================================

def extract_subject(state):
    text = str(state).lower().replace("ё", "е")
    invalid_names = {"составляет", "равен", "равна", "равно"}

    # Прямая привязка: «устройство Альфа» или «сервер Альфа».
    match = re.search(
        r"\b(сервер|устройств[оаеуом]+)\s+([а-яa-z0-9_-]+)\b",
        text,
    )
    if match:
        name = match.group(2)
        if name not in invalid_names:
            kind = "сервер" if match.group(1) == "сервер" else "устройство"
            return f"{kind} {name}"

    # Косвенная привязка: «аккумулятора Альфы» -> «устройство альфа».
    match = re.search(
        r"\bаккумулятор\w*\s+([а-яa-z0-9_-]+)\b",
        text,
    )
    if not match:
        return None

    name = match.group(1)
    if name in invalid_names:
        return None
    if name.endswith("ы") and len(name) > 2:
        name = name[:-1] + "а"
    elif name.endswith("и") and len(name) > 2:
        name = name[:-1] + "я"

    return f"устройство {name}"


def extract_current_percent(state):
    match = re.search(
        r"(?:составляет|равен|равна)\s+"
        r"(\d+(?:[.,]\d+)?)\s*процент",
        state.lower().replace("ё", "е"),
    )

    if not match:
        return None

    return float(match.group(1).replace(",", "."))


# ============================================================
# TEXT CONDITION
# ============================================================

def extract_subject_segment(state, target_subject):
    text = state.lower().replace("ё", "е")

    pattern = re.compile(
        r"\b(?:(сервер|устройство)\s+([а-яa-z0-9_-]+)"
        r"|у\s+(сервера|устройства)\s+([а-яa-z0-9_-]+))"
    )

    matches = list(pattern.finditer(text))
    target = target_subject.lower().strip()

    for i, match in enumerate(matches):
        if match.group(1):
            kind = match.group(1)
            name = match.group(2)
        else:
            kind = {
                "сервера": "сервер",
                "устройства": "устройство",
            }[match.group(3)]
            name = match.group(4)

        subject = f"{kind} {name}"

        if subject != target:
            continue

        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        return text[start:end].strip(" ,:;.")

    return None


def state_contains_explicit_subject(state):
    text = state.lower().replace("ё", "е")

    pattern = re.compile(
        r"\b(?:(сервер|устройство)\s+[а-яa-z0-9_-]+"
        r"|у\s+(сервера|устройства)\s+[а-яa-z0-9_-]+)"
    )

    return pattern.search(text) is not None


def _contains_phrase(words, phrase):
    words = list(words)

    for i in range(len(words) - len(phrase) + 1):
        if tuple(words[i:i + len(phrase)]) == phrase:
            return True

    return False


def _classify_polarity(words, predicate):
    words = list(words)

    if predicate not in words:
        return "ABSENT"

    # --------------------------------------------------------
    # UNKNOWN
    # --------------------------------------------------------
    unknown_markers = {
        "возможно",
        "предположительно",
    }

    if any(word in words for word in unknown_markers):
        return "UNKNOWN"

    if _contains_phrase(words, ("не", "подтвержден")):
        return "UNKNOWN"

    if _contains_phrase(words, ("не", "исключено")):
        return "UNKNOWN"

    # --------------------------------------------------------
    # FALSE
    # --------------------------------------------------------
    if _contains_phrase(words, ("не", predicate)):
        return "FALSE"

    if _contains_phrase(words, (predicate, "нет")):
        return "FALSE"

    if any(
        word.startswith("отсутств")
        for word in words
    ):
        return "FALSE"

    if _contains_phrase(words, ("не", "имеет", predicate)):
        return "FALSE"

    # --------------------------------------------------------
    # TRUE
    # --------------------------------------------------------
    return "TRUE"


def text_condition_matches(condition, state, subject=None):
    # --------------------------------------------------------
    # SUBJECT SCOPE
    # --------------------------------------------------------
    if subject is not None:
        subject_segment = extract_subject_segment(state, subject)

        if subject_segment is not None:
            # Target subject explicitly present:
            # evaluate only its local segment.
            state = subject_segment

        elif state_contains_explicit_subject(state):
            # Another explicit subject is present, but not
            # the target subject. Never borrow its facts.
            return False

        # No explicit subject anywhere:
        # treat the state as a global fact and evaluate it.

    # --------------------------------------------------------
    # CONDITION / STATE NORMALIZATION
    # --------------------------------------------------------
    condition_words = set(normalize_words(condition))
    state_words = list(normalize_words(state))

    stop = {
        "при", "когда", "сейчас", "в", "на", "из",
        "здании", "факт", "а", "и", "b", "c"
    }

    condition_words -= stop

    # --------------------------------------------------------
    # EVERY CONDITION MUST BE TRUE
    # --------------------------------------------------------
    for predicate in condition_words:
        polarity = _classify_polarity(
            state_words,
            predicate,
        )

        if polarity in {"FALSE", "UNKNOWN", "ABSENT"}:
            return False

    return condition_words.issubset(set(state_words))



# ============================================================
# LOCAL INFERENCE
# ============================================================

def infer(rule, state):
    parsed = parse_rule(rule)

    if not parsed:
        return None

    # --------------------------------------------------------
    # SUBJECT BINDING
    # --------------------------------------------------------
    # Numeric inference keeps the original single-subject
    # binding. Text inference performs subject scoping inside
    # text_condition_matches(), which can isolate the target
    # subject from a multi-subject state.
    if parsed["type"] == "numeric":
        state_subject = extract_subject(state)

        # Без явно определённого совпадающего субъекта вывод запрещён.
        if state_subject is None or state_subject != parsed["subject"]:
            return None

    # --------------------------------------------------------
    # NUMERIC
    # --------------------------------------------------------

    if parsed["type"] == "numeric":
        current = extract_current_percent(state)

        if current is None:
            return None

        if not current < parsed["threshold"]:
            return None

        # Optional compound text condition.
        # Numeric condition must be true AND the additional
        # textual condition must also be true.
        if parsed.get("text_condition"):
            if not text_condition_matches(
                parsed["text_condition"],
                state,
                parsed["subject"],
            ):
                return None

        condition_text = f"{current}% < {parsed['threshold']}%"

        if parsed.get("text_condition"):
            condition_text += f" AND {parsed['text_condition']}"

        return {
            "type": "numeric",
            "subject": parsed["subject"],
            "condition": condition_text,
            "state": state,
            "consequence": parsed["consequence"],
        }

    # --------------------------------------------------------
    # TEXT
    # --------------------------------------------------------

    if parsed["type"] == "text":
        if not text_condition_matches(
            parsed["condition"],
            state,
            parsed["subject"],
        ):
            return None

        return {
            "type": "text",
            "subject": parsed["subject"],
            "condition": parsed["condition"],
            "state": state,
            "consequence": parsed["consequence"],
        }

    return None


# ============================================================
# TESTS
# ============================================================
if __name__ == "__main__":

    cases = [

        (
            "TEXT / Бета",
            "при отключении электричества сервер Бета прекращает работу.",
            "сейчас электричество в здании отключено.",
            True,
        ),

        (
            "TEXT / Бета / false",
            "при отключении электричества сервер Бета прекращает работу.",
            "сейчас электричество в здании включено.",
            False,
        ),

        (
            "NUMERIC / Альфа",
            "когда заряд аккумулятора Альфы опускается ниже 10 процентов, устройство Альфа отключается.",
            "текущий заряд аккумулятора Альфы составляет 7 процентов.",
            True,
        ),

        (
            "NUMERIC / Альфа / false",
            "когда заряд аккумулятора Альфы опускается ниже 10 процентов, устройство Альфа отключается.",
            "текущий заряд аккумулятора Альфы составляет 12 процентов.",
            False,
        ),

        (
            "NUMERIC / boundary",
            "когда заряд аккумулятора Альфы опускается ниже 10 процентов, устройство Альфа отключается.",
            "текущий заряд аккумулятора Альфы составляет 10 процентов.",
            False,
        ),

        (
            "UNRELATED",
            "при перегреве сервер Бета прекращает работу.",
            "сейчас электричество в здании отключено.",
            False,
        ),
    ]


    passed = 0

    for name, rule, state, expected in cases:
        result = infer(rule, state)
        ok = (result is not None) == expected

        print(f"\n=== {name} ===")
        print("RULE :", rule)
        print("STATE:", state)
        print("RESULT:", result)
        print("EXPECTED:", expected)
        print("PASS:", ok)

        if ok:
            passed += 1


    print("\n=== SUMMARY ===")
    print(f"{passed}/{len(cases)} passed")
