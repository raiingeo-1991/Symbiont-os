# Symbiont Memory V2

## Overview

Memory V2 is an additional long-term memory architecture developed for
Symbiont.

The goal was to introduce associative memory, experience relationships,
reflection, knowledge consolidation and memory decay without replacing
the existing Symbiont Core or its MemoryVault.

The existing MemoryVault remains the source of truth.

Memory V2 was integrated as a separate layer and initially operates in
Shadow Mode so that the new system can be tested without modifying or
endangering the existing memory.

---

## Inspiration and Attribution

The Memory V2 architecture was developed with inspiration from the work
of Artemy Voikhansky and the AVA project.

The following concepts and architectural approaches were studied and
adapted:

- associative memory;
- experience graph;
- reflection;
- knowledge consolidation;
- memory decay;
- separation of memory-related
