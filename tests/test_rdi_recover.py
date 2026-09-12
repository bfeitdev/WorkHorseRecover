from __future__ import annotations

import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import os
from datetime import datetime, timedelta
from pathlib import Path

try:
    import rdi_recover
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    import rdi_recover


def build_pd0_like_ensemble(
    ensemble_number: int,
    timestamp: datetime,
    *,
    fixed_seed: int = 1,
    payload_seed: int = 1,
    extra_payload: bytes | None = None,
) -> bytes:
    number_of_data_types = 3
    header_len = 6 + 2 * number_of_data_types
    fixed_len = 40
    variable_len = 21
    data_len = 8
    offsets = (header_len, header_len + fixed_len, header_len + fixed_len + variable_len)
    byte_count = header_len + fixed_len + variable_len + data_len
    payload = bytearray(byte_count)
    payload[0:2] = rdi_recover.SYNC
    struct.pack_into("<H", payload, 2, byte_count)
    payload[4] = 0
    payload[5] = number_of_data_types
    struct.pack_into("<3H", payload, 6, *offsets)

    fixed = bytearray(fixed_len)
    fixed[0:2] = rdi_recover.FIXED_LEADER_ID
    for index in range(2, fixed_len):
        fixed[index] = (fixed_seed + index) % 256
    payload[offsets[0] : offsets[0] + fixed_len] = fixed

    variable = bytearray(variable_len)
    variable[0:2] = rdi_recover.VARIABLE_LEADER_ID
    struct.pack_into("<H", variable, 2, ensemble_number & 0xFFFF)
    variable[4] = timestamp.year - 2000
    variable[5] = timestamp.month
    variable[6] = timestamp.day
    variable[7] = timestamp.hour
    variable[8] = timestamp.minute
    variable[9] = timestamp.second
    variable[10] = round(timestamp.microsecond / 10000)
    variable[11] = (ensemble_number >> 16) & 0xFF
    struct.pack_into("<H", variable, 16, 1000 + payload_seed)
    payload[offsets[1] : offsets[1] + variable_len] = variable

    data_block = bytearray(data_len)
    data_block[0:2] = b"\x01\x00"
    raw_extra = extra_payload if extra_payload is not None else bytes((payload_seed + index) % 256 for index in range(data_len - 2))
    data_block[2:] = raw_extra[: data_len - 2].ljust(data_len - 2, b"\x00")
    payload[offsets[2] : offsets[2] + data_len] = data_block

    checksum = rdi_recover.checksum_rdi(payload)
    return bytes(payload) + struct.pack("<H", checksum)


def write_file(path: Path, chunks: list[bytes]) -> None:
    path.write_bytes(b"".join(chunks))


class RdiRecoverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="rdi-recover-test-"))
        self.uninstalled_subprocess_env = os.environ.copy()
        src_path = str(Path(__file__).resolve().parents[1] / "src")
        existing = self.uninstalled_subprocess_env.get("PYTHONPATH")
        self.uninstalled_subprocess_env["PYTHONPATH"] = src_path if not existing else os.pathsep.join([src_path, existing])

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def test_clean_single_file(self) -> None:
        base = datetime(2024, 1, 1, 0, 0, 0)
        file_path = self.temp_dir / "single.000"
        write_file(file_path, [build_pd0_like_ensemble(index, base + timedelta(seconds=index - 1)) for index in range(1, 4)])
        output_dir = self.temp_dir / "out"
        result = rdi_recover.recover_dataset([file_path], output_dir)
        self.assertEqual(result.verdict, "PASS")
        self.assertTrue((output_dir / "recovered.000").exists())
        self.assertEqual(result.validation.valid_count, 3)

    def test_multiple_clean_chronological_files(self) -> None:
        base = datetime(2024, 1, 1, 0, 0, 0)
        a = self.temp_dir / "a.000"
        b = self.temp_dir / "b.000"
        write_file(a, [build_pd0_like_ensemble(index, base + timedelta(seconds=index - 1)) for index in range(1, 3)])
        write_file(b, [build_pd0_like_ensemble(index, base + timedelta(seconds=index - 1)) for index in range(3, 5)])
        result = rdi_recover.recover_dataset([a, b], self.temp_dir / "out")
        self.assertEqual(result.verdict, "PASS")
        self.assertEqual([record.ensemble_number for record in result.accepted_records], [1, 2, 3, 4])

    def test_filenames_out_of_chronological_order(self) -> None:
        base = datetime(2024, 1, 1, 0, 0, 0)
        late = self.temp_dir / "aaa_late.000"
        early = self.temp_dir / "zzz_early.000"
        write_file(late, [build_pd0_like_ensemble(3, base + timedelta(seconds=2)), build_pd0_like_ensemble(4, base + timedelta(seconds=3))])
        write_file(early, [build_pd0_like_ensemble(1, base + timedelta(seconds=0)), build_pd0_like_ensemble(2, base + timedelta(seconds=1))])
        analysis = rdi_recover.analyze_dataset([late, early])
        self.assertEqual([inv.path.name for inv in analysis.ordered_files], ["zzz_early.000", "aaa_late.000"])

    def test_counter_reset_between_files(self) -> None:
        base = datetime(2024, 1, 1, 0, 0, 0)
        a = self.temp_dir / "a.000"
        b = self.temp_dir / "b.000"
        write_file(a, [build_pd0_like_ensemble(10, base), build_pd0_like_ensemble(11, base + timedelta(seconds=1))])
        write_file(b, [build_pd0_like_ensemble(1, base + timedelta(seconds=2)), build_pd0_like_ensemble(2, base + timedelta(seconds=3))])
        analysis = rdi_recover.analyze_dataset([a, b])
        self.assertIn("CLEAN_WITH_COUNTER_RESET", analysis.boundaries[0].facts)

    def test_16_bit_ensemble_rollover(self) -> None:
        base = datetime(2024, 1, 1, 0, 0, 0)
        a = self.temp_dir / "a.000"
        b = self.temp_dir / "b.000"
        write_file(a, [build_pd0_like_ensemble(65535, base)])
        write_file(b, [build_pd0_like_ensemble(65536, base + timedelta(seconds=1))])
        analysis = rdi_recover.analyze_dataset([a, b])
        self.assertEqual(analysis.boundaries[0].counter_transition, "counter_rollover")

    def test_real_time_gap(self) -> None:
        base = datetime(2024, 1, 1, 0, 0, 0)
        a = self.temp_dir / "gap.000"
        write_file(
            a,
            [
                build_pd0_like_ensemble(1, base),
                build_pd0_like_ensemble(2, base + timedelta(seconds=1)),
                build_pd0_like_ensemble(3, base + timedelta(seconds=4)),
            ],
        )
        result = rdi_recover.recover_dataset([a], self.temp_dir / "out")
        self.assertEqual(len(result.gaps), 1)
        self.assertEqual(result.gaps[0].missing_acquisition_ms, 2000)
        self.assertEqual(result.verdict, "PASS_WITH_GAPS")

    def test_exact_duplicate_overlap(self) -> None:
        base = datetime(2024, 1, 1, 0, 0, 0)
        duplicate = build_pd0_like_ensemble(2, base + timedelta(seconds=1))
        a = self.temp_dir / "a.000"
        b = self.temp_dir / "b.000"
        write_file(a, [build_pd0_like_ensemble(1, base), duplicate])
        write_file(b, [duplicate, build_pd0_like_ensemble(3, base + timedelta(seconds=2))])
        result = rdi_recover.recover_dataset([a, b], self.temp_dir / "out")
        self.assertEqual(result.duplicate_removed, 1)
        self.assertEqual(result.verdict, "PASS")

    def test_overlapping_time_with_different_valid_records_is_conflict(self) -> None:
        base = datetime(2024, 1, 1, 0, 0, 0)
        a = self.temp_dir / "a.000"
        b = self.temp_dir / "b.000"
        write_file(a, [build_pd0_like_ensemble(1, base), build_pd0_like_ensemble(2, base + timedelta(seconds=1), payload_seed=2)])
        write_file(b, [build_pd0_like_ensemble(9, base + timedelta(seconds=1), payload_seed=9)])
        result = rdi_recover.recover_dataset([a, b], self.temp_dir / "out")
        self.assertEqual(result.verdict, "MANUAL_REVIEW_REQUIRED")
        self.assertFalse((self.temp_dir / "out" / "recovered.000").exists())

    def test_truncated_final_ensemble(self) -> None:
        base = datetime(2024, 1, 1, 0, 0, 0)
        full = build_pd0_like_ensemble(1, base)
        truncated = build_pd0_like_ensemble(2, base + timedelta(seconds=1))[:-10]
        file_path = self.temp_dir / "truncated.000"
        write_file(file_path, [full, truncated])
        result = rdi_recover.recover_dataset([file_path], self.temp_dir / "out")
        self.assertEqual(result.verdict, "PASS_WITH_UNRECOVERABLE_FRAGMENTS")
        self.assertEqual(result.validation.valid_count, 1)

    def test_file_beginning_with_non_pd0_bytes(self) -> None:
        base = datetime(2024, 1, 1, 0, 0, 0)
        file_path = self.temp_dir / "leading_noise.000"
        write_file(file_path, [b"noise", build_pd0_like_ensemble(1, base)])
        analysis = rdi_recover.analyze_dataset([file_path])
        self.assertEqual(analysis.ordered_files[0].fragments[0].boundary_side, "leading")

    def test_safe_cross_file_split_record_with_valid_original_checksum(self) -> None:
        base = datetime(2024, 1, 1, 0, 0, 0)
        first = build_pd0_like_ensemble(1, base)
        split = build_pd0_like_ensemble(2, base + timedelta(seconds=1))
        third = build_pd0_like_ensemble(3, base + timedelta(seconds=2))
        split_point = len(split) - 12
        a = self.temp_dir / "a.000"
        b = self.temp_dir / "b.000"
        write_file(a, [first, split[:split_point]])
        write_file(b, [split[split_point:], third])
        result = rdi_recover.recover_dataset([a, b], self.temp_dir / "out")
        safe_splits = [split_result for split_result in result.analysis.split_candidates if split_result.status == "SAFE_RECONSTRUCTION"]
        self.assertEqual(len(safe_splits), 1)
        self.assertIn(2, [record.ensemble_number for record in result.accepted_records])

    def test_unsafe_fragment_join(self) -> None:
        base = datetime(2024, 1, 1, 0, 0, 0)
        first = build_pd0_like_ensemble(1, base)
        split = build_pd0_like_ensemble(2, base + timedelta(seconds=1))
        next_full = build_pd0_like_ensemble(3, base + timedelta(seconds=2))
        a = self.temp_dir / "a.000"
        b = self.temp_dir / "b.000"
        write_file(a, [first, split[:-8]])
        write_file(b, [next_full])
        analysis = rdi_recover.analyze_dataset([a, b])
        self.assertFalse(any(split_result.status == "SAFE_RECONSTRUCTION" for split_result in analysis.split_candidates))

    def test_configuration_change(self) -> None:
        base = datetime(2024, 1, 1, 0, 0, 0)
        a = self.temp_dir / "a.000"
        b = self.temp_dir / "b.000"
        write_file(a, [build_pd0_like_ensemble(1, base, fixed_seed=1)])
        write_file(b, [build_pd0_like_ensemble(2, base + timedelta(seconds=1), fixed_seed=40)])
        analysis = rdi_recover.analyze_dataset([a, b])
        self.assertIn("CONFIGURATION_CHANGE", analysis.boundaries[0].facts)

    def test_corrupted_checksum(self) -> None:
        base = datetime(2024, 1, 1, 0, 0, 0)
        corrupt = bytearray(build_pd0_like_ensemble(1, base))
        corrupt[-1] ^= 0xFF
        file_path = self.temp_dir / "corrupt.000"
        write_file(file_path, [bytes(corrupt)])
        inventory = rdi_recover.inventory_file(file_path)
        self.assertEqual(len(inventory.ensembles), 0)
        self.assertTrue(any(region.classification == "BAD_CHECKSUM" for region in inventory.regions))

    def test_false_sync_inside_arbitrary_data(self) -> None:
        base = datetime(2024, 1, 1, 0, 0, 0)
        file_path = self.temp_dir / "embedded_sync.000"
        write_file(file_path, [build_pd0_like_ensemble(1, base, extra_payload=b"\x7f\x7f\x00\x01\x02\x03")])
        inventory = rdi_recover.inventory_file(file_path)
        self.assertEqual(len(inventory.ensembles), 1)
        self.assertEqual(len(inventory.regions), 1)

    def test_output_validation_failure(self) -> None:
        base = datetime(2024, 1, 1, 0, 0, 0)
        file_path = self.temp_dir / "single.000"
        write_file(file_path, [build_pd0_like_ensemble(1, base)])
        result = rdi_recover.recover_dataset([file_path], self.temp_dir / "out")
        recovered = self.temp_dir / "out" / "recovered.000"
        corrupted = bytearray(recovered.read_bytes())
        corrupted[-1] ^= 0xAA
        recovered.write_bytes(bytes(corrupted))
        validation = rdi_recover.validate_recovered_file(recovered)
        self.assertTrue(validation.issues)

    def test_cli_inspect_and_directory_discovery(self) -> None:
        base = datetime(2024, 1, 1, 0, 0, 0)
        input_dir = self.temp_dir / "input"
        input_dir.mkdir()
        write_file(input_dir / "one.000", [build_pd0_like_ensemble(1, base)])
        write_file(input_dir / "two.000", [build_pd0_like_ensemble(2, base + timedelta(seconds=1))])
        output_dir = input_dir / "output"
        output_dir.mkdir()
        write_file(output_dir / "recovered.000", [build_pd0_like_ensemble(99, base + timedelta(seconds=99))])
        result = subprocess.run(
            [sys.executable, "-m", "rdi_recover", "inspect", str(input_dir)],
            capture_output=True,
            text=True,
            check=False,
            env=self.uninstalled_subprocess_env,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Chronological order", result.stdout)
        self.assertNotIn("recovered.000", result.stdout)
        self.assertFalse((input_dir / "recovered.000").exists())

    def test_cli_version(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "rdi_recover", "--version"],
            capture_output=True,
            text=True,
            check=False,
            env=self.uninstalled_subprocess_env,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("rdi-recover 1.1.0", result.stdout)

    def test_non_recursive_directory_discovery_does_not_enter_subdirectories(self) -> None:
        top = self.temp_dir / "top"
        nested = top / "nested"
        top.mkdir()
        nested.mkdir()
        base = datetime(2024, 1, 1, 0, 0, 0)
        write_file(nested / "nested.000", [build_pd0_like_ensemble(1, base)])
        groups = rdi_recover.discover_candidate_groups([str(top)], recursive=False)
        self.assertEqual(groups, [])

    def test_recursive_discovery_finds_both_deployments_but_does_not_merge(self) -> None:
        root = self.temp_dir / "root"
        dataset_a = root / "dataset_a"
        dataset_b = root / "dataset_b"
        dataset_a.mkdir(parents=True)
        dataset_b.mkdir(parents=True)
        base_a = datetime(2024, 1, 1, 0, 0, 0)
        base_b = datetime(2024, 1, 4, 0, 0, 0)
        write_file(dataset_a / "a1.000", [build_pd0_like_ensemble(1, base_a), build_pd0_like_ensemble(2, base_a + timedelta(seconds=1))])
        write_file(dataset_b / "b1.000", [build_pd0_like_ensemble(1, base_b), build_pd0_like_ensemble(2, base_b + timedelta(seconds=1))])
        groups = rdi_recover.discover_candidate_groups([str(root)], recursive=True)
        self.assertEqual(len(groups), 2)
        self.assertEqual([len(group.files) for group in groups], [1, 1])
        selected, status = rdi_recover.select_single_group_or_status(groups)
        self.assertIsNone(selected)
        self.assertEqual(status, "MULTIPLE_CANDIDATE_DATASETS")

    def test_explicit_files_preserve_operator_selected_grouping(self) -> None:
        base_a = datetime(2024, 1, 1, 0, 0, 0)
        base_b = datetime(2024, 1, 4, 0, 0, 0)
        a = self.temp_dir / "a.000"
        b = self.temp_dir / "b.000"
        write_file(a, [build_pd0_like_ensemble(1, base_a)])
        write_file(b, [build_pd0_like_ensemble(1, base_b)])
        groups = rdi_recover.discover_candidate_groups([str(a), str(b)], recursive=False)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].discovery_basis, "explicit_files")
        self.assertEqual({path.name for path in groups[0].files}, {"a.000", "b.000"})

    def test_generated_output_directories_remain_excluded(self) -> None:
        root = self.temp_dir / "root"
        root.mkdir()
        data_dir = root / "data"
        output_dir = root / "recovered_output"
        data_dir.mkdir()
        output_dir.mkdir()
        base = datetime(2024, 1, 1, 0, 0, 0)
        write_file(data_dir / "real.000", [build_pd0_like_ensemble(1, base)])
        write_file(output_dir / "recovered.000", [build_pd0_like_ensemble(2, base + timedelta(seconds=1))])
        groups = rdi_recover.discover_candidate_groups([str(root)], recursive=True, output_dir=output_dir)
        self.assertEqual(len(groups), 1)
        self.assertEqual([path.name for path in groups[0].files], ["real.000"])

    def test_slice_removes_first_ensembles_without_changing_input(self) -> None:
        base = datetime(2024, 1, 1)
        source = self.temp_dir / "source.000"
        records = [build_pd0_like_ensemble(index, base + timedelta(seconds=index)) for index in range(1, 5)]
        write_file(source, records)
        original_bytes = source.read_bytes()
        plan = rdi_recover.build_slice_plan(source, first=2)
        output = self.temp_dir / "first_removed.000"

        validation = rdi_recover.write_slice_output(plan, output)

        self.assertEqual(plan.removed_indexes, (1, 2))
        self.assertEqual(plan.retained_indexes, (3, 4))
        self.assertEqual(output.read_bytes(), b"".join(records[2:]))
        self.assertEqual(source.read_bytes(), original_bytes)
        self.assertEqual(validation.valid_count, 2)
        self.assertFalse(validation.issues)
        self.assertTrue(validation.retained_bytes_match)

    def test_slice_removes_last_and_middle_ranges_byte_identically(self) -> None:
        base = datetime(2024, 1, 1)
        source = self.temp_dir / "source.000"
        records = [build_pd0_like_ensemble(index, base + timedelta(seconds=index)) for index in range(1, 6)]
        write_file(source, records)

        last_plan = rdi_recover.build_slice_plan(source, last=2)
        last_output = self.temp_dir / "last_removed.000"
        rdi_recover.write_slice_output(last_plan, last_output)
        self.assertEqual(last_output.read_bytes(), b"".join(records[:3]))

        range_plan = rdi_recover.build_slice_plan(source, range_spec="2:4")
        range_output = self.temp_dir / "middle_removed.000"
        validation = rdi_recover.write_slice_output(range_plan, range_output)
        self.assertEqual(range_plan.removed_indexes, (2, 3, 4))
        self.assertEqual(range_output.read_bytes(), records[0] + records[4])
        self.assertEqual(validation.valid_count, 2)
        self.assertFalse(validation.issues)

    def test_slice_removes_exactly_one_by_physical_index_despite_rdi_rollover(self) -> None:
        base = datetime(2024, 1, 1)
        source = self.temp_dir / "rollover.000"
        records = [
            build_pd0_like_ensemble(65535, base),
            build_pd0_like_ensemble(65536, base + timedelta(seconds=1)),
            build_pd0_like_ensemble(1, base + timedelta(seconds=2)),
        ]
        write_file(source, records)
        plan = rdi_recover.build_slice_plan(source, range_spec="2:2")
        output = self.temp_dir / "one_removed.000"

        rdi_recover.write_slice_output(plan, output)

        self.assertEqual([entry.rdi_ensemble_number for entry in plan.ensembles], [65535, 65536, 1])
        self.assertEqual(plan.removed_indexes, (2,))
        self.assertEqual(output.read_bytes(), records[0] + records[2])

    def test_slice_rejects_invalid_or_combined_selections(self) -> None:
        base = datetime(2024, 1, 1)
        source = self.temp_dir / "source.000"
        write_file(source, [build_pd0_like_ensemble(index, base + timedelta(seconds=index)) for index in range(1, 3)])
        for kwargs in ({"first": 0}, {"last": -1}, {"range_spec": "3:3"}, {"range_spec": "2:1"}, {"first": 1, "last": 1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                rdi_recover.build_slice_plan(source, **kwargs)

        result = subprocess.run(
            [sys.executable, "-m", "rdi_recover", "slice", str(source), "--first", "1", "--last", "1", "--output", str(self.temp_dir / "out.000")],
            capture_output=True,
            text=True,
            check=False,
            env=self.uninstalled_subprocess_env,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not allowed with argument", result.stderr)

    def test_slice_dry_run_writes_nothing_and_reports_trailing_data_safely(self) -> None:
        base = datetime(2024, 1, 1)
        source = self.temp_dir / "trailing.000"
        write_file(source, [build_pd0_like_ensemble(1, base), build_pd0_like_ensemble(2, base + timedelta(seconds=1)), b"truncated"])
        output = self.temp_dir / "should_not_exist.000"

        result = subprocess.run(
            [sys.executable, "-m", "rdi_recover", "slice", str(source), "--last", "1", "--dry-run"],
            capture_output=True,
            text=True,
            check=False,
            env=self.uninstalled_subprocess_env,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Trailing/unparsed bytes after final complete ensemble: 9", result.stdout)
        self.assertIn("DRY RUN: no output file written.", result.stdout)
        self.assertFalse(output.exists())

        plan = rdi_recover.build_slice_plan(source, last=1)
        with self.assertRaises(ValueError):
            rdi_recover.write_slice_output(plan, output)
        self.assertFalse(output.exists())

    def test_slice_rejects_input_as_output_and_existing_output(self) -> None:
        base = datetime(2024, 1, 1)
        source = self.temp_dir / "source.000"
        write_file(source, [build_pd0_like_ensemble(1, base), build_pd0_like_ensemble(2, base + timedelta(seconds=1))])
        plan = rdi_recover.build_slice_plan(source, first=1)
        with self.assertRaises(ValueError):
            rdi_recover.write_slice_output(plan, source)

        existing = self.temp_dir / "existing.000"
        existing.write_bytes(b"do not replace")
        with self.assertRaises(ValueError):
            rdi_recover.write_slice_output(plan, existing)
        self.assertEqual(existing.read_bytes(), b"do not replace")

    def test_slice_bins_trims_standard_fixture_and_preserves_retained_payloads(self) -> None:
        source = Path(__file__).resolve().parents[1] / "test_data" / "stnr0877" / "stnr0877_LADCPM.000"
        output = self.temp_dir / "trimmed.000"
        plan = rdi_recover.build_bin_trim_plan(source, 15)

        self.assertEqual(len(plan.inventory.ensembles), 4520)
        self.assertEqual((plan.source_cells, plan.resulting_cells, plan.beam_count), (30, 15, 4))
        self.assertEqual(plan.cell_size_cm, 800)
        self.assertEqual((plan.source_ensemble_bytes, plan.resulting_ensemble_bytes), (841, 541))
        self.assertEqual(plan.removed_bytes_per_ensemble, 300)
        self.assertEqual(plan.expected_output_bytes, 2445320)

        validation = rdi_recover.write_bin_trim_output(plan, output)

        self.assertFalse(validation.issues)
        self.assertEqual(validation.valid_count, 4520)
        self.assertEqual(output.stat().st_size, 2445320)
        output_inventory = rdi_recover.inventory_file(output)
        self.assertEqual(len(output_inventory.ensembles), 4520)
        self.assertTrue(all(ensemble.total_bytes == 541 for ensemble in output_inventory.ensembles))
        self.assertTrue(all(ensemble.stored_checksum == ensemble.calculated_checksum for ensemble in output_inventory.ensembles))

    def test_slice_bins_dry_run_reports_detected_configuration_without_writing(self) -> None:
        source = Path(__file__).resolve().parents[1] / "test_data" / "stnr0877" / "stnr0877_LADCPM.000"
        output = self.temp_dir / "not-written.000"
        result = subprocess.run(
            [sys.executable, "-m", "rdi_recover", "slice-bins", str(source), "--last", "15", "--dry-run"],
            capture_output=True,
            text=True,
            check=False,
            env=self.uninstalled_subprocess_env,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("Source depth cells: 30", result.stdout)
        self.assertIn("Resulting depth cells: 15", result.stdout)
        self.assertIn("Depth-cell size: 8.00 m", result.stdout)
        self.assertIn("Nominal removed outer range: 120.00 m", result.stdout)
        self.assertIn("Resulting ensemble bytes: 541", result.stdout)
        self.assertIn("Expected output bytes: 2445320", result.stdout)
        self.assertIn("DRY RUN: no output file written.", result.stdout)
        self.assertFalse(output.exists())

    def test_slice_bins_rejects_invalid_depth_cell_count(self) -> None:
        source = Path(__file__).resolve().parents[1] / "test_data" / "stnr0877" / "stnr0877_LADCPM.000"
        for value in (0, -1, 30, 31):
            with self.subTest(value=value), self.assertRaises(ValueError):
                rdi_recover.build_bin_trim_plan(source, value)


if __name__ == "__main__":
    unittest.main()
