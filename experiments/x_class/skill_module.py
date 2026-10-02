from __future__ import annotations

from typing import Any


class XClassSkillModule:
    """
    Minimal contract for an optional X-Class skill module.

    A skill module extends an X-Class node without becoming Core.
    It owns no Symbiont identity, memory or cognitive state.
    """

    VERSION = "SKILL/1"

    def __init__(
        self,
        name: str,
        specialization: str,
        capabilities=None,
    ):
        self.name = str(name).strip()
        self.specialization = str(specialization).strip()
        self.capabilities = tuple(
            str(cap).strip()
            for cap in (capabilities or [])
            if str(cap).strip()
        )

        if not self.name:
            raise ValueError("Skill module name cannot be empty")

        if not self.specialization:
            raise ValueError("Skill module specialization cannot be empty")

    def info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "specialization": self.specialization,
            "version": self.VERSION,
            "capabilities": list(self.capabilities),
        }
