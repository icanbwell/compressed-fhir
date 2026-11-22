import json
import logging
import math
from decimal import Decimal
from typing import Any, Dict, List, Union, Optional, overload
from datetime import datetime, date

import orjson

logger = logging.getLogger(__name__)


def _is_non_finite(x: Any) -> bool:
    """True for NaN and +/-Infinity, as float or Decimal."""
    if type(x) is float:
        return not math.isfinite(x)
    if isinstance(x, Decimal):
        return not x.is_finite()
    return False


def _is_empty(x: Any) -> bool:
    """True for None, an empty list, an empty dict, or a blank string."""
    if x is None:
        return True
    if isinstance(x, str):
        return x.strip() == ""
    if isinstance(x, (list, dict)):
        return len(x) == 0
    return bool(x == [] or x == {})


class FhirClientJsonHelpers:
    def __init__(self) -> None:
        pass

    @staticmethod
    def json_serial(obj: Any) -> str:
        """JSON serializer for objects not serializable by default json code"""

        # https://stackoverflow.com/questions/11875770/how-to-overcome-datetime-datetime-not-json-serializable
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return str(obj)

    @overload
    @staticmethod
    def remove_empty_elements(
        d: Dict[str, Any],
        skip_keys: frozenset[str] = frozenset(),
        drop_non_finite: bool = False,
    ) -> Dict[str, Any]: ...

    @overload
    @staticmethod
    def remove_empty_elements(
        d: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]: ...

    @staticmethod
    def remove_empty_elements(
        d: List[Dict[str, Any]] | Dict[str, Any],
        skip_keys: frozenset[str] = frozenset(),
        drop_non_finite: bool = False,
    ) -> List[Dict[str, Any]] | Dict[str, Any]:
        """
        Recursively remove empty lists, empty dicts, or None elements from a dictionary
        or a list of dictionaries
        :param d: dictionary or list of dictionaries
        :param skip_keys: top-level keys whose values the caller has already pruned; they are
                          kept as-is (still dropped if empty) instead of being walked again
        :param drop_non_finite: also drop NaN/Infinity floats and Decimals, which FHIR JSON
                                cannot hold (the default json()/dict() output omits them)
        :return: dictionary or list of dictionaries
        """

        # int/float/bool can never be empty, so they skip the equality checks below
        scalar_types = (int, float, bool)

        def prune_list(items: List[Any]) -> List[Any]:
            kept: List[Any] = []
            for v in items:
                if v is None:
                    continue
                if isinstance(v, dict):
                    v = prune_dict(v)
                elif isinstance(v, list):
                    v = prune_list(v)
                elif type(v) in scalar_types:
                    if drop_non_finite and _is_non_finite(v):
                        continue
                    kept.append(v)
                    continue
                elif drop_non_finite and _is_non_finite(v):
                    continue
                if not _is_empty(v):
                    kept.append(v)
            return kept

        def prune_dict(
            items: Dict[str, Any], skip: frozenset[str] = frozenset()
        ) -> Dict[str, Any]:
            kept: Dict[str, Any] = {}
            for k, v in items.items():
                if v is None:
                    continue
                if k in skip:
                    pass
                elif isinstance(v, dict):
                    v = prune_dict(v)
                elif isinstance(v, list):
                    v = prune_list(v)
                elif type(v) in scalar_types:
                    if drop_non_finite and _is_non_finite(v):
                        continue
                    kept[k] = v
                    continue
                elif drop_non_finite and _is_non_finite(v):
                    continue
                if not _is_empty(v):
                    kept[k] = v
            return kept

        if isinstance(d, list):
            return prune_list(d)
        if isinstance(d, dict):
            return prune_dict(d, skip_keys)
        return d

    @staticmethod
    def convert_dict_to_fhir_json(
        dict_: Dict[str, Any], *, byte_identical: bool = False
    ) -> str:
        """
        Returns dictionary as JSON string

        :param dict_: the dictionary; empty elements are removed first
        :param byte_identical: False (default) writes compact orjson text.  Inputs orjson
            writes natively differ from the exact text: a plain Enum is written as its value
            (not str(enum)), a dataclass as a dict (not its repr), NaN/Infinity as null.
            Anything orjson raises on falls back to the standard library.  True writes
            exactly the text json.dumps with json_serial wrote in 4.0.0 and earlier.
        :return: JSON text
        """
        instance_variables: Dict[str, Any] = (
            FhirClientJsonHelpers.remove_empty_elements(dict_)
        )
        if not byte_identical:
            try:
                return orjson.dumps(
                    instance_variables, default=FhirClientJsonHelpers.json_serial
                ).decode()
            except TypeError as e:  # orjson.JSONEncodeError subclasses TypeError
                logger.debug(
                    "convert_dict_to_fhir_json fell back to the standard library: %s", e
                )
        instance_variables_text: str = json.dumps(
            instance_variables, default=FhirClientJsonHelpers.json_serial
        )
        return instance_variables_text

    @staticmethod
    def orjson_dumps(
        obj: Any, indent: Optional[int] = None, sort_keys: bool = False
    ) -> str:
        """
        Wrapper for orjson.dumps() to mimic json.dumps() behavior

        Args:
            obj: Object to serialize
            indent: Optional indentation (note: orjson has limited indent support)
            sort_keys: Whether to sort dictionary keys

        Returns:
            JSON string
        """
        # Serialization options
        options = 0

        # Handle sorting keys
        if sort_keys:
            options |= orjson.OPT_SORT_KEYS

        # Handle indentation (limited support)
        if indent is not None:
            options |= orjson.OPT_INDENT_2  # Fixed indentation

        # Serialize to bytes
        json_bytes = orjson.dumps(obj, option=options)

        # Convert bytes to string
        return json_bytes.decode("utf-8")

    @staticmethod
    def orjson_loads(json_input: Union[str, bytes]) -> Any:
        """
        Safely load JSON with type flexibility
        """
        try:
            # Converts input to the appropriate type if needed
            if isinstance(json_input, str):
                json_input = json_input.encode("utf-8")

            return orjson.loads(json_input)
        except (orjson.JSONDecodeError, TypeError) as e:
            print(f"JSON Parsing Error: {e}")
            return None
