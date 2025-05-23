from datetime import datetime
from typing import Any, Dict, Optional, OrderedDict

from compressedfhir.utilities.json_helpers import FhirClientJsonHelpers


class FhirBundleEntryRequest:
    """
    FHIR Bundle Entry Request class for encapsulating the request to be sent to FHIR server
    """

    __slots__ = ["url", "method", "ifModifiedSince", "ifNoneMatch", "ifNoneExist"]

    # noinspection PyPep8Naming
    def __init__(
        self,
        *,
        url: str,
        method: str = "GET",
        ifNoneMatch: Optional[str] = None,
        ifModifiedSince: Optional[datetime] = None,
        ifNoneExist: Optional[str] = None,
    ) -> None:
        self.url: str = url or "https://example.com"
        self.method: str = method or "GET"
        self.ifModifiedSince: Optional[datetime] = ifModifiedSince
        self.ifNoneMatch: Optional[str] = ifNoneMatch
        self.ifNoneExist: Optional[str] = ifNoneExist

    def dict(self) -> OrderedDict[str, Any]:
        result: OrderedDict[str, Any] = OrderedDict[str, Any](
            {"url": self.url, "method": self.method}
        )
        if self.ifModifiedSince is not None:
            result["ifModifiedSince"] = self.ifModifiedSince.isoformat()
        if self.ifNoneMatch is not None:
            result["ifNoneMatch"] = self.ifNoneMatch
        if self.ifNoneExist is not None:
            result["ifNoneExist"] = self.ifNoneExist
        return FhirClientJsonHelpers.remove_empty_elements_from_ordered_dict(result)

    @classmethod
    def from_dict(
        cls, d: Dict[str, Any] | OrderedDict[str, Any]
    ) -> "FhirBundleEntryRequest":
        date_if_modified_since: Optional[datetime] = None
        if "ifModifiedSince" in d:
            if isinstance(d["ifModifiedSince"], datetime):
                date_if_modified_since = d["ifModifiedSince"]
            elif isinstance(d["ifModifiedSince"], str):
                date_if_modified_since = datetime.fromisoformat(d["ifModifiedSince"])
        return cls(
            url=d.get("url", "https://example.com"),
            method=d.get("method", "GET"),
            ifModifiedSince=date_if_modified_since,
            ifNoneMatch=d["ifNoneMatch"] if "ifNoneMatch" in d else None,
            ifNoneExist=d["ifNoneExist"] if "ifNoneExist" in d else None,
        )

    def __deepcopy__(self, memo: Dict[int, Any]) -> "FhirBundleEntryRequest":
        return FhirBundleEntryRequest(
            url=self.url,
            method=self.method,
            ifModifiedSince=self.ifModifiedSince,
            ifNoneMatch=self.ifNoneMatch,
            ifNoneExist=self.ifNoneExist,
        )

    def __repr__(self) -> str:
        return (
            f"FhirBundleEntryRequest(url={self.url}, method={self.method}, "
            f"ifModifiedSince={self.ifModifiedSince}, ifNoneMatch={self.ifNoneMatch})"
        )
