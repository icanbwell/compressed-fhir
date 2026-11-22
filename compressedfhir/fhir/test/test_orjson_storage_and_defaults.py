"""
Pins the orjson storage writer, the stored-blob marker, the decode-walk skip, and the
json() defaults of FhirResourceMap and convert_dict_to_fhir_json.  Expected text for the
exact (byte_identical=True) paths is literal output of the released 4.0.0 package, so
these tests do not depend on the code they check.  All data is synthetic.
"""

import dataclasses
import enum
import json
import logging
import uuid
import zlib
from collections import OrderedDict
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any, Dict

import orjson
import pytest

from compressedfhir.fhir.fhir_resource import FhirResource
from compressedfhir.fhir.fhir_resource_list import FhirResourceList
from compressedfhir.fhir.fhir_resource_map import FhirResourceMap
from compressedfhir.utilities.compressed_dict.v1.compressed_dict_storage_mode import (
    CompressedDictStorageMode,
    CompressedDictStorageType,
)
from compressedfhir.utilities.json_helpers import FhirClientJsonHelpers
from compressedfhir.utilities.json_serializers.type_preservation_serializer import (
    NativeParseUnsupported,
    TypePreservationSerializer,
)


class _PlainEnum(enum.Enum):
    ONE = 1


class _StrEnum(str, enum.Enum):
    A = "a"


class _PlainStr(str):
    pass


@dataclasses.dataclass
class _Data:
    x: int = 1


class _Custom:
    def __init__(self) -> None:
        self.a = 1


def _roundtrip_with_writer(data: Any) -> Any:
    return TypePreservationSerializer.deserialize_stored(
        TypePreservationSerializer.serialize_to_bytes(data)
    )


def _roundtrip_with_stdlib(data: Any) -> Any:
    return TypePreservationSerializer.deserialize(
        TypePreservationSerializer.serialize(data), use_ordered_dict=False
    )


# ---- storage writer: same data as the stdlib writer, except the documented differences ----


@pytest.mark.parametrize(
    "payload",
    [
        {"a": 1, "b": [1, 2, {"c": "x"}], "d": None, "t": (1, 2)},
        {
            "when": datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
            "d": date(2024, 1, 2),
        },
        {"naive": datetime(2024, 1, 2, 3, 4, 5), "clock": time(3, 4, 5)},
        {"n": Decimal("100.25"), "whole": Decimal("100"), "blob": b"abc", "s": {1, 2}},
        {"c": complex(1, 2)},
        {"text": "Müller ☃ \U0001f600", "esc": 'a"b\\c\n'},
        {"f": 0.1, "g": 1e-07, "h": 1e22, "i": -0.0, "big64": 2**63},
        {"nested": [{"deep": {"when": datetime(2024, 5, 6, 7, 8, 9)}}]},
        {"big": 2**100, "neg": -(2**100)},
        {1: "int key", None: "none key", 2.5: "float key"},
        {"se": _StrEnum.A},
        {"lone": "\ud800"},
    ],
    ids=[
        "plain",
        "tz-datetime-and-date",
        "naive-datetime-and-time",
        "decimal-bytes-set",
        "complex",
        "unicode-and-escapes",
        "floats",
        "nested-typed",
        "ints-beyond-64-bits",
        "non-string-keys",
        "str-enum",
        "lone-surrogate",
    ],
)
def test_writer_round_trip_matches_stdlib_writer(payload: Dict[str, Any]) -> None:
    actual = _roundtrip_with_writer(payload)
    expected = _roundtrip_with_stdlib(payload)
    assert json.dumps(actual, default=repr) == json.dumps(expected, default=repr)
    assert type(actual) is type(expected)


@pytest.mark.parametrize(
    "obj", [_Custom(), _Data()], ids=["custom-object", "dataclass"]
)
def test_writer_stores_custom_objects_like_the_stdlib_writer(obj: Any) -> None:
    """Both writers store the class name and attributes; neither read rebuilds the class."""
    for result in (
        _roundtrip_with_writer({"o": obj}),
        _roundtrip_with_stdlib({"o": obj}),
    ):
        assert not isinstance(result["o"], type(obj))
        assert result["o"]["__type__"] == type(obj).__name__
        assert dict(result["o"]["attributes"]) == vars(obj)


@pytest.mark.parametrize(
    ("payload", "stored"),
    [
        ({"big": 2**100}, False),
        ({1: "x"}, False),
        ({"dc": _Data()}, False),
        ({"obj": _Custom()}, False),
        ({"se": _StrEnum.A}, True),  # orjson writes any Enum natively, as its value
        ({"plain_str_subclass": _PlainStr("x")}, False),
        ({"lone": "\ud800"}, False),
        ({"a": 1, "when": datetime(2024, 1, 2)}, True),
        ({"o": OrderedDict(x=1)}, True),
    ],
    ids=[
        "big-int",
        "int-key",
        "dataclass",
        "custom-object",
        "str-enum",
        "str-subclass",
        "lone-surrogate",
        "typed-values",
        "dict-subclass",
    ],
)
def test_writer_marks_only_orjson_output(payload: Dict[str, Any], stored: bool) -> None:
    """A leading space marks orjson output; anything orjson raised on is the stdlib text."""
    blob = TypePreservationSerializer.serialize_to_bytes(payload)
    assert blob.startswith(b" ") is stored
    if not stored:
        assert blob == TypePreservationSerializer.serialize(payload).encode("utf-8")


def test_writer_keeps_the_iteration_order_of_a_reordered_dict_subclass() -> None:
    reordered: "OrderedDict[str, int]" = OrderedDict([("z", 1), ("a", 2), ("m", 3)])
    reordered.move_to_end("z")
    nested = {"outer": reordered}
    assert list(_roundtrip_with_writer(nested)["outer"]) == ["a", "m", "z"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (float("nan"), None),
        (float("inf"), None),
        (float("-inf"), None),
        (_PlainEnum.ONE, 1),
        (uuid.UUID(int=5), "00000000-0000-0000-0000-000000000005"),
    ],
    ids=["nan", "inf", "-inf", "plain-enum", "uuid"],
)
def test_writer_documented_differences_from_the_stdlib_writer(
    value: Any, expected: Any
) -> None:
    """Accepted: orjson writes NaN/Infinity as null and writes a plain Enum or UUID as a value."""
    assert _roundtrip_with_writer({"v": value})["v"] == expected


def test_writer_logs_every_fallback(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        TypePreservationSerializer.serialize_to_bytes({"big": 2**100})
    assert any("fell back to the standard library" in r.message for r in caplog.records)


def test_resource_stored_blob_is_marked_and_older_versions_can_read_it() -> None:
    resource = FhirResource(
        initial_dict={
            "resourceType": "Patient",
            "id": "1",
            "name": [{"family": "Zoë"}],
        },
        storage_mode=CompressedDictStorageMode.default(),
    )
    blob = resource._serialized_dict
    assert blob is not None
    text = zlib.decompress(blob)
    assert text.startswith(b" ")
    # what the released versions do: a plain json.loads with an object hook
    assert json.loads(text)["name"][0]["family"] == "Zoë"


# ---- the stored-blob marker and the digit-run guard ----


_BIG_INT_TEXT = b'{"v": 12345678901234567890123}'


def test_marked_blob_skips_the_digit_guard_unmarked_blob_keeps_it() -> None:
    marked = b" " + _BIG_INT_TEXT
    assert isinstance(TypePreservationSerializer.parse_stored(marked)["v"], float)
    with pytest.raises(NativeParseUnsupported):
        TypePreservationSerializer.parse_stored(_BIG_INT_TEXT)


def test_stored_blob_without_marker_keeps_big_ints_exact() -> None:
    assert TypePreservationSerializer.deserialize_stored(_BIG_INT_TEXT) == {
        "v": 12345678901234567890123
    }


def test_external_text_starting_with_a_space_never_skips_the_guard() -> None:
    text = " " + _BIG_INT_TEXT.decode()
    assert TypePreservationSerializer.deserialize(text, use_ordered_dict=False) == {
        "v": 12345678901234567890123
    }


def test_blob_from_the_stdlib_writer_still_reads() -> None:
    """What 4.0.0 and earlier stored: no marker, \\u escapes, NaN written as a literal."""
    legacy = TypePreservationSerializer.serialize(
        {"s": "café", "n": float("nan"), "d": date(2024, 1, 2)}
    ).encode("utf-8")
    assert b"\\u00e9" in legacy and b"NaN" in legacy
    result = TypePreservationSerializer.deserialize_stored(legacy)
    assert result["s"] == "café"
    assert result["n"] != result["n"]  # NaN
    assert result["d"] == date(2024, 1, 2)


# ---- skipping the decode walk for payloads that cannot hold a type marker ----


def test_marker_free_payload_gives_plain_dicts_without_a_walk() -> None:
    text = '{"a": {"b": [1, {"c": 2.5}]}, "s": "x"}'
    result = TypePreservationSerializer.deserialize(text, use_ordered_dict=False)
    assert result == json.loads(text)
    assert type(result) is dict and type(result["a"]) is dict


def test_default_deserialize_still_builds_ordered_dicts() -> None:
    result = TypePreservationSerializer.deserialize('{"a": {"b": 1}}')
    assert type(result) is OrderedDict and type(result["a"]) is OrderedDict


def test_marker_key_spelled_with_escapes_is_still_decoded() -> None:
    text = '{"d": {"\\u005f\\u005ftype\\u005f\\u005f": "date", "iso": "2024-01-02"}}'
    result = TypePreservationSerializer.deserialize(text, use_ordered_dict=False)
    assert result["d"] == date(2024, 1, 2)


def test_string_value_containing_the_marker_text_is_left_alone() -> None:
    text = '{"s": "talks about __type__ and \\u00e9"}'
    result = TypePreservationSerializer.deserialize(text, use_ordered_dict=False)
    assert result == {"s": "talks about __type__ and é"}


def test_custom_decoders_still_apply_to_marker_free_text() -> None:
    result = TypePreservationSerializer.deserialize(
        '{"a": 1}', custom_decoders={"x": lambda d: d}, use_ordered_dict=False
    )
    assert result == {"a": 1}


# ---- json() through the dict() fast path writes the same text as the general path ----


@pytest.mark.parametrize("seed", range(40))
def test_json_text_is_the_same_through_the_fast_and_general_paths(seed: int) -> None:
    import random

    rng = random.Random(seed)
    resource = FhirResource(
        initial_dict={
            "resourceType": "X",
            "id": str(seed),
            "when": datetime(2024, 1, 2, 3, 4, 5, rng.randint(0, 999999)),
            "n": Decimal(rng.choice(["100", "100.25", "1E+3"])),
            "text": rng.choice(["plain", "Müller ☃", ""]),
            "items": [{"q": rng.random(), "empty": [], "none": None} for _ in range(3)],
        },
        storage_mode=CompressedDictStorageMode.default(),
    )
    fast = resource.json()
    with resource.transaction():  # an open transaction bypasses the fast path
        general = resource.json()
    assert fast == general
    assert ", " not in fast and ": " not in fast  # compact text
    assert json.loads(fast) == json.loads(resource.json(byte_identical=True))


# ---- FhirResourceMap.json() ----


def _map() -> FhirResourceMap:
    return FhirResourceMap(
        {
            "Patient": FhirResourceList(
                [
                    FhirResource.from_dict(
                        {
                            "resourceType": "Patient",
                            "id": "p1",
                            "name": [{"given": ["Zoë"]}],
                            "empty": [],
                        }
                    )
                ]
            )
        }
    )


def test_resource_map_exact_text_is_what_4_0_0_wrote() -> None:
    assert _map().json(byte_identical=True) == (
        '{"Patient": [{"resourceType": "Patient", "id": "p1", '
        '"name": [{"given": ["Zo\\u00eb"]}]}]}'
    )


def test_resource_map_default_text_is_compact_and_carries_the_same_data() -> None:
    compact = _map().json()
    assert compact == (
        '{"Patient":[{"resourceType":"Patient","id":"p1","name":[{"given":["Zoë"]}]}]}'
    )
    assert json.loads(compact) == json.loads(_map().json(byte_identical=True))


# ---- FhirClientJsonHelpers.convert_dict_to_fhir_json() ----


_CONVERT_INPUT = {
    "resourceType": "Observation",
    "id": "o1",
    "effectiveDateTime": datetime(2024, 1, 2, 3, 4, 5),
    "valueQuantity": {"value": Decimal("1.50"), "unit": "µg"},
    "note": [],
    "text": "Glucosé",
}


def test_convert_dict_exact_text_is_what_4_0_0_wrote() -> None:
    assert FhirClientJsonHelpers.convert_dict_to_fhir_json(
        _CONVERT_INPUT, byte_identical=True
    ) == (
        '{"resourceType": "Observation", "id": "o1", '
        '"effectiveDateTime": "2024-01-02T03:04:05", '
        '"valueQuantity": {"value": "1.50", "unit": "\\u00b5g"}, '
        '"text": "Glucos\\u00e9"}'
    )


def test_convert_dict_default_is_compact_with_the_same_data() -> None:
    compact = FhirClientJsonHelpers.convert_dict_to_fhir_json(_CONVERT_INPUT)
    exact = FhirClientJsonHelpers.convert_dict_to_fhir_json(
        _CONVERT_INPUT, byte_identical=True
    )
    assert compact == orjson.dumps(json.loads(exact)).decode()
    assert "\\u" not in compact and ", " not in compact


@pytest.mark.parametrize(
    ("value", "default_data", "exact_data"),
    [
        (_PlainEnum.ONE, 1, "_PlainEnum.ONE"),
        (_Data(), {"x": 1}, "_Data(x=1)"),
        (float("nan"), None, float("nan")),
    ],
    ids=["plain-enum", "dataclass", "nan"],
)
def test_convert_dict_documented_differences(
    value: Any, default_data: Any, exact_data: Any
) -> None:
    default = json.loads(FhirClientJsonHelpers.convert_dict_to_fhir_json({"v": value}))
    exact = json.loads(
        FhirClientJsonHelpers.convert_dict_to_fhir_json(
            {"v": value}, byte_identical=True
        )
    )
    assert default["v"] == default_data if default_data is not None else "v" in default
    if exact_data == exact_data:  # not NaN
        assert exact["v"] == exact_data
    else:
        assert exact["v"] != exact["v"]


def test_convert_dict_big_ints_fall_back_and_stay_exact() -> None:
    text = FhirClientJsonHelpers.convert_dict_to_fhir_json({"v": 2**100})
    assert json.loads(text)["v"] == 2**100


# ---- reading data never imports a module or instantiates a class named in it ----


@pytest.mark.parametrize("storage_type", ["compressed", "raw"])
@pytest.mark.parametrize(
    "marker",
    [
        {
            "__type__": "Victim",
            "__module__": "reader_probe_module",
            "attributes": {"a": 1},
        },
        {"__type__": "path", "__module__": "os", "attributes": {"a": 1}},
        {
            "__type__": "X",
            "__module__": "no_such_module_for_reader_probe",
            "attributes": {"a": 1},
        },
    ],
    ids=["importable-class", "not-a-class", "unknown-module"],
)
def test_reading_a_resource_never_imports_or_instantiates_named_classes(
    marker: Dict[str, Any],
    storage_type: CompressedDictStorageType,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    marker_file = tmp_path / "imported.txt"
    (tmp_path / "reader_probe_module.py").write_text(
        f"import pathlib\npathlib.Path({str(marker_file)!r}).write_text('imported')\n"
        "class Victim:\n    pass\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "reader_probe_module", raising=False)
    mode = CompressedDictStorageMode(storage_type=storage_type)
    content = {"resourceType": "Observation", "id": "1", "extension": [dict(marker)]}

    resource = FhirResource.from_dict(content, storage_mode=mode)
    from_text = FhirResource.from_json(json.dumps(content))  # always compressed
    for r in (resource, from_text):
        assert r.raw_dict()["extension"][0] == marker
        assert r.dict()["extension"][0] == marker
        assert json.loads(r.json())["extension"][0] == marker
        assert json.loads(r.json(byte_identical=True))["extension"][0] == marker

    assert not marker_file.exists()
    assert "reader_probe_module" not in sys.modules


@pytest.mark.parametrize(
    "value", [-(2**63) - 1, -(2**63), -(10**19) + 1, 2**64, -(2**100)]
)
def test_integers_at_the_64_bit_boundary_read_back_exact_from_stdlib_text(
    value: int,
) -> None:
    resource = FhirResource.from_json(json.dumps({"resourceType": "Basic", "n": value}))

    assert resource.raw_dict()["n"] == value
    assert isinstance(resource.raw_dict()["n"], int)
    assert resource.dict()["n"] == value


@pytest.mark.parametrize("storage_type", ["raw", "compressed"])
def test_entry_and_bundle_drop_empties_created_by_encoding(
    storage_type: CompressedDictStorageType,
) -> None:
    from compressedfhir.fhir.fhir_bundle_entry import FhirBundleEntry

    mode = CompressedDictStorageMode(storage_type=storage_type)
    content: Dict[str, Any] = {
        "resourceType": "Basic",
        "id": "1",
        "s": {"k": {1}},
        "b": {"k": [{"z": set()}]},
        "e": {"q": b""},
        "f": [set()],
    }
    expected = {"resourceType": "Basic", "id": "1", "s": {"k": [1]}}
    entry = FhirBundleEntry(
        resource=FhirResource(initial_dict=content, storage_mode=mode)
    )

    assert entry.dict() == {"resource": expected}
    assert json.loads(entry.json())["resource"] == expected
    assert json.loads(entry.json(byte_identical=True))["resource"] == expected


def test_dataclass_in_a_resource_goes_through_asdict() -> None:
    @dataclasses.dataclass
    class Part:
        name: str
        _hidden: int = 3

    resource = FhirResource(
        initial_dict={"resourceType": "Basic", "id": "1", "p": Part(name="a")},
        storage_mode=CompressedDictStorageMode(storage_type="raw"),
    )

    expected = {"name": "a", "_hidden": 3}
    assert resource.dict()["p"] == expected
    assert json.loads(resource.json())["p"] == expected
