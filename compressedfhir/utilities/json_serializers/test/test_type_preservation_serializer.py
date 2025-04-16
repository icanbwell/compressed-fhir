from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Any

from compressedfhir.utilities.json_serializers.type_preservation_serializer import (
    TypePreservationSerializer,
)


class TestCustomObject:
    def __init__(self, name: str, value: int):
        self.name: str = name
        self.value: int = value

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, TestCustomObject):
            return False
        return self.name == other.name and self.value == other.value


def test_complex_data_serialization() -> None:
    """
    Test serialization and deserialization of complex data
    """
    complex_data = {
        "timestamp": datetime.now(timezone.utc),
        "today": date.today(),
        "precise_value": Decimal("3.14159"),
        "complex_number": 3 + 4j,
        "byte_data": b"Hello",
        "unique_items": {1, 2, 3},
        "custom_obj": TestCustomObject("test", 42),
    }

    # Serialize
    serialized = TypePreservationSerializer.serialize(complex_data)

    # Deserialize
    deserialized = TypePreservationSerializer.deserialize(serialized)

    # Verify types
    assert isinstance(deserialized["timestamp"], datetime)
    assert isinstance(deserialized["today"], date)
    assert isinstance(deserialized["precise_value"], Decimal)
    assert isinstance(deserialized["complex_number"], complex)
    assert isinstance(deserialized["byte_data"], bytes)
    assert isinstance(deserialized["unique_items"], set)
    assert isinstance(deserialized["custom_obj"], TestCustomObject)


def test_nested_complex_data() -> None:
    """
    Test serialization of nested complex data
    """
    nested_data = {"level1": {"level2": {"timestamp": datetime.now(timezone.utc)}}}

    serialized = TypePreservationSerializer.serialize(nested_data)
    deserialized = TypePreservationSerializer.deserialize(serialized)

    assert isinstance(deserialized["level1"]["level2"]["timestamp"], datetime)
