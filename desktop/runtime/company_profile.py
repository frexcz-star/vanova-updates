"""Company Profile — structured business context for agents."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from . import config_store


@dataclass
class CompanyProfile:
    identity: dict = field(default_factory=lambda: {"name": "", "slug": ""})
    industry: str = ""
    description: str = ""
    products: list[str] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    integrations: list[str] = field(default_factory=list)
    priorities: list[str] = field(default_factory=list)
    preferences: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CompanyProfile":
        return cls(
            identity=data.get("identity", {"name": "", "slug": ""}),
            industry=data.get("industry", ""),
            description=data.get("description", ""),
            products=data.get("products", []),
            channels=data.get("channels", []),
            goals=data.get("goals", []),
            integrations=data.get("integrations", []),
            priorities=data.get("priorities", []),
            preferences=data.get("preferences", {}),
        )


def save_profile(profile: CompanyProfile) -> None:
    # BUG-037 (fix): merge con el perfil existente en vez de sobrescribirlo.
    # La UI puede enviar un PATCH parcial (p.ej. solo preferences) para declarar
    # el margen global; sobrescribir con from_dict perdería identity/channels.
    existing = load_profile()
    merged = CompanyProfile(
        identity=profile.identity if profile.identity.get("name") or profile.identity.get("slug") else existing.identity,
        industry=profile.industry or existing.industry,
        description=profile.description or existing.description,
        products=profile.products or existing.products,
        channels=profile.channels or existing.channels,
        goals=profile.goals or existing.goals,
        integrations=profile.integrations or existing.integrations,
        priorities=profile.priorities or existing.priorities,
        preferences={**existing.preferences, **profile.preferences},
    )
    config_store.save({"companyProfile": merged.to_dict()})


def load_profile() -> CompanyProfile:
    data = config_store.load().get("companyProfile", {})
    return CompanyProfile.from_dict(data) if data else CompanyProfile()
