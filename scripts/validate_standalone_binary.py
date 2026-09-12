from __future__ import annotations

import argparse
import csv
import json
import os
import struct
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

try:
    from rdi_recover.rdi_recover import FIXED_LEADER_ID, VARIABLE_LEADER_ID, checksum_rdi, validate_recovered_file
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from rdi_recover.rdi_recover import FIXED_LEADER_ID, VARIABLE_LEADER_ID, checksum_rdi, validate_recovered_file


def build_pd0_like_ensemble(ensemble_number: int, timestamp: datetime) -> bytes:
    number_of_data_types = 3
    header_len = 6 + 2 * number_of_data_types
    fixed_len = 40
    variable_len = 21
    data_len = 8
    offsets = (header_len, header_len + fixed_len, header_len + fixed_len + variable_len)
    byte_count = header_len + fixed_len + variable_len + data_len
    payload = bytearray(byte_count)
    payload[0:2] = b"\x7f\x7f"
    struct.pack_into("<H", payload, 2, byte_count)
    payload[4] = 0
    payload[5] = number_of_data_types
    struct.pack_into("<3H", payload, 6, *offsets)

    fixed = bytearray(fixed_len)
    fixed[0:2] = FIXED_LEADER_ID
    for index in range(2, fixed_len):
        fixed[index] = (1 + index) % 256
    payload[offsets[0] : offsets[0] + fixed_len] = fixed

    variable = bytearray(variable_len)
    variable[0:2] = VARIABLE_LEADER_ID
    struct.pack_into("<H", variable, 2, ensemble_number & 0xFFFF)
    variable[4] = timestamp.year - 2000
    variable[5] = timestamp.month
    variable[6] = timestamp.day
    variable[7] = timestamp.hour
    variable[8] = timestamp.minute
    variable[9] = timestamp.second
    variable[10] = round(timestamp.microsecond / 10000)
    variable[11] = (ensemble_number >> 16) & 0xFF
    struct.pack_into("<H", variable, 16, 1001)
    payload[offsets[1] : offsets[1] + variable_len] = variable

    data_block = bytearray(data_len)
    data_block[0:2] = b"\x01\x00"
    data_block[2:] = bytes(range(1, data_len - 1))[: data_len - 2].ljust(data_len - 2, b"\x00")
    payload[offsets[2] : offsets[2] + data_len] = data_block

    checksum = checksum_rdi(payload)
    return bytes(payload) + struct.pack("<H", checksum)


def run_checked(command: list[str], *, expected_substring: str | None = None) -> subprocess.CompletedProcess[str]:
    print(f"$ {' '.join(command)}")
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip(), file=sys.stderr)
    if result.returncode != 0:
        raise SystemExit(f"command failed with exit code {result.returncode}: {' '.join(command)}")
    if expected_substring is not None and expected_substring not in result.stdout:
        raise SystemExit(f"expected substring {expected_substring!r} not found in output of {' '.join(command)}")
    return result


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("binary")
    parser.add_argument("--expected-version", default="rdi-recover 1.0.0")
    args = parser.parse_args(argv)

    binary = Path(args.binary).resolve()
    if os.name != "nt":
        binary.chmod(binary.stat().st_mode | 0o111)

    run_checked([str(binary), "--version"], expected_substring=args.expected_version)
    run_checked([str(binary), "--help"], expected_substring="inspect")

    with tempfile.TemporaryDirectory(prefix="rdi-recover-bin-") as tmp_dir:
        root = Path(tmp_dir)
        input_file = root / "single.000"
        input_file.write_bytes(build_pd0_like_ensemble(1, datetime(2024, 1, 1, 0, 0, 0)))
        output_dir = root / "out"

        inspect_result = run_checked([str(binary), "inspect", str(input_file)], expected_substring="Valid ensemble count: 1")
        recover_result = run_checked([str(binary), "recover", str(input_file), "--output-dir", str(output_dir)], expected_substring="PASS")

        recovered_path = output_dir / "recovered.000"
        expected_outputs = [
            recovered_path,
            output_dir / "source_inventory.csv",
            output_dir / "boundary_analysis.csv",
            output_dir / "recovered_gaps.csv",
            output_dir / "recovered_ensemble_map.csv",
            output_dir / "recovery_manifest.json",
            output_dir / "recovery_report.md",
            output_dir / "recovered_validation.md",
        ]
        missing = [str(path) for path in expected_outputs if not path.exists()]
        if missing:
            raise SystemExit(f"missing expected output files: {missing}")

        validation = validate_recovered_file(recovered_path)
        if validation.valid_count != 1 or validation.issues:
            raise SystemExit(f"recovered file validation failed: valid_count={validation.valid_count}, issues={validation.issues}")

        manifest = json.loads((output_dir / "recovery_manifest.json").read_text(encoding="utf-8"))
        if manifest["verdict"] != "PASS":
            raise SystemExit(f"unexpected manifest verdict: {manifest['verdict']}")
        if len(manifest["accepted_records"]) != 1:
            raise SystemExit(f"unexpected accepted record count: {len(manifest['accepted_records'])}")
        record = manifest["accepted_records"][0]
        if record["source_file"] != "single.000":
            raise SystemExit(f"unexpected source file in manifest: {record['source_file']}")
        if record["ensemble_number"] != 1:
            raise SystemExit(f"unexpected ensemble number in manifest: {record['ensemble_number']}")

        map_rows = read_csv_rows(output_dir / "recovered_ensemble_map.csv")
        if len(map_rows) != 1:
            raise SystemExit(f"unexpected recovered_ensemble_map.csv row count: {len(map_rows)}")
        row = map_rows[0]
        if row["source_file"] != "single.000":
            raise SystemExit(f"unexpected source file in recovered_ensemble_map.csv: {row['source_file']}")
        if int(row["ensemble_number"]) != 1:
            raise SystemExit(f"unexpected ensemble number in recovered_ensemble_map.csv: {row['ensemble_number']}")
        if row["reconstructed"].strip().lower() != "false":
            raise SystemExit(f"unexpected reconstructed flag in recovered_ensemble_map.csv: {row['reconstructed']}")
        if int(row["output_byte_offset"]) != 0:
            raise SystemExit(f"unexpected output byte offset in recovered_ensemble_map.csv: {row['output_byte_offset']}")

        print("Standalone binary validation passed")
        print(inspect_result.stdout.strip())
        print(recover_result.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
