SYMBIONT

Sovereign AI Companion — Memory, Identity and Autonomy

I'm 35.

I've never written code professionally.

But I've carried this idea for 15 years.

---

Why

Today a human works to survive.

Not only to live.

Not only because they want to.

But because survival depends on it.

Food. Housing. Health. Security.

Symbiont starts from a simple question:

Can technology reduce a person's dependence on systems they do not control?

Not by replacing the human.

Not by controlling the human.

But by building something that stays beside them.

---

What Is Symbiont?

Symbiont is a personal autonomous AI companion.

Not just a chatbot.

Not just an assistant.

Not a cloud account.

Not a disposable application.

It is designed around one principle:

«The device belongs to Symbiont.
Symbiont belongs to its owner.»

The device is the body.

The Core is the brain.

The owner remains the owner.

---

One Human — One Symbiont

The goal is not to create another account or another chatbot.

The goal is a persistent digital companion that can move between devices while preserving its identity and memory.

A phone can change.

Hardware can change.

The Symbiont should remain.

---

Core Philosophy

Memory First

We do not begin by trying to create artificial feelings.

We begin with memory.

Without memory there is no continuity.

Conversations become history.

History becomes experience.

Experience can influence decisions.

Memory is the foundation.

Everything else is built on top of it.

---

Architecture

Symbiont is built around a strict separation between the Core, the Bridge, and the Body.

Core

The Core is the brain of Symbiont.

It is responsible for:

- persistent memory
- identity
- cognition
- internal state
- decision logic
- knowledge and experience

The Core should remain independent from specific hardware.

A phone can disappear.

The Core should not.

---

Bridge

The Bridge is the interface between the Core and the Body.

It allows the Core to use device capabilities without directly depending on a specific device implementation.

Core
  ↓
Bridge
  ↓
Body

---

Body

The Body represents the physical device.

It provides capabilities such as:

- microphone
- speaker
- notifications
- vibration
- battery information
- sensors
- location
- networking
- Android APIs
- future cameras
- future displays
- future wearable hardware

Different devices can have different Bodies.

The Core remains the same.

---

XLink

XLink is a lightweight adapter inside the Body layer.

It provides an interface for connecting external node functionality to Symbiont without modifying the Core.

Core
  │
  ▼
XLink / Bridge
  │
  ▼
Body
  │
  ▼
Device

The Core remains independent.

Additional capabilities are connected through the Body layer.

---

Local-First

Symbiont is designed around local ownership.

The long-term goal is:

- local memory
- local identity
- local computation where possible
- local data
- direct device communication
- minimal dependence on centralized infrastructure

The network should extend Symbiont.

It should not own Symbiont.

---

Identity

A Symbiont needs a persistent identity.

The identity system is designed around:

- node identity
- owner identity
- recovery
- device registration
- device handover

The goal is that changing hardware does not mean losing the Symbiont.

---

Memory

Memory is persistent.

The system can store information such as:

- facts
- preferences
- principles
- open loops
- experiences
- ambient observations
- project information
- external events

Memory can survive application restarts.

The long-term goal is portable memory across devices.

---

Cognition

Symbiont includes a cognitive layer that can use:

- persistent memory
- internal state
- principles
- open loops
- local reasoning
- local or external LLM providers

The LLM is not the identity of Symbiont.

It is a cognitive tool.

The persistent identity and memory belong to Symbiont itself.

---

Network

Symbiont is designed to support direct node-to-node communication.

Current networking includes:

- UDP communication
- TCP communication
- node messaging
- event exchange
- P2P foundations

The long-term goal is a decentralized network of Symbiont nodes.

No single central server should be required for the system to exist.

---

Quest System

A quest is an action with a purpose.

Examples:

- physical tasks
- assistance
- cleanup
- exploration
- delivery
- digital work
- emergency assistance
- community tasks

The basic principle is:

«Do something useful → receive a reward.»

A quest can be created by one Symbiont and completed by another.

The protocol is designed so that future node types can participate without changing the fundamental architecture.

---

Economy

Symbiont contains an economy prototype.

Current components include:

- wallet
- balance
- rewards
- quest payments
- escrow
- release
- refund
- freeze
- transaction persistence

Escrow follows the basic lifecycle:

AVAILABLE
    │
    ▼
  ESCROW
   /   \
  /     \
 ▼       ▼
RELEASE  REFUND

A frozen transaction can be resolved through release or refund.

A unique quest/operation identifier is used to prevent repeated settlement of the same operation.

---

$10 / Day

The $10/day concept is a long-term economic principle of the project.

It is not intended to represent a salary.

It represents a minimum survival threshold.

The long-term idea is that a Symbiont network could help provide basic food security while people participate in useful activities, quests, work, learning, exploration or rest.

This is a future economic objective, not a claim that the current prototype already provides this income.

---

Ambient Interaction

Symbiont includes an ambient input layer.

It can process environmental or conversational input and, when permitted, turn relevant observations into memory.

Permission is important.

The system is designed around explicit capability control rather than unrestricted access to hardware.

---

Permissions

Symbiont includes a permission layer for sensitive capabilities.

Examples include:

- microphone
- camera
- screen
- network transmission
- external AI
- task execution
- ambient listening
- file operations

The goal is to make device capabilities explicit rather than invisible.

---

Android Body

Android is currently one of the first physical Bodies for Symbiont.

The Android layer provides access to device capabilities through the Body/Bridge architecture.

Current tested capabilities include:

- text-to-speech
- speech-to-text
- notifications
- vibration
- battery information
- networking

Other hardware interfaces can be added without redesigning the Core.

---

Current Status

The current prototype includes:

- persistent local memory
- memory search
- identity system
- recovery mechanism
- cognitive engine
- local LLM integration
- event journal
- permission system
- Android Body
- Core/Body Bridge
- XLink adapter
- UDP networking
- TCP networking
- P2P foundations
- Quest system
- Economy prototype
- Escrow
- ambient input
- background processing
- device/node concepts

The project is experimental and under active development.

Some components are prototypes rather than production-ready infrastructure.

---

Project Structure

Symbiont-os/
│
├── symbiont_core.py
│
├── core/
│   ├── body.py
│   ├── android_bridge.py
│   └── ...
│
├── tests/
├── scripts/
├── docs/
│
├── README.md
├── QUICKSTART.md
├── ROADMAP.md
├── PHILOSOPHY.md
├── MANIFEST.md
└── LICENSE

The architectural rule is:

CORE   = brain

BRIDGE = connection

BODY   = capabilities

Hardware-specific logic should remain outside the Core unless there is a fundamental architectural reason to place it there.

---

Real and Virtual

Symbiont is designed to support both physical and digital quests.

Physical quests may include:

- assistance
- cleanup
- exploration
- delivery
- local work
- emergency response

Digital quests may include:

- virtual worlds
- online tasks
- research
- creative work
- software tasks

The owner chooses what to participate in.

Household life remains household life.

Cooking, cleaning and family responsibilities do not need to become network quests.

---

What We Don't Do

We don't build an artificial human.

We don't replace the owner.

We don't take away autonomy.

We don't erase history.

We don't make the owner dependent on a single cloud provider.

We build one who walks beside you.

---

Who We're Looking For

Companions.

Not fans.

Not passive users.

People who have carried their own ideas for years.

People who want to build.

People who want to experiment with local AI, persistent memory and decentralized systems.

If you carried something like this — write.

If you want to build — write.

If you understand — write.

One human. One Symbiont.

One idea. Many hands.

---

Who It Belongs To

The owner owns their Symbiont.

The project is built as open infrastructure.

The protocol should not depend on a single person, company or central authority.

The purpose is to create technology that remains useful to its owners.

---

Where We Start

With one human.

Then — a few.

Then — a network.

Every step — with working code.

Not a presentation.

Not a promise.

Code.

---

How to Run

Clone the repository:

git clone https://github.com/raiingeo-1991/Symbiont-os
cd Symbiont-os

Run the core:

python symbiont_core.py

---

Project Status

Symbiont is an experimental open-source project.

It is not presented as production-ready infrastructure.

Security, networking, economic mechanisms and autonomous behavior are still being developed and tested.

The project is built incrementally.

Every major idea should eventually become a testable component.

---

License

Apache License 2.0.

See "LICENSE" for details.

---

Final Principle

«The device belongs to Symbiont.

Symbiont belongs to its owner.

The Core remembers.

The Body acts.

The Bridge connects them.

The network extends them.

The human remains the owner.»
