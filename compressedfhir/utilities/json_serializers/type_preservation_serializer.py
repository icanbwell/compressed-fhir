import json
import logging
import re

import orjson
from typing import Any, Callable, Dict

from compressedfhir.utilities.json_serializers.type_preservation_decoder import (
    TypePreservationDecoder,
)
from compressedfhir.utilities.json_serializers.type_preservation_encoder import (
    TYPE_MARKER_KEY,
    TypePreservationEncoder,
)

logger = logging.getLogger(__name__)

# An integer beyond 64 bits needs this many digits.  orjson silently turns those into floats
# (stdlib json keeps the int), so such payloads take the stdlib path.  Long digit runs that
# are not ints (e.g. float fractions) only cost the fallback, never correctness.
_DIGITS_IN_INTEGER_BEYOND_64_BITS = 20
_LONG_DIGIT_RUN = re.compile(r"\d{%d}" % _DIGITS_IN_INTEGER_BEYOND_64_BITS)

# Stored blobs written by the orjson writer start with this one byte.  JSON parsers ignore
# leading whitespace, so older versions still read such blobs.  It records that the text came
# from orjson, which cannot write an integer beyond 64 bits, so the reader may skip the
# digit-run guard.  Blobs from the stdlib writer (or from older versions) have no marker.
_ORJSON_WRITER_MARKER = b" "

_WRITER_OPTIONS = (
    orjson.OPT_PASSTHROUGH_DATETIME  # datetimes go through the marker table, not orjson's own text
    | orjson.OPT_PASSTHROUGH_SUBCLASS  # keep the iteration order of OrderedDict and friends
    | orjson.OPT_PASSTHROUGH_DATACLASS  # dataclasses keep the stdlib writer's marker form
)


class NativeUnsupported(Exception):
    """orjson cannot be used here; the caller must use the standard library instead."""


class NativeParseUnsupported(NativeUnsupported):
    """orjson cannot parse this text exactly as the standard library would."""


def parse_json_natively(json_str: str) -> Any:
    """
    orjson.loads, but raises NativeParseUnsupported for text where orjson would differ from
    stdlib json: NaN/Infinity, lone surrogates, and anything that may hold an integer beyond
    64 bits (see _LONG_DIGIT_RUN).
    """
    if _LONG_DIGIT_RUN.search(json_str):
        raise NativeParseUnsupported("possible integer beyond 64 bits")
    try:
        return orjson.loads(json_str)
    except orjson.JSONDecodeError as e:
        raise NativeParseUnsupported(str(e)) from e


def _orjson_writer_default(o: Any) -> Any:
    """Types orjson does not write natively; raising here sends the payload to the stdlib writer."""
    if isinstance(
        o, dict
    ):  # dict subclass (OrderedDict, ...): keep its own iteration order
        return dict(o)
    if isinstance(o, list):
        return list(o)
    for type_, to_marker in TypePreservationEncoder.TYPE_MAP.items():
        if isinstance(o, type_):
            return to_marker(o)
    raise TypeError(f"not handled by the orjson writer: {type(o).__name__}")


def _may_hold_type_markers(text: str | bytes) -> bool:
    """
    False only when the text cannot contain a type marker.  A key can be spelled with \\u
    escapes, so any escape counts as a possible marker.
    """
    if isinstance(text, bytes):
        return TYPE_MARKER_KEY.encode() in text or b"\\u" in text
    return TYPE_MARKER_KEY in text or "\\u" in text


class TypePreservationSerializer:
    """
    Comprehensive serialization and deserialization utility
    """

    @classmethod
    def serialize(cls, data: Any, **kwargs: Any) -> str:
        """
        Serialize data with advanced type handling (standard library writer)

        Args:
            data: Data to serialize
            kwargs: Additional JSON dumps arguments

        Returns:
            JSON string representation
        """
        return json.dumps(
            data, cls=TypePreservationEncoder, separators=(",", ":"), **kwargs
        )

    @classmethod
    def serialize_to_bytes(cls, data: Any) -> bytes:
        """
        Serialize for storage with orjson, falling back to the standard library writer.

        orjson output starts with _ORJSON_WRITER_MARKER.  The standard library writer is used
        for anything orjson raises on: integers beyond 64 bits, non-string keys, dataclasses,
        custom objects, str/int subclasses that are not Enums, lone surrogates.  Differences from that writer: NaN
        and Infinity are written as null, and a plain Enum or a UUID is written as its value
        or string instead of raising.
        """
        try:
            return _ORJSON_WRITER_MARKER + orjson.dumps(
                data, default=_orjson_writer_default, option=_WRITER_OPTIONS
            )
        except TypeError as e:  # orjson.JSONEncodeError subclasses TypeError
            logger.debug("orjson writer fell back to the standard library: %s", e)
            return cls.serialize(data).encode("utf-8")

    @classmethod
    def parse_stored(cls, data: bytes) -> Any:
        """
        Parse a stored blob into plain JSON data with orjson.  The digit-run guard is skipped
        for blobs the orjson writer produced.  Raises NativeParseUnsupported when orjson
        cannot be trusted with this text.
        """
        if data[:1] == _ORJSON_WRITER_MARKER:
            try:
                return orjson.loads(data)
            except orjson.JSONDecodeError as e:
                raise NativeParseUnsupported(str(e)) from e
        return parse_json_natively(data.decode("utf-8"))

    @classmethod
    def deserialize_stored(cls, data: bytes) -> Any:
        """Read a stored blob back into Python data with plain dicts, rebuilding typed values."""
        try:
            parsed = cls.parse_stored(data)
        except NativeParseUnsupported as e:
            logger.debug("stored blob read with the standard library: %s", e)
            return json.loads(
                data.decode("utf-8"),
                object_hook=lambda dct: TypePreservationDecoder.decode(
                    dct, None, use_ordered_dict=False
                ),
            )
        return cls._decode_parsed(
            parsed, _may_hold_type_markers(data), None, use_ordered_dict=False
        )

    @classmethod
    def deserialize(
        cls,
        json_str: str,
        custom_decoders: Dict[str, Callable[[Any], Any]] | None = None,
        use_ordered_dict: bool = True,
        **kwargs: Any,
    ) -> Any:
        """
        Deserialize JSON string with advanced type reconstruction

        Args:
            json_str: JSON string to deserialize
            custom_decoders: Optional additional custom decoders
            use_ordered_dict: Whether to use OrderedDict for deserialized dicts
            kwargs: Additional JSON loads arguments (these select the standard library parser)

        Returns:
            Reconstructed object
        """
        if not kwargs:
            try:
                # orjson parses in C without the per-object Python hook
                return cls._decode_parsed(
                    parse_json_natively(json_str),
                    _may_hold_type_markers(json_str),
                    custom_decoders,
                    use_ordered_dict=use_ordered_dict,
                )
            except NativeParseUnsupported as e:
                logger.debug("deserialize fell back to the standard library: %s", e)
        return json.loads(
            json_str,
            object_hook=lambda dct: TypePreservationDecoder.decode(
                dct, custom_decoders, use_ordered_dict=use_ordered_dict
            ),
            **kwargs,
        )

    @classmethod
    def _decode_parsed(
        cls,
        parsed: Any,
        may_hold_markers: bool,
        custom_decoders: Dict[str, Callable[[Any], Any]] | None,
        *,
        use_ordered_dict: bool,
    ) -> Any:
        """
        Turn orjson's output into the final structure.  When plain dicts are wanted and the text
        cannot hold a type marker, orjson's output is already the answer and the walk is skipped.
        """
        if not use_ordered_dict and custom_decoders is None and not may_hold_markers:
            return parsed
        return TypePreservationDecoder.decode_tree(
            parsed, custom_decoders, use_ordered_dict=use_ordered_dict
        )
