"""
Pins the output of the dict()/json()/deserialize paths to the original
(pre-optimization) implementation.  The reference_* helpers below are
independent re-statements of that implementation built from stdlib json,
so they do not move when the production code is optimized.  All data is synthetic.
"""

import json
from collections import OrderedDict
from datetime import date, datetime, time, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, cast

import pytest

from compressedfhir.fhir.fhir_bundle import FhirBundle
from compressedfhir.fhir.fhir_bundle_entry import FhirBundleEntry
from compressedfhir.fhir.fhir_resource import FhirResource
from compressedfhir.utilities.compressed_dict.v1.compressed_dict import CompressedDict
from compressedfhir.utilities.compressed_dict.v1.compressed_dict_storage_mode import (
    CompressedDictStorageMode,
    CompressedDictStorageType,
)
from compressedfhir.utilities.fhir_json_encoder import FhirJSONEncoder
from compressedfhir.utilities.json_helpers import FhirClientJsonHelpers
from compressedfhir.utilities.json_serializers.type_preservation_decoder import (
    TypePreservationDecoder,
)
from compressedfhir.utilities.json_serializers.type_preservation_serializer import (
    TypePreservationSerializer,
)

STORAGE_TYPES: List[CompressedDictStorageType] = [
    "raw",
    "compressed",
    "msgpack",
    "compressed_msgpack",
]


def reference_deserialize(json_str: str) -> Any:
    return json.loads(
        json_str, object_hook=lambda dct: TypePreservationDecoder.decode(dct, None)
    )


def reference_resource_dict(resource: FhirResource) -> Dict[str, Any]:
    pruned = reference_remove_empty(resource.raw_dict())
    return cast(
        Dict[str, Any],
        json.loads(json.dumps(pruned, cls=FhirJSONEncoder)),
    )


def reference_compressed_dict_dict(d: CompressedDict[str, Any]) -> Dict[str, Any]:
    return cast(
        Dict[str, Any],
        json.loads(json.dumps(d.raw_dict(), cls=FhirJSONEncoder)),
    )


def reference_entry_dict(entry: FhirBundleEntry) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    if entry.fullUrl is not None:
        result["fullUrl"] = entry.fullUrl
    if entry.resource is not None:
        result["resource"] = reference_resource_dict(entry.resource)
    if entry.request is not None:
        result["request"] = entry.request.dict()
    if entry.response is not None:
        result["response"] = entry.response.dict()
    if entry.link is not None:
        result["link"] = [link.dict() for link in entry.link]
    if entry.search is not None:
        result["search"] = entry.search.dict()
    return cast(Dict[str, Any], reference_remove_empty(result))


def reference_bundle_dict(bundle: FhirBundle) -> Dict[str, Any]:
    entries = [reference_entry_dict(e) for e in bundle.entry] if bundle.entry else None
    result: Dict[str, Any] = {"type": bundle.type_, "resourceType": "Bundle"}
    if bundle.id_ is not None:
        result["id"] = bundle.id_
    if bundle.identifier is not None:
        result["identifier"] = bundle.identifier.dict()
    if bundle.timestamp is not None:
        result["timestamp"] = bundle.timestamp
    if bundle.total is not None:
        result["total"] = bundle.total
    if entries and len(entries) > 0:
        result["entry"] = entries
    if bundle.link:
        result["link"] = [link.dict() for link in bundle.link]
    if bundle.meta:
        result["meta"] = bundle.meta.dict()
    return cast(Dict[str, Any], reference_remove_empty(result))


def assert_identical(actual: Any, expected: Any, path: str = "$") -> None:
    """Strict: same types (OrderedDict vs dict, int vs float vs bool), same order, same values."""
    assert type(actual) is type(expected), f"{path}: {type(actual)} != {type(expected)}"
    if isinstance(expected, dict):
        assert list(actual.keys()) == list(expected.keys()), f"{path}: key order"
        for k in expected:
            assert_identical(actual[k], expected[k], f"{path}.{k}")
    elif isinstance(expected, list):
        assert len(actual) == len(expected), f"{path}: length"
        for i, (a, e) in enumerate(zip(actual, expected)):
            assert_identical(a, e, f"{path}[{i}]")
    else:
        assert actual == expected, f"{path}: {actual!r} != {expected!r}"


MSGPACK_TYPES = ("msgpack", "compressed_msgpack")


def synthetic_resource(i: int = 0, storage_type: str = "compressed") -> Dict[str, Any]:
    """msgpack storage cannot hold datetime/Decimal/bytes, so those modes get JSON-native values."""
    resource = _rich_resource(i)
    if storage_type in MSGPACK_TYPES:
        resource = {
            k: v
            for k, v in resource.items()
            if not isinstance(v, (datetime, date, time, Decimal, bytes))
        }
        resource["item"] = [
            {k: v for k, v in it.items() if k not in ("net", "servicedDate")}
            for it in resource["item"]
        ]
    return resource


def _rich_resource(i: int) -> Dict[str, Any]:
    return {
        "resourceType": "ExplanationOfBenefit",
        "id": f"eob-{i}",
        "status": "active",
        "created": datetime(2024, 1, 2, 3, 4, 5, 123456, tzinfo=timezone.utc),
        "naive": datetime(2024, 1, 2, 3, 4, 5),
        "offset": datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=-5))),
        "day": date(2024, 1, 2),
        "clock": time(3, 4, 5),
        "amount_whole": Decimal("100"),
        "amount_fraction": Decimal("100.25"),
        "ratio": 0.1,
        "tiny": 1e-07,
        "big": 2**62,
        "negative": -7,
        "flag": True,
        "off": False,
        "zero": 0,
        "text": 'héllo ☃ "quoted" \n newline',
        "blank": "   ",
        "empty_list": [],
        "empty_dict": {},
        "nothing": None,
        "nested_empty": {"a": [], "b": {"c": None}},
        "list_with_empties": [{}, [], None, "", {"keep": 1}],
        "bytes_value": b"abc",
        "item": [
            {
                "sequence": k,
                "net": {"value": Decimal("1.5"), "currency": "USD"},
                "servicedDate": date(2024, 1, 3),
                "adjudication": [{"amount": {"value": 10.5}}],
            }
            for k in range(3)
        ],
    }


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
def test_resource_dict_identical_to_reference(
    storage_type: CompressedDictStorageType,
) -> None:
    resource = FhirResource(
        initial_dict=synthetic_resource(storage_type=storage_type),
        storage_mode=CompressedDictStorageMode(storage_type=storage_type),
    )
    assert_plain_matches(resource.dict(), reference_resource_dict(resource))


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
def test_resource_json_identical_to_reference(
    storage_type: CompressedDictStorageType,
) -> None:
    resource = FhirResource(
        initial_dict=synthetic_resource(storage_type=storage_type),
        storage_mode=CompressedDictStorageMode(storage_type=storage_type),
    )
    pruned = reference_remove_empty(resource.raw_dict())
    exact = resource.json(byte_identical=True)
    assert exact == json.dumps(pruned, cls=FhirJSONEncoder)
    assert_identical(resource.to_fhir_dict(), json.loads(exact))


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
def test_plain_compressed_dict_dict_identical_to_reference(
    storage_type: CompressedDictStorageType,
) -> None:
    d: CompressedDict[str, Any] = CompressedDict(
        initial_dict=OrderedDict(synthetic_resource(storage_type=storage_type)),
        properties_to_cache=[],
        storage_mode=CompressedDictStorageMode(storage_type=storage_type),
    )
    assert_plain_matches(d.dict(), reference_compressed_dict_dict(d))


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
def test_raw_dict_roundtrip_preserves_python_types(
    storage_type: CompressedDictStorageType,
) -> None:
    source = synthetic_resource(storage_type=storage_type)
    resource = FhirResource(
        initial_dict=source,
        storage_mode=CompressedDictStorageMode(storage_type=storage_type),
    )
    raw = resource.raw_dict()
    assert raw["id"] == source["id"]
    assert raw["item"][0]["sequence"] == 0
    if storage_type not in MSGPACK_TYPES:  # msgpack storage is JSON-native only
        assert raw == source
        assert isinstance(raw["day"], date) and not isinstance(raw["day"], datetime)
        assert raw["amount_fraction"] == Decimal("100.25")


@pytest.mark.parametrize(
    "payload",
    [
        {"a": 1, "b": [1, 2, {"c": "x"}], "d": None},
        {"when": datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)},
        {"when": date(2024, 1, 2), "at": time(1, 2, 3), "n": Decimal("1.50")},
        {"nested": [{"deep": {"when": datetime(2024, 5, 6, 7, 8, 9)}}]},
        {"blob": b"\x00\xffabc", "s": {1, 2}},
        {"f": 0.1, "g": 1e-07, "h": 1e22, "i": -0.0, "j": 2**63},
        {"nan": float("nan")},
        {"inf": float("inf"), "ninf": float("-inf")},
        {"huge": 2**100},
        {"hugeneg": -(2**100), "edge": 2**64, "max": 2**64 - 1, "min": -(2**63)},
        {"floatfrac": 0.12345678901234567890123},
        {},
        {"unicode": "snow☃ \U0001f600", "esc": 'a"b\\c\n'},
    ],
)
def test_deserialize_identical_to_reference(payload: Dict[str, Any]) -> None:
    text = TypePreservationSerializer.serialize(OrderedDict(payload))
    actual = TypePreservationSerializer.deserialize(text)
    expected = reference_deserialize(text)
    if "nan" in payload:
        assert actual["nan"] != actual["nan"] and expected["nan"] != expected["nan"]
        assert type(actual) is type(expected)
    else:
        assert_identical(actual, expected)


def test_deserialize_unknown_type_marker_matches_reference() -> None:
    text = json.dumps({"x": {"__type__": "nonexistent_type", "v": 1}, "y": [1]})
    assert_identical(
        TypePreservationSerializer.deserialize(text), reference_deserialize(text)
    )


def test_deserialize_top_level_list_matches_reference() -> None:
    text = json.dumps([{"a": 1}, [2, {"b": 3}]])
    assert_identical(
        TypePreservationSerializer.deserialize(text), reference_deserialize(text)
    )


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
def test_bundle_dict_identical_to_reference(
    storage_type: CompressedDictStorageType,
) -> None:
    mode = CompressedDictStorageMode(storage_type=storage_type)
    bundle = FhirBundle.construct(type_="searchset", id_="b1", total=4)
    for i in range(3):
        bundle.entry.append(
            FhirBundleEntry(
                fullUrl=f"urn:uuid:{i}",
                resource=FhirResource(
                    initial_dict=synthetic_resource(i, storage_type), storage_mode=mode
                ),
            )
        )
    # entry that prunes down to nothing, and entries with no / all-empty resource
    bundle.entry.append(FhirBundleEntry(resource=None))
    bundle.entry.append(
        FhirBundleEntry(
            fullUrl="urn:uuid:empty",
            resource=FhirResource(
                initial_dict={"a": [], "b": None, "c": "  "}, storage_mode=mode
            ),
        )
    )
    assert_plain_matches(bundle.dict(), reference_bundle_dict(bundle))


def test_empty_bundle_dict_identical_to_reference() -> None:
    bundle = FhirBundle.construct(type_="searchset")
    assert_plain_matches(bundle.dict(), reference_bundle_dict(bundle))


def reference_remove_empty(d: Any) -> Any:
    """Verbatim copy of the pre-4.0.0 remove_empty_elements_from_ordered_dict."""
    from typing import Dict as TDict

    def empty(x: Any) -> bool:
        return (
            x is None or x == [] or x == {} or (isinstance(x, str) and x.strip() == "")
        )

    if not isinstance(d, (OrderedDict, list, TDict)):
        return d
    elif isinstance(d, list):
        return [v for v in (reference_remove_empty(v) for v in d) if not empty(v)]
    else:
        return OrderedDict(
            {
                k: v
                for k, v in ((k, reference_remove_empty(v)) for k, v in d.items())
                if not empty(v)
            }
        )


def _random_value(rng: Any, depth: int) -> Any:
    leaves: List[Any] = [
        None, "", "  ", "x", " y ", 0, 1, -3, 0.0, 2.5, True, False, [], {},
        (), (1,), Decimal("0"), date(2024, 1, 2), b"", OrderedDict(),
    ]  # fmt: skip
    if depth <= 0 or rng.random() < 0.3:
        return rng.choice(leaves)
    if rng.random() < 0.5:
        return [_random_value(rng, depth - 1) for _ in range(rng.randint(0, 4))]
    cls = rng.choice([dict, OrderedDict])
    return cls(
        (f"k{i}", _random_value(rng, depth - 1)) for i in range(rng.randint(0, 4))
    )


@pytest.mark.parametrize("seed", range(200))
def test_remove_empty_matches_reference_on_random_structures(seed: int) -> None:
    import random

    value = _random_value(random.Random(seed), 5)
    assert_plain_matches(
        FhirClientJsonHelpers.remove_empty_elements(value),
        reference_remove_empty(value),
    )


@pytest.mark.parametrize("scalar", [None, "", "text", 5, 1.5, True])
def test_remove_empty_returns_non_containers_unchanged(scalar: Any) -> None:
    assert FhirClientJsonHelpers.remove_empty_elements(scalar) is scalar


def assert_plain_matches(actual: Any, expected: Any, path: str = "$") -> None:
    """actual must be plain dict/list all the way down, with the same values and key order."""
    if isinstance(expected, dict):
        assert type(actual) is dict, f"{path}: {type(actual)} is not a plain dict"
        assert list(actual.keys()) == list(expected.keys()), f"{path}: key order"
        for k in expected:
            assert_plain_matches(actual[k], expected[k], f"{path}.{k}")
    elif isinstance(expected, list):
        assert type(actual) is list and len(actual) == len(expected), path
        for i, (a, e) in enumerate(zip(actual, expected)):
            assert_plain_matches(a, e, f"{path}[{i}]")
    else:
        assert type(actual) is type(expected), f"{path}: {type(actual)}"
        assert actual == expected, f"{path}: {actual!r} != {expected!r}"


def test_dict_returns_plain_dicts_and_takes_no_arguments() -> None:
    resource = FhirResource(
        initial_dict={"resourceType": "Patient", "id": "1", "name": [{"family": "X"}]}
    )
    result = resource.dict()
    assert type(result) is dict
    assert type(result["name"][0]) is dict
    assert type(FhirBundle.construct(type_="searchset").dict()) is dict
    with pytest.raises(TypeError):
        resource.dict(ordered=True)  # type: ignore[call-arg]


@pytest.mark.parametrize("storage_type", ["compressed", "raw"])
@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
    ids=["nan", "inf", "-inf", "Decimal-NaN", "Decimal-Infinity"],
)
def test_non_finite_values_are_omitted_in_every_storage_mode(
    value: Any, storage_type: CompressedDictStorageType
) -> None:
    """FHIR cannot hold NaN/Infinity: dict() and json() omit them, whatever the storage mode."""
    resource = FhirResource(
        initial_dict={
            "resourceType": "Observation",
            "id": "1",
            "q": {"v": value, "u": "mg"},
        },
        storage_mode=CompressedDictStorageMode(storage_type=storage_type),
    )
    expected = {"resourceType": "Observation", "id": "1", "q": {"u": "mg"}}
    assert resource.dict() == expected
    assert json.loads(resource.json()) == expected


@pytest.mark.parametrize("storage_type", ["compressed", "raw"])
def test_big_ints_stay_exact_in_every_storage_mode(
    storage_type: CompressedDictStorageType,
) -> None:
    resource = FhirResource(
        initial_dict={"resourceType": "X", "id": "1", "big": 2**100, "neg": -(2**70)},
        storage_mode=CompressedDictStorageMode(storage_type=storage_type),
    )
    assert resource.dict()["big"] == 2**100
    assert resource.dict()["neg"] == -(2**70)
    assert json.loads(resource.json())["big"] == 2**100


def test_exact_text_keeps_nan_only_where_storage_kept_it() -> None:
    """
    byte_identical=True writes NaN as the standard library always did, but compressed storage
    already turned it into null when the resource was built (accepted change), so there the
    key is gone.
    """
    initial = {"resourceType": "Observation", "id": "1", "q": {"v": float("nan")}}
    raw = FhirResource(
        initial_dict=dict(initial, q={"v": float("nan")}),
        storage_mode=CompressedDictStorageMode.raw(),
    )
    compressed = FhirResource(
        initial_dict=dict(initial, q={"v": float("nan")}),
        storage_mode=CompressedDictStorageMode.default(),
    )
    assert "NaN" in raw.json(byte_identical=True)
    assert "NaN" not in compressed.json(byte_identical=True)
    assert json.loads(compressed.json(byte_identical=True)) == {
        "resourceType": "Observation",
        "id": "1",
    }


def _bundle_for_json(storage_type: CompressedDictStorageType) -> FhirBundle:
    mode = CompressedDictStorageMode(storage_type=storage_type)
    bundle = FhirBundle.construct(type_="searchset", id_="b1")
    for i in range(2):
        bundle.entry.append(
            FhirBundleEntry(
                fullUrl=f"urn:uuid:{i}",
                resource=FhirResource(
                    initial_dict=synthetic_resource(i, storage_type), storage_mode=mode
                ),
            )
        )
    return bundle


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
def test_json_byte_identical_true_matches_reference(
    storage_type: CompressedDictStorageType,
) -> None:
    bundle = _bundle_for_json(storage_type)
    entry = bundle.entry[0]
    assert entry.resource is not None
    expected_resource = json.dumps(
        reference_resource_dict(entry.resource), cls=FhirJSONEncoder
    )
    assert entry.resource.json(byte_identical=True) == expected_resource
    assert entry.json(byte_identical=True) == json.dumps(
        reference_entry_dict(entry), cls=FhirJSONEncoder
    )
    assert bundle.json(byte_identical=True) == json.dumps(
        reference_bundle_dict(bundle), cls=FhirJSONEncoder
    )


def test_json_default_is_the_fast_text() -> None:
    """4.0.0: json() defaults to orjson text; byte_identical=True restores the stdlib text."""
    bundle = _bundle_for_json("compressed")
    entry = bundle.entry[0]
    assert entry.resource is not None
    for obj in (entry.resource, entry, bundle):
        assert obj.json() == obj.json(byte_identical=False)
        assert obj.json() != obj.json(byte_identical=True)  # compact vs ", " separators
        assert json.loads(obj.json()) == json.loads(obj.json(byte_identical=True))


@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
def test_json_not_byte_identical_is_equivalent_json(
    storage_type: CompressedDictStorageType,
) -> None:
    bundle = _bundle_for_json(storage_type)
    entry = bundle.entry[0]
    assert entry.resource is not None
    for obj, reference in (
        (entry.resource, reference_resource_dict(entry.resource)),
        (entry, reference_entry_dict(entry)),
        (bundle, reference_bundle_dict(bundle)),
    ):
        fast = obj.json(byte_identical=False)
        assert isinstance(fast, str)
        assert_plain_matches(json.loads(fast), reference)
        assert ", " not in fast.split('"text"')[0]  # compact separators


def test_json_not_byte_identical_documented_differences() -> None:
    resource = FhirResource(
        initial_dict={
            "resourceType": "Observation",
            "id": "1",
            "text": "snow\u2603",
            "tiny": 1e-07,
        },
        storage_mode=CompressedDictStorageMode.raw(),
    )
    exact = resource.json(byte_identical=True)
    fast = resource.json(byte_identical=False)
    assert "\\u2603" in exact and "\u2603" in fast
    assert "1e-07" in exact and "1e-7" in fast


def test_json_not_byte_identical_falls_back_to_exact_text_for_big_ints() -> None:
    """orjson cannot encode ints beyond 64 bits; the whole payload then uses the stdlib."""
    resource = FhirResource(
        initial_dict={
            "resourceType": "Observation",
            "id": "1",
            "huge": 2**100,
            "t": "\u2603",
        },
        storage_mode=CompressedDictStorageMode.raw(),
    )
    assert resource.json(byte_identical=False) == resource.json(byte_identical=True)
    assert json.loads(resource.json(byte_identical=False))["huge"] == 2**100


# ---- the dict() fast path (compressed storage) must agree with the general path ----------


def _random_typed_value(rng: Any, depth: int, allow_unsupported: bool) -> Any:
    leaves: List[Any] = [
        None, "", "  ", "x", " y ", 0, 1, -3, 2.5, 1e-07, True, False, [], {},
        datetime(2024, 1, 2, 3, 4, 5),
        datetime(2024, 1, 2, 3, 4, 5, 123456, tzinfo=timezone.utc),
        datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=-5, minutes=-30))),
        date(2024, 1, 2), time(3, 4, 5), time(3, 4, 5, 6),
        Decimal("100"), Decimal("100.25"), Decimal("-0.5"), Decimal("1E+3"), Decimal("0"),
        b"", b"abc", "snow☃", "a\"b\\c\n",
    ]  # fmt: skip
    if allow_unsupported:
        leaves += [{1, 2}, complex(1, 2), time(1, 2, 3, tzinfo=timezone.utc)]
    if depth <= 0 or rng.random() < 0.3:
        return rng.choice(leaves)
    if rng.random() < 0.5:
        return [
            _random_typed_value(rng, depth - 1, allow_unsupported)
            for _ in range(rng.randint(0, 4))
        ]
    return OrderedDict(
        (f"k{i}", _random_typed_value(rng, depth - 1, allow_unsupported))
        for i in range(rng.randint(0, 4))
    )


def _general_path_dict(d: CompressedDict[str, Any]) -> Any:
    """dict() while a transaction is open: the stored-JSON fast path is bypassed."""
    with d.transaction():
        return d.dict()


@pytest.mark.parametrize("allow_unsupported", [False, True])
@pytest.mark.parametrize("seed", range(150))
def test_fast_path_matches_general_path(seed: int, allow_unsupported: bool) -> None:
    import random

    rng = random.Random(seed)
    payload = OrderedDict(
        (f"top{i}", _random_typed_value(rng, 5, allow_unsupported))
        for i in range(rng.randint(1, 6))
    )
    mode = CompressedDictStorageMode(storage_type="compressed")
    candidates: List[CompressedDict[str, Any]] = [
        FhirResource(initial_dict=OrderedDict(payload), storage_mode=mode),
        CompressedDict(
            initial_dict=OrderedDict(payload), storage_mode=mode, properties_to_cache=[]
        ),
    ]
    for d in candidates:
        fast = d.dict()
        general = _general_path_dict(d)
        assert_plain_matches(fast, general)
        assert json.dumps(fast) == json.dumps(general)


@pytest.mark.parametrize(
    "payload",
    [
        {"s": {1, 2}},
        {"c": complex(1, 2)},
        {"t": time(1, 2, 3, tzinfo=timezone.utc)},
        {"big": 2**100},
        {"n": float("nan")},
        {"d": Decimal("NaN")},
        {"nested": [{"s": {3}}]},
    ],
    ids=["set", "complex", "tz-time", "big-int", "nan", "decimal-nan", "nested-set"],
)
def test_unusual_content_gives_same_dict_through_both_paths(
    payload: Dict[str, Any],
) -> None:
    """Content the fast path cannot reproduce falls back, so both paths always agree."""
    r = FhirResource(
        initial_dict={"resourceType": "X", "id": "1", **payload},
        storage_mode=CompressedDictStorageMode(storage_type="compressed"),
    )
    assert_plain_matches(r.dict(), _general_path_dict(r))


def test_dict_inside_a_transaction_reflects_pending_changes() -> None:
    r = FhirResource(
        initial_dict={"resourceType": "Patient", "id": "1"},
        storage_mode=CompressedDictStorageMode(storage_type="compressed"),
    )
    with r.transaction() as d:
        d["id"] = "2"
        assert r.dict()["id"] == "2"
    assert r.dict()["id"] == "2"
