# rdi-recover

`rdi-recover` is a conservative command-line tool for inspecting, recovering, and explicitly slicing complete ensembles from Teledyne RDI WorkHorse PD0 `.000` files.

It is designed to help operators and developers assess split files, overlaps, gaps, truncated fragments, and configuration changes without fabricating measurement content.

It scans PD0 files for structurally valid ensembles, validates stored checksums, preserves original measurement bytes, detects gaps, truncation, and duplicate ensembles, can combine accepted records into a clean recovered output file, and can remove an operator-selected contiguous run of complete ensembles without rewriting retained records. It does not fabricate missing measurements or rewrite invalid measurement data merely to make a file parse.

## Download Standalone Binaries

Prebuilt standalone binaries are available for Windows, Linux, and macOS. Python is not required when using these builds.

Primary download location:

- [GitHub Releases](https://github.com/bfeitdev/WorkHorseRecover/releases/latest)

Development / CI artifacts:

- [GitHub Actions](https://github.com/bfeitdev/WorkHorseRecover/actions)
- [Standalone Binaries workflow](https://github.com/bfeitdev/WorkHorseRecover/actions/workflows/binaries.yml)

GitHub Releases is the primary download location for end users. Published releases include validated standalone binaries for Windows x64, Linux x64, Linux ARM64, macOS ARM64, and macOS x64; GitHub Actions artifacts remain useful for development and CI verification.

Supported standalone downloads:

| Platform | Architecture | Download |
| --- | --- | --- |
| Windows | x64 | [`rdi-recover-windows-x64.zip`](https://github.com/bfeitdev/WorkHorseRecover/releases/latest/download/rdi-recover-windows-x64.zip) |
| Linux | x64 | [`rdi-recover-linux-x64.tar.gz`](https://github.com/bfeitdev/WorkHorseRecover/releases/latest/download/rdi-recover-linux-x64.tar.gz) |
| Linux | ARM64 | [`rdi-recover-linux-arm64.tar.gz`](https://github.com/bfeitdev/WorkHorseRecover/releases/latest/download/rdi-recover-linux-arm64.tar.gz) |
| macOS | Apple Silicon ARM64 | [`rdi-recover-macos-arm64.tar.gz`](https://github.com/bfeitdev/WorkHorseRecover/releases/latest/download/rdi-recover-macos-arm64.tar.gz) |
| macOS | Intel x64 | [`rdi-recover-macos-x64.tar.gz`](https://github.com/bfeitdev/WorkHorseRecover/releases/latest/download/rdi-recover-macos-x64.tar.gz) |

Architecture help:

- Windows: most current Windows PCs use x64.
- Linux: run `uname -m`
- `x86_64` -> `linux-x64`
- `aarch64` -> `linux-arm64`
- macOS: run `uname -m`
- `arm64` -> `macos-arm64` / Apple Silicon
- `x86_64` -> `macos-x64` / Intel

Windows standalone example:

1. Download `rdi-recover-windows-x64.zip`.
2. Extract it.
3. Run:

```powershell
rdi-recover.exe --version
rdi-recover.exe inspect .
rdi-recover.exe recover . --output-dir recovered_output
```

No Python installation is required.

Linux standalone example:

1. Download the correct archive for your architecture.
2. Extract it.
3. Run:

```bash
tar -xzf rdi-recover-linux-x64.tar.gz
chmod +x rdi-recover
./rdi-recover --version
./rdi-recover inspect .
./rdi-recover recover . --output-dir recovered_output
```

For Linux ARM64, extract `rdi-recover-linux-arm64.tar.gz` instead.

macOS standalone example:

1. Download `rdi-recover-macos-arm64.tar.gz` for Apple Silicon or `rdi-recover-macos-x64.tar.gz` for Intel.
2. Extract it.
3. Run:

```bash
tar -xzf rdi-recover-macos-arm64.tar.gz
chmod +x rdi-recover
./rdi-recover --version
./rdi-recover inspect .
./rdi-recover recover . --output-dir recovered_output
```

Security notes:

- Windows executable is currently unsigned. SmartScreen may warn on first launch.
- macOS binaries are currently unsigned and not notarized. Gatekeeper may warn or block first launch.
- Code signing and notarization are planned future distribution improvements.

## Quick Start

Analyze, recover, or explicitly slice complete ensembles:

```bash
rdi-recover inspect .
rdi-recover recover . --output-dir recovered_output
rdi-recover slice deployment.000 --last 15 --output deployment_slice15.000
```

- `inspect` analyzes input without creating recovered PD0 output.
- `recover` creates recovered output using only accepted original records and safely reconstructed records under the existing conservative policy.
- `slice` removes an operator-selected contiguous range of complete ensembles from one file without modifying the input or retained records.

## Recovery Philosophy

`rdi-recover` is intentionally conservative.

- It accepts only complete ensembles that structurally validate.
- It preserves original ensemble bytes and original stored checksums.
- It does not fabricate measurement bytes.
- It does not generate replacement checksums.
- It does not silently merge multiple recursively discovered datasets into one output.
- It withholds recovery output when ambiguity or scientifically meaningful conflict is detected.
- Slice refuses any source with unparsed or non-ensemble bytes, including malformed trailing data, rather than silently dropping those bytes.
- Slice is explicit ensemble removal only. It does not remove depth cells/bins and does not automatically identify false bottoms or bad measurements.

## Python Package Requirements

These requirements apply only to Python-package installation. Standalone binaries do not require Python.

- Python 3.10+
- Windows, macOS, or Linux

## Installation

### Install From Local Source

From the project root:

```bash
python -m pip install .
```

This installs the CLI command:

```bash
rdi-recover --version
```

Expected output:

```text
rdi-recover 1.0.5
```

### Editable Developer Install

```bash
python -m pip install -e .
```

### Windows Example

```powershell
py -3.10 -m pip install .
rdi-recover --help
```

### macOS Example

```bash
python3 -m pip install .
rdi-recover --help
```

### Linux Example

```bash
python3 -m pip install .
rdi-recover --help
```

## CLI Usage

After installation, these entry points are available:

```bash
rdi-recover --help
python -m rdi_recover --help
python -m rdi_recover.rdi_recover --help
```

Examples:

```bash
rdi-recover inspect .
rdi-recover recover . --output-dir recovered
rdi-recover slice deployment.000 --last 15 --output deployment_slice15.000
rdi-recover slice deployment.000 --last 15 --dry-run
rdi-recover slice deployment.000 --first 10 --output deployment_first10_removed.000
rdi-recover slice deployment.000 --range 12000:12020 --output deployment_range_removed.000
python -m rdi_recover slice deployment.000 --last 15 --dry-run
rdi-recover inspect . --recursive
```

Usage model:

- `inspect`: analyzes files without creating recovered PD0 output
- `recover`: creates recovered output from only accepted original records and safely reconstructed records under the existing conservative policy
- `slice`: removes a contiguous selection of complete ensembles from one file without modifying retained ensemble bytes

General forms:

```bash
rdi-recover inspect FILES...
rdi-recover recover FILES... --output-dir recovered_output
rdi-recover slice INPUT.000 (--first N | --last N | --range A:B) --output OUTPUT.000
python -m rdi_recover slice INPUT.000 --last N --output OUTPUT.000
```

## Input Discovery Rules

- Directory scanning is non-recursive by default.
- `--recursive` searches subdirectories for `.000` files.
- Recursive discovery does not silently merge multiple detected datasets into one recovered output.
- When multiple candidate datasets are found, the tool reports them instead of forcing a merge.
- Explicit file arguments are treated as operator-selected input and kept together as one candidate group.
- Automatically generated recovery output directories are excluded from discovery to avoid feeding output back into analysis.

## Commands

### Inspect

Inspect files without writing `recovered.000`:

```bash
rdi-recover inspect DATA_DIR
rdi-recover inspect DATA_DIR --recursive
rdi-recover inspect file1.000 file2.000
```

### Recover

Recover trustworthy complete ensembles into an output directory:

```bash
rdi-recover recover DATA_DIR --output-dir recovered
rdi-recover recover DATA_DIR --output-dir recovered --recursive
rdi-recover recover file1.000 file2.000 --output-dir recovered
```

### Slice

Remove complete ensembles from a single input file while preserving every retained ensemble byte-for-byte:

```bash
rdi-recover slice deployment.000 --last 15 --output deployment_slice15.000
rdi-recover slice deployment.000 --first 10 --output deployment_first10_removed.000
rdi-recover slice deployment.000 --range 12000:12020 --output deployment_range_removed.000
rdi-recover slice deployment.000 --last 15 --dry-run
python -m rdi_recover slice deployment.000 --last 15 --dry-run
```

- `--first`, `--last`, and `--range` are mutually exclusive.
- `--range A:B` is inclusive.
- Slice indexes are physical ensemble order in the input file and are 1-based. They are not the RDI ensemble number stored in an ensemble; that number is reported only for reference.
- The command reports every selected ensemble's byte offsets, RDI ensemble number, and parser/checksum status before writing.
- `--dry-run` performs the same scan and validation without creating an output file.
- Slicing never modifies the input. The output must be a new file: existing output files and input-as-output are refused.
- Retained records are copied byte-for-byte without recalculating checksums or rewriting bytes, then the output is reparsed and compared byte-for-byte with the retained input records before publication.
- If any source bytes are not complete validated ensembles, including malformed or truncated trailing data, they are reported and writing is refused so they cannot be silently dropped.
- Depth-cell/bin removal is not implemented. Slice does not automatically detect false bottoms; it removes only the ensembles explicitly selected by the operator.

## Output Files

When recovery output is allowed, the output directory contains:

- `recovered.000`: recovered complete ensembles only
- `source_inventory.csv`: per-source file inventory
- `boundary_analysis.csv`: file-boundary classification details
- `recovered_gaps.csv`: remaining temporal gaps
- `recovered_ensemble_map.csv`: mapping from output offsets back to source files
- `recovery_manifest.json`: machine-readable recovery summary
- `recovery_report.md`: human-readable recovery report
- `recovered_validation.md`: validation report for `recovered.000`

If manual review is required, report files are still produced, but `recovered.000` is withheld.

## Verdict Semantics

The tool emits one of these final verdicts:

- `PASS`: no gaps, no unrecoverable fragments, no ambiguity, no validation issues
- `PASS_WITH_GAPS`: recovery succeeded, but temporal gaps remain
- `PASS_WITH_UNRECOVERABLE_FRAGMENTS`: recovery succeeded for trustworthy complete ensembles, but truncated or unrecoverable fragments were detected
- `MANUAL_REVIEW_REQUIRED`: ambiguity or conflict was detected, so recovery output is withheld
- `FAIL`: written recovery output did not validate cleanly

## Version

```bash
rdi-recover --version
```

## Testing

Run the test suite with:

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

## Platform Validation

- Supported target operating systems: Windows, macOS, Linux
- Supported Python versions: Python 3.10+
- Source-package CI validation completed for:
  - Linux x64
  - Linux ARM64
  - Windows x64
  - macOS ARM64
  - macOS Intel/x64

Current validation status:

- Source package and installable CLI validated across the supported GitHub-hosted platform matrix.

Standalone binary validation is tracked separately from the Python package. The standalone matrix passed natively on GitHub-hosted runners for Windows x64, Linux x64, Linux ARM64, macOS ARM64, and macOS Intel/x64.

Local Docker validation examples:

```bash
docker run --rm --platform linux/arm64 -v "$PWD:/app" -w /app python:3.13-slim sh -lc 'uname -m && python --version && python -m pip install . && rdi-recover --version && rdi-recover --help >/dev/null && python -m unittest discover -s tests -p "test_*.py"'

docker run --rm --platform linux/amd64 -v "$PWD:/app" -w /app python:3.13-slim sh -lc 'uname -m && python --version && python -m pip install . && rdi-recover --version && rdi-recover --help >/dev/null && python -m unittest discover -s tests -p "test_*.py"'
```

Windows and macOS validation are performed using GitHub-hosted runners through the repository workflows.
