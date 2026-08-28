"""Loads device profiles from JSON and resolves them against incoming frames."""
import json
import logging
import os
from typing import Dict, List, Optional, Tuple

from src.channel_schema import FrameSchema, MessageType, ProtocolMode, SchemaError

logger = logging.getLogger(__name__)

DEFAULT_PROFILE_FILE = "device_profiles.json"


def _name_of(enum_cls, value: int) -> str:
    try:
        return enum_cls(value).name
    except ValueError:
        return f"unknown({value})"


class UnknownSchemaError(LookupError):
    """No profile matches the received frame."""

    def __init__(self, protocol_mode: int, message_type: int, payload_count: int):
        self.protocol_mode = protocol_mode
        self.message_type = message_type
        self.payload_count = payload_count
        super().__init__(
            f"No device profile for protocol_mode={_name_of(ProtocolMode, protocol_mode)}, "
            f"message_type={_name_of(MessageType, message_type)}, "
            f"payload_count={payload_count}"
        )


class SchemaRegistry:
    """Holds all known frame layouts and looks them up by frame header."""

    def __init__(self, schemas: List[FrameSchema]):
        self._by_key: Dict[Tuple[int, int, int], FrameSchema] = {}
        self._by_id: Dict[str, FrameSchema] = {}
        self._forced_id: Optional[str] = None

        for schema in schemas:
            if schema.key in self._by_key:
                raise SchemaError(
                    f"Duplicate profile for {schema.key}: "
                    f"'{self._by_key[schema.key].id}' and '{schema.id}'"
                )
            if schema.id in self._by_id:
                raise SchemaError(f"Duplicate profile id '{schema.id}'")
            self._by_key[schema.key] = schema
            self._by_id[schema.id] = schema

    @classmethod
    def from_file(cls, path: str = DEFAULT_PROFILE_FILE) -> "SchemaRegistry":
        if not os.path.exists(path):
            raise SchemaError(f"Device profile file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if "profiles" not in raw:
            raise SchemaError(f"{path}: missing top-level 'profiles' key")
        return cls([FrameSchema.from_dict(p) for p in raw["profiles"]])

    @property
    def schemas(self) -> List[FrameSchema]:
        return list(self._by_id.values())

    def by_id(self, profile_id: str) -> FrameSchema:
        if profile_id not in self._by_id:
            raise SchemaError(f"Unknown profile id '{profile_id}'")
        return self._by_id[profile_id]

    def force_profile(self, profile_id: Optional[str]) -> None:
        """Pin resolution to one profile, or pass None to resume auto-detection."""
        if profile_id is not None:
            self.by_id(profile_id)
        self._forced_id = profile_id

    @property
    def forced_profile(self) -> Optional[str]:
        return self._forced_id

    def resolve(self, protocol_mode: int, message_type: int, payload_count: int) -> FrameSchema:
        if self._forced_id is not None:
            return self._by_id[self._forced_id]

        schema = self._by_key.get((protocol_mode, message_type, payload_count))
        if schema is not None:
            return schema

        # Same frame layout declared under a different protocol mode is still unambiguous.
        candidates = [
            s for s in self._by_id.values()
            if s.message_type == message_type and s.payload_count == payload_count
        ]
        if len(candidates) == 1:
            return candidates[0]

        raise UnknownSchemaError(protocol_mode, message_type, payload_count)
