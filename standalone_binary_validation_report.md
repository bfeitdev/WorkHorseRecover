# Standalone Binary Validation Report

## Summary

- Validation status: `STANDALONE_BINARY_CI_READY`
- Recovery logic changed: no
- Existing `v1.0.0` tag modified: no
- Standalone binary GitHub Actions jobs executed in this session: no
- Local supplementary standalone validation completed: macOS ARM64 only
- PyInstaller version observed locally: `6.22.2`
- Python version observed locally: `3.13.15`

## PyInstaller Build Matrix

| Platform | Runner | Expected architecture | Archive |
| --- | --- | --- | --- |
| Windows x64 | `windows-latest` | `x64` | `rdi-recover-windows-x64.zip` |
| Linux x64 | `ubuntu-latest` | `x64` | `rdi-recover-linux-x64.tar.gz` |
| Linux ARM64 | `ubuntu-24.04-arm` | `arm64` | `rdi-recover-linux-arm64.tar.gz` |
| macOS ARM64 | `macos-15` | `arm64` | `rdi-recover-macos-arm64.tar.gz` |
| macOS Intel/x64 | `macos-15-intel` | `x64` | `rdi-recover-macos-x64.tar.gz` |

## Current Observed Results

- GitHub Actions binary workflow definition created: yes
- GitHub Actions binary job results observed from this session: none yet
- Local macOS ARM64 standalone build: PASS
- Local macOS ARM64 binary `--version`: PASS
- Local macOS ARM64 binary `--help`: PASS
- Local macOS ARM64 synthetic `inspect`: PASS
- Local macOS ARM64 synthetic `recover`: PASS
- Local macOS ARM64 binary size: `7952544` bytes
- Local macOS ARM64 binary SHA256: `73b2db962f0ec446624a11fe52cd0e13fe0e495d3af17f05210e71dbbac6fca8`
- Local macOS ARM64 archive size: `7831725` bytes
- Local macOS ARM64 archive SHA256: `892e338be517d0e1dd97e528896c78dcf5d4184eb093d1005a5ca6df00f14c15`

## Expected Binary Validation Steps Per Runner

Each native job performs:

1. `python --version`
2. `platform.platform()` / `platform.machine()` / `platform.architecture()`
3. `python -m pip install .`
4. `python -m pip install pyinstaller`
5. `python -m PyInstaller --version`
6. native `--onefile` build
7. binary existence verification
8. binary `--version`
9. binary `--help`
10. synthetic `inspect`
11. synthetic `recover`
12. archive packaging
13. size and SHA256 reporting
14. artifact upload

## Platform Results

| Platform | PyInstaller build | --version | --help | inspect | recover | Result |
| --- | --- | --- | --- | --- | --- | --- |
| Windows x64 | pending | pending | pending | pending | pending | pending |
| Linux x64 | pending | pending | pending | pending | pending | pending |
| Linux ARM64 | pending | pending | pending | pending | pending | pending |
| macOS ARM64 | PASS locally | PASS locally | PASS locally | PASS locally | PASS locally | pending GitHub Actions |
| macOS Intel/x64 | pending | pending | pending | pending | pending | pending |

## Local Supplementary Validation Detail

- Platform: macOS ARM64
- Runner: local development machine, supplementary only
- Observed architecture: `arm64`
- PyInstaller build: PASS
- `--version` output: `rdi-recover 1.0.0`
- `--help` output: PASS
- Synthetic `inspect`: PASS with `Valid ensemble count: 1`
- Synthetic `recover`: PASS and `recovered.000` plus report files created
- Recovered output reparsed successfully with the normal Python validation code

## Signing And Notarization Limitations

- Windows executable will be unsigned. SmartScreen may warn for a low-reputation unsigned executable.
- macOS binaries will be unsigned and not notarized. Gatekeeper may warn or block first launch until the binary is explicitly allowed.
- Apple code signing and notarization are future distribution improvements and are not attempted here.
- Authenticode signing is not attempted here.

## Files Changed

- `scripts/rdi_recover_entry.py`
- `scripts/validate_standalone_binary.py`
- `scripts/package_standalone_binary.py`
- `.github/workflows/binaries.yml`
- `.github/workflows/release.yml`
- `README.md`
- `.gitignore`
- `cross_platform_validation_report.md`
- `standalone_binary_validation_report.md`

## Notes

- No PD0 parsing logic was changed.
- No recovery policy was changed.
- No package version was changed.
- No claim of standalone binary success should be made until the native GitHub Actions jobs actually pass.
- macOS binary is unsigned and not notarized.
