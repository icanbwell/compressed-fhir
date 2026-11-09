import collections
import json
from typing import Any, Dict, List, cast, Union, Optional, OrderedDict, overload
from datetime import datetime, date

import orjson


def _is_empty(x: Any) -> bool:
    """True for None, an empty list, an empty dict, or a blank string."""
    if x is None:
        return True
    if isinstance(x, str):
        return x.strip() == ""
    if isinstance(x, (list, dict)):
        return len(x) == 0
    return bool(x == [] or x == {})


def _remove_empty_elements_ordered(d: Any) -> Any:
    # Called for every value in a resource, so it checks against the builtin dict/list.
    # isinstance against typing.Dict / typing.OrderedDict goes through typing's slow
    # __instancecheck__ and dominated the cost of FhirResource.json().
    if isinstance(d, dict):
        result: OrderedDict[str, Any] = collections.OrderedDict()
        for k, v in d.items():
            v = _remove_empty_elements_ordered(v)
            if not _is_empty(v):
                result[k] = v
        return result
    if isinstance(d, list):
        stripped = (_remove_empty_elements_ordered(v) for v in d)
        return [v for v in stripped if not _is_empty(v)]
    return d


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

    @staticmethod
    def remove_empty_elements(
        d: List[Dict[str, Any]] | Dict[str, Any],
    ) -> List[Dict[str, Any]] | Dict[str, Any]:
        """
        Recursively remove empty lists, empty dicts, or None elements from a dictionary
        or a list of dictionaries
        :param d: dictionary or list of dictionaries
        :return: dictionary or list of dictionaries
        """

        def empty(x: Any) -> bool:
            # Check if the input is None, an empty list, an empty dict, or an empty string
            return (
                x is None
                or x == []
                or x == {}
                or (isinstance(x, str) and x.strip() == "")
            )

        if not isinstance(d, (dict, list)):
            return d
        elif isinstance(d, list):
            return [
                cast(Dict[str, Any], v)
                for v in (FhirClientJsonHelpers.remove_empty_elements(v) for v in d)
                if not empty(v)
            ]
        else:
            return {
                k: v
                for k, v in (
                    (k, FhirClientJsonHelpers.remove_empty_elements(v))
                    for k, v in d.items()
                )
                if not empty(v)
            }

    @staticmethod
    @overload
    def remove_empty_elements_from_ordered_dict(
        d: List[OrderedDict[str, Any]],
    ) -> List[OrderedDict[str, Any]]: ...

    @staticmethod
    @overload
    def remove_empty_elements_from_ordered_dict(
        d: OrderedDict[str, Any],
    ) -> OrderedDict[str, Any]: ...

    @staticmethod
    def remove_empty_elements_from_ordered_dict(
        d: List[OrderedDict[str, Any]] | OrderedDict[str, Any],
    ) -> List[OrderedDict[str, Any]] | OrderedDict[str, Any]:
        """
        Recursively remove empty lists, empty dicts, or None elements from a dictionary
        or a list of dictionaries. Dictionaries are returned as OrderedDicts in the same key order.
        :param d: dictionary or list of dictionaries
        :return: dictionary or list of dictionaries
        """
        return cast(
            List[OrderedDict[str, Any]] | OrderedDict[str, Any],
            _remove_empty_elements_ordered(d),
        )

    @staticmethod
    def convert_dict_to_fhir_json(dict_: Dict[str, Any]) -> str:
        """
        Returns dictionary as json string


        :return:
        """
        instance_variables: Dict[str, Any] = cast(
            Dict[str, Any], FhirClientJsonHelpers.remove_empty_elements(dict_)
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
            # Converts input to appropriate type if needed
            if isinstance(json_input, str):
                json_input = json_input.encode("utf-8")

            return orjson.loads(json_input)
        except (orjson.JSONDecodeError, TypeError) as e:
            print(f"JSON Parsing Error: {e}")
            return None
