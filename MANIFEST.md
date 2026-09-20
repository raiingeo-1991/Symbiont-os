# SYMBIONT — MANIFEST

## System Architecture and Internal Structure

This document describes what exists inside Symbiont and how the major components interact.

It is not a quickstart guide.

It is not a roadmap.

It is the map of the system.

For the project overview, see [README](README.md).

For the development direction, see [ROADMAP](ROADMAP.md).

For installation and testing, see [QUICKSTART](QUICKSTART.md).

---

# 1. The System

Symbiont is built as a layered system.

The layers have different responsibilities.

The central rule is:

**The Core is not the Body.**

The Core represents the continuity of the Symbiont.

The Body represents the capabilities available to it.

The Bridge connects the two.

---

# 2. Core

The Core contains the internal state of the Symbiont.

Its primary responsibilities are:

- Identity
- Persistent memory
- Cognition
- Internal knowledge
- Relationships between memories
- Principles
- Preferences
- Open loops
- Internal events
- Decision context

The Core should remain as independent as possible from specific hardware.

A phone can disappear.

A different device can become the Body.

The Core should remain the same Symbiont.

---

# 3. Identity

Identity answers a fundamental question:

**Which Symbiont is this?**

Identity is connected to:

- Node identity
- Recovery
- Ownership
- Primary / secondary state
- Persistent local configuration

Identity is not the same thing as the language model.

Changing the model does not automatically create a new Symbiont.

---

# 4. Memory

Memory is one of the central components of the Core.

Symbiont uses persistent local storage so information can survive a process restart.

Memory can contain different types of information, including:

- General memories
- Principles
- Preferences
- Open loops
- Ambient observations
- Project information
- External events

Memory also tracks relevance and recall.

The purpose is not simply to store more data.

The purpose is to make previous experience available when it becomes useful.

---

# 5. Memory Retrieval

Memory retrieval connects stored information with current context.

The system can use:

- Text search
- Relevance
- Importance
- Memory type
- Recall history
- Relationships
- Identity-related information

This creates a distinction between:

**Storage**

and:

**Useful recall**

A large memory without retrieval is only a database.

A useful Symbiont needs both.

---

# 6. Cognition

The Cognitive Engine operates above memory.

Its role is to process context and produce useful internal reasoning or responses.

The architecture allows the cognitive layer to use an external or local language model without making that model the permanent identity of the Symbiont.

Conceptually:

**Memory → Context → Cognition → Action**

The language model is therefore a tool available to cognition.

It is not the Core itself.

---
# 7. Bridge

The Bridge is the connection layer between the Core and external capabilities.

Its purpose is to prevent hardware-specific logic from becoming part of the Core.

The Bridge can translate between:

**Core requests**

and:

**Body capabilities**

This makes it possible to replace or extend a Body without redesigning the Core.

---

# 8. Body

The Body represents the capabilities available to the Symbiont.

A Body may provide:

- Audio
- Microphone
- Camera
- Display
- Sensors
- Location
- Battery information
- Notifications
- Vibration
- Network access
- Operating system APIs
- Other hardware capabilities

The Body does not define the identity of the Symbiont.

It provides the environment in which the Symbiont can operate.

---

# 9. Android Body

Android is currently the first practical Body implementation.

The Android layer provides interfaces for capabilities such as:

- Text-to-speech
- Speech-to-text
- Notifications
- Vibration
- Battery information
- Network communication

Some capabilities depend on the Android version, installed components and permissions.

The Android Body is therefore an adapter to the device environment, not the Symbiont itself.

---

# 10. Permissions

Capabilities are not automatically trusted.

Symbiont contains a permission layer that can control access to sensitive operations.

Examples include:

- Microphone
- Camera
- Screen access
- Network transmission
- External AI
- File operations
- Task execution
- Ambient listening

The purpose is to separate:

**What Symbiont can do**

from:

**What Symbiont is allowed to do.**

Autonomy without permission boundaries would undermine the ownership model.

---

# 11. XLink

XLink is a lightweight adapter between the Core and an external node layer.

Its purpose is intentionally narrow.

It can:

- Connect a node
- Disconnect a node
- Attach a Core
- Report connection state
- Pass external events toward the Core

XLink does not replace the Core.

It does not become the identity system.

It does not contain the intelligence of the Symbiont.

It is a connection point.

This allows additional external systems to be introduced without turning the Core into a collection of unrelated integrations.

---

# 12. Events

Events provide a way for different parts of Symbiont to communicate changes and actions.

Examples include:

- Memory events
- Ambient events
- Economy events
- Quest events
- Network events
- Body events
- System events

Events can also become part of the persistent history of the Symbiont.

This creates an important distinction:

**State describes what exists now.**

**Events describe what happened.**

Both can be useful to cognition and recovery.

---

# 13. Network Layer

The network layer allows Symbiont nodes to communicate.

The current foundation includes:

- UDP communication
- TCP communication
- Node identity
- Basic node messaging

The network is intentionally separate from the Core's internal memory.

A network message may become a memory or event, but network transport itself is not the Core.

Future network development can therefore evolve independently.

---

# 14. Node-to-Node Communication

A Symbiont node can eventually communicate with another Symbiont node.

The conceptual flow is:

**Node → Network → Node**

The receiving node can then decide what to do with the information according to its own:

- Identity
- Permissions
- Memory
- Rules
- Context

This is important for a future decentralized Symbiont network.

Communication does not automatically mean authority.

Receiving a message does not automatically mean executing it.

---
# 15. Quest System

The Quest system represents tasks that can be created, assigned and completed.

A Quest can contain:

- Quest ID
- Title
- Description
- Reward
- Creator
- Assignee
- Status
- Creation time
- Completion time
- Requirements

The Quest system is responsible for the task itself.

It does not define the identity of the Symbiont.

It does not control the Core's memory.

It does not replace the Economy.

---

# 16. Quest Lifecycle

A Quest can move through different states during its lifetime.

Conceptually:

**Created → Available → Accepted → Completed**

A completed Quest can then trigger settlement through the Economy layer.

The exact lifecycle can evolve as verification, proof and network functionality are added.

---

# 17. Economy

The Economy layer handles value associated with Symbiont tasks.

Its current foundation includes:

- Wallet
- Balance
- Rewards
- Persistent economy state
- Quest settlement
- Escrow

The Economy is intentionally separated from memory and cognition.

The Core may remember that an economic event happened.

The Economy is responsible for enforcing the financial state.

---

# 18. Escrow

Escrow prevents a reward from being immediately available while a Quest is still unresolved.

The current lifecycle supports:

**Available → Escrow → Released**

or:

**Available → Escrow → Refunded**

A Quest can also become:

**Escrow → Frozen**

A frozen Quest can later be released or refunded according to the settlement logic.

---

# 19. Unique Operations

Financial operations must be uniquely identifiable.

The Quest ID is therefore important to settlement.

The system must prevent the same Quest from being released or refunded multiple times.

This principle becomes increasingly important when settlement moves from one local process to a distributed network.

A repeated network message must not automatically create a second payment.

---

# 20. Economy and Quest Separation

Quest and Economy have different responsibilities.

**Quest**

Defines:

- What needs to be done
- Who created it
- Who performs it
- Whether the task is completed

**Economy**

Defines:

- What value is reserved
- Where the reward is held
- Whether it is released
- Whether it is refunded
- Whether settlement is frozen

This separation allows both systems to evolve independently.

---

# 21. Future Settlement

Future network settlement may introduce:

- Proof of completion
- Transaction verification
- Signatures
- Replay protection
- Dispute handling
- Witnesses
- Quorum
- Distributed accounting
- Offline synchronization

The current local implementation is the foundation for those future mechanisms.

---

# 22. External Nodes

The architecture is prepared for different types of nodes.

A future transaction can contain:

- `creator_node`
- `worker_node`
- `creator_type`
- `worker_type`

The current model can remain simple while preserving compatibility with future node types.

The Core does not need to know the external business rules of every possible node.

It only needs a stable interface for identity, events and interaction.

---
# 23. How the Layers Work Together

The major components of Symbiont have different responsibilities.

The Core provides continuity.

The Bridge provides connection.

The Body provides capabilities.

The surrounding systems provide interaction, tasks and communication.

Conceptually:

**Core → Bridge → Body → Device**

While other systems operate alongside the Core:

**Memory**
provides persistent knowledge.

**Cognition**
processes memory and context.

**Network**
connects Symbiont nodes.

**Quest**
defines tasks.

**Economy**
handles value and settlement.

**Permissions**
define what the Symbiont is allowed to do.

---

# 24. Responsibility Boundaries

Keeping boundaries clear is one of the important architectural principles of Symbiont.

### Core

Responsible for:

- Identity
- Memory
- Cognition
- Internal continuity

### Bridge

Responsible for:

- Connecting the Core to external capabilities
- Translating interfaces between layers

### Body

Responsible for:

- Hardware
- Sensors
- Device capabilities
- Operating system interfaces

### Quest

Responsible for:

- Tasks
- Assignment
- Completion
- Quest state

### Economy

Responsible for:

- Value
- Rewards
- Escrow
- Settlement

### Network

Responsible for:

- Communication
- Node-to-node transport
- Network events

### Permission System

Responsible for:

- Capability authorization
- Access control
- Owner-controlled actions

No single layer should silently become responsible for everything.

---

# 25. The Language Model

A language model can be connected to Symbiont as a cognitive tool.

It can help with:

- Language generation
- Reasoning
- Interpretation
- Planning
- Context processing

But the model is not the Symbiont itself.

The model can be replaced.

The provider can change.

The model can run locally or externally.

The persistent identity and memory remain part of the Core.

This separation is fundamental.

---

# 26. Local-First Design

Symbiont is designed with a local-first direction.

Important information should not have to depend permanently on a remote service.

The long-term goal is to allow the owner to maintain control over:

- Identity
- Memory
- Local state
- Devices
- Permissions
- Symbiont interactions

External services may extend the system.

They should not define the existence of the Symbiont.

---

# 27. Continuity

The most important relationship in the architecture is:

**Identity + Memory + Cognition = Continuity**

Continuity means that the Symbiont should remain conceptually the same system even when parts of its environment change.

A device can change.

A Body can change.

A language model can change.

A network connection can change.

The Core should preserve the continuity of the Symbiont.

---

# 28. Evolution

Symbiont is designed to evolve in layers.

A new capability should not automatically require rebuilding the Core.

For example:

**New hardware**

→ new Body capability

**New operating system**

→ new Bridge implementation

**New AI model**

→ new cognitive provider

**New network protocol**

→ new communication layer

**New task type**

→ new Quest capability

The objective is controlled evolution rather than constant architectural replacement.

---

# 29. Current State

The current implementation is an experimental foundation.

Some components are already functional.

Others are prototypes.

Some are architectural foundations for future development.

The architecture described in this document represents the intended separation of responsibilities while the implementation continues to evolve.

---

# 30. The Core Principle

Symbiont is not one model.

It is not one application window.

It is not one phone.

It is not one server.

It is a system built around persistent identity, memory and cognition.

Everything else can evolve around that foundation.

**The Core is the continuity.**

---

# End of Manifest
