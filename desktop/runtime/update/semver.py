"""Semantic version comparison for VANOVA updates."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

_VERSION_RE = re.compile(
    r"^v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?"
    r"(?:\+(?P<build>[0-9A-Za-z.-]+))?$"
)


@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int
    prerelease: Optional[str] = None
    build: Optional[str] = None

    @classmethod
    def parse(cls, raw: str) -> "Version":
        raw = (raw or "").strip()
        m = _VERSION_RE.match(raw)
        if not m:
            raise ValueError(f"Invalid version: {raw!r}")
        return cls(
            int(m.group("major")),
            int(m.group("minor")),
            int(m.group("patch")),
            m.group("prerelease"),
            m.group("build"),
        )

    def __str__(self) -> str:
        s = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            s += f"-{self.prerelease}"
        if self.build:
            s += f"+{self.build}"
        return s


def compare(a: str, b: str) -> int:
    """Return -1 if a<b, 0 if equal, 1 if a>b."""
    va, vb = Version.parse(a), Version.parse(b)
    for field in ("major", "minor", "patch"):
        da, db = getattr(va, field), getattr(vb, field)
        if da < db:
            return -1
        if da > db:
            return 1
    # Stable beats prerelease
    if va.prerelease and not vb.prerelease:
        return -1
    if vb.prerelease and not va.prerelease:
        return 1
    if va.prerelease and vb.prerelease:
        return _compare_prerelease(va.prerelease, vb.prerelease)
    return 0


def _compare_prerelease(a: str, b: str) -> int:
    """Compare two prerelease strings per semver 2.0.0: dot-separated
    identifiers, numeric identifiers compare numerically, numeric <
    alphanumeric, fewer identifiers < more. Fixes beta.10 > beta.2 (string
    comparison would say the opposite and block the update)."""
    ai = a.split(".")
    bi = b.split(".")
    for x, y in zip(ai, bi):
        xn, yn = x.isdigit(), y.isdigit()
        if xn and yn:
            ix, iy = int(x), int(y)
            if ix < iy:
                return -1
            if ix > iy:
                return 1
        elif xn != yn:
            return -1 if xn else 1  # numeric < alphanumeric
        else:
            if x < y:
                return -1
            if x > y:
                return 1
    if len(ai) < len(bi):
        return -1
    if len(ai) > len(bi):
        return 1
    return 0


def gt(a: str, b: str) -> bool:
    return compare(a, b) > 0


def gte(a: str, b: str) -> bool:
    return compare(a, b) >= 0


def lt(a: str, b: str) -> bool:
    return compare(a, b) < 0


def satisfies_minimum(version: str, minimum: str) -> bool:
    return gte(version, minimum)
