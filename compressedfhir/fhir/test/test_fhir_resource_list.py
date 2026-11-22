import json
from typing import Any, Dict, List
from unittest.mock import Mock

import pytest

from compressedfhir.fhir.fhir_resource import FhirResource
from compressedfhir.fhir.fhir_resource_list import FhirResourceList
from compressedfhir.utilities.fhir_json_encoder import FhirJSONEncoder


class TestFhirResourceList:
    def test_get_resource_type_and_ids(self) -> None:
        # Create mock FhirResource objects
        mock_resources = [
            Mock(resource_type="Patient", id="123"),
            Mock(resource_type="Observation", id="456"),
        ]

        resource_list = FhirResourceList(mock_resources)

        # Check the returned resource type and ids
        expected_result = ["Patient/123", "Observation/456"]
        assert resource_list.get_resource_type_and_ids() == expected_result

    def test_get_operation_outcomes(self) -> None:
        # Create mock FhirResource objects with different resource types
        mock_resources = [
            Mock(resource_type="OperationOutcome", id="err1"),
            Mock(resource_type="Patient", id="123"),
            Mock(resource_type="OperationOutcome", id="err2"),
        ]

        resource_list = FhirResourceList(mock_resources)

        # Get operation outcomes
        operation_outcomes = resource_list.get_operation_outcomes()

        # Check the result
        assert len(operation_outcomes) == 2
        assert all(r.resource_type == "OperationOutcome" for r in operation_outcomes)

    def test_get_resources_except_operation_outcomes(self) -> None:
        # Create mock FhirResource objects with different resource types
        mock_resources = [
            Mock(resource_type="OperationOutcome", id="err1"),
            Mock(resource_type="Patient", id="123"),
            Mock(resource_type="Observation", id="456"),
            Mock(resource_type="OperationOutcome", id="err2"),
        ]

        resource_list = FhirResourceList(mock_resources)

        # Get resources except operation outcomes
        valid_resources = resource_list.get_resources_except_operation_outcomes()

        # Check the result
        assert len(valid_resources) == 2
        assert all(r.resource_type != "OperationOutcome" for r in valid_resources)

    def test_remove_duplicates(self) -> None:
        # Create mock FhirResource objects with duplicates
        mock_resources = [
            Mock(resource_type="Patient", id="123", resource_type_and_id="Patient/123"),
            Mock(resource_type="Patient", id="123", resource_type_and_id="Patient/123"),
            Mock(
                resource_type="Observation",
                id="456",
                resource_type_and_id="Observation/456",
            ),
            Mock(resource_type="Patient", id="789", resource_type_and_id="Patient/789"),
        ]

        resource_list = FhirResourceList(mock_resources)

        # Remove duplicates
        resource_list.remove_duplicates()

        # Check the result
        assert len(resource_list) == 3
        assert len(set(r.resource_type_and_id for r in resource_list)) == 3

    def test_to_json(self) -> None:
        # Arrange
        resource_list = FhirResourceList(
            [
                FhirResource.from_dict({"id": "123", "resourceType": "Patient"}),
                FhirResource.from_dict(
                    {"id": "456", "resourceType": "Observation", "note": []}
                ),
            ]
        )

        # Act
        json_str = resource_list.json()

        # Assert
        assert json_str == (
            '[{"id": "123", "resourceType": "Patient"},'
            ' {"id": "456", "resourceType": "Observation"}]'
        )
        assert json.loads(json_str)[1]["resourceType"] == "Observation"

    @pytest.mark.parametrize(
        "resources",
        [
            [],
            [{"resourceType": "Patient", "id": "p1", "name": [{"given": ["Ann"]}]}],
            [
                {
                    "resourceType": "Observation",
                    "id": "o1",
                    "valueQuantity": {"value": 1.10},
                },
                {
                    "resourceType": "Observation",
                    "id": "o2",
                    "code": {"text": "Glucosé — 血糖"},
                },
                {
                    "resourceType": "Observation",
                    "id": "o3",
                    "extension": [],
                    "status": "",
                },
            ],
        ],
        ids=["empty", "single", "floats-non-ascii-and-empties"],
    )
    def test_to_json_matches_serializing_each_resource_dict(
        self, resources: List[Dict[str, Any]]
    ) -> None:
        # Arrange
        resource_list = FhirResourceList([FhirResource.from_dict(r) for r in resources])

        # Act
        json_str = resource_list.json()

        # Assert: identical to the previous json.dumps([r.dict() for r in self]) output
        assert json_str == json.dumps(
            [r.dict() for r in resource_list], cls=FhirJSONEncoder
        )

    @pytest.mark.asyncio
    async def test_consume_resource_async_default(self) -> None:
        # Create mock FhirResource objects
        mock_resources = [
            Mock(resource_type="Patient", id="123"),
            Mock(resource_type="Observation", id="456"),
        ]

        resource_list = FhirResourceList(mock_resources)

        # Consume resources asynchronously with default (None) batch size
        async for batch in resource_list.consume_resource_batch_async(batch_size=None):
            assert len(batch) == 2

        # Ensure all resources are consumed
        assert len(resource_list) == 0

    @pytest.mark.asyncio
    async def test_consume_resource_async_with_batch_size(self) -> None:
        # Create mock FhirResource objects
        mock_resources = [
            Mock(resource_type="Patient", id="123"),
            Mock(resource_type="Observation", id="456"),
            Mock(resource_type="Condition", id="789"),
        ]

        resource_list = FhirResourceList(mock_resources)

        # Consume resources asynchronously with batch size of 2
        batches = []
        async for batch in resource_list.consume_resource_batch_async(batch_size=2):
            batches.append(batch)

        # Check batches
        assert len(batches) == 2
        assert len(batches[0]) == 2
        assert len(batches[1]) == 1

        # Ensure all resources are consumed
        assert len(resource_list) == 0

    def test_consume_resource_async_invalid_batch_size(self) -> None:
        resource_list = FhirResourceList()

        # Test invalid batch sizes
        with pytest.raises(ValueError, match="Batch size must be greater than 0."):

            async def test() -> None:
                async for _ in resource_list.consume_resource_batch_async(batch_size=0):
                    pass

            # Run the async function
            import asyncio

            asyncio.run(test())
