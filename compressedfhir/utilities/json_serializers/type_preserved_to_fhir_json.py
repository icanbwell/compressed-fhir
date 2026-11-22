from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Callable, Dict, List

from compressedfhir.utilities.json_serializers.type_preservation_encoder import (
    TYPE_MARKER_KEY,
)
from compressedfhir.utilities.json_serializers.type_preservation_serializer import (
    NativeUnsupported,
)


class UnsupportedForFastPath(NativeUnsupported):
    """The payload has something the fast path cannot reproduce exactly; use the slow path."""


def _decimal_to_json(marker: Dict[str, Any]) -> int | float:
    value = Decimal(marker["value"])
    if not value.is_finite():
        # NaN and Infinity: let the general path decide, so the result never depends on the
        # storage mode (Infinity raises in FhirJSONEncoder)
        raise UnsupportedForFastPath("non-finite Decimal")
    # same rule as FhirJSONEncoder
    return int(value) if value == value.to_integral_value() else float(value)


def _time_to_json(marker: Dict[str, Any]) -> str:
    if marker.get("tzinfo"):
        # TypePreservationDecoder attaches a ZoneInfo here; leave that to the slow path
        raise UnsupportedForFastPath("time with tzinfo")
    return time.fromisoformat(marker["iso"]).isoformat()


# marker name -> FHIR JSON value, equal to decode-then-FhirJSONEncoder for that type
_MARKER_CONVERTERS: Dict[str, Callable[[Dict[str, Any]], Any]] = {
    "datetime": lambda m: datetime.fromisoformat(m["iso"]).isoformat(),
    "date": lambda m: date.fromisoformat(m["iso"]).isoformat(),
    "time": _time_to_json,
    "decimal": _decimal_to_json,
    "bytes": lambda m: m["value"].encode("latin-1").decode("utf-8"),
}


# What a malformed type marker can raise (InvalidOperation is an ArithmeticError,
# UnicodeDecodeError is a ValueError).
_MALFORMED_MARKER_ERRORS = (
    KeyError,
    TypeError,
    ValueError,
    AttributeError,
    ArithmeticError,
)


class TypePreservedToFhirJson:
    """
    Turns the output of a plain JSON parse of a TypePreservationSerializer payload straight into
    FHIR friendly plain data (typed markers become strings/numbers), optionally pruning empty
    elements in the same pass.

    The result equals TypePreservationDecoder -> FhirClientJsonHelpers.remove_empty_elements ->
    FhirJSONEncoder -> json.loads, but visits each node once and builds no OrderedDicts or
    datetime/Decimal objects.  Anything it cannot reproduce exactly raises
    UnsupportedForFastPath so the caller can use the slow path.
    """

    @classmethod
    def convert(cls, parsed: Any, *, prune_empty: bool) -> Any:
        try:
            if type(parsed) is dict:
                return cls._dict(parsed, prune_empty)
            if type(parsed) is list:
                return cls._list(parsed, prune_empty)
            return parsed
        except UnsupportedForFastPath:
            raise
        except _MALFORMED_MARKER_ERRORS as e:
            # missing key, wrong value shape, bad iso string, invalid Decimal, undecodable
            # bytes; anything else is a bug and must not be hidden
            raise UnsupportedForFastPath(f"malformed marker: {e!r}") from e

    @classmethod
    def _marker(cls, node: Dict[str, Any]) -> Any:
        converter = _MARKER_CONVERTERS.get(node[TYPE_MARKER_KEY])
        if converter is None:  # complex, set, custom objects, unknown markers
            raise UnsupportedForFastPath(f"marker {node['__type__']!r}")
        value = converter(node)
        if type(value) is str and not value.strip():
            # blank bytes become an empty element only after encoding; the general path prunes
            # those, so leave them to it
            raise UnsupportedForFastPath("blank bytes marker")
        return value

    @classmethod
    def _dict(cls, node: Dict[str, Any], prune_empty: bool) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for k, v in node.items():
            t = type(v)
            if t is dict:
                if TYPE_MARKER_KEY in v:
                    out[k] = cls._marker(v)  # marker values are never pruned as empty
                    continue
                v = cls._dict(v, prune_empty)
                if prune_empty and not v:
                    continue
            elif t is list:
                v = cls._list(v, prune_empty)
                if prune_empty and not v:
                    continue
            elif prune_empty and (v is None or (t is str and not v.strip())):
                continue
            out[k] = v
        return out

    @classmethod
    def _list(cls, node: List[Any], prune_empty: bool) -> List[Any]:
        out: List[Any] = []
        for v in node:
            t = type(v)
            if t is dict:
                if TYPE_MARKER_KEY in v:
                    out.append(cls._marker(v))
                    continue
                v = cls._dict(v, prune_empty)
                if prune_empty and not v:
                    continue
            elif t is list:
                v = cls._list(v, prune_empty)
                if prune_empty and not v:
                    continue
            elif prune_empty and (v is None or (t is str and not v.strip())):
                continue
            out.append(v)
        return out
