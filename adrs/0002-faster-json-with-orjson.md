# Use orjson for stored, parsed and written JSON, with compact text by default (5.0.0)

* Status: accepted
* Deciders: Imran Qureshi
* Date: 2026-11-21
* Jira: BAI-1955

## Context and Problem Statement

`FhirBundle.dict()` on about 1,000 ExplanationOfBenefit resources took 12.1 s in a production
service that uses this package. Every step was pure Python or the standard library `json`, which holds
the GIL, so the asyncio loop was starved for the whole call. Profiling found that each resource's
stored JSON was decoded twice, the decode hook re-walked subtrees at every object, and empty
elements were pruned three times per resource. On the latest release before this work (4.0.0) a
bundle of 1,000 large resources took about 3.5 s.

## Decision Drivers

* Large speedup on `dict()`, `json()`, construction and `from_json`, without changing what FHIR
  consumers see.
* orjson is already a declared dependency of this package.
* Callers that depend on the exact old text must have a simple way to keep it.
* Changes to default public output are breaking and must be versioned as such.

## Considered Options

1. Keep the standard library and only optimize the Python code (single decode, single prune).
2. Use orjson for parsing and writing, keep the exact stdlib text as the default, orjson text opt-in.
3. Use orjson for parsing and writing, compact orjson text as the default, exact text opt-in.

## Decision Outcome

Chosen option: **3**, released as **5.0.0** because it changes the default `json()` text.

* Option 1 alone gives about 5x; orjson parsing and writing roughly doubles that.
* Option 2 keeps the default text but leaves most callers on the slow path until they edit code.
* `json(byte_identical=True)` and `convert_dict_to_fhir_json(byte_identical=True)` return the exact
  4.0.0 text; this is tested against literal output of the 4.0.0 package.

### Further decisions

* **Stored blobs.** The writer uses orjson and falls back to the standard library for anything
  orjson raises on (integers beyond 64 bits, non-string keys, dataclasses, custom objects,
  non-Enum str/int subclasses, lone surrogates). orjson cannot write an integer beyond 64 bits, so
  blobs it wrote are marked with one leading space and the reader skips the 20-digit guard for
  them. Alternatives: an in-memory flag (8 bytes per object and old pickles lack the attribute) or
  a version prefix (older versions could no longer read the blob). A leading space is ignored by
  JSON parsers; 3.0.6 and 4.0.0 read such blobs.
* **NaN and Infinity.** orjson writes them as `null`. Accepted: they cannot appear in FHIR JSON,
  and `dict()`/`json()` omit them in every storage mode. The exact text path keeps writing a NaN
  held in raw storage as `NaN`. Alternative: keep the standard library writer for storage and
  preserve NaN, rejected because it costs the construction speedup.
* **Reading stored data.** The decoder rebuilds only the built-in types and decoders passed
  explicitly through `custom_decoders`; a custom-object marker reads back as its attributes dict
  (what `dict()` returned for it in 4.0.0) and no module is imported. Alternative: keep rebuilding classes by name, rejected
  because data should not choose what gets instantiated.
* **`dict(ordered=True)`.** Not provided. 4.0.0 already returns plain dicts and nothing found in
  the repositories searched relies on ordered mappings.
* **Fallbacks.** Every fallback to the standard library is silent to callers and logged at debug
  level.

### Consequences

* Good: about 11 to 14x faster `dict()` and `json()` than 4.0.0; about 2x faster resource
  construction; the pruner and decoder do one pass.
* Bad: a custom object stored in a resource reads back as its attributes dict; default `json()` text changes (compact, raw UTF-8, `1e-7`); callers that hash, compare or
  persist the exact text must pass `byte_identical=True`; NaN is silently omitted; a plain `Enum`
  or `UUID` is accepted where it raised before.
* One known kind of downstream coupling: code that estimates a payload size from `json.dumps` text
  and compares it with `len(resource.json())` must pass `byte_identical=True` when it upgrades.

## References

* PR #30 (faster pruner, 3.0.6), PR #16 (plain dicts, 4.0.0), PR #31 (this work).
