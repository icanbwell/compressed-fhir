import logging
from collections import OrderedDict
from datetime import datetime, timezone, date
from decimal import Decimal
from logging import Logger
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


def test_nested_dict() -> None:
    """
    Test serialization of nested dictionaries
    """
    logger: Logger = logging.getLogger(__name__)
    nested_dict = {
        "resourceType": "Coverage",
        "id": "3456789012345670304",
        "beneficiary": {"reference": "Patient/1234567890123456703", "type": "Patient"},
        "class": [
            {
                "name": "Aetna Plan",
                "type": {
                    "coding": [
                        {
                            "code": "plan",
                            "display": "Plan",
                            "system": "http://terminology.hl7.org/CodeSystem/coverage-class",
                        }
                    ]
                },
                "value": "AE303",
            }
        ],
        "costToBeneficiary": [
            {
                "type": {"text": "Annual Physical Exams NMC - In Network"},
                "valueQuantity": {
                    "system": "http://aetna.com/Medicare/CostToBeneficiary/ValueQuantity/code",
                    "unit": "$",
                    "value": 50.0,
                },
            }
        ],
        "identifier": [
            {
                "system": "https://sources.aetna.com/coverage/identifier/membershipid/59",
                "type": {
                    "coding": [
                        {
                            "code": "SN",
                            "system": "http://terminology.hl7.org/CodeSystem/v2-0203",
                        }
                    ]
                },
                "value": "435679010300+AE303+2021-01-01",
            },
            {
                "id": "uuid",
                "system": "https://www.icanbwell.com/uuid",
                "value": "92266603-aa8b-58c6-99bd-326fd1da1896",
            },
        ],
        "meta": {
            "security": [
                {"code": "aetna", "system": "https://www.icanbwell.com/owner"},
                {"code": "aetna", "system": "https://www.icanbwell.com/access"},
                {"code": "aetna", "system": "https://www.icanbwell.com/vendor"},
                {"code": "proa", "system": "https://www.icanbwell.com/connectionType"},
            ],
            "source": "http://mock-server:1080/test_patient_access_transformer/source/4_0_0/Coverage/3456789012345670304",
        },
        "network": "Medicare - MA/NY/NJ - Full Reciprocity",
        "payor": [
            {
                "display": "Aetna",
                "reference": "Organization/6667778889990000015",
                "type": "Organization",
            }
        ],
        "period": {
            "end": datetime.fromisoformat("2021-12-31").date(),
            "start": datetime.fromisoformat("2021-01-01").date(),
        },
        "policyHolder": {"reference": "Patient/1234567890123456703", "type": "Patient"},
        "relationship": {
            "coding": [
                {
                    "code": "self",
                    "system": "http://terminology.hl7.org/CodeSystem/subscriber-relationship",
                }
            ]
        },
        "status": "active",
        "subscriber": {"reference": "Patient/1234567890123456703", "type": "Patient"},
        "subscriberId": "435679010300",
        "type": {
            "coding": [
                {
                    "code": "PPO",
                    "display": "preferred provider organization policy",
                    "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                }
            ]
        },
    }

    logger.info("-------- Serialized --------")
    serialized: str = TypePreservationSerializer.serialize(nested_dict)
    logger.info(serialized)
    logger.info("-------- Deserialized --------")
    deserialized: OrderedDict[str, Any] = TypePreservationSerializer.deserialize(
        serialized
    )
    logger.info(deserialized)

    assert isinstance(deserialized, OrderedDict)

    assert isinstance(deserialized["period"]["start"], date)
    assert isinstance(deserialized["period"]["end"], date)
    assert nested_dict == deserialized
