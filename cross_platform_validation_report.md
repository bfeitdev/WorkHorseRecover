# Cross-Platform Validation Report

## Summary

- Recovery logic changed: no
- Packaging/CI fixes made: yes
- Local synthetic baseline: `22 tests`, `OK`
- Existing `v1.0.0` tag modified: no
- Source-package GitHub Actions validation completed: yes
- Overall source-package status: `CROSS_PLATFORM_VALIDATED`

## 1. Local Linux ARM64 Docker Result

- Result: PASS
- Container image: `python:3.13-slim`
- Python version: `3.13.15`
- `uname -m`: `aarch64`
- Install method: `python -m pip install .`
- CLI result: `rdi-recover 1.0.0`
- Test result: `22 tests`, `OK`

## 2. Local Linux AMD64 Docker Result

- Result: PASS
- Docker emulation used successfully: yes
- Container image: `python:3.13-slim`
- Python version: `3.13.15`
- `uname -m`: `x86_64`
- Install method: `python -m pip install .`
- CLI result: `rdi-recover 1.0.0`
- Test result: `22 tests`, `OK`

## 3. Direct Source Install Result

- Linux ARM64 Docker: PASS
- Linux AMD64 Docker: PASS
- Note: source installs were validated with a writable bind mount. A read-only bind mount is not a valid portability requirement for `pip install .` because build metadata generation requires write access to the checkout.

## 4. Wheel Install Result

- Wheel built: `dist/rdi_recover-1.0.0-py3-none-any.whl`
- Linux ARM64 Docker wheel install: PASS
- Linux AMD64 Docker wheel install: PASS
- Same `py3-none-any` wheel reused across both architectures: yes

## 5. GitHub Actions Matrix Definition

Created workflows:

- `.github/workflows/test.yml`
- `.github/workflows/build.yml`
- `.github/workflows/release.yml`

`test.yml` coverage:

- `ubuntu-latest` with Python `3.10`, `3.13`
- `windows-latest` with Python `3.10`, `3.13`
- `macos-15` with Python `3.10`, `3.13`
- `ubuntu-24.04-arm` with Python `3.13`
- `macos-15-intel` with Python `3.13`

Expected runner architectures:

- `ubuntu-latest` -> Linux x64
- `windows-latest` -> Windows x64
- `macos-15` -> macOS ARM64
- `ubuntu-24.04-arm` -> Linux ARM64
- `macos-15-intel` -> macOS Intel/x64

Each job:

- checks out the repo
- sets up Python
- prints platform diagnostics
- runs `python -m pip install .`
- runs `rdi-recover --version`
- verifies `rdi-recover --help`
- verifies `python -m rdi_recover --version`
- runs `python -m unittest discover -s tests -p 'test_*.py'`

## 6. Actual GitHub Actions Results If Available

- Linux x64: PASS
- Linux ARM64: PASS
- Windows x64: PASS
- macOS ARM64: PASS
- macOS Intel/x64: PASS
- Python 3.10: PASS where configured
- Python 3.13: PASS

## 7. Windows x64 Result

- Local result: not available
- GitHub Actions hosted runner result: PASS

## 8. macOS ARM64 Result

- GitHub Actions hosted runner result: PASS

## 9. macOS Intel Result

- Local result: not available
- GitHub Actions hosted runner result: PASS

## 10. Linux x64 Result

- Local Docker source install: PASS
- Local Docker wheel install: PASS
- GitHub Actions hosted runner result: PASS

## 11. Linux ARM64 Result

- Local Docker source install: PASS
- Local Docker wheel install: PASS
- GitHub Actions hosted runner result: PASS

## 12. Python 3.10 Result

- Local result: not re-run in this phase
- GitHub Actions result: PASS where configured

## 13. Python 3.13 Result

- Local Linux ARM64 Docker: PASS
- Local Linux AMD64 Docker: PASS
- Local macOS baseline from earlier package validation: PASS
- GitHub Actions result: PASS

## Standalone Binary Validation

| Platform | Runner | Architecture | PyInstaller build | --version | --help | inspect | recover | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Windows x64 | `windows-latest` | `x64` | pending | pending | pending | pending | pending | pending |
| Linux x64 | `ubuntu-latest` | `x64` | pending | pending | pending | pending | pending | pending |
| Linux ARM64 | `ubuntu-24.04-arm` | `arm64` | pending | pending | pending | pending | pending | pending |
| macOS ARM64 | `macos-15` | `arm64` | PASS locally, pending CI | PASS locally, pending CI | PASS locally, pending CI | PASS locally, pending CI | PASS locally, pending CI | pending GitHub Actions |
| macOS Intel/x64 | `macos-15-intel` | `x64` | pending | pending | pending | pending | pending | pending |

## 14. Defects Found

1. Packaging portability defect: generated `src/rdi_recover.egg-info/` files were present in the repo. This caused `pip install .` to fail on a read-only-mounted checkout because `setuptools` attempted to update metadata timestamps.
2. Test portability defect: `tests/test_rdi_recover.py` unconditionally injected `src/` into `sys.path`, which would cause wheel-install tests to exercise the checkout copy instead of the installed package.
3. CI robustness defect: workflow artifact verification originally hardcoded `1.0.0` filenames, which would have broken future tag-based releases without any runtime code defect.

## 15. Files Changed

- `tests/test_rdi_recover.py`
- `README.md`
- `.github/workflows/test.yml`
- `.github/workflows/build.yml`
- `.github/workflows/release.yml`
- removed generated files under `src/rdi_recover.egg-info/`
- `cross_platform_validation_report.md`

## 16. Whether Any Recovery Logic Changed

- No recovery logic changed
- No recovery policy changed
- No scientific output behavior changed

## Notes

- The existing `v1.0.0` tag was not modified.
- The new workflow files exist on the current branch only, not retroactively inside the historical `v1.0.0` tag.
- Real dataset regression remains a local/manual release verification step and is not moved into CI.
- Standalone binary validation remains pending until the new GitHub Actions binary workflow completes successfully on each native runner.

CROSS_PLATFORM_VALIDATED
