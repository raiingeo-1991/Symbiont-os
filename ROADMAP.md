# SYMBIONT — ROADMAP

The path from a persistent personal AI to a distributed Symbiont network.

This document describes where Symbiont is going.

It is not an installation guide.

For the project overview, see [README](README.md).

For installation and testing, see [QUICKSTART](QUICKSTART.md).

---

# Stage 0 — Foundation

**STATUS: COMPLETED / WORKING FOUNDATION**

The first functional foundation of Symbiont is already in place.

The project currently has:

- Persistent identity
- Recovery mechanism
- Persistent memory
- Memory search
- Cognitive engine
- Event journal
- Permission system
- Proactive processing
- Android Body
- Android Bridge
- Local LLM interface
- Network foundation
- Quest system
- Economy foundation
- Escrow
- XLink
- Automated tests

The foundation is working, but the project is still experimental.

---

# Stage 1 — Persistent Memory

**STATUS: IN DEVELOPMENT**

Memory is one of the central parts of Symbiont.

The goal is not simply to store conversations.

The goal is to build persistent knowledge that can remain useful over time.

### Current direction

- Persistent local storage
- Memory search
- Importance
- Principles
- Preferences
- Open loops
- Recall
- Memory relationships

### Next

- Memory consolidation
- Duplicate detection
- Archiving
- Memory graph
- Better relevance ranking
- Integrity verification
- Backup and recovery
- Encrypted storage
- Multi-device synchronization
- Conflict resolution

The long-term goal is simple:

**Experience → Memory → Knowledge → Context → Better decisions**

---

# Stage 2 — Bodies

**STATUS: IN DEVELOPMENT**

The Core should not depend on a single physical device.

Android is the first Body.

Future Bodies may include:

- Phones
- Tablets
- PCs
- Watches
- Glasses
- Earbuds
- Other hardware

The same Symbiont should eventually be able to use different Bodies without losing its identity or memory.

---

# Stage 3 — Perception

**STATUS: FOUNDATION / FUTURE**

Symbiont needs ways to perceive its environment.

### Current foundation

- Microphone / speech recognition
- Ambient input
- Event processing
- Permission control

### Future

- Camera
- Image understanding
- OCR
- Object recognition
- Screen and context perception
- Richer sensor integration

Perception should always remain controlled by the owner's permissions.

---
# Stage 4 — Network

**STATUS: FOUNDATION IMPLEMENTED**

Symbionts need to communicate with other nodes without requiring one central system.

### Current foundation

- UDP communication
- TCP communication
- Node identity
- Basic node messaging
- Local node-to-node testing

### Next

- Automatic node discovery
- Authenticated peers
- Encrypted transport
- Trusted peer system
- Memory synchronization
- Conflict resolution
- Offline message delivery
- Resilient routing
- Node reputation

The goal is to allow Symbionts to communicate directly while keeping ownership and identity independent.

---

# Stage 5 — Autonomy

**STATUS: IN DEVELOPMENT**

Symbiont should gradually move from simply responding to requests toward understanding context and performing approved actions.

### Current foundation

- Cognitive engine
- Proactive mode
- Background processing
- Night processing
- Ambient events
- Permission system
- Event journal

### Next

- Planning
- Reminders
- Approved task execution
- Information gathering
- Data analysis
- Reports
- Context-aware actions
- Long-running objectives

Autonomy must remain controlled by permissions and owner authority.

The goal is not uncontrolled automation.

The goal is useful autonomy.

---

# Stage 6 — Quest System

**STATUS: PROTOTYPE**

Quests are intended to connect real-world tasks with Symbiont.

The basic principle is:

**Task → Work → Proof → Settlement**

A quest may eventually represent anything from a personal task to a network task.

### Current foundation

- Quest creation
- Quest identifiers
- Descriptions
- Rewards
- Assignees
- Completion
- QuestBoard
- Economy integration
- Escrow

### Next

- Network quests
- Proof of completion
- Expiration
- Reputation
- Witnesses
- Quorum verification
- Dispute handling
- Offline synchronization
- Secure settlement

The Quest system is intentionally being developed separately from the Core.

The Core remembers and understands.

The Quest system manages tasks.

The Economy manages settlement.

---
# Stage 7 — Economy

**STATUS: PROTOTYPE**

The Economy layer provides the foundation for task-based rewards and future distributed settlement.

### Current foundation

- Wallet
- Balance
- Rewards
- Persistent economy state
- Escrow
- Reserve
- Release
- Refund
- Freeze
- Unique quest operation IDs

The current Escrow lifecycle supports:

**Available → Escrow → Release**

or:

**Available → Escrow → Refund**

An operation can also enter:

**Escrow → Frozen**

before being released or refunded.

### Next

- Network settlement
- Transaction verification
- Replay protection
- Distributed accounting
- Proof-based payments
- Dispute handling
- Multi-node settlement
- Transaction history
- Stronger cryptographic integrity

The current Economy is experimental.

It is not a production financial system.

---

# Stage 8 — External Node Types

**STATUS: FUTURE ARCHITECTURE**

The Symbiont protocol is being designed so that different types of nodes can interact without changing the Core.

Future transactions can contain:

- `creator_node`
- `worker_node`
- `creator_type`
- `worker_type`

The current model is:

**personal → personal**

Future combinations may include:

**personal → external**

**external → personal**

**external → external**

The important architectural rule is:

**External node logic stays outside the Core.**

The Core remains responsible for:

- Memory
- Identity
- Cognition
- Internal continuity

This allows the system to evolve without turning the Core into a collection of external business or hardware logic.

---

# Stage 9 — Scaling

**STATUS: FUTURE**

Scaling comes after the fundamental architecture becomes reliable.

Planned testing levels include:

**10 → 50 → 100 → 500 → 1,000 → 3,000 → 10,000 → 30,000+ nodes**

Future tests will examine:

- Memory load
- Network traffic
- Concurrent nodes
- Quest traffic
- Economy operations
- Synchronization
- CPU usage
- RAM usage
- Failure recovery

Scaling is not the current primary development target.

The priority is first to make the foundation reliable.

---
# Stage 10 — Security

**STATUS: CONTINUOUS DEVELOPMENT**

Security is not a final feature.

It is a permanent part of Symbiont development.

### Current foundation

- Recovery mechanism
- Node identity
- Permission system
- Event journal
- Persistent state
- Operation identifiers
- Escrow state protection

### Next

- Cryptographic identity verification
- Encrypted transport
- Authenticated peers
- Secure key storage
- Replay protection
- Transaction signatures
- Memory integrity verification
- Secure synchronization
- Threat modeling
- Security testing
- Recovery procedures

The goal is to keep the owner in control of the Symbiont and its capabilities.

---

# Stage 11 — Portability

**STATUS: FUTURE**

A Symbiont should not be permanently tied to one device.

The long-term goal is to move the same Symbiont between different Bodies while preserving its continuity.

A future migration may look like:

**Device A → Secure Recovery → Device B**

The following should eventually be preserved:

- Identity
- Memory
- History
- Principles
- Preferences
- Relationships
- Configuration
- Authorized capabilities

The hardware may change.

The Symbiont should remain.

---

# Stage 12 — Symbiont Network

**STATUS: LONG-TERM**

The long-term vision is a network of autonomous Symbionts.

The network may eventually support:

- Peer-to-peer communication
- Distributed tasks
- Cooperation between Symbionts
- Reputation
- Quests
- Verified work
- Economic settlement
- Shared infrastructure
- Autonomous agents

The network should not require every Symbiont to depend permanently on one central system.

The objective is a network where people retain ownership of their own Symbionts.

---

# Current Development Priority

The immediate priority is not maximum scale.

The priority is a reliable foundation.

The current order is:

1. Persistent memory
2. Identity and recovery
3. Core stability
4. Body and Bridge
5. Android integration
6. Secure networking
7. Quest reliability
8. Economy reliability
9. Portability
10. Security
11. Multi-device operation
12. Large-scale networking

---

# The Architecture Must Remain Stable

Symbiont should grow by adding capabilities around the Core rather than constantly rewriting the Core.

The principle is:

**Core → Bridge → Body → Device**

The Core remains responsible for:

- Memory
- Identity
- Cognition
- Continuity

The Body provides capabilities.

The Bridge connects them.

This separation allows Symbiont to evolve without making the Core dependent on a particular device, operating system or AI model.

---

# Long-Term Direction

The development path is:

**Personal AI → Persistent Symbiont → Multi-device Symbiont → Networked Symbionts → Distributed Symbiont Ecosystem**

The exact implementation will evolve as the project is tested.

The architecture is designed to evolve with it.

---

# Final Principle

The device belongs to the Symbiont.

The Symbiont belongs to its owner.
