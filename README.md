# Compressed FHIR

A Python library for storing FHIR JSON resources in a compressed form in memory, optimizing memory usage while maintaining fast access to FHIR data.

## Overview

Compressed FHIR is a specialized library that provides efficient memory storage for FHIR (Fast Healthcare Interoperability Resources) JSON resources. It uses zlib or msgpack for compression while ensuring quick access to the stored healthcare data.

## Features

- Efficient memory storage of FHIR resources
- Fast access to compressed FHIR data
- Compatible with standard FHIR JSON formats
- Minimal memory footprint

## Installation

You can install the package using pip:

```bash
pip install compressedfhir
```

Or using uv:

```bash
uv add compressedfhir
```

## Requirements

See [pyproject.toml](pyproject.toml) for the supported Python versions and dependencies.

## Usage

```python
from typing import Any

from compressedfhir.fhir.fhir_resource import FhirResource
from compressedfhir.utilities.compressed_dict.v1.compressed_dict_storage_mode import CompressedDictStorageMode


resource1 = FhirResource(
    initial_dict={"resourceType": "Observation", "id": "456"},
    storage_mode=CompressedDictStorageMode.default(),
)

my_dict: dict[str, Any] = resource1.dict()  # plain nested dicts (fast)
my_plain_dict: dict[str, Any] = resource1.to_plain_dict()
my_json: str = resource1.json()  # compact orjson text (fast)
my_exact_json: str = resource1.json(byte_identical=True)  # exactly the text 4.0.0 and earlier wrote

with resource1.transaction():
   assert "email" not in resource1
   assert resource1.get("name") == "Custom Mode User"
   assert resource1.get("active") is True
```

## Upgrading to 5.0.0

5.0.0 is several times faster than 4.0.0 because JSON is parsed and written with orjson. It changes
the default output of `json()`, so it is a major version:

| Call | 4.0.0 | 5.0.0 default | To keep the 4.0.0 text |
|---|---|---|---|
| `json()` on resources, bundles, bundle entries, resource lists and `FhirResourceMap` | stdlib text (`", "` separators, `\uXXXX` escapes, `1e-07`) | compact orjson text (raw UTF-8, `1e-7`) | `json(byte_identical=True)` |
| `FhirClientJsonHelpers.convert_dict_to_fhir_json()` | the same stdlib text | compact orjson text | `byte_identical=True` |

`dict()` already returns plain nested dicts since 4.0.0 and still does.

Details:

- The JSON is equivalent for any parser.
- **NaN and Infinity** cannot be written in FHIR JSON, so `dict()` and `json()` now omit them, and
  compressed storage records them as `null` when the resource is built (`raw_dict()` returns `None`
  for them). `json(byte_identical=True)` still writes a NaN held in raw storage as `NaN`, but a
  compressed resource no longer has it.
- A plain `Enum` or a `UUID` inside a resource is now accepted and stored as its value or string
  (it raised `TypeError` before).
- `convert_dict_to_fhir_json()` also writes a plain `Enum` as its value (it wrote `str(enum)`), a
  dataclass as a dict (it wrote its `repr`), and NaN as `null`.
- Integers beyond 64 bits and non-string keys still work and stay exact: they fall back to the
  standard library.
- Reading stored data rebuilds only the built-in types (datetime, date, time, Decimal, bytes, set,
  complex) and decoders you pass through `custom_decoders`. A custom object stored in a resource
  (written with its class name and attributes) reads back as that plain dict, and no module is
  imported while reading.
- Stored data: new compressed blobs start with one space, which JSON parsers ignore, so 4.0.0 can
  still read them, and blobs written by older versions still load.
- Upgrading from 3.x: 4.0.0 already changed `dict()` and `raw_dict()` to plain dicts instead of
  `OrderedDict`, removed the `OrderedDict`-specific helper functions, and made `CompressedDict`
  equality ignore key order at every level.

The reasoning and the alternatives are in `adrs/0002-faster-json-with-orjson.md`.

## Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/icanbwell/compressed-fhir.git
   cd compressed-fhir
   ```

2. Install dependencies using [uv](https://docs.astral.sh/uv/):
   ```bash
   uv sync --group dev
   ```

3. Set up pre-commit hooks:
   ```bash
   pre-commit install
   ```

## Docker Support

The project includes Docker support for development and deployment:

```bash
# Build the Docker image
docker build -t compressed-fhir .

# Run using docker-compose
docker-compose up
```

## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Authors

- Imran Qureshi (imran.qureshi@icanbwell.com)

## Support

For support, please open an issue in the GitHub repository or contact the maintainers.

## Project Status

Current status: Beta

The project is under active development. Please check the GitHub repository for the latest updates and changes.
