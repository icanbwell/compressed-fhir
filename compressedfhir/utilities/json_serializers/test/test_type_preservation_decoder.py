from datetime import datetime, date
from decimal import Decimal
from typing import Type, Any, Dict

import pytest

from compressedfhir.utilities.json_serializers.type_preservation_decoder import (
    TypePreservationDecoder,
)


class TestCustomObject:
    def __init__(self, name: str, value: int):
        self.name: str = name
        self.value: int = value

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, TestCustomObject):
            return False
        return self.name == other.name and self.value == other.value


@pytest.mark.parametrize(
    "input_type, input_dict, expected_type",
    [
        (
            "datetime",
            {"__type__": "datetime", "iso": "2023-01-01T00:00:00+00:00"},
            datetime,
        ),
        ("date", {"__type__": "date", "iso": "2023-01-01"}, date),
        ("decimal", {"__type__": "decimal", "value": "3.14"}, Decimal),
        ("complex", {"__type__": "complex", "real": 3, "imag": 4}, complex),
        ("bytes", {"__type__": "bytes", "value": "test"}, bytes),
        ("set", {"__type__": "set", "values": [1, 2, 3]}, set),
    ],
)
def test_complex_type_decoding(
    input_type: str, input_dict: Dict[str, Any], expected_type: Type[Any]
) -> None:
    """
    Test decoding of various complex types
    """
    decoded = TypePreservationDecoder.decode(input_dict)

    assert isinstance(decoded, expected_type)


def test_custom_object_decoding() -> None:
    """
    Test decoding of custom objects
    """
    custom_obj_dict = {
        "__type__": "TestCustomObject",
        "__module__": __name__,
        "attributes": {"name": "test", "value": 42},
    }

    decoded = TypePreservationDecoder.decode(custom_obj_dict)

    assert isinstance(decoded, TestCustomObject)
    assert decoded.name == "test"
    assert decoded.value == 42


def test_custom_decoder() -> None:
    """
    Test custom decoder functionality
    """

    def custom_decoder(data: Dict[str, Any]) -> Any:
        if data.get("__type__") == "special_type":
            return f"Decoded: {data['value']}"
        return data

    special_dict = {"__type__": "special_type", "value": "test"}

    decoded = TypePreservationDecoder.decode(
        special_dict, custom_decoders={"special_type": custom_decoder}
    )

    assert decoded == "Decoded: test"
