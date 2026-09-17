"""Optional, configuration-defined confidentiality marking providers."""

from __future__ import annotations

import importlib
import json
import os
import re
from dataclasses import asdict, dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

import yaml

CONTRACT_VERSION = 1
__version__ = "0.1.0"


class MarkingError(ValueError):
    """An assignment or stored envelope is invalid for the selected profile."""


class ConfigurationError(ValueError):
    """A configured provider or profile cannot safely be used."""


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{name} must be a nonempty string")
    if any(ord(c) < 32 for c in value):
        raise ConfigurationError(f"{name} must not contain control characters")
    return value


def _identifier(value: Any, name: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value
    ):
        raise ConfigurationError(
            f"{name} must be a portable identifier of 1 to 128 characters"
        )
    return value


def _color(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ConfigurationError("Presentation colors must use #RRGGBB")
    return value


def _json_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(k, str) for k in value):
        raise MarkingError(f"{name} must be an object with string keys")
    try:
        encoded = json.dumps(dict(value), allow_nan=False)
        return json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise MarkingError(f"{name} must contain JSON values") from exc


@dataclass(frozen=True)
class Level:
    id: str
    name: str
    rank: int
    aliases: tuple[str, ...] = ()
    background_color: str = "#64748b"
    foreground_color: str = "#ffffff"
    assignable: bool = True

    def __post_init__(self) -> None:
        _identifier(self.id, "Level id")
        _text(self.name, "Level name")
        if not isinstance(self.rank, int) or isinstance(self.rank, bool):
            raise ConfigurationError("Level rank must be an integer")
        if not isinstance(self.assignable, bool):
            raise ConfigurationError("Level assignable must be boolean")
        if isinstance(self.aliases, str):
            raise ConfigurationError("Level aliases must be a sequence")
        object.__setattr__(self, "aliases", tuple(self.aliases))
        for alias in self.aliases:
            _text(alias, "Level alias")
        _color(self.background_color)
        _color(self.foreground_color)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["aliases"] = list(self.aliases)
        return value


@dataclass(frozen=True)
class Profile:
    id: str
    revision: str
    levels: tuple[Level, ...]
    defaults: Mapping[str, str] = field(default_factory=dict)
    identity: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _identifier(self.id, "Profile id")
        _text(self.revision, "Profile revision")
        object.__setattr__(self, "levels", tuple(self.levels))
        if not self.levels or not all(
            isinstance(level, Level) for level in self.levels
        ):
            raise ConfigurationError("A profile needs at least one configured Level")
        seen: dict[str, str] = {}
        ranks: set[int] = set()
        ids: set[str] = set()
        for level in self.levels:
            if level.id in ids or level.rank in ranks:
                raise ConfigurationError("Level ids and ranks must be unique")
            ids.add(level.id)
            ranks.add(level.rank)
            for alias in (level.id, level.name, *level.aliases):
                key = alias.strip().casefold()
                if key in seen and seen[key] != level.id:
                    raise ConfigurationError(f"Ambiguous level name or alias: {alias}")
                seen[key] = level.id
        if not isinstance(self.defaults, Mapping):
            raise ConfigurationError("Profile defaults must be an object")
        for key, value in self.defaults.items():
            _text(key, "Default operation")
            if (
                not isinstance(value, str)
                or value not in ids
                or not self.level(value).assignable
            ):
                raise ConfigurationError(
                    f"Unknown or nonassignable default level: {value}"
                )
        object.__setattr__(self, "defaults", dict(self.defaults))
        try:
            object.__setattr__(
                self, "identity", _json_mapping(self.identity, "identity")
            )
        except MarkingError as exc:
            raise ConfigurationError(str(exc)) from exc

    def level(self, value: str) -> Level:
        if not isinstance(value, str) or not value.strip():
            raise MarkingError("A nonempty configured level is required")
        key = value.strip().casefold()
        for level in self.levels:
            if key in {
                s.strip().casefold() for s in (level.id, level.name, *level.aliases)
            }:
                return level
        raise MarkingError(f"Unknown level: {value}")

    def rank(self, value: str) -> int:
        return self.level(value).rank

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": CONTRACT_VERSION,
            "id": self.id,
            "revision": self.revision,
            "levels": [level.to_dict() for level in self.levels],
            "defaults": dict(self.defaults),
            "identity": dict(self.identity),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Profile:
        if not isinstance(value, Mapping):
            raise ConfigurationError("Profile must be an object")
        data = dict(value)
        version = data.pop("contract_version", None)
        if type(version) is not int or version != CONTRACT_VERSION:
            raise ConfigurationError("Unsupported or missing profile contract_version")
        try:
            data["levels"] = tuple(Level(**item) for item in data["levels"])
            return cls(**data)
        except (KeyError, TypeError, MarkingError) as exc:
            raise ConfigurationError(f"Invalid profile: {exc}") from exc


@dataclass(frozen=True)
class NormalizedMarking:
    profile_id: str
    profile_revision: str
    level_id: str
    raw_text: str = ""
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("profile_id", "profile_revision", "level_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise MarkingError(f"{name} must be a nonempty string")
        try:
            _identifier(self.profile_id, "profile_id")
            _identifier(self.level_id, "level_id")
        except ConfigurationError as exc:
            raise MarkingError(str(exc)) from exc
        if not isinstance(self.raw_text, str):
            raise MarkingError("raw_text must be a string")
        object.__setattr__(
            self, "attributes", _json_mapping(self.attributes, "attributes")
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> NormalizedMarking:
        try:
            return cls(**dict(value))
        except (TypeError, ValueError) as exc:
            raise MarkingError(f"Invalid marking envelope: {exc}") from exc


@dataclass(frozen=True)
class Display:
    text: str
    background_color: str
    foreground_color: str

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise MarkingError("Display text must be a string")
        _color(self.background_color)
        _color(self.foreground_color)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@runtime_checkable
class MarkingProvider(Protocol):
    contract_version: int
    profile: Profile

    def parse(self, text: str) -> NormalizedMarking: ...
    def validate(self, marking: NormalizedMarking) -> NormalizedMarking: ...
    def present(self, marking: NormalizedMarking) -> Display: ...
    def compose(
        self,
        markings: Sequence[NormalizedMarking],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Display | None: ...


class ConfiguredProvider:
    """Reference exact-label parser; it has no compound marking grammar."""

    contract_version = CONTRACT_VERSION

    def __init__(self, profile: Profile):
        self.profile = profile

    def parse(self, text: str) -> NormalizedMarking:
        level = self.profile.level(text)
        return self.validate(
            NormalizedMarking(self.profile.id, self.profile.revision, level.id, text)
        )

    def _level(self, marking: NormalizedMarking) -> Level:
        if not isinstance(marking, NormalizedMarking):
            raise MarkingError("Expected a normalized marking")
        if (marking.profile_id, marking.profile_revision) != (
            self.profile.id,
            self.profile.revision,
        ):
            raise MarkingError(
                "Marking profile or revision does not match the active provider"
            )
        level = self.profile.level(marking.level_id)
        if level.id != marking.level_id:
            raise MarkingError("Envelope level_id must be a stable configured ID")
        return level

    def validate(self, marking: NormalizedMarking) -> NormalizedMarking:
        level = self._level(marking)
        if not level.assignable:
            raise MarkingError("This level is available for presentation only")
        if marking.attributes:
            raise MarkingError(
                "The reference profile does not define marking attributes"
            )
        return marking

    def present(self, marking: NormalizedMarking) -> Display:
        level = self._level(marking)
        if marking.attributes:
            raise MarkingError(
                "The reference profile does not define marking attributes"
            )
        return Display(level.name, level.background_color, level.foreground_color)

    def compose(
        self,
        markings: Sequence[NormalizedMarking],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Display | None:
        for marking in markings:
            self._level(marking)
            if marking.attributes:
                raise MarkingError(
                    "The reference profile does not define marking attributes"
                )
        if not markings:
            return None
        return self.present(max(markings, key=lambda m: self.profile.rank(m.level_id)))


def create_provider(
    profile: str | Path | Mapping[str, Any] | None = None,
) -> ConfiguredProvider:
    try:
        if profile is None:
            document = yaml.safe_load(
                files(__package__).joinpath("profiles/commercial.yaml").read_text()
            )
        elif isinstance(profile, Mapping):
            document = profile
        else:
            path = Path(profile)
            if not path.is_absolute():
                raise ConfigurationError("Profile path must be an absolute local path")
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        return ConfiguredProvider(Profile.from_dict(document))
    except (OSError, yaml.YAMLError, TypeError) as exc:
        raise ConfigurationError(f"Unable to load marking profile: {exc}") from exc


def load_provider(
    *,
    enabled: bool,
    provider: str = "kamiwaza_confidentiality:create_provider",
    profile: str | Path | Mapping[str, Any] | None = None,
) -> MarkingProvider | None:
    if not isinstance(enabled, bool):
        raise ConfigurationError("enabled must be boolean")
    if not enabled:
        return None
    try:
        module, factory = provider.split(":")
        instance = getattr(importlib.import_module(module), factory)(profile)
        if (
            not isinstance(instance, MarkingProvider)
            or type(instance.contract_version) is not int
            or instance.contract_version != CONTRACT_VERSION
            or not all(
                callable(getattr(instance, method, None))
                for method in ("parse", "validate", "present", "compose")
            )
        ):
            raise ConfigurationError("Incompatible marking provider contract")
        if not isinstance(instance.profile, Profile):
            raise ConfigurationError(
                "Provider profile must implement the neutral Profile contract"
            )
        return instance
    except ConfigurationError:
        raise
    except Exception as exc:
        raise ConfigurationError(
            f"Unable to load configured marking provider {provider}: {exc}"
        ) from exc


def load_from_env(environ: Mapping[str, str] | None = None) -> MarkingProvider | None:
    env = os.environ if environ is None else environ
    enabled = env.get("KAMIWAZA_MARKINGS_ENABLED", "false").strip().casefold()
    if enabled not in {"true", "false", "1", "0"}:
        raise ConfigurationError("KAMIWAZA_MARKINGS_ENABLED must be true or false")
    return load_provider(
        enabled=enabled in {"true", "1"},
        provider=env.get(
            "KAMIWAZA_MARKINGS_PROVIDER", "kamiwaza_confidentiality:create_provider"
        ),
        profile=env.get("KAMIWAZA_MARKINGS_PROFILE") or None,
    )
