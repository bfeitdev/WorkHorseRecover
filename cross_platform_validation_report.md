# Cross-Platform Validation Report

## Summary

- Recovery logic changed: no
- Packaging/CI fixes made: yes
- Local synthetic baseline: `22 tests`, `OK`
- Existing `v1.0.0` tag modified: no
- Source-package GitHub Actions validation completed: yes
- Standalone binary GitHub Actions validation completed: yes
- Overall source-package status: `CROSS_PLATFORM_VALIDATED`
- Overall standalone status: `STANDALONE_BINARY_VALIDATED`

## Source Package Validation Matrix

| Platform | Runner | Architecture | Python versions | Install | CLI | Tests | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Windows x64 | `windows-latest` | `x64` | `3.10`, `3.13` | PASS | PASS | PASS | PASS |
| Linux x64 | `ubuntu-latest` | `x64` | `3.10`, `3.13` | PASS | PASS | PASS | PASS |
| Linux ARM64 | `ubuntu-24.04-arm` | `arm64` | `3.13` | PASS | PASS | PASS | PASS |
| macOS ARM64 | `macos-15` | `arm64` | `3.10`, `3.13` | PASS | PASS | PASS | PASS |
| macOS Intel/x64 | `macos-15-intel` | `x64` | `3.13` | PASS | PASS | PASS | PASS |

## Standalone Binary Validation Matrix

| Platform | Runner | Architecture | Native build | `--version` | `--help` | `inspect` | `recover` | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Windows x64 | `windows-latest` | `x64` | PASS | PASS | PASS | PASS | PASS | PASS |
| Linux x64 | `ubuntu-latest` | `x64` | PASS | PASS | PASS | PASS | PASS | PASS |
| Linux ARM64 | `ubuntu-24.04-arm` | `arm64` | PASS | PASS | PASS | PASS | PASS | PASS |
| macOS ARM64 | `macos-15` | `arm64` | PASS | PASS | PASS | PASS | PASS | PASS |
| macOS Intel/x64 | `macos-15-intel` | `x64` | PASS | PASS | PASS | PASS | PASS | PASS |

Standalone binaries were built natively on matching GitHub-hosted runners for Windows x64, Linux x64, Linux ARM64, macOS ARM64, and macOS Intel/x64.

## Local Supplementary Validation

- Linux ARM64 Docker source install: PASS
- Linux AMD64 Docker source install: PASS
- Linux ARM64 Docker wheel install: PASS
- Linux AMD64 Docker wheel install: PASS
- Local macOS ARM64 standalone supplementary validation: PASS

## Workflow Coverage Restored

- `.github/workflows/test.yml`
- `.github/workflows/build.yml`
- `.github/workflows/release.yml`
- `.github/workflows/binaries.yml`

Restored workflow behavior:

- source-package validation across the existing GitHub-hosted platform matrix
- standalone binary validation across the existing native GitHub-hosted platform matrix
- preserved artifact names, permissions, validation steps, and release gating
- fail-closed future-release tag/package-version guard before publication

## Safety Notes

- No recovery logic changed.
- No recovery policy changed.
- No scientific output behavior changed.
- The existing `v1.0.0` tag was not modified.
- The current branch README standalone guidance cleanup remains intact.

CROSS_PLATFORM_VALIDATED
STANDALONE_BINARY_VALIDATED
