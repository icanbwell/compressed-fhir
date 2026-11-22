from datetime import datetime, date, time
from decimal import Decimal
from typing import Type, Any, Dict, Optional
import pytest

from compressedfhir.utilities.json_serializers.type_preservation_decoder import (
    TypePreservationDecoder,
)


class TestCustomObject:
    def __init__(
        self,
        name: str,
        value: int,
        created_at: Optional[datetime] = None,
        nested_data: Optional[Dict[str, Any]] = None,
    ):
        self.name: str = name
        self.value: int = value
        self.created_at: Optional[datetime] = created_at
        self.nested_data: Optional[Dict[str, Any]] = nested_data

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, TestCustomObject):
            return False
        return (
            self.name == other.name
            and self.value == other.value
            and self.created_at == other.created_at
            and self.nested_data == other.nested_data
        )


@pytest.mark.parametrize(
    "input_type, input_dict, expected_type",
    [
        (
            "datetime",
            {"__type__": "datetime", "iso": "2023-01-01T00:00:00+00:00"},
            datetime,
        ),
        (
            "datetime",
            {
                "__type__": "datetime",
                "iso": "2023-01-01T00:00:00-08:00",
                "tzinfo": "Pacific/Honolulu",
            },
            datetime,
        ),
        ("date", {"__type__": "date", "iso": "2023-01-01"}, date),
        ("time", {"__type__": "time", "iso": "14:30:15"}, time),
        (
            "time",
            {"__type__": "time", "iso": "14:30:15", "tzinfo": "Pacific/Honolulu"},
            time,
        ),
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


def test_custom_object_marker_is_not_rebuilt() -> None:
    """
    Data never chooses which class gets instantiated: a custom-object marker reads back as
    its attributes dict.
    """
    marker = {
        "__type__": "TestCustomObject",
        "__module__": __name__,
        "attributes": {"name": "test", "value": 42},
    }
    for decoded in (
        TypePreservationDecoder.decode(dict(marker)),
        TypePreservationDecoder.decode_tree(dict(marker)),
        TypePreservationDecoder.decode_tree(dict(marker), use_ordered_dict=False),
    ):
        assert not isinstance(decoded, TestCustomObject)
        assert dict(decoded) == marker["attributes"]


def test_custom_object_is_rebuilt_only_by_an_explicit_decoder() -> None:
    marker = {
        "__type__": "TestCustomObject",
        "__module__": __name__,
        "attributes": {"name": "test", "value": 42},
    }

    def rebuild(data: Dict[str, Any]) -> Any:
        return TestCustomObject(**data["attributes"])

    for decoded in (
        TypePreservationDecoder.decode(
            dict(marker), custom_decoders={"TestCustomObject": rebuild}
        ),
        TypePreservationDecoder.decode_tree(
            dict(marker), custom_decoders={"TestCustomObject": rebuild}
        ),
    ):
        assert isinstance(decoded, TestCustomObject)
        assert decoded.name == "test"
        assert decoded.value == 42


def test_marker_naming_a_module_never_imports_it(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reading data must not import a module by name or instantiate a class from it."""
    import sys

    marker_file = tmp_path / "imported.txt"
    (tmp_path / "decoder_probe_module.py").write_text(
        f"import pathlib\npathlib.Path({str(marker_file)!r}).write_text('imported')\n"
        "class Victim:\n    pass\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "decoder_probe_module", raising=False)
    payload = {
        "__type__": "Victim",
        "__module__": "decoder_probe_module",
        "attributes": {"role": "injected"},
    }
    not_a_class = {"__type__": "path", "__module__": "os", "attributes": {}}
    for data in (payload, not_a_class):
        for decoded in (
            TypePreservationDecoder.decode(dict(data)),
            TypePreservationDecoder.decode_tree(dict(data)),
        ):
            assert isinstance(decoded, dict)
    assert not marker_file.exists()
    assert "decoder_probe_module" not in sys.modules


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


def test_nested_datetime_decoding() -> None:
    """
    Typed values nested inside a custom-object marker are still decoded
    """
    nested_datetime_dict = {
        "__type__": "TestCustomObject",
        "__module__": __name__,
        "attributes": {
            "name": "test",
            "value": 42,
            "created_at": {"__type__": "datetime", "iso": "2023-06-15T10:30:00"},
            "nested_data": {
                "timestamp": {"__type__": "datetime", "iso": "2023-06-16T15:45:00"}
            },
        },
    }

    decoded = TypePreservationDecoder.decode(nested_datetime_dict)

    assert isinstance(decoded, dict)
    attributes = decoded
    assert attributes["name"] == "test"
    assert attributes["value"] == 42
    assert isinstance(attributes["created_at"], datetime)
    assert (attributes["created_at"].year, attributes["created_at"].month) == (2023, 6)
    assert attributes["created_at"].day == 15
    assert isinstance(attributes["nested_data"], dict)
    assert isinstance(attributes["nested_data"]["timestamp"], datetime)
    assert attributes["nested_data"]["timestamp"].day == 16


def test_direct_value_decoding() -> None:
    """
    Test decoding of direct values without type markers
    """
    # Test datetime direct string
    datetime_str = "2023-01-01T00:00:00"
    decoded_datetime = TypePreservationDecoder.decode(datetime_str)
    assert decoded_datetime == datetime_str

    # Test list with mixed types
    mixed_list = [
        {"__type__": "datetime", "iso": "2023-06-15T10:30:00"},
        42,
        "plain string",
    ]
    decoded_list = TypePreservationDecoder.decode(mixed_list)
    assert len(decoded_list) == 3
    assert isinstance(decoded_list[0], datetime)
    assert decoded_list[1] == 42
    assert decoded_list[2] == "plain string"
