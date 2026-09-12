# Standalone Binary Validation Report

## Summary

- Validation status: `STANDALONE_BINARY_VALIDATED`
- Recovery logic changed: no
- Existing `v1.0.0` tag modified: no
- Standalone binary GitHub Actions jobs executed in this validation phase: yes
- Native GitHub-hosted standalone targets passed: 5 of 5
- PyInstaller version observed locally during supplementary validation: `6.22.2`
- Python version observed locally during supplementary validation: `3.13.15`

## Native Build Matrix

| Platform | Runner | Expected architecture | Package archive | Result |
| --- | --- | --- | --- | --- |
| Windows x64 | `windows-latest` | `x64` | `rdi-recover-windows-x64.zip` | PASS |
| Linux x64 | `ubuntu-latest` | `x64` | `rdi-recover-linux-x64.tar.gz` | PASS |
| Linux ARM64 | `ubuntu-24.04-arm` | `arm64` | `rdi-recover-linux-arm64.tar.gz` | PASS |
| macOS ARM64 | `macos-15` | `arm64` | `rdi-recover-macos-arm64.tar.gz` | PASS |
| macOS Intel/x64 | `macos-15-intel` | `x64` | `rdi-recover-macos-x64.tar.gz` | PASS |

## Validation Steps Per Native Runner

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
13. artifact upload

## Platform Results

| Platform | PyInstaller build | `--version` | `--help` | `inspect` | `recover` | Result |
| --- | --- | --- | --- | --- | --- | --- |
| Windows x64 | PASS | PASS | PASS | PASS | PASS | PASS |
| Linux x64 | PASS | PASS | PASS | PASS | PASS | PASS |
| Linux ARM64 | PASS | PASS | PASS | PASS | PASS | PASS |
| macOS ARM64 | PASS | PASS | PASS | PASS | PASS | PASS |
| macOS Intel/x64 | PASS | PASS | PASS | PASS | PASS | PASS |

Standalone binaries were built natively on matching GitHub-hosted runners for all five targets.

## GitHub Actions Artifact Digests

These digests are the GitHub Actions artifact digests reported for the uploaded workflow artifacts, not the SHA256 of the executable inside the archive and not the SHA256 of the packaged archive file itself.

| Platform | Artifact name | Artifact size | Artifact digest |
| --- | --- | --- | --- |
| Linux ARM64 | `rdi-recover-linux-arm64` | `19.4 MB` | `sha256:9a38355bc99f7f99f6049fb0b2b2c081daf0d5820e484b2b222940290d20be36` |
| Linux x64 | `rdi-recover-linux-x64` | `20.3 MB` | `sha256:93cf46c29de00488080b4154cf8f15569a892e3344a238884b1bb616f04f0bcf` |
| macOS ARM64 | `rdi-recover-macos-arm64` | `6.93 MB` | `sha256:ccaeb74a9c958a976e3342e9e94928ffc7069b781413528f9770534ffd5353a1` |
| macOS Intel/x64 | `rdi-recover-macos-x64` | `7.5 MB` | `sha256:9b8f5a6f99ebacafcac41d8266f9813a150b773a55f2d376bbb0a34a2e1e3d40` |
| Windows x64 | `rdi-recover-windows-x64` | `7.79 MB` | `sha256:7c7a5e5d7e1b1adad1a02d721c6a3e80f9dade2788e1d4d956091af12d27bfb6` |

## Executable And Packaged Archive SHA256

- Native GitHub Actions artifact digests were recorded for all five targets.
- Per-platform executable SHA256 and packaged archive SHA256 values were not recorded for every target in the GitHub Actions results and are therefore not invented here.
- Local supplementary macOS ARM64 executable and archive SHA256 values are preserved below because they were part of the report design.

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
- Local macOS ARM64 binary size: `7952544` bytes
- Local macOS ARM64 executable SHA256: `73b2db962f0ec446624a11fe52cd0e13fe0e495d3af17f05210e71dbbac6fca8`
- Local macOS ARM64 archive size: `7831725` bytes
- Local macOS ARM64 packaged archive SHA256: `892e338be517d0e1dd97e528896c78dcf5d4184eb093d1005a5ca6df00f14c15`

## Signing And Notarization Limitations

- Windows executable is unsigned. SmartScreen may warn on first launch.
- macOS binaries are unsigned and not notarized. Gatekeeper may warn or block first launch.
- Apple code signing and notarization are future distribution improvements and are not attempted here.
- Authenticode signing is not attempted here.

## Notes

- No PD0 parsing logic was changed.
- No recovery policy was changed.
- No package version was changed.
- The current branch README standalone guidance cleanup remains intact.

STANDALONE_BINARY_VALIDATED
