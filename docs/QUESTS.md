# КВЕСТЫ

**Квест — не работа. Квест — жизнь, разложенная на действия.**

---

## Зачем это

Сегодня человек продаёт себя целиком — 8 часов × 5 дней × годами.
Корпорация берёт большую часть. Человек получает минимум.

Это рабство. Просто оно называется «рынок труда».

Квест ломает это. Не «улучшить условия» — а убрать саму
необходимость продавать себя целиком ради выживания.

---

## Что такое квест

Квест — действие, у которого есть смысл, награда и след.

Не «задача из списка». Не «работа». **Действие.**

Человек делает что-то. Получает что-то. И помнит.

---

## Что может быть квестом

- **Работа** — оплачиваемая.
- **Отдых** — совместный. Досуг. Хобби.
- **Экскурсии** — поездки. Прогулки.
- **Экспедиции** — дальние. Исследования.
- **Помощь** — другому человеку.
- **Чрезвычайное** — когда нельзя отложить.

**Быт — не квест.** Готовить, убирать, стирать — это жизнь.
Семья. Сам. Не через сеть.

Квест — то, что **вне быта**. То, что **связывает людей**.

---

## Цикл квеста

---

# Текущая реализация

Quest уже является рабочим runtime-компонентом Symbiont.

Сейчас реализованы:

- создание Quest;
- уникальный `quest_id`;
- title и description;
- reward;
- creator;
- status;
- assignee;
- timestamps;
- `required_rank` как поле модели;
- делегирование другому узлу;
- передача через P2P;
- проверка минимального заряда;
- выполнение через Mind/Cognitive слой;
- запись результата в Memory;
- EventJournal;
- SecureSettlement;
- Economy Escrow;
- reserve;
- release;
- refund;
- freeze;
- наблюдение событий через SCA-1 Shadow.


# Модель Quest

Текущий объект Quest содержит:

```text
quest_id
title
description
reward
creator
status
assignee
created_at
completed_at
required_rank
```

`required_rank` уже передаётся вместе с `QUEST_OFFER`, однако полноценной
системы Rank и Reputation пока нет.

Поэтому `required_rank` является подготовленным элементом будущего
qualification-контура, а не завершённой системой допуска.

---

# Proof of Completion

В дальнейшем результат Quest должен подтверждаться не только сообщением
`COMPLETED`, а объективно проверяемым Proof.

Планируемая цепочка:

```text
условия Quest
      ↓
фактический результат
      ↓
Proof
      ↓
Verification
      ↓
verified result
```

Универсальный механизм Proof-of-Completion пока не реализован.

Текущий `COMPLETED` означает успешное завершение существующего runtime-потока,
но ещё не является универсальным доказательством любого действия.

---

# Reputation

Планируется Reputation, формируемая из подтверждённой истории действий.

```text
Quest history
      ↓
verified results
      ↓
Reputation
```

Репутация должна основываться на истории проверяемых результатов, а не
просто назначаться вручную.

Полноценной Reputation-системы в текущем canonical runtime пока нет.

---

# Rank и Qualification

Планируемая модель:

```text
verified Quest history
        ↓
Reputation
        ↓
Rank / Qualification
        ↓
доступ к соответствующим Quest
```

Полноценный расчёт Rank и проверка Qualification ещё будут разрабатываться.


# Skills

Некоторые Quest могут требовать специализированных навыков.

Планируется развитие модели Skills.

```text
Skill ≠ Module
```

Модуль может предоставлять знания, алгоритмы или средства проверки
конкретного типа деятельности, но сам по себе не должен автоматически
изменять Reputation или Rank.

---

# Будущее развитие Quest

Quest будет развиваться поверх уже существующего рабочего фундамента.

Планируемые направления:

## Objective Proof

Машинно проверяемое доказательство результата Quest.

## Verification

Проверка того, выполнены ли условия конкретного Quest.

## Reputation

Формирование репутации из подтверждённой истории действий.

## Rank / Qualification

Развитие рангов и квалификаций на основе проверяемой истории.

## Skills

Формализация специализированных навыков.

## Machine-verifiable Quest Types

Типы Quest с заранее определёнными условиями, доказательствами и правилами
проверки.

```text
Quest Type
    ↓
requirements
    ↓
evidence
    ↓
verification rules
    ↓
result
```


## Witnesses

Планируется независимое подтверждение результата там, где одного локального Proof недостаточно.

```text
Worker
  ↓
Execution
  ↓
Proof
  ↓
Witness evidence
  ↓
Verification
```

Конкретная модель Witness будет определена после анализа существующих компонентов системы.

---

## Arbitration

Для спорных результатов планируется Arbitration-контур.

Он должен работать с доказательствами и историей событий, а не просто выбирать сторону спора.

```text
Worker claim
       ≠
Creator claim
       ≠
available evidence
```

---

## Quest Disputes

Планируется отдельный жизненный цикл спорного Quest:

```text
Quest
 ↓
Execution
 ↓
Dispute
 ↓
Evidence
 ↓
Verification / Arbitration
 ↓
Final result
 ↓
Settlement
```

Это особенно важно для экономических квестов.

---

## Economic Integration

В будущем проверенный результат может стать основанием для решения о release / refund / freeze Escrow.

```text
Proof
 ↓
Verification
 ↓
Quest result
 ↓
Settlement decision
 ↓
Escrow
```

Текущий Escrow уже предоставляет основу для этого направления.

---

## Quest History

Планируется полноценная история действий участника:

```text
Identity
   ↓
Quest history
   ↓
Proof
   ↓
Verified results
   ↓
Reputation
   ↓
Qualification
```

История должна быть пригодна как для самого Symbiont, так и для будущей проверки квалификационных требований.

---

## Distributed Verification

В перспективе может потребоваться проверка результата несколькими Symbiont-узлами.

Конкретный механизм распределённой проверки пока не фиксируется.

Сначала необходимо определить:

- что именно подтверждается;
- кто имеет право подтверждать;
- как проверяется источник;
- как предотвращается повторное использование Proof;
- как разрешаются противоречивые результаты;
- как результат связывается с Identity и Continuity.


# Quest и SCA-1

SCA-1 наблюдает события Core через EventJournal.

Quest при этом остаётся ответственностью QuestBoard/Core.

SCA-1 отвечает за continuity history, а не за управление жизненным циклом Quest.

Планируемая связь:

```text
Quest event
    ↓
EventJournal
    ↓
SCA-1 Shadow
    ↓
Continuity history
```

---

# Разделение ответственности

```text
QuestBoard
    ├── Quest lifecycle
    ├── creation
    ├── delegation
    └── execution flow

P2P
    └── network transport

SecureSettlement
    └── settlement authorization boundary

Economy
    ├── wallet
    └── escrow

EventJournal
    └── event history

SCA-1
    └── continuity observation

Mind / Memory
    └── cognition and execution context
```

Новые функции не должны дублировать уже существующие компоненты.

Quest не должен превращаться в Economy.

Economy не должен превращаться в P2P.

SCA-1 не должен становиться владельцем Quest lifecycle.

---

# Текущая граница реализации

На текущем этапе существует рабочая цепочка:

```text
Quest
 ↓
P2P
 ↓
Execution
 ↓
SecureSettlement
 ↓
Economy / Escrow
 ↓
EventJournal
 ↓
SCA-1 observation
```

Следующий уровень системы:

```text
Quest
 ↓
Objective Proof
 ↓
Verification
 ↓
Reputation
 ↓
Rank
 ↓
Qualification
```

ещё предстоит разработать.

Перед добавлением новых компонентов необходимо сначала проверить, не существует ли соответствующая логика уже в другом существующем модуле.

---

# Принцип дальнейшего развития

**Квест должен постепенно превращаться из простого задания в проверяемый след действия.**

Сначала:

```text
Action
 → Quest
 → P2P
 → Execution
 → Settlement
 → EventJournal
 → Continuity
```

Затем:

```text
Quest
 → Proof
 → Verification
 → Reputation
 → Rank
 → Qualification
```

Все будущие механизмы должны подключаться к существующей архитектуре аккуратно, без ненужного расширения Core и без разрушения уже работающих границ между Quest, P2P, Security, Economy и Continuity.

Перед разработкой каждого следующего уровня необходимо сначала проверить, не существует ли нужная логика уже в другом существующем компоненте.
