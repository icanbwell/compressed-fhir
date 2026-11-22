import json
from collections import OrderedDict
from datetime import datetime, date
from typing import List, Dict, Any, cast

import pytest

from compressedfhir.utilities.json_helpers import FhirClientJsonHelpers


class TestFhirClientJsonHelpers:
    def test_json_serial(self) -> None:
        # Test datetime serialization
        dt = datetime(2023, 1, 15, 12, 30)
        assert FhirClientJsonHelpers.json_serial(dt) == "2023-01-15T12:30:00"

        # Test date serialization
        d = date(2023, 1, 15)
        assert FhirClientJsonHelpers.json_serial(d) == "2023-01-15"

        # Test other types
        assert FhirClientJsonHelpers.json_serial(123) == "123"
        assert FhirClientJsonHelpers.json_serial("test") == "test"

    def test_remove_empty_elements(self) -> None:
        # Test dictionary removal
        input_dict = {"a": 1, "b": "", "c": None, "d": [], "e": {}, "f": [1, 2, 3]}
        expected_dict = {"a": 1, "f": [1, 2, 3]}
        assert FhirClientJsonHelpers.remove_empty_elements(input_dict) == expected_dict

        # Test list of dictionaries
        input_list: List[Dict[str, Any]] = [
            {"a": 1, "b": None},
            {"c": [], "d": "test"},
            {"e": {}},
        ]
        expected_list: List[Dict[str, Any]] = [{"a": 1}, {"d": "test"}]
        assert FhirClientJsonHelpers.remove_empty_elements(input_list) == expected_list

    def test_remove_empty_elements_from_ordered_dict(self) -> None:
        from collections import OrderedDict

        # Test OrderedDict removal
        input_dict = OrderedDict(
            [("a", 1), ("b", ""), ("c", None), ("d", []), ("e", {}), ("f", [1, 2, 3])]
        )
        expected_dict = OrderedDict([("a", 1), ("f", [1, 2, 3])])
        result: List[OrderedDict[str, Any]] | OrderedDict[str, Any] = (
            FhirClientJsonHelpers.remove_empty_elements_from_ordered_dict(input_dict)
        )
        assert result == expected_dict

        # Test list of OrderedDicts
        input_list: List[OrderedDict[str, Any]] = [
            OrderedDict([("a", 1), ("b", None)]),
            OrderedDict([("c", []), ("d", "test")]),
            OrderedDict([("e", {})]),
        ]
        expected_list: List[OrderedDict[str, Any]] = [
            OrderedDict([("a", 1)]),
            OrderedDict([("d", "test")]),
        ]
        result = FhirClientJsonHelpers.remove_empty_elements_from_ordered_dict(
            input_list
        )
        assert result == expected_list

    def test_convert_dict_to_fhir_json(self) -> None:
        input_dict = {"name": "John Doe", "age": 30, "address": None, "hobbies": []}
        result = FhirClientJsonHelpers.convert_dict_to_fhir_json(input_dict)
        parsed_result = json.loads(result)
        assert parsed_result == {"name": "John Doe", "age": 30}

    def test_orjson_dumps(self) -> None:
        # Test basic serialization
        data = {"a": 1, "b": "test"}
        result = FhirClientJsonHelpers.orjson_dumps(data)
        assert json.loads(result) == data

        # Test sorting keys
        result_sorted = FhirClientJsonHelpers.orjson_dumps(data, sort_keys=True)
        assert result_sorted == '{"a":1,"b":"test"}'

        # Test indentation (limited support)
        result_indent = FhirClientJsonHelpers.orjson_dumps(data, indent=2)
        assert isinstance(result_indent, str)

    def test_orjson_loads(self) -> None:
        # Test string input
        json_str = '{"a": 1, "b": "test"}'
        result = FhirClientJsonHelpers.orjson_loads(json_str)
        assert result == {"a": 1, "b": "test"}

        # Test bytes input
        json_bytes = b'{"a": 1, "b": "test"}'
        result = FhirClientJsonHelpers.orjson_loads(json_bytes)
        assert result == {"a": 1, "b": "test"}

        # Test invalid JSON
        invalid_json = "{invalid json}"
        result = FhirClientJsonHelpers.orjson_loads(invalid_json)
        assert result is None


@pytest.mark.parametrize(
    "value, expected",
    [
        (
            {"a": 0, "b": False, "c": 0.0},
            OrderedDict([("a", 0), ("b", False), ("c", 0.0)]),
        ),
        ({"a": "  ", "b": "\n", "c": " x "}, OrderedDict([("c", " x ")])),
        ({"a": {"b": {"c": None}}, "d": [[], {}, None, ""]}, OrderedDict()),
        (
            {"a": [{"b": None}, {"c": 1}]},
            OrderedDict([("a", [OrderedDict([("c", 1)])])]),
        ),
        ([{"a": None}, {"b": [None, 2]}], [OrderedDict([("b", [2])])]),
        ("text", "text"),
        (5, 5),
        ((), ()),
    ],
    ids=[
        "falsy-scalars-kept",
        "blank-strings-removed",
        "nested-empties-collapse",
        "list-of-dicts",
        "top-level-list",
        "string-passthrough",
        "number-passthrough",
        "tuple-passthrough",
    ],
)
def test_remove_empty_elements_from_ordered_dict_cases(
    value: Any, expected: Any
) -> None:
    # Act
    result = FhirClientJsonHelpers.remove_empty_elements_from_ordered_dict(value)

    # Assert
    assert result == expected


def test_remove_empty_elements_from_ordered_dict_keeps_order_and_returns_ordered_dicts() -> (
    None
):
    # Arrange
    value = {"z": 1, "y": {"b": 2, "a": None, "c": 3}, "x": [{"k": "v"}]}

    # Act
    result = FhirClientJsonHelpers.remove_empty_elements_from_ordered_dict(
        cast(OrderedDict[str, Any], value)
    )

    # Assert
    assert isinstance(result, OrderedDict)
    assert list(result.keys()) == ["z", "y", "x"]
    assert type(result["y"]) is OrderedDict
    assert list(result["y"].keys()) == ["b", "c"]
    assert type(result["x"][0]) is OrderedDict
