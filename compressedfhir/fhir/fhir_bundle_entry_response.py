from datetime import datetime
from typing import Any, Dict, Optional, OrderedDict

from compressedfhir.utilities.json_helpers import FhirClientJsonHelpers


class FhirBundleEntryResponse:
    """
    FHIR Bundle Entry Response class for encapsulating the response from FHIR server when processing bundle entries
    """

    __slots__ = ["status", "lastModified", "etag", "location"]

    # noinspection PyPep8Naming
    def __init__(
        self,
        *,
        status: str = "200",
        etag: Optional[str] = None,
        lastModified: Optional[datetime] = None,
        location: Optional[str] = None,
    ) -> None:
        self.status: str = status or "200"
        if isinstance(status, int):
            self.status = str(status)
        self.lastModified: Optional[datetime] = lastModified
        self.etag: Optional[str] = etag
        self.location: Optional[str] = location

    def dict(self) -> OrderedDict[str, Any]:
        result: OrderedDict[str, Any] = OrderedDict[str, Any]({"status": self.status})
        if self.lastModified is not None:
            result["lastModified"] = self.lastModified.isoformat()
        if self.etag is not None:
            result["etag"] = self.etag
        if self.location is not None:
            result["location"] = self.location
        return FhirClientJsonHelpers.remove_empty_elements_from_ordered_dict(result)

    @classmethod
    def from_dict(
        cls, d: Dict[str, Any] | OrderedDict[str, Any]
    ) -> "FhirBundleEntryResponse":
        date_last_modified: Optional[datetime] = None
        if "lastModified" in d:
            if isinstance(d["lastModified"], datetime):
                date_last_modified = d["lastModified"]
            elif isinstance(d["lastModified"], str):
                date_last_modified = datetime.fromisoformat(d["lastModified"])

        return cls(
            status=d["status"] if "status" in d else "200",
            lastModified=date_last_modified,
            etag=d["etag"] if "etag" in d else None,
            location=d["location"] if "location" in d else None,
        )

    def __deepcopy__(self, memo: Dict[int, Any]) -> "FhirBundleEntryResponse":
        return FhirBundleEntryResponse(
            status=self.status,
            lastModified=self.lastModified,
            etag=self.etag,
            location=self.location,
        )

    def __repr__(self) -> str:
        return f"FhirBundleEntryResponse(status: {self.status}, lastModified: {self.lastModified}, etag: {self.etag})"
