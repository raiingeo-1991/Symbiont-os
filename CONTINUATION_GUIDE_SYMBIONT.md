# SYMBIONT — CONTINUATION GUIDE
## Инструкция для следующей сессии ChatGPT
## Актуально после checkpoint 2026-09-29

---

# 1. ГДЕ МЫ

Canonical project:

    ~/Symbiont-os

Основная рабочая ветка/текущая локальная линия:

    continuity-context-experiment

Последний локальный commit:

    6d0c59f
    Checkpoint learning and temporal continuity audit

GitHub сейчас НЕ использовать.
Ничего не публиковать и не push-ить без отдельного указания владельца.

---

# 2. ГЛАВНАЯ ЦЕЛЬ ПРОЕКТА

Symbiont — долгоживущий персональный автономный субъект/компаньон.

Главная исследовательская задача текущего этапа:

проверить, способен ли существующий Core после смены
execution environment / Body / process продолжать деятельность,
сохраняя:

    Identity
    Memory
    State
    Context
    History

без "начала с нуля".


интеллектуальный/языковой усилитель.

Identity, Memory, State, principles и история
не должны исчезать.

---

# 3. ГЛАВНЫЙ ПРИНЦИП ПАМЯТИ

Ключевой принцип:

    Прошлое не заменяется настоящим.
    Текущее понимание формируется на основе истории.

Symbiont должен помнить изменение человека во времени,
а не переписывать прошлое под последнее состояние.

Историческая память должна оставаться источником истории.

Текущее понимание должно формироваться на основании истории.

---

# 4. ВАЖНОЕ ПРАВИЛО РАБОТЫ

НЕ добавлять сейчас:

- новый LearningEngine;
- новые крупные архитектурные слои;
- дублирующие механизмы;
- новую систему памяти поверх существующей;
- новую identity system;
- новую security system;
- новую network system.

Сначала искать существующий механизм в проекте.

Философия:

    "Все иголки уже внутри проекта.
     Нужно найти их и поставить на свои места."

Сначала аудит и эксперимент.
Потом минимальное усиление существующего механизма,
если эксперимент докажет необходимость.

---

# 5. CANONICAL CORE

Основной Core:

    symbiont_core.py

Текущий проект содержит существующие функциональные подсистемы,
которые должны рассматриваться как единая canonical линия.

Historical `.bak`, `.before-*`, `.v1-*`, `.pre-*`
не считать параллельными функциональными модулями.

Guardian:

    core/guardian_node.py

Guardian пока НЕ интегрировать в основной Core.

Guardian — отдельный security/protection contour.

---

# 6. CONTINUITY

SCA-1 уже существует и протестирован.

Основные компоненты:

    core/continuity/
        identity.py
        state.py
        events.py
        ledger.py
        recovery.py
        body.py
        handoff.py
        verifier.py
        shadow.py

SCA-1 проверяет continuity независимо от физического Body.

Core остаётся субъектом.

Body является заменяемым execution interface.

Последний важный patch:

    core/continuity/handoff.py

Body registry теперь восстанавливается из существующего ledger
после restart.

---

# 7. MEMORY

Основной persistent source:

    MemoryVault

MemoryVault сохраняет:

- memory_id
- text
- kind
- importance
- created_at
- updated_at
- source
- project
- tags
- metadata
- recall_count
- last_recall

MemoryVault также содержит:

- links
- conversations
- night reports
- ambient log
- FTS index

---

# 10. EXPERIENCE GRAPH

ExperienceGraph хранит:

    ExperienceNode
    ExperienceEdge

Graph поддерживает metadata.

В текущем эксперименте metadata теперь передаётся

Это важно для будущего temporal analysis.

Graph умеет хранить отношения и читать контекст,
но сам по себе не понимает время или смысл изменения.

---

# 11. AUTOMATIC LINKING

CognitiveEngine.build_links() существует.

Он использует:

    token overlap
    Jaccard similarity
    threshold >= 0.3

Автоматические связи сейчас являются
преимущественно лексическими.

Эксперимент Q07 доказал:

семантически связанная фраза с другим словарём
может не получить automatic link.

Это известное ограничение текущей реализации.

---

# 12. REFLECTION

ReflectionEngine уже существует.

Он предназначен для поиска повторяющихся pattern experiences.

Текущий механизм:

    pattern detection
    → normalization/tokenization
    → lexical similarity
    → groups
    → candidate

Минимальные observations:

    2

Минимальная confidence:

    0.65

Confidence:

    min(0.50 + 0.18 * (observations - 1), 0.98)

Representative:

    group[-1]

Это означает, что текущая Reflection логика
ориентирована на повторяющийся паттерн,
а не на полноценное temporal reasoning.

---

# 13. KNOWLEDGE CONSOLIDATION

KnowledgeConsolidation уже существует.

Цепочка:

    ReflectionCandidate
        ↓
    KnowledgeCandidate
        ↓
    validate()
        ↓
    consolidate()

Проверяет:

- непустой content;
- confidence >= 0.65;
- evidence >= 2.

Сохраняет provenance.

Не считать это полноценным temporal learning.

---

# 14. ЧТО УЖЕ ДОКАЗАНО

## SCA-1

Последний тест:

    12/12 PASSED

Проверены:

- Body registry restart;
- Core shadow;
- Body handoff;
- authorization;
- ledger;
- crash window;
- rollback;
- replay;
- missing state;
- state binding;
- deletion detection;
- tail truncation.

---

# 15. FIRST ACQUAINTANCE

Проверена идея первого знакомства.

Q01–Q06 были сохранены как owner memories
с metadata:

    phase
    question_id
    topic
    source_role

MemoryVault сохранил их после restart.


ExperienceGraph сохранил metadata.

CognitiveEngine смог использовать накопленный контекст.

---

# 16. FIRST ACQUAINTANCE — ВАЖНЫЙ ВЫВОД

Первое знакомство — не просто questionnaire.

Это controlled first acquaintance protocol.

Оно одновременно создаёт:

    initial owner history
    initial preferences
    values
    goals
    open loops
    relationships
    temporal baseline

Позже новые ответы должны позволять строить trajectory:

    прошлое
       ↓
    изменения
       ↓
    текущее понимание

При этом старые ответы не должны исчезать.

---

# 17. LEARNING EXPERIMENT

Проверены две разные ситуации.

## Повторение

    Мне нравится работать ночью.
    Обычно мне нравится работать ночью.
    Я предпочитаю работать ночью.
    Мне нравится работать ночью.

Reflection:

    observations: 4
    candidates: 1
    confidence: 0.98

Consolidation:

    accepted: 1
    rejected: 0
    status: validated

Следовательно:

    Experience
      ↓
    Reflection
      ↓
    Candidate
      ↓
    Consolidation
      ↓
    Validated knowledge

реально работает.

---

# 18. TEMPORAL LIMITATION

Последовательность:

    хочу Симбионта, который понимает меня
        ↓
    важно взаимопонимание
        ↓
    Симбионт должен помнить обо мне
        ↓
    со временем Симбионт должен понимать меня лучше

Reflection:

    observations: 4
    candidates: 0

Причина:

текущий ReflectionEngine не моделирует
полноценную временную эволюцию состояния.

---

# 19. КРИТИЧЕСКАЯ ПРОБЛЕМА

Нужно отличать:

    повторение
    перефразирование
    изменение состояния
    развитие одной мысли
    временную траекторию

Например:

    A:
    Мне нравится работать ночью.

    B:
    Я предпочитаю работать ночью.

Это может быть одно состояние.

Но:

    A:
    Мне нравится работать ночью.

    B:
    Теперь мне нравится работать утром.

Это может быть изменение состояния.

Нельзя просто заменить A на B.

Нужно сохранить:

    A — историческое состояние
    B — новое состояние

и вывести текущее понимание как результат истории.

---

# 20. НЕПРАВИЛЬНЫЙ ПУТЬ

Не делать:

    old memory → delete
    new memory → replace old

Не делать:

    latest statement = truth forever

Не делать:

    lexical similarity = semantic understanding

Не делать:

    ReflectionEngine = complete learning system

---

# 21. ПРАВИЛЬНОЕ НАПРАВЛЕНИЕ

Целевая концепция:

    experience
        ↓
    record
        ↓
    links
        ↓
    reflection
        ↓
    temporal interpretation
        ↓
    candidate knowledge
        ↓
    validation
        ↓
    consolidation
        ↓
    current understanding

При этом исходные experiences остаются.

---

# 22. СЛЕДУЮЩИЙ ЭКСПЕРИМЕНТ

Следующая диагностическая серия:

A — повторение

    ночь → ночь → ночь

B — перефразирование

    нравится ночь
        →
    предпочитаю ночь
        →
    удобнее ночью

C — изменение

    нравится ночь
        →
    нравится утро

Цель:

не сразу писать код,

а увидеть точное поведение существующего ReflectionEngine.

---

# 23. ПОСЛЕ A/B/C

Только после эксперимента решить:

нужно ли минимально усилить существующий
Reflection/temporal logic.

Не создавать новый LearningEngine.

---

# 24. CURRENT GIT STATE

Последний commit:

    6d0c59f
    Checkpoint learning and temporal continuity audit

В commit вошли:

    CHECKPOINT_2026-09-29_LEARNING-FIRST-ACQUAINTANCE.md
    core/continuity/handoff.py
    tests/test_sca1_body_registry_restart.py

---

# 25. GITHUB

Пока:

    НЕ PUSH
    НЕ PUBLISH
    НЕ SYNCHRONIZE

Работа ведётся локально.

Перед публикацией необходимо отдельное указание владельца.

---

# 26. УДАЛЁННЫЕ ЭКСПЕРИМЕНТЫ

Временные экспериментальные каталоги после checkpoint были удалены.

Оставлены:

    ~/Symbiont-os
    ~/Symbiont-backups
    ~/symbiont-clean-run

symbiont-clean-run — T0 control baseline.

---

# 27. CHECKPOINTS

Существуют:

    CHECKPOINT_2026-09-24.md
    CHECKPOINT_2026-09-28_FULL-CONTINUITY-BODY.md
    CHECKPOINT_2026-09-28_TIME-PROACTIVE-CONTINUITY.md
    CHECKPOINT_2026-09-29_LEARNING-FIRST-ACQUAINTANCE.md

---

# 29. ПРАВИЛО ДЛЯ СЛЕДУЮЩЕЙ СЕССИИ

Если текущая сессия потеряна:

1. Прочитать этот CONTINUATION_GUIDE.
2. Прочитать последний CHECKPOINT.
3. Проверить git status.
4. Не считать экспериментальные старые копии частью Core.
5. Не начинать проект заново.
6. Не создавать новую архитектуру без доказанной необходимости.
7. Продолжить именно с указанного следующего эксперимента.

---

# 30. ГЛАВНЫЙ ВОПРОС ПРОЕКТА

Не:

    "Как добавить ещё один AI-модуль?"

А:

    "Может ли существующий Symbiont,
     живущий с человеком годами,
     сохранять историю,
     понимать изменения человека во времени
     и формировать текущее понимание,
     не уничтожая прошлое?"

Это текущая исследовательская линия.

