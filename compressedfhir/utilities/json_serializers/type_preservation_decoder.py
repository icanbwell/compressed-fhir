from datetime import datetime, date
from decimal import Decimal
from typing import Any, Dict, Callable


class TypePreservationDecoder:
    """
    Advanced JSON decoder for complex type reconstruction
    """

    @classmethod
    def decode(
        cls,
        dct: Dict[str, Any],
        custom_decoders: Dict[str, Callable[[Any], Any]] | None = None,
    ) -> Any:
        """
        Decode complex types

        Args:
            dct: Dictionary to decode
            custom_decoders: Optional additional custom decoders

        Returns:
            Reconstructed object or original dictionary
        """
        # Default decoders for built-in types
        default_decoders: Dict[str, Callable[[Any], Any]] = {
            "datetime": lambda d: datetime.fromisoformat(d["iso"]),
            "date": lambda d: date.fromisoformat(d["iso"]),
            "decimal": lambda d: Decimal(d["value"]),
            "complex": lambda d: complex(d["real"], d["imag"]),
            "bytes": lambda d: d["value"].encode("latin-1"),
            "set": lambda d: set(d["values"]),
        }

        # Merge custom decoders with default decoders
        decoders = {**default_decoders, **(custom_decoders or {})}

        # Check for type marker
        if "__type__" in dct:
            type_name = dct["__type__"]

            # Handle built-in type decoders
            if type_name in decoders:
                return decoders[type_name](dct)

            # Handle custom object reconstruction
            if "__module__" in dct and "attributes" in dct:
                try:
                    # Dynamically import the class
                    module = __import__(dct["__module__"], fromlist=[type_name])
                    cls_ = getattr(module, type_name)

                    # Create instance and set attributes
                    obj = cls_.__new__(cls_)
                    obj.__dict__.update(dct["attributes"])
                    return obj
                except (ImportError, AttributeError) as e:
                    print(f"Could not reconstruct {type_name}: {e}")
                    return dct

        return dct
