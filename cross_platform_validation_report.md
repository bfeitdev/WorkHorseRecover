# Cross-Platform Validation Report

## Summary

- Recovery logic changed: no
- Packaging/CI fixes made: yes
- Local synthetic baseline: `22 tests`, `OK`
- Existing `v1.0.0` tag modified: no
- Already locally validated: Linux ARM64, Linux AMD64 under Docker emulation, Python 3.13
- Pending actual GitHub Actions execution: Linux x64 hosted runner, Linux ARM64 hosted runner, Windows x64, macOS ARM64, macOS Intel/x64, Python 3.10

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

- Not available in this session
- Workflows were created locally but not executed on GitHub from here

## 7. Windows x64 Result

- Local result: not available
- CI workflow coverage added: yes, `windows-latest` with Python `3.10` and `3.13`
- Status in this report: pending GitHub Actions execution

## 8. macOS ARM64 Result

- Local result: not validated on a GitHub-hosted runner in this session
- Dedicated GitHub Actions coverage added: `macos-15` with Python `3.10` and `3.13`
- Status in this report: pending GitHub Actions execution

## 9. macOS Intel Result

- Local result: not available
- CI workflow coverage added: yes, `macos-15-intel` with Python `3.13`
- Status in this report: pending GitHub Actions execution

## 10. Linux x64 Result

- Local Docker source install: PASS
- Local Docker wheel install: PASS
- CI workflow coverage added: yes, `ubuntu-latest` with Python `3.10` and `3.13`
- Status in this report: pending GitHub Actions execution

## 11. Linux ARM64 Result

- Local Docker source install: PASS
- Local Docker wheel install: PASS
- CI workflow coverage added: yes, `ubuntu-24.04-arm` with Python `3.13`
- Status in this report: pending GitHub Actions execution

## 12. Python 3.10 Result

- Local result: not re-run in this phase
- CI workflow coverage added for `3.10` on `ubuntu-latest`, `windows-latest`, and `macos-15`
- Status in this report: pending GitHub Actions execution

## 13. Python 3.13 Result

- Local Linux ARM64 Docker: PASS
- Local Linux AMD64 Docker: PASS
- Local macOS baseline from earlier package validation: PASS
- CI workflow coverage added across all configured runners

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
- Full cross-platform validation should not be claimed until the GitHub-hosted workflows complete successfully.

PENDING_GITHUB_ACTIONS_VALIDATION
