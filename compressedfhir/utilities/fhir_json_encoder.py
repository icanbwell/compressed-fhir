import dataclasses
import json
import logging
import uuid
from datetime import datetime, date, time
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import orjson

# Optional: Import for additional type support
try:
    import ipaddress
except ImportError:
    ipaddress = None  # type:ignore[assignment]


logger = logging.getLogger(__name__)


class FhirJSONEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        # Existing type handlers
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)  # type:ignore[arg-type]

        if isinstance(o, Enum):
            return o.value

        if isinstance(o, Decimal):
            # Custom Decimal conversion
            if o == o.to_integral_value():
                return int(o)
            else:
                return float(o)

        if isinstance(o, bytes):
            return o.decode("utf-8")

        if isinstance(o, (datetime, date)):
            return o.isoformat()

        if isinstance(o, time):
            return o.isoformat()

        if hasattr(o, "to_dict"):
            return o.to_dict()

        # New type handlers

        # UUID handling
        if isinstance(o, uuid.UUID):
            return str(o)

        # Set and frozenset handling
        if isinstance(o, (set, frozenset)):
            return list(o)

        # Complex number handling
        if isinstance(o, complex):
            return {"real": o.real, "imag": o.imag}

        # Path-like objects
        if isinstance(o, (Path, Path)):
            return str(o)

        # IP Address handling (if ipaddress module is available)
        if ipaddress and isinstance(o, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
            return str(o)

        # Custom object serialization fallback
        if hasattr(o, "__dict__"):
            return o.__dict__

        return super().default(o)


# Reused by the orjson paths so they apply exactly the same type conversions as FhirJSONEncoder
FHIR_JSON_ENCODER = FhirJSONEncoder()


def dumps_orjson(obj: Any) -> str:
    """
    Fast JSON text for FHIR data.  NOT byte-identical to json.dumps(cls=FhirJSONEncoder):
    output is compact, non-ASCII is written as UTF-8, exponents print as 1e-7, and NaN/Infinity
    become null.  Payloads orjson cannot encode (integers beyond 64 bits, non-string keys)
    fall back to the standard library, so those stay exact.
    """
    try:
        return orjson.dumps(
            obj,
            default=FHIR_JSON_ENCODER.default,
            # route datetime/date/time through FhirJSONEncoder for identical values
            option=orjson.OPT_PASSTHROUGH_DATETIME,
        ).decode()
    except TypeError as e:  # orjson.JSONEncodeError subclasses TypeError
        logger.debug("dumps_orjson fell back to the standard library: %s", e)
        return json.dumps(obj, cls=FhirJSONEncoder)


def render_json(
    *,
    byte_identical: bool,
    exact: Callable[[], Any],
    fast: Callable[[], Any],
) -> str:
    """
    The one place that decides how a json() method writes its text.

    byte_identical=True writes exactly what json.dumps(cls=FhirJSONEncoder) always wrote, from
    the object `exact` returns.  False writes compact orjson text from the object `fast` returns.
    """
    if byte_identical:
        return json.dumps(exact(), cls=FhirJSONEncoder)
    return dumps_orjson(fast())
