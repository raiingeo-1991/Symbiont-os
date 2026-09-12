# SYMBIONT

**Sovereign Personal Autonomous Agent**

![Status](https://img.shields.io/badge/status-alpha-orange)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-Apache%202.0-green)
![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)

---

**Память даёт непрерывность.**
**Интеллект даёт способность действовать.**
**Сеть даёт взаимодействие.**
**Человек даёт смысл.**

---

## Что такое Symbiont

Symbiont — персональный автономный агент человека.

Он **помнит** — не сессию, а **тебя**. Он **растёт** с тобой. Он **живёт**, пока ты спишь. Он **не привязан** к устройству — телефон, часы, очки, наушники: всё это его **тела**.

- Устройство — **интерфейс**
- Symbiont — **постоянный агент**
- Владелец — **хозяин**

**Один человек — один Symbiont.**

---

## Почему

ИИ сегодня — **внешний инструмент**. Открыл, спросил, закрыл. Каждый раз — **с нуля**.

Symbiont — **помнит**. Не «контекст». **Тебя**.

Это меняет всё.

Подробнее — в [MANIFEST](docs/MANIFEST.md) и [PHILOSOPHY](docs/PHILOSOPHY.md).

---

## Архитектура

```mermaid
flowchart TD
    H([HUMAN]) --> S[SYMBIONT]
    S --> I[IDENTITY]
    S --> M[MEMORY]
    S --> ST[STATE]
    I --> INT[INTELLIGENCE]
    M --> INT
    ST --> INT
    INT --> T[TOOLS]
    INT --> E[EXTERNAL AI]
    INT --> N[NETWORK]
    T --> A[ACTIONS]
    E --> A
    N --> A
    A --> EX[EXPERIENCE]
    EX --> M
