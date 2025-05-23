from datetime import datetime, timezone

from compressedfhir.fhir.fhir_bundle_entry import FhirBundleEntry
from compressedfhir.fhir.fhir_bundle_entry_request import FhirBundleEntryRequest
from compressedfhir.fhir.fhir_bundle_entry_response import (
    FhirBundleEntryResponse,
)
from compressedfhir.utilities.compressed_dict.v1.compressed_dict_storage_mode import (
    CompressedDictStorageMode,
)


class TestBundleEntry:
    def test_init_minimal(self) -> None:
        """Test initialization with minimal parameters."""
        entry = FhirBundleEntry(
            resource={"resourceType": "Patient"},
            request=None,
            response=None,
            storage_mode=CompressedDictStorageMode(),
        )
        assert entry.resource is not None
        with entry.resource.transaction():
            assert entry.resource.dict() == {"resourceType": "Patient"}
            assert entry.request is None
            assert entry.response is None
            assert entry.fullUrl is None

    def test_init_full(self) -> None:
        """Test initialization with all parameters."""
        resource = {"resourceType": "Patient", "id": "123"}
        request = FhirBundleEntryRequest(url="https://example.com")
        response = FhirBundleEntryResponse(status="200", etag=None, lastModified=None)

        entry = FhirBundleEntry(
            resource=resource,
            request=request,
            response=response,
            fullUrl="https://example.com/Patient/123",
            storage_mode=CompressedDictStorageMode(),
        )
        assert entry.resource is not None
        with entry.resource.transaction():
            assert entry.resource.dict() == resource
            assert entry.request == request
            assert entry.response == response
            assert entry.fullUrl == "https://example.com/Patient/123"

    def test_to_dict_minimal(self) -> None:
        """Test converting to dictionary with minimal parameters."""
        entry = FhirBundleEntry(
            resource={"resourceType": "Patient"},
            request=None,
            response=None,
            storage_mode=CompressedDictStorageMode(),
        )
        result = entry.dict()
        assert result == {"resource": {"resourceType": "Patient"}}

    def test_to_dict_full(self) -> None:
        """Test converting to dictionary with all parameters."""
        resource = {"resourceType": "Patient", "id": "123"}
        request = FhirBundleEntryRequest(url="https://example.com")
        response = FhirBundleEntryResponse(status="200", etag=None, lastModified=None)

        entry = FhirBundleEntry(
            resource=resource,
            request=request,
            response=response,
            fullUrl="https://example.com/Patient/123",
            storage_mode=CompressedDictStorageMode(),
        )
        result = entry.dict()
        assert result == {
            "fullUrl": "https://example.com/Patient/123",
            "resource": resource,
            "request": request.dict(),
            "response": response.dict(),
        }

    def test_from_dict_minimal(self) -> None:
        """Test creating from dictionary with minimal parameters."""
        data = {"resource": {"resourceType": "Patient"}}
        entry = FhirBundleEntry.from_dict(
            data, storage_mode=CompressedDictStorageMode()
        )

        assert entry.resource is not None
        with entry.resource.transaction():
            assert entry.resource.dict() == {"resourceType": "Patient"}
            assert entry.request is None
            assert entry.response is None
            assert entry.fullUrl is None

    def test_from_dict_full(self) -> None:
        """Test creating from dictionary with all parameters."""
        now = datetime.now(timezone.utc)
        data = {
            "fullUrl": "https://example.com/Patient/123",
            "resource": {"resourceType": "Patient", "id": "123"},
            "request": {"url": "https://example.com", "method": "GET"},
            "response": {
                "status": "200",
                "lastModified": now.isoformat(),
                "etag": 'W/"abc"',
            },
        }
        entry = FhirBundleEntry.from_dict(
            data, storage_mode=CompressedDictStorageMode()
        )
        assert entry.resource is not None
        with entry.resource.transaction():
            assert entry.fullUrl == "https://example.com/Patient/123"
            assert entry.resource.dict() == {"resourceType": "Patient", "id": "123"}
            assert entry.request is not None
            assert entry.request.url == "https://example.com"
            assert entry.response is not None
            assert entry.response.status == "200"

    def test_repr(self) -> None:
        """Test string representation of BundleEntry."""
        resource = {"resourceType": "Patient", "id": "123"}
        entry = FhirBundleEntry(
            resource=resource,
            request=None,
            response=None,
            storage_mode=CompressedDictStorageMode(),
        )
        assert repr(entry) == "BundleEntry(Patient/123)"
