# rdi-recover

`rdi-recover` is a conservative command-line tool for inspecting and recovering trustworthy complete ensembles from Teledyne RDI WorkHorse PD0 `.000` files.

It is designed to help operators and developers assess split files, overlaps, gaps, truncated fragments, and configuration changes without fabricating measurement content.

## Recovery Philosophy

`rdi-recover` is intentionally conservative.

- It accepts only complete ensembles that structurally validate.
- It preserves original ensemble bytes and original stored checksums.
- It does not fabricate measurement bytes.
- It does not generate replacement checksums.
- It does not silently merge multiple recursively discovered datasets into one output.
- It withholds recovery output when ambiguity or scientifically meaningful conflict is detected.

## Requirements

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
rdi-recover 1.0.0
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
rdi-recover inspect . --recursive
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

Local Docker validation examples:

```bash
docker run --rm --platform linux/arm64 -v "$PWD:/app" -w /app python:3.13-slim sh -lc 'uname -m && python --version && python -m pip install . && rdi-recover --version && rdi-recover --help >/dev/null && python -m unittest discover -s tests -p "test_*.py"'

docker run --rm --platform linux/amd64 -v "$PWD:/app" -w /app python:3.13-slim sh -lc 'uname -m && python --version && python -m pip install . && rdi-recover --version && rdi-recover --help >/dev/null && python -m unittest discover -s tests -p "test_*.py"'
```

Windows and macOS validation are performed using GitHub-hosted runners through the repository workflows.

## Standalone Binaries

Platform-specific standalone binaries can be produced with PyInstaller. These binaries do not require Python to be installed on the target machine.

Windows example:

```powershell
rdi-recover.exe --version
rdi-recover.exe inspect .
```

Linux and macOS example:

```bash
./rdi-recover --version
./rdi-recover inspect .
```

Standalone binary validation status is tracked separately from the Python package. Do not treat a platform's standalone binary as validated until its GitHub Actions binary job has passed.

Windows note: the generated executable is unsigned, so SmartScreen may warn on first launch.

macOS note: the generated binary is unsigned and not notarized, so Gatekeeper may warn or block first launch until the binary is explicitly allowed.
