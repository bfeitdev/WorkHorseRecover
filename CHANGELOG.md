# Changelog

## v1.0.5

- Added `slice` for explicit removal of complete PD0 ensembles by physical file order.
- Supports mutually exclusive `--first`, `--last`, and inclusive `--range A:B` selection modes, plus `--dry-run`.
- Fails closed when the source contains unparsed/non-ensemble bytes, so slicing cannot silently discard malformed trailing data.
- Copies retained ensembles byte-for-byte without regenerating checksums, then reparses and byte-compares the output before publication.
- Validated by the 28-test suite and on `test_data/stnr0877/stnr0877_LADCPM.000`: 4,520 complete input ensembles, physical ensembles 4,506-4,520 removed, 4,505 retained, no unparsed bytes, valid checksums, and exact retained-byte matching.
- Slice does not automatically identify false bottoms or bad measurements, and it does not remove depth cells/bins.
