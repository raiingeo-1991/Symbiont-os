# Symbiont X-Class

Experimental architecture for specialized Symbiont forks.

## Position

X-Class is a specialized external node connected to Symbiont
through the existing XLink adapter.

SYMBIONT
|
+- Personal
|  +- Main Symbiont
|
+- X-Class
   +- Specialized forks

## Boundary

X-Class is not a second Core.

X-Class does not own:

- Identity
- MemoryVault
- Memory V2
- CognitiveState
- EventJournal
- Economy
- PermissionGate
- CognitiveEngine
- ContextBus

X-Class communicates with Symbiont through XLink.

## Allowed interaction

The experimental X-Class node may:

- connect
- disconnect
- report status
- emit external events

## Specializations

The experimental X-Class profile supports:

- general
- medical
- police
- enterprise

Owner types:

- personal
- organization
- none

A specialized node may represent a domain-specific Symbiont configuration
without becoming a second Core.

## Skill Modules

X-Class may be extended with optional Skill Modules.

A Skill Module:

- declares a skill name;
- declares its X-Class specialization;
- may declare capabilities;
- does not authorize capabilities itself;
- does not own Security, PermissionGate, Identity, Memory or Core state;
- is attached to an X-Class node rather than becoming part of Core.

Capabilities declared by a Skill Module are descriptive only.
Authorization remains outside the Skill Module boundary.

This allows specialized modules such as medical diagnostics,
police incident analysis, or enterprise operations to be developed
as separate extensions.

## Forbidden architecture

X-Class must not:

- import symbiont_core
- instantiate another Symbiont Core
- directly access MemoryVault
- directly access Identity
- directly access CognitiveState
- directly access EventJournal
- directly access Memory V2
- become the owner of Symbiont identity or memory

## Existing integration point

The project already contains:

core/body.py -> XLink

X-Class intentionally uses this existing connection point instead
of introducing another Core integration layer.

## Experimental status

This is an experimental branch.

The implementation is not part of the canonical Personal Symbiont
architecture until the boundary and lifecycle experiments are complete.
