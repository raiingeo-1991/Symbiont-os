# Symbiont

**A local-first personal AI system built around identity, memory, continuity and controlled evolution.**

Symbiont is not intended to be another chatbot.

The project started from a different question:

> **What if an AI system could remember, preserve its identity, and continue existing when the device, model, network or environment changes?**

The answer is being built as Symbiont.

Symbiont is an experimental system whose Core is separated from the devices, models and external services it uses.

The philosophy comes first. The architecture follows it. The code serves the architecture.

---

## What is Symbiont?

Symbiont is a system built around several persistent concepts:

- **Identity** — the Symbiont has its own persistent identity.
- **Memory** — experience can survive beyond a single conversation or process.
- **Cognition** — language models are tools used by the system, not the identity of the system itself.
- **Continuity** — the system is designed to preserve its state and identity across changes in its environment.
- **Core** — the persistent logical center of the system.
- **Bridge / Body** — interfaces through which the Core interacts with hardware and external capabilities.

The device is not the Symbiont.

The model is not the Symbiont.

The network is not the Symbiont.

They are components and environments around it.

---

## Core Architecture

The current system is organized around existing components rather than one monolithic Core.

```text
                    ┌─────────────────────┐
                    │       Symbiont      │
                    │        Core         │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
          Identity          Memory          Cognition
              │                │                │
              └────────────────┼────────────────┘
                               │
                         EventJournal
                               │
                               ▼
                         SCA-1 Shadow
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
        ▼                      ▼                      ▼
      Quest                  P2P                  Economy
        │                      │                      │
        └──────────────────────┼──────────────────────┘
                               │
                               ▼
                           Security
                               │
                     ┌─────────┴─────────┐
                     ▼                   ▼
                  Bridge                Body
```

The architecture is intentionally evolutionary: new capabilities should extend existing boundaries rather than constantly replace the system underneath them.

---

## Memory

Memory is one of the foundational ideas of Symbiont.

The system maintains persistent memory instead of treating every application launch as a completely new beginning.

The current implementation includes persistent memory storage, retrieval, journaling and Memory V2 components.

The goal is not simply to store text. The goal is to preserve experience as part of the history of the system.

---

## Continuity

Continuity is a central architectural principle of Symbiont.

The current implementation includes the optional **SCA-1 Continuity Shadow**.

```text
Core → EventJournal → SCA-1 Shadow
```

SCA-1 observes Core events and maintains an independent continuity contour containing state versions, hashes, event history and validation information.

SCA-1 does not replace the Core and does not require moving the continuity system into the Core itself.

Enable it explicitly with:

```bash
export SYMBIONT_SCA1_SHADOW=1
```

## Security

Symbiont contains several security boundaries with separate responsibilities.

### SCP-1

SCP-1 provides authenticated protocol envelopes, freshness checks, structure validation and Zero-Trust verification.

Optional P2P integration can be enabled with:

```bash
export SYMBIONT_SCP1_P2P=1
```

Discovery and trust remain separate concepts.

### SMSA

SMSA provides an additional security and authorization boundary for supported capabilities and settlement operations.

Enable it with:

```bash
export SYMBIONT_SMSA=1
```

The application-facing PermissionGate remains responsible for explicit capability permissions.

---

## Quest and Economy

A Quest in Symbiont is not limited to conventional employment.

It represents an action or activity that can become part of the system history.

The current implementation connects Quest delegation with P2P execution and secure settlement:

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
SCA-1
```

The current runtime already contains Quest lifecycle handling, required-rank metadata, settlement authorization and escrow operations.

Proof of completion, reputation, qualification, skills, machine-verifiable quest types, witnesses and dispute/arbitration mechanisms remain areas for further development rather than being presented as completed functionality.

This distinction is intentional: the documentation describes what exists separately from what is planned.

---

## Current State

Symbiont remains an experimental project under active development.

The current development priority is:

- integration testing;
- regression testing;
- bug fixing;
- verification of component boundaries;
- strengthening existing mechanisms;
- preserving Core stability.

Large new architectural layers are not added without a demonstrated need.

The current full test suite contains **92 tests**.

---

## Quick Start

From the canonical project directory:

```bash
cd ~/Symbiont-os
python symbiont_core.py
```

For the complete startup procedure and integration checks, see [`QUICKSTART.md`](QUICKSTART.md).

If a local LLM is used, it can be started separately through llama.cpp and connected through the configured local endpoint.

---

## Documentation

- [`PHILOSOPHY.md`](PHILOSOPHY.md) — the ideas and principles behind Symbiont.
- [`MANIFEST.md`](MANIFEST.md) — system architecture, components and responsibility boundaries.
- [`QUICKSTART.md`](QUICKSTART.md) — current canonical startup and verification procedure.
- [`ROADMAP.md`](ROADMAP.md) — development direction.
- [`docs/SCA-1.md`](docs/SCA-1.md) — continuity architecture and Core Shadow integration.
- [`docs/SCP-1.md`](docs/SCP-1.md) — authenticated protocol and Zero-Trust integration.
- [`docs/docs/ECONOMY.md`](docs/docs/ECONOMY.md) — Economy and escrow model.
- [`docs/QUESTS.md`](docs/QUESTS.md) — Quest model, lifecycle and planned verification mechanisms.
- [`docs/README.ru.md`](docs/README.ru.md) — Russian documentation entry point.

---

## Development Principle

Symbiont is developed from the top down.

The philosophy defines the boundaries.

The architecture implements those boundaries.

The code expresses the current implementation.

The implementation may change.

The principle should remain.

**The Symbiont should remain more persistent than the technology used to run it.**

---

## Project Status

This project is experimental. Components and interfaces may change as testing continues.

The canonical local development line is:

`~/Symbiont-os`

Do not treat archived or legacy copies as the active development line.

---

## Credits

Some ideas and architectural approaches used in the Memory V2 layer
were inspired by the work of Artemy Voikhansky (@artemyvo).

Special thanks for the discussion and permission to adapt these ideas
for the Symbiont project.

## License

See [`LICENSE`](LICENSE) for the current licensing terms.

---

**Symbiont — this is only the beginning.**

