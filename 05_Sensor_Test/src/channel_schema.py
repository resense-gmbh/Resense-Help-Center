"""Declarative description of the payload layout of a sensor frame.

A ``FrameSchema`` describes what the floats inside a frame mean, so that
consumers (display, CSV logger, plotter) no longer have to hardcode indices.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from math import isfinite
from typing import Any, Dict, Iterator, List, Optional, Tuple

import src.protocol_definition as protocol
import src.serial_decoder as serial_decoder

ROLE_FORCE = "force"
ROLE_TORQUE = "torque"
ROLE_TEMPERATURE = "temperature"
ROLE_CURRENT = "current"
ROLE_VOLTAGE = "voltage"
ROLE_RAW = "raw"
ROLE_OTHER = "other"

VALID_ROLES = frozenset({
    ROLE_FORCE, ROLE_TORQUE, ROLE_TEMPERATURE,
    ROLE_CURRENT, ROLE_VOLTAGE, ROLE_RAW, ROLE_OTHER,
})


class SchemaError(Exception):
    """Raised when a profile definition is invalid."""


class ProtocolMode(IntEnum):
    legacy = protocol.LEGACY
    standard = protocol.STANDARD
    extended = protocol.EXTENDED


class MessageType(IntEnum):
    measurement = serial_decoder.MEASUREMENT_DATA
    config = serial_decoder.CONFIGURATION_DATA
    diagnostic = serial_decoder.DIAGNOSTIC_DATA


def _parse_enum(enum_cls, raw: Any, field_name: str, profile_id: str):
    """Accept only the spelled-out names, never the underlying numbers."""
    valid = ", ".join(f"'{e.name}'" for e in enum_cls)
    if not isinstance(raw, str):
        raise SchemaError(
            f"Profile '{profile_id}': '{field_name}' must be one of {valid}, "
            f"not the numeric value {raw!r}"
        )
    try:
        return enum_cls[raw.strip().lower()]
    except KeyError:
        raise SchemaError(
            f"Profile '{profile_id}': unknown {field_name} '{raw}'. Valid values: {valid}"
        ) from None


@dataclass(frozen=True)
class ChannelSpec:
    """One float inside the frame payload."""
    key: str
    label: str
    unit: str = ""
    role: str = ROLE_OTHER
    tarable: bool = False
    csv_column: str = ""
    scale: float = 1.0
    precision: int = 5
    valid_min: Optional[float] = None
    valid_max: Optional[float] = None

    def __post_init__(self):
        if not self.key:
            raise SchemaError("ChannelSpec requires a non-empty 'key'")
        if self.role not in VALID_ROLES:
            raise SchemaError(
                f"Channel '{self.key}': unknown role '{self.role}'. "
                f"Valid roles: {sorted(VALID_ROLES)}"
            )
        if not self.label:
            object.__setattr__(self, "label", self.key)
        if not self.csv_column:
            object.__setattr__(self, "csv_column", self.key)
        if (self.valid_min is not None and self.valid_max is not None
                and self.valid_min > self.valid_max):
            raise SchemaError(
                f"Channel '{self.key}': valid_min {self.valid_min} > valid_max {self.valid_max}"
            )

    def implausibility(self, value: float) -> Optional[str]:
        """Return a reason string when the value cannot come from a healthy frame."""
        if not isfinite(value):
            return "not a finite number"
        if self.valid_min is not None and value < self.valid_min:
            return f"below valid_min {self.valid_min}"
        if self.valid_max is not None and value > self.valid_max:
            return f"above valid_max {self.valid_max}"
        return None

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "ChannelSpec":
        unknown = set(raw) - {
            "key", "label", "unit", "role", "tarable",
            "csv_column", "scale", "precision", "valid_min", "valid_max",
        }
        if unknown:
            raise SchemaError(f"Channel '{raw.get('key')}': unknown keys {sorted(unknown)}")
        return cls(
            key=raw["key"],
            label=raw.get("label", ""),
            unit=raw.get("unit", ""),
            role=raw.get("role", ROLE_OTHER),
            tarable=bool(raw.get("tarable", False)),
            csv_column=raw.get("csv_column", ""),
            scale=float(raw.get("scale", 1.0)),
            precision=int(raw.get("precision", 5)),
            valid_min=None if raw.get("valid_min") is None else float(raw["valid_min"]),
            valid_max=None if raw.get("valid_max") is None else float(raw["valid_max"]),
        )


@dataclass(frozen=True)
class FrameSchema:
    """Payload layout of one frame type of one device."""
    id: str
    device: str
    protocol_mode: ProtocolMode
    message_type: MessageType
    payload_count: int
    channels: Tuple[ChannelSpec, ...]
    csv_order: Tuple[str, ...] = ()

    def __post_init__(self):
        if len(self.channels) != self.payload_count:
            raise SchemaError(
                f"Profile '{self.id}': payload_count={self.payload_count} "
                f"but {len(self.channels)} channels defined"
            )
        for attr in ("key", "csv_column"):
            seen = [getattr(c, attr) for c in self.channels]
            duplicates = {v for v in seen if seen.count(v) > 1}
            if duplicates:
                raise SchemaError(f"Profile '{self.id}': duplicate {attr} {sorted(duplicates)}")

        wire_columns = tuple(c.csv_column for c in self.channels)
        if not self.csv_order:
            object.__setattr__(self, "csv_order", wire_columns)
        elif sorted(self.csv_order) != sorted(wire_columns):
            raise SchemaError(
                f"Profile '{self.id}': csv_order must contain exactly the channel "
                f"csv_columns, got {list(self.csv_order)} vs {list(wire_columns)}"
            )

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "FrameSchema":
        profile_id = raw.get("id", "<unnamed>")
        try:
            channels = tuple(ChannelSpec.from_dict(c) for c in raw["channels"])
            return cls(
                id=raw["id"],
                device=raw.get("device", raw["id"]),
                protocol_mode=_parse_enum(ProtocolMode, raw["protocol_mode"], "protocol_mode", profile_id),
                message_type=_parse_enum(MessageType, raw["message_type"], "message_type", profile_id),
                payload_count=int(raw["payload_count"]),
                channels=channels,
                csv_order=tuple(raw.get("csv_order", ())),
            )
        except KeyError as e:
            raise SchemaError(f"Profile '{profile_id}' is missing required key {e}") from e

    @property
    def key(self) -> Tuple[int, int, int]:
        return (self.protocol_mode, self.message_type, self.payload_count)

    def csv_columns(self) -> Tuple[str, ...]:
        return self.csv_order

    def csv_value_indices(self) -> Tuple[int, ...]:
        """Wire indices in the order the CSV columns expect them."""
        wire = {c.csv_column: i for i, c in enumerate(self.channels)}
        return tuple(wire[column] for column in self.csv_order)

    def index_of(self, key: str) -> Optional[int]:
        return next((i for i, c in enumerate(self.channels) if c.key == key), None)

    def tarable_indices(self) -> Tuple[int, ...]:
        return tuple(i for i, c in enumerate(self.channels) if c.tarable)

    def columns_by_role(self, *roles: str) -> Tuple[str, ...]:
        matching = {c.csv_column for c in self.channels if c.role in roles}
        return tuple(column for column in self.csv_order if column in matching)

    def __str__(self):
        return f"{self.id} ({self.device}, {self.payload_count} channels)"


@dataclass
class SensorSample:
    """One decoded frame: the values plus the schema that explains them.

    Behaves like the plain float tuple that used to be returned, so existing
    positional access keeps working.
    """
    values: Tuple[float, ...]
    schema: FrameSchema
    timestamp: datetime = field(default_factory=datetime.now)
    frame_counter: Optional[int] = None
    message_type: int = 0

    def __iter__(self) -> Iterator[float]:
        return iter(self.values)

    def __getitem__(self, index):
        return self.values[index]

    def __len__(self) -> int:
        return len(self.values)

    def __bool__(self) -> bool:
        return bool(self.values)

    def get(self, key: str, default: float = 0.0) -> float:
        index = self.schema.index_of(key)
        return default if index is None else self.values[index]

    def format_channels(self) -> str:
        return ", ".join(
            f"{c.label}: {v:+10.{c.precision}f}"
            for c, v in zip(self.schema.channels, self.values)
        )

    def implausible_channels(self) -> List[Tuple[ChannelSpec, float, str]]:
        """Channels whose value violates the range declared in the device profile."""
        issues = []
        for channel, value in zip(self.schema.channels, self.values):
            reason = channel.implausibility(value)
            if reason is not None:
                issues.append((channel, value, reason))
        return issues
