"""
Characterization tests for the behavior that 3.x callers rely on.

These pin what 3.0.6 did so the OrderedDict -> dict change and the json -> orjson change
cannot silently alter values, key order, value types, pruning, or the persisted storage
format.  Every assertion was verified against the 3.0.6 release.  Intentional 4.0
differences (container types, key-order-insensitive nested equality, compact orjson text)
are deliberately not asserted.

Only public API that exists in 3.0.6 is used, with default arguments, except the private
_deserialize_dict helper and _serialized_dict attribute used to pin the persisted format.
All data is synthetic.
"""

import base64
import copy
import json
import zlib
from collections import OrderedDict
from collections.abc import Callable
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

import msgpack
import pytest

from compressedfhir.fhir.fhir_bundle import FhirBundle
from compressedfhir.fhir.fhir_resource import FhirResource
from compressedfhir.fhir.fhir_resource_list import FhirResourceList
from compressedfhir.utilities.compressed_dict.v1.compressed_dict import CompressedDict
from compressedfhir.utilities.compressed_dict.v1.compressed_dict_access_error import (
    CompressedDictAccessError,
)
from compressedfhir.utilities.compressed_dict.v1.compressed_dict_storage_mode import (
    CompressedDictStorageMode,
    CompressedDictStorageType,
)
from compressedfhir.utilities.json_serializers.type_preservation_serializer import (
    TypePreservationSerializer,
)

STORAGE_TYPES: tuple[CompressedDictStorageType, ...] = (
    "raw",
    "compressed",
    "msgpack",
    "compressed_msgpack",
)

# Raw storage hands out its live internal dict and never copies, so copy/aliasing behavior
# is only a contract for the serialized storage types.
SERIALIZED_STORAGE_TYPES: tuple[CompressedDictStorageType, ...] = (
    "compressed",
    "msgpack",
    "compressed_msgpack",
)

# Storage types that can hold python-typed values (datetime, date, time, Decimal)
TYPED_VALUE_STORAGE_TYPES: tuple[CompressedDictStorageType, ...] = ("raw", "compressed")

# The msgpack storage types can only hold msgpack-native values (no datetime/date/time/
# Decimal) and store floats as float32.
MSGPACK_STORAGE_TYPES: tuple[CompressedDictStorageType, ...] = (
    "msgpack",
    "compressed_msgpack",
)

TYPED_ONLY_KEYS: tuple[str, ...] = (
    "x_date",
    "x_time",
    "x_decimal_fraction",
    "x_decimal_whole",
    "x_float_small",
    "x_float_big",
)


def mode(storage_type: CompressedDictStorageType) -> CompressedDictStorageMode:
    return CompressedDictStorageMode(storage_type=storage_type)


def structure(value: Any) -> Any:
    """
    Order- and type-sensitive view of a nested value.  Container type (dict vs OrderedDict)
    is not part of it, but key order is, and so is the type of every leaf: 1, 1.0 and True
    differ, and so do a str and a datetime.
    """
    if isinstance(value, dict):
        return ("map", [(k, structure(v)) for k, v in value.items()])
    if isinstance(value, list):
        return ("list", [structure(v) for v in value])
    if isinstance(value, float):
        # repr keeps the sign of -0.0, which == would treat as 0.0
        return ("float", repr(value))
    if isinstance(value, Decimal):
        # str keeps the exponent, which == ignores (Decimal("1.50") == Decimal("1.5"))
        return ("Decimal", str(value))
    return (type(value).__name__, value)


DIV_TEXT = '<div>"é" \\ ' + chr(0x2028) + "</div>"
ODD_TEXT = "日本 é " + chr(0x2028) + " " + chr(0xA0)


def build_typed_patient() -> dict[str, Any]:
    """Synthetic resource with python types, non-alphabetical key order and tricky scalars."""
    return {
        "resourceType": "Patient",
        "id": "synthetic-1",
        "meta": {
            "versionId": "1",
            "lastUpdated": datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC),
        },
        "active": True,
        "inactive": False,
        "zero": 0,
        "name": [{"given": ["José", "Zoë"], "family": "Ñandú 日本"}],
        "x_date": date(1980, 2, 3),
        "x_time": time(3, 4, 5),
        "x_decimal_fraction": Decimal("1.50"),
        "x_decimal_whole": Decimal(2),
        "x_float_whole": 1.0,
        "x_float_small": 1e-07,
        "x_float_big": 1e21,
        "x_int_above_2_53": 2**53 + 1,
        "text": {"status": "generated", "div": DIV_TEXT},
    }


# What dict()/json() give for build_typed_patient(), as FHIR-friendly JSON values.
TYPED_EXPECTED_PATIENT: dict[str, Any] = {
    "resourceType": "Patient",
    "id": "synthetic-1",
    "meta": {"versionId": "1", "lastUpdated": "2024-01-02T03:04:05+00:00"},
    "active": True,
    "inactive": False,
    "zero": 0,
    "name": [{"given": ["José", "Zoë"], "family": "Ñandú 日本"}],
    "x_date": "1980-02-03",
    "x_time": "03:04:05",
    "x_decimal_fraction": 1.5,
    "x_decimal_whole": 2,
    "x_float_whole": 1.0,
    "x_float_small": 1e-07,
    "x_float_big": 1e21,
    "x_int_above_2_53": 2**53 + 1,
    "text": {"status": "generated", "div": DIV_TEXT},
}


def build_patient(storage_type: str = "compressed") -> dict[str, Any]:
    patient = build_typed_patient()
    if storage_type in MSGPACK_STORAGE_TYPES:
        for key in TYPED_ONLY_KEYS:
            del patient[key]
        patient["meta"]["lastUpdated"] = "2024-01-02T03:04:05+00:00"
    return patient


def expected_patient(storage_type: str = "compressed") -> dict[str, Any]:
    expected = copy.deepcopy(TYPED_EXPECTED_PATIENT)
    if storage_type in MSGPACK_STORAGE_TYPES:
        for key in TYPED_ONLY_KEYS:
            del expected[key]
    return expected


def build_empties() -> dict[str, Any]:
    return {
        "resourceType": "Observation",
        "id": "synthetic-2",
        "none": None,
        "empty_str": "",
        "blank_str": "   ",
        "empty_list": [],
        "empty_dict": {},
        "nested_empty": {"a": {"b": None, "c": []}, "d": [[], {}, None, ""]},
        "list_with_empties": [{"a": None}, {"b": [None, 2]}, "", "x", 0, False],
        "kept_zero": 0,
        "kept_false": False,
        "kept_float_zero": 0.0,
        "kept_text": " x ",
    }


EXPECTED_EMPTIES_PRUNED: dict[str, Any] = {
    "resourceType": "Observation",
    "id": "synthetic-2",
    "list_with_empties": [{"b": [2]}, "x", 0, False],
    "kept_zero": 0,
    "kept_false": False,
    "kept_float_zero": 0.0,
    "kept_text": " x ",
}


def make_dict(
    data: dict[str, Any], storage_type: CompressedDictStorageType
) -> CompressedDict[str, Any]:
    return CompressedDict(
        initial_dict=data, storage_mode=mode(storage_type), properties_to_cache=None
    )


def make_resource(
    storage_type: CompressedDictStorageType, **kwargs: Any
) -> FhirResource:
    return FhirResource(
        initial_dict=build_patient(storage_type),
        storage_mode=mode(storage_type),
        **kwargs,
    )


# ------------------------------------------------------------------ storage round trip


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
def test_raw_dict_preserves_values_key_order_and_types(
    storage_type: CompressedDictStorageType,
) -> None:
    # Arrange
    source = build_patient(storage_type)

    # Act
    result = FhirResource(
        initial_dict=source, storage_mode=mode(storage_type)
    ).raw_dict()

    # Assert
    assert structure(result) == structure(build_patient(storage_type))


@pytest.mark.parametrize("storage_type", TYPED_VALUE_STORAGE_TYPES)
def test_raw_dict_keeps_python_types(storage_type: CompressedDictStorageType) -> None:
    # Arrange / Act
    result = make_resource(storage_type).raw_dict()

    # Assert
    assert isinstance(result["meta"]["lastUpdated"], datetime)
    assert result["meta"]["lastUpdated"].tzinfo is not None
    assert isinstance(result["x_date"], date)
    assert isinstance(result["x_time"], time)
    assert isinstance(result["x_decimal_fraction"], Decimal)


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
def test_dict_is_fhir_friendly_with_expected_values_and_order(
    storage_type: CompressedDictStorageType,
) -> None:
    # Arrange
    resource = make_dict(build_patient(storage_type), storage_type)

    # Act
    result = resource.dict()

    # Assert
    assert structure(result) == structure(expected_patient(storage_type))


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
def test_json_parses_to_same_values_order_and_types_as_dict(
    storage_type: CompressedDictStorageType,
) -> None:
    # Arrange
    resource = make_dict(build_patient(storage_type), storage_type)

    # Act
    parsed = json.loads(resource.json())

    # Assert
    assert structure(parsed) == structure(expected_patient(storage_type))
    assert structure(parsed) == structure(resource.dict())


@pytest.mark.parametrize(
    "value",
    [
        1.0,
        0.1,
        -0.0,
        1e-07,
        1e21,
        5,
        -5,
        0,
        True,
        False,
        2**53 + 1,
        2**63,
        2**64 - 1,
        2**64,
        -(2**63),
        -(2**70),
        None,
        "",
        ODD_TEXT,
        'quote " backslash \\ newline \n tab \t nul \x00',
        "😀 astral",
    ],
    ids=repr,
)
def test_json_and_dict_scalar_round_trip(value: Any) -> None:
    # Arrange
    expected = {"v": value, "list": [value]}
    resource = make_dict(expected, "compressed")

    # Act
    from_json = json.loads(resource.json())
    from_dict = resource.dict()

    # Assert
    assert structure(from_json) == structure(expected)
    assert structure(from_dict) == structure(expected)


def test_dict_and_json_stringify_non_string_keys() -> None:
    # Arrange
    # intentional: the non-str keys are the input under test
    resource = make_dict({1: "a", 2: {3: "b"}}, "raw")  # type:ignore[dict-item]

    # Act / Assert
    assert resource.dict() == {"1": "a", "2": {"3": "b"}}
    assert json.loads(resource.json()) == {"1": "a", "2": {"3": "b"}}


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
def test_empty_resource_serializes_to_empty_object(
    storage_type: CompressedDictStorageType,
) -> None:
    # Arrange
    resource = FhirResource(storage_mode=mode(storage_type))

    # Act / Assert
    assert json.loads(resource.json()) == {}
    assert resource.dict() == {}
    assert resource.to_fhir_dict() == {}


# ------------------------------------------------------------------ pruning


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
def test_fhir_resource_dict_json_and_to_fhir_dict_prune_empty_elements(
    storage_type: CompressedDictStorageType,
) -> None:
    # Arrange
    resource = FhirResource(
        initial_dict=build_empties(), storage_mode=mode(storage_type)
    )

    # Act
    as_dict = resource.dict()
    as_json = json.loads(resource.json())
    as_fhir_dict = resource.to_fhir_dict()

    # Assert
    expected = structure(EXPECTED_EMPTIES_PRUNED)
    assert structure(as_dict) == expected
    assert structure(as_json) == expected
    assert structure(as_fhir_dict) == expected


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
def test_fhir_resource_pruning_does_not_change_stored_data(
    storage_type: CompressedDictStorageType,
) -> None:
    # Arrange
    source = build_empties()
    resource = FhirResource(initial_dict=source, storage_mode=mode(storage_type))

    # Act
    resource.dict()
    resource.json()

    # Assert
    stored = resource.raw_dict()
    assert stored["none"] is None
    assert stored["empty_list"] == []
    assert list(stored) == list(source)


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
def test_plain_compressed_dict_does_not_prune(
    storage_type: CompressedDictStorageType,
) -> None:
    # Arrange
    source: dict[str, Any] = {"a": None, "b": "", "c": [], "d": {}, "e": 0}
    resource = make_dict(source, storage_type)

    # Act / Assert
    assert structure(resource.dict()) == structure(source)
    assert structure(json.loads(resource.json())) == structure(source)


# ------------------------------------------------------------------ detached output


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
def test_dict_returns_a_detached_copy(
    storage_type: CompressedDictStorageType,
) -> None:
    # Arrange
    resource = make_resource(storage_type)
    first = resource.dict()

    # Act
    first["name"][0]["given"].append("mutated")
    first["new_key"] = 1
    del first["id"]
    second = resource.dict()

    # Assert
    assert structure(second) == structure(expected_patient(storage_type))


@pytest.mark.parametrize("storage_type", SERIALIZED_STORAGE_TYPES)
def test_source_dict_mutation_after_construction_does_not_affect_resource(
    storage_type: CompressedDictStorageType,
) -> None:
    # Arrange
    source = build_patient(storage_type)
    resource = FhirResource(initial_dict=source, storage_mode=mode(storage_type))

    # Act
    source["name"][0]["given"].append("mutated")
    source["id"] = "changed"
    source["added"] = 1

    # Assert
    assert structure(resource.dict()) == structure(expected_patient(storage_type))
    assert len(resource) == len(expected_patient(storage_type))
    with resource.transaction():
        assert "added" not in resource


# ------------------------------------------------------------------ equality


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
@pytest.mark.parametrize(
    "other_factory, expected",
    [
        (lambda: {"a": 1, "b": {"c": [1, 2]}}, True),
        (lambda: OrderedDict([("a", 1), ("b", {"c": [1, 2]})]), True),
        (lambda: {"b": {"c": [1, 2]}, "a": 1}, True),
        (lambda: {"a": 1, "b": {"c": [1, 3]}}, False),
        (lambda: {"a": 1}, False),
        (lambda: {"a": 1, "b": {"c": [1, 2]}, "z": 0}, False),
        (dict, False),
        (lambda: [("a", 1)], False),
        (lambda: None, False),
        (lambda: "a", False),
    ],
    ids=[
        "equal-dict",
        "equal-ordered-dict",
        "top-level-order-ignored",
        "different-nested-value",
        "missing-key",
        "extra-key",
        "empty",
        "list",
        "none",
        "str",
    ],
)
def test_equality_with_other_types(
    storage_type: CompressedDictStorageType,
    other_factory: Callable[[], Any],
    expected: bool,
) -> None:
    # Arrange
    resource = make_dict({"a": 1, "b": {"c": [1, 2]}}, storage_type)

    # Act / Assert
    assert (resource == other_factory()) is expected
    assert (resource != other_factory()) is (not expected)


@pytest.mark.parametrize("left_type", STORAGE_TYPES)
@pytest.mark.parametrize("right_type", STORAGE_TYPES)
def test_equality_across_storage_types(
    left_type: CompressedDictStorageType, right_type: CompressedDictStorageType
) -> None:
    # Arrange: the msgpack-safe variant so the content is storable in every type
    left = FhirResource(
        initial_dict=build_patient("msgpack"), storage_mode=mode(left_type)
    )
    right = FhirResource(
        initial_dict=build_patient("msgpack"), storage_mode=mode(right_type)
    )

    # Act / Assert
    assert left == right


def test_equality_compares_the_fhir_friendly_values() -> None:
    # Arrange: equality goes through dict(), so a datetime equals its FHIR string form
    resource = make_dict({"at": datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)}, "raw")

    # Act / Assert
    assert resource == {"at": "2024-01-02T03:04:05+00:00"}


def test_compressed_dict_is_unhashable() -> None:
    # Arrange / Act / Assert
    with pytest.raises(TypeError):
        hash(make_dict({"a": 1}, "raw"))


# ------------------------------------------------------------------ copy


@pytest.mark.parametrize("storage_type", SERIALIZED_STORAGE_TYPES)
def test_deepcopy_is_independent_and_keeps_storage_mode(
    storage_type: CompressedDictStorageType,
) -> None:
    # Arrange
    resource = make_resource(storage_type, properties_to_cache=["id"])

    # Act
    clone = copy.deepcopy(resource)
    with clone.transaction():
        clone["name"][0]["given"].append("mutated")
        clone["id"] = "changed"

    # Assert
    assert structure(resource.raw_dict()) == structure(build_patient(storage_type))
    assert resource.id == "synthetic-1"
    assert clone.id == "changed"
    assert clone.get_storage_mode().storage_type == storage_type


@pytest.mark.parametrize("storage_type", TYPED_VALUE_STORAGE_TYPES)
def test_deepcopy_keeps_python_types(storage_type: CompressedDictStorageType) -> None:
    # Arrange
    resource = make_resource(storage_type)

    # Act
    clone = copy.deepcopy(resource)

    # Assert
    assert structure(clone.raw_dict()) == structure(resource.raw_dict())
    assert isinstance(clone.raw_dict()["meta"]["lastUpdated"], datetime)


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
def test_copy_method_is_equal_to_original(
    storage_type: CompressedDictStorageType,
) -> None:
    # Arrange
    resource = make_resource(storage_type)

    # Act
    clone = resource.copy()

    # Assert
    assert clone == resource
    assert clone is not resource
    assert structure(clone.raw_dict()) == structure(resource.raw_dict())


# ------------------------------------------------------------------ mutation / transactions


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
def test_mutations_in_transaction_are_visible_afterwards(
    storage_type: CompressedDictStorageType,
) -> None:
    # Arrange
    resource = make_resource(storage_type)

    # Act
    with resource.transaction():
        resource["name"][0]["given"].append("Added")
        resource["added"] = {"k": [1, 2]}
        resource["zero"] = 7
        del resource["x_float_whole"]
        resource.pop("inactive")

    # Assert
    expected = expected_patient(storage_type)
    expected["name"][0]["given"].append("Added")
    expected["added"] = {"k": [1, 2]}
    expected["zero"] = 7
    del expected["x_float_whole"]
    del expected["inactive"]
    assert structure(resource.dict()) == structure(expected)
    assert structure(json.loads(resource.json())) == structure(expected)
    assert len(resource) == len(expected)
    with resource.transaction():
        assert "x_float_whole" not in resource
        assert "added" in resource
        assert list(resource.keys()) == list(expected.keys())


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
def test_dict_and_json_inside_open_transaction_see_uncommitted_changes(
    storage_type: CompressedDictStorageType,
) -> None:
    # Arrange
    resource = make_dict({"a": 1, "b": {"c": 2}}, storage_type)

    # Act / Assert
    with resource.transaction():
        resource["a"] = 99
        resource["b"]["c"] = 100
        assert resource.dict() == {"a": 99, "b": {"c": 100}}
        assert json.loads(resource.json()) == {"a": 99, "b": {"c": 100}}


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
def test_mutation_outside_transaction_is_rejected_and_data_unchanged(
    storage_type: CompressedDictStorageType,
) -> None:
    # Arrange
    resource = make_dict({"a": 1}, storage_type)

    # Act / Assert
    with pytest.raises(CompressedDictAccessError):
        resource["a"] = 2
    with pytest.raises(CompressedDictAccessError):
        del resource["a"]
    assert resource.dict() == {"a": 1}


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
def test_resource_stays_usable_after_an_exception_in_a_transaction(
    storage_type: CompressedDictStorageType,
) -> None:
    # Arrange
    resource = make_dict({"a": 1}, storage_type)

    # Act
    with pytest.raises(RuntimeError), resource.transaction():
        resource["a"] = 2
        raise RuntimeError("boom")

    # Assert: end_transaction runs in a finally, so the partial change is committed (as in
    # 3.x), and further transactions work
    with resource.transaction():
        resource["b"] = 3
        assert resource["b"] == 3
    assert resource.dict() == {"a": 2, "b": 3}


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
def test_cached_properties_follow_replace_and_setitem(
    storage_type: CompressedDictStorageType,
) -> None:
    # Arrange
    resource = FhirResource(
        initial_dict={"resourceType": "Patient", "id": "one"},
        storage_mode=mode(storage_type),
        properties_to_cache=["id", "resourceType"],
    )
    assert resource.id == "one"

    # Act
    resource.replace(value={"resourceType": "Observation", "id": "two"})

    # Assert: cached values are readable without a transaction and reflect the change
    assert resource.id == "two"
    assert resource.resource_type == "Observation"
    with resource.transaction():
        resource["id"] = "three"
    assert resource.id == "three"
    assert resource.resource_type_and_id == "Observation/three"


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
@pytest.mark.parametrize("factory", [dict, OrderedDict], ids=["dict", "ordered-dict"])
def test_replace_accepts_dict_and_ordered_dict(
    storage_type: CompressedDictStorageType, factory: Any
) -> None:
    # Arrange
    resource = make_dict({"old": 1}, storage_type)

    # Act
    resource.replace(value=factory([("z", 1), ("a", {"y": 2, "b": 3})]))

    # Assert
    assert len(resource) == 2
    assert structure(resource.dict()) == structure({"z": 1, "a": {"y": 2, "b": 3}})
    with resource.transaction():
        assert list(resource.keys()) == ["z", "a"]
        assert "old" not in resource


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
def test_clear_and_replace_with_empty_leave_an_empty_resource(
    storage_type: CompressedDictStorageType,
) -> None:
    # Arrange
    cleared = make_dict({"a": 1}, storage_type)
    replaced = make_dict({"a": 1}, storage_type)

    # Act
    cleared.clear()
    replaced.replace(value={})

    # Assert
    for resource in (cleared, replaced):
        assert len(resource) == 0
        assert resource.dict() == {}
        assert json.loads(resource.json()) == {}


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
def test_key_order_survives_mutation_and_storage(
    storage_type: CompressedDictStorageType,
) -> None:
    # Arrange
    resource = make_dict({"z": 1, "m": 2, "a": 3}, storage_type)

    # Act
    with resource.transaction():
        resource["b"] = 4
        del resource["m"]

    # Assert
    assert list(resource.dict().keys()) == ["z", "a", "b"]
    assert list(json.loads(resource.json()).keys()) == ["z", "a", "b"]
    assert list(resource.raw_dict().keys()) == ["z", "a", "b"]
    with resource.transaction():
        assert list(resource.keys()) == ["z", "a", "b"]


# ------------------------------------------------------------------ to_plain_dict / from_json


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
def test_to_plain_dict_keeps_python_types_and_order(
    storage_type: CompressedDictStorageType,
) -> None:
    # Arrange
    resource = make_resource(storage_type)

    # Act
    plain = resource.to_plain_dict()

    # Assert
    assert structure(plain) == structure(build_patient(storage_type))
    assert type(plain) is dict
    assert type(plain["meta"]) is dict


def test_from_json_reads_type_preserving_text_and_round_trips() -> None:
    # Arrange
    text = TypePreservationSerializer.serialize(build_patient())

    # Act
    resource = FhirResource.from_json(text)

    # Assert
    assert structure(resource.raw_dict()) == structure(build_patient())
    assert structure(resource.dict()) == structure(expected_patient())


# ------------------------------------------------------------------ serializer defaults


def test_type_preservation_round_trip_default_returns_ordered_dicts() -> None:
    # Arrange
    source = build_patient()

    # Act
    result = TypePreservationSerializer.deserialize(
        TypePreservationSerializer.serialize(source)
    )

    # Assert: the default is unchanged from 3.x, so callers that rely on it keep working
    assert isinstance(result, OrderedDict)
    assert isinstance(result["meta"], OrderedDict)
    assert isinstance(result["name"][0], OrderedDict)
    assert structure(result) == structure(source)


# ------------------------------------------------------------------ persisted format
# Golden values captured from the 3.0.6 release.  A 4.x reader must load what 3.x wrote,
# and a 4.x writer must write what a 3.x reader loads.


def golden_source() -> dict[str, Any]:
    return {
        "resourceType": "Patient",
        "id": "golden-1",
        "meta": {"lastUpdated": datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)},
        "name": [{"given": ["José"], "family": "Ñandú"}],
        "x_date": date(1980, 2, 3),
        "x_time": time(3, 4, 5),
        "x_decimal": Decimal("1.50"),
        "x_float": 1.0,
        "x_int": 2**53 + 1,
        "active": True,
        "none": None,
    }


def golden_msgpack_source() -> dict[str, Any]:
    return {
        "resourceType": "Patient",
        "id": "golden-1",
        "name": [{"given": ["José"], "family": "Ñandú"}],
        "x_float": 1.0,
        "x_int": 2**53 + 1,
        "active": True,
        "none": None,
    }


GOLDEN_COMPRESSED_JSON_TEXT = '{"resourceType":"Patient","id":"golden-1","meta":{"lastUpdated":{"__type__":"datetime","iso":"2024-01-02T03:04:05+00:00","tzinfo":"UTC"}},"name":[{"given":["Jos\\u00e9"],"family":"\\u00d1and\\u00fa"}],"x_date":{"__type__":"date","iso":"1980-02-03"},"x_time":{"__type__":"time","iso":"03:04:05","tzinfo":null},"x_decimal":{"__type__":"decimal","value":"1.50"},"x_float":1.0,"x_int":9007199254740993,"active":true,"none":null}'
GOLDEN_COMPRESSED_B64 = "eNptUMtOwzAQ/Je9klTrPFTsa2+cOKQnQNGq3lSWHKdKnIoS5d9Zl4Io4rYzntGMZ4GRp2EeD9xcTgwGnik6DhEycFbgcfCWQ64E9xwJzAKeprg/WYpsE2zbKM62FXHious5madBiAKLKkeVY9FgabAyWD8gGkRRxA8XuiTaNztY1wwCidO8LHB0Zw5ywdMwvc6IrOEtg4565y+iT5RVFGw6OoJVHt/blP1PnZ8qSj+i9MixhDXprz3v9XfVv/v+ahpm769eywfXk/8bd2MzOJOf05ZqU+NXWucHimDUBhNysq/RiFuldVFX2wq1LjOgQ5Sfg4njzDLHEPiW+Qkl6ID3"  # pragma: allowlist secret
GOLDEN_MSGPACK_B64 = "h6xyZXNvdXJjZVR5cGWnUGF0aWVudKJpZKhnb2xkZW4tMaRuYW1lkYKlZ2l2ZW6RpUpvc8OppmZhbWlseafDkWFuZMO6p3hfZmxvYXTKP4AAAKV4X2ludM8AIAAAAAAAAaZhY3RpdmXDpG5vbmXA"  # pragma: allowlist secret
GOLDEN_COMPRESSED_MSGPACK_B64 = "eNprX1OUWpxfWpScGlJZkLo8ILEkMzWvZFFmyor0/JyU1DxdwyV5ibmpE5uWpmeWpeZNXOqVX3x45bK0xNzMnMrlhycm5qUc3rW8Ij4tJz+x5JR9AwPD0or4zLyS8wwKDCDAuCwxuQSo8/CSvPy81AMA4ZYwLA=="  # pragma: allowlist secret

GOLDEN_BYTES: dict[str, bytes] = {
    "msgpack": base64.b64decode(GOLDEN_MSGPACK_B64),
    "compressed": base64.b64decode(GOLDEN_COMPRESSED_B64),
    "compressed_msgpack": base64.b64decode(GOLDEN_COMPRESSED_MSGPACK_B64),
}


@pytest.mark.parametrize(
    "storage_type, expected_factory",
    [
        ("compressed", golden_source),
        ("msgpack", golden_msgpack_source),
        ("compressed_msgpack", golden_msgpack_source),
    ],
)
def test_data_serialized_by_3x_still_deserializes(
    storage_type: CompressedDictStorageType,
    expected_factory: Callable[[], dict[str, Any]],
) -> None:
    # Arrange
    golden = GOLDEN_BYTES[storage_type]

    # Act
    result: dict[str, Any] = CompressedDict._deserialize_dict(
        serialized_dict_bytes=golden, storage_type=storage_type
    )

    # Assert
    assert structure(result) == structure(expected_factory())


def test_compressed_storage_writes_the_3x_type_preserving_json_text() -> None:
    # Arrange
    resource = make_dict(golden_source(), "compressed")

    # Act
    stored = resource._serialized_dict
    assert stored is not None
    stored_text = zlib.decompress(stored).decode("utf-8")

    # Assert
    assert stored_text == GOLDEN_COMPRESSED_JSON_TEXT
    assert zlib.decompress(GOLDEN_BYTES["compressed"]).decode("utf-8") == stored_text


def test_msgpack_storage_writes_the_3x_bytes() -> None:
    # Arrange
    plain = make_dict(golden_msgpack_source(), "msgpack")
    zipped = make_dict(golden_msgpack_source(), "compressed_msgpack")

    # Act / Assert
    assert plain._serialized_dict == GOLDEN_BYTES["msgpack"]
    assert zipped._serialized_dict is not None
    assert zlib.decompress(zipped._serialized_dict) == GOLDEN_BYTES["msgpack"]
    assert msgpack.unpackb(GOLDEN_BYTES["msgpack"]) == msgpack.unpackb(
        zlib.decompress(GOLDEN_BYTES["compressed_msgpack"])
    )


def test_type_preserving_text_from_3x_deserializes_to_3x_values() -> None:
    # Arrange / Act
    result = TypePreservationSerializer.deserialize(GOLDEN_COMPRESSED_JSON_TEXT)

    # Assert
    assert structure(result) == structure(golden_source())


# ------------------------------------------------------------------ bundles and lists


def build_bundle_dict(storage_type: str) -> dict[str, Any]:
    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "id": "bundle-1",
        "total": 2,
        "link": [{"relation": "self", "url": "http://example.test/Patient"}],
        "entry": [
            {
                "fullUrl": "http://example.test/Patient/synthetic-1",
                "resource": build_patient(storage_type),
                "search": {"mode": "match"},
            },
            {
                "fullUrl": "http://example.test/Observation/synthetic-2",
                "resource": build_empties(),
            },
            {"resource": {}},
        ],
    }


def make_bundle(storage_type: CompressedDictStorageType) -> FhirBundle:
    return FhirBundle.from_dict(
        build_bundle_dict(storage_type), storage_mode=mode(storage_type)
    )


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
def test_bundle_dict_has_3x_values_key_order_and_pruning(
    storage_type: CompressedDictStorageType,
) -> None:
    # Arrange
    bundle = make_bundle(storage_type)

    # Act
    result = bundle.dict()

    # Assert
    assert list(result.keys()) == [
        "type",
        "resourceType",
        "id",
        "total",
        "entry",
        "link",
    ]
    assert [list(e.keys()) for e in result["entry"]] == [
        ["fullUrl", "resource", "search"],
        ["fullUrl", "resource"],
    ]
    assert structure(result["entry"][0]["resource"]) == structure(
        expected_patient(storage_type)
    )
    assert structure(result["entry"][1]["resource"]) == structure(
        EXPECTED_EMPTIES_PRUNED
    )


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
def test_bundle_json_and_to_plain_dict_match_dict(
    storage_type: CompressedDictStorageType,
) -> None:
    # Arrange
    bundle = make_bundle(storage_type)

    # Act
    parsed = json.loads(bundle.json())

    # Assert
    assert structure(parsed) == structure(bundle.dict())
    assert structure(bundle.to_plain_dict()) == structure(bundle.dict())


def test_bundle_with_only_empty_entries_drops_the_entry_key() -> None:
    # Arrange
    bundle = FhirBundle.from_dict(
        {
            "resourceType": "Bundle",
            "type": "searchset",
            "entry": [{"resource": {}}, {}],
        },
        storage_mode=CompressedDictStorageMode(),
    )

    # Act / Assert
    assert bundle.dict() == {"type": "searchset", "resourceType": "Bundle"}
    assert json.loads(bundle.json()) == {"type": "searchset", "resourceType": "Bundle"}


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
def test_bundle_dict_round_trip_is_stable(
    storage_type: CompressedDictStorageType,
) -> None:
    # Arrange
    first = make_bundle(storage_type)

    # Act
    second = FhirBundle.from_dict(first.dict(), storage_mode=mode(storage_type))

    # Assert
    assert structure(second.dict()) == structure(first.dict())


@pytest.mark.parametrize("storage_type", SERIALIZED_STORAGE_TYPES)
def test_bundle_copy_is_independent(
    storage_type: CompressedDictStorageType,
) -> None:
    # Arrange
    bundle = make_bundle(storage_type)

    # Act
    clone = bundle.copy()
    assert clone.entry[0].resource is not None
    with clone.entry[0].resource.transaction():
        clone.entry[0].resource["id"] = "changed"

    # Assert
    assert structure(bundle.dict()["entry"][0]["resource"]) == structure(
        expected_patient(storage_type)
    )
    assert clone.dict()["entry"][0]["resource"]["id"] == "changed"


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
def test_resource_list_json_parses_to_each_resource_dict(
    storage_type: CompressedDictStorageType,
) -> None:
    # Arrange
    resources = FhirResourceList(
        [
            make_resource(storage_type),
            FhirResource(initial_dict=build_empties(), storage_mode=mode(storage_type)),
        ]
    )

    # Act
    parsed = json.loads(resources.json())

    # Assert
    assert structure(parsed) == structure([r.dict() for r in resources])
    assert structure(parsed[0]) == structure(expected_patient(storage_type))
    assert structure(parsed[1]) == structure(EXPECTED_EMPTIES_PRUNED)


def test_empty_resource_list_json_is_empty_array() -> None:
    # Arrange / Act / Assert
    assert json.loads(FhirResourceList().json()) == []
