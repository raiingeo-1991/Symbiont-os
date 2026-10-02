from __future__ import annotations

from typing import Any


class XClassNode:
    """
    Minimal experimental specialized Symbiont node.

    X-Class is NOT a second Core.
    It owns no identity, memory, state, journal or cognition.

    All communication with Symbiont happens through XLink.
    """

    CLASS = "X-Class"
    VERSION = "XCLASS/1"

    SPECIALIZATIONS = {
        "general",
        "medical",
        "police",
        "enterprise",
    }

    OWNER_TYPES = {
        "personal",
        "organization",
        "none",
    }

    def __init__(
        self,
        xlink,
        specialization="general",
        owner_type="personal",
    ):
        specialization = str(specialization)
        owner_type = str(owner_type)

        if specialization not in self.SPECIALIZATIONS:
            raise ValueError(
                f"Unsupported X-Class specialization: {specialization}"
            )

        if owner_type not in self.OWNER_TYPES:
            raise ValueError(
                f"Unsupported X-Class owner type: {owner_type}"
            )

        self.xlink = xlink
        self.node_id: str | None = None
        self.specialization = specialization
        self.owner_type = owner_type
        self.skill_modules = []

    def add_skill_module(self, module) -> bool:
        if module is None:
            return False

        if not hasattr(module, "specialization"):
            return False

        if not hasattr(module, "info"):
            return False

        if module.specialization != self.specialization:
            raise ValueError(
                "Skill module specialization does not match X-Class"
            )

        self.skill_modules.append(module)
        return True

    def skill_modules_info(self) -> list[dict[str, Any]]:
        return [module.info() for module in self.skill_modules]

    def connect(self, node_id: str) -> bool:
        node_id = str(node_id).strip()

        if not node_id:
            return False

        if not self.xlink.connect(node_id):
            return False

        self.node_id = node_id
        return True

    def disconnect(self) -> bool:
        result = self.xlink.disconnect()

        if result:
            self.node_id = None

        return result

    def status(self) -> dict[str, Any]:
        return {
            "class": self.CLASS,
            "version": self.VERSION,
            "node_id": self.node_id,
            "specialization": self.specialization,
            "owner_type": self.owner_type,
            "xlink": self.xlink.status(),
        }

    def emit(self, event: str, data: dict[str, Any] | None = None) -> bool:
        if not self.node_id:
            return False

        return self.xlink.send_event(
            event,
            data or {},
        )
