# Changelog

## v1.1.0

- Added `slice-bins` to remove final depth cells from every ensemble in a proven standard PD0 profile layout.
- The command derives depth-cell count, beam/component count, cell size, data-block layout, offsets, and lengths directly from the source file.
- It trims Velocity, Correlation Magnitude, Echo Intensity, and Percent Good; preserves non-bin-dependent blocks; updates the Fixed Leader cell count, offsets, ensemble byte count, and checksum; then validates the complete output before publication.
- It fails closed for unparsed bytes, invalid checksums, inconsistent configurations or layouts, unsupported blocks, and unexpected bin-dependent block sizes.
- Validated on `test_data/stnr0877/stnr0877_LADCPM.000`: 4,520 ensembles, 30 cells at 8.00 m, `--last 15`, 15 resulting cells, 120 m nominal removed outer range, and 841-to-541 byte ensembles. The generated file was processed successfully by the normal downstream workflow.

## v1.0.5

- Added `slice` for explicit removal of complete PD0 ensembles by physical file order.
- Supports mutually exclusive `--first`, `--last`, and inclusive `--range A:B` selection modes, plus `--dry-run`.
- Fails closed when the source contains unparsed/non-ensemble bytes, so slicing cannot silently discard malformed trailing data.
- Copies retained ensembles byte-for-byte without regenerating checksums, then reparses and byte-compares the output before publication.
- Validated by the 28-test suite and on `test_data/stnr0877/stnr0877_LADCPM.000`: 4,520 complete input ensembles, physical ensembles 4,506-4,520 removed, 4,505 retained, no unparsed bytes, valid checksums, and exact retained-byte matching.
- Slice does not automatically identify false bottoms or bad measurements, and it does not remove depth cells/bins.
