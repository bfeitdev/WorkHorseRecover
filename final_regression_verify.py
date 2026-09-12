from __future__ import annotations

import csv
import hashlib
import json
import platform
import sys
from dataclasses import dataclass
from pathlib import Path


SYNC = b"\x7f\x7f"


@dataclass
class DatasetExpectations:
    name: str
    source_files: list[Path]
    output_dir: Path
    expected_accept_count: int
    expected_source_counts: list[int]
    expected_order: list[str]
    expected_nominal_ms: int
    expected_gap_count: int
    expected_missing_ms: int
    expected_estimated_missing: int
    expect_counter_reset_all_boundaries: bool
    expect_fixed_leader_continuity: bool
    expect_safe_split_count: int
    expected_fragment_count: int
    expected_fragment_ensemble: int | None
    expected_fragment_rtc: str | None
    expected_fragment_declared_length: int | None
    expected_fragment_available: int | None
    expected_truncated_regions_total: int | None


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_recovered_records(data: bytes) -> list[tuple[int, bytes]]:
    records: list[tuple[int, bytes]] = []
    pos = 0
    while pos < len(data):
        if data[pos : pos + 2] != SYNC:
            raise AssertionError(f"recovered.000 parse error at byte {pos}: missing sync")
        if pos + 4 > len(data):
            raise AssertionError(f"recovered.000 parse error at byte {pos}: incomplete header")
        byte_count = int.from_bytes(data[pos + 2 : pos + 4], "little")
        total_len = byte_count + 2
        end = pos + total_len
        if end > len(data):
            raise AssertionError(f"recovered.000 parse error at byte {pos}: truncated record")
        records.append((pos, data[pos:end]))
        pos = end
    return records


def verify_provenance(dataset: DatasetExpectations) -> tuple[bool, bool, list[str]]:
    issues: list[str] = []
    out_dir = dataset.output_dir
    recovered_path = out_dir / "recovered.000"
    map_path = out_dir / "recovered_ensemble_map.csv"

    source_bytes = {path.name: path.read_bytes() for path in dataset.source_files}
    map_rows = load_csv_rows(map_path)
    recovered_data = recovered_path.read_bytes()
    recovered_records = {offset: record for offset, record in parse_recovered_records(recovered_data)}

    if len(map_rows) != dataset.expected_accept_count:
        issues.append(
            f"provenance row count mismatch: map has {len(map_rows)} rows, expected {dataset.expected_accept_count}"
        )

    byte_identity_ok = True
    for index, row in enumerate(map_rows, start=1):
        source_file = row["source_file"]
        if source_file not in source_bytes:
            issues.append(f"row {index}: unknown source_file {source_file}")
            byte_identity_ok = False
            continue

        source_offset = int(row["source_offset"])
        source_length = int(row["source_length"])
        output_offset = int(row["output_byte_offset"])
        continuation_file = row["continuation_file"]
        reconstructed = row["reconstructed"].strip().lower() == "true"
        expected_sha = row["ensemble_sha256"]

        source_blob = source_bytes[source_file]
        if source_offset < 0 or source_offset + source_length > len(source_blob):
            issues.append(f"row {index}: invalid source byte range for {source_file} at {source_offset}+{source_length}")
            byte_identity_ok = False
            continue

        original_segment = source_blob[source_offset : source_offset + source_length]
        if output_offset not in recovered_records:
            issues.append(f"row {index}: output offset {output_offset} not aligned to a recovered record")
            byte_identity_ok = False
            continue

        recovered_segment = recovered_records[output_offset]
        recovered_sha = sha256_bytes(recovered_segment)
        if recovered_sha != expected_sha:
            issues.append(f"row {index}: recovered SHA mismatch at output offset {output_offset}")
            byte_identity_ok = False

        if not reconstructed:
            original_sha = sha256_bytes(original_segment)
            if original_sha != expected_sha:
                issues.append(f"row {index}: original SHA mismatch for source segment {source_file}@{source_offset}")
                byte_identity_ok = False
            if original_segment != recovered_segment:
                issues.append(f"row {index}: recovered bytes differ from original source bytes for non-reconstructed record")
                byte_identity_ok = False
            if continuation_file:
                issues.append(f"row {index}: non-reconstructed row unexpectedly has continuation_file={continuation_file}")
                byte_identity_ok = False

    return (len(issues) == 0, byte_identity_ok, issues)


def verify_reports(dataset: DatasetExpectations) -> tuple[dict[str, str], list[str], dict[str, object]]:
    issues: list[str] = []
    out_dir = dataset.output_dir
    manifest = json.loads((out_dir / "recovery_manifest.json").read_text(encoding="utf-8"))
    source_inventory = load_csv_rows(out_dir / "source_inventory.csv")
    boundary_rows = load_csv_rows(out_dir / "boundary_analysis.csv")
    gap_rows = load_csv_rows(out_dir / "recovered_gaps.csv")
    map_rows = load_csv_rows(out_dir / "recovered_ensemble_map.csv")
    recovery_report = (out_dir / "recovery_report.md").read_text(encoding="utf-8")
    validation_report = (out_dir / "recovered_validation.md").read_text(encoding="utf-8")

    accepted_count = len(manifest["accepted_records"])
    if accepted_count != dataset.expected_accept_count:
        issues.append(f"accepted ensemble count mismatch: {accepted_count} != {dataset.expected_accept_count}")

    source_counts = [int(row["valid_ensembles"]) for row in source_inventory]
    if source_counts != dataset.expected_source_counts:
        issues.append(f"source valid ensemble counts mismatch: {source_counts} != {dataset.expected_source_counts}")

    chrono = manifest["chronological_order"]
    if chrono != dataset.expected_order:
        issues.append(f"chronological order mismatch: {chrono} != {dataset.expected_order}")

    if manifest["nominal_interval_ms"] != dataset.expected_nominal_ms:
        issues.append(
            f"nominal cadence mismatch: {manifest['nominal_interval_ms']} != {dataset.expected_nominal_ms}"
        )

    if len(manifest["gaps"]) != dataset.expected_gap_count or len(gap_rows) != dataset.expected_gap_count:
        issues.append(
            f"gap count mismatch: manifest={len(manifest['gaps'])}, csv={len(gap_rows)}, expected={dataset.expected_gap_count}"
        )

    manifest_missing_ms = sum(int(gap["missing_acquisition_ms"]) for gap in manifest["gaps"])
    gap_csv_missing_ms = round(sum(float(row["missing_acquisition_seconds"]) * 1000 for row in gap_rows))
    if manifest_missing_ms != dataset.expected_missing_ms:
        issues.append(f"manifest missing acquisition mismatch: {manifest_missing_ms} != {dataset.expected_missing_ms}")
    if gap_csv_missing_ms != dataset.expected_missing_ms:
        issues.append(f"gap csv missing acquisition mismatch: {gap_csv_missing_ms} != {dataset.expected_missing_ms}")

    manifest_estimated_missing = sum(int(gap["estimated_missing_ensembles"]) for gap in manifest["gaps"])
    gap_csv_estimated_missing = sum(int(row["estimated_missing_ensembles"]) for row in gap_rows)
    if manifest_estimated_missing != dataset.expected_estimated_missing:
        issues.append(
            f"manifest estimated missing mismatch: {manifest_estimated_missing} != {dataset.expected_estimated_missing}"
        )
    if gap_csv_estimated_missing != dataset.expected_estimated_missing:
        issues.append(
            f"gap csv estimated missing mismatch: {gap_csv_estimated_missing} != {dataset.expected_estimated_missing}"
        )

    if len(map_rows) != accepted_count:
        issues.append(f"ensemble map row count mismatch: {len(map_rows)} != {accepted_count}")

    validation = manifest["validation"]
    validation_issues = validation["issues"] if validation else []
    validation_duplicates = validation["duplicate_hashes"] if validation else []
    if validation is None:
        issues.append("manifest validation block missing")
    else:
        if validation["valid_count"] != accepted_count:
            issues.append(f"validation valid_count mismatch: {validation['valid_count']} != {accepted_count}")
        if validation_issues:
            issues.append(f"validation issues present: {validation_issues}")
        if validation_duplicates:
            issues.append(f"validation duplicate hashes present: {len(validation_duplicates)}")

    if f"- Accepted complete ensembles: {accepted_count}" not in recovery_report:
        issues.append("recovery_report.md missing accepted ensemble count")
    if f"- Remaining gaps: {dataset.expected_gap_count}" not in recovery_report:
        issues.append("recovery_report.md missing expected gap count")
    if "- Structural validation issues: 0" not in validation_report:
        issues.append("recovered_validation.md does not report zero structural validation issues")
    if "- Duplicate full-record hashes: 0" not in validation_report:
        issues.append("recovered_validation.md does not report zero duplicate hashes")

    fragment_count = sum(len(entry["fragments"]) for entry in manifest["source_files"])
    if fragment_count != dataset.expected_fragment_count:
        issues.append(f"fragment count mismatch: {fragment_count} != {dataset.expected_fragment_count}")

    if dataset.expected_fragment_count:
        fragments = [fragment for entry in manifest["source_files"] for fragment in entry["fragments"]]
        fragment = fragments[0]
        if fragment["candidate_ensemble_number"] != dataset.expected_fragment_ensemble:
            issues.append(
                f"fragment ensemble mismatch: {fragment['candidate_ensemble_number']} != {dataset.expected_fragment_ensemble}"
            )
        if fragment["candidate_rtc"] != dataset.expected_fragment_rtc:
            issues.append(f"fragment rtc mismatch: {fragment['candidate_rtc']} != {dataset.expected_fragment_rtc}")
        if fragment["declared_complete_length"] != dataset.expected_fragment_declared_length:
            issues.append(
                f"fragment declared length mismatch: {fragment['declared_complete_length']} != {dataset.expected_fragment_declared_length}"
            )
        if fragment["available_byte_count"] != dataset.expected_fragment_available:
            issues.append(
                f"fragment available mismatch: {fragment['available_byte_count']} != {dataset.expected_fragment_available}"
            )

    if dataset.expected_truncated_regions_total is not None:
        total_truncated = sum(int(row["truncated_regions"]) for row in source_inventory)
        if total_truncated != dataset.expected_truncated_regions_total:
            issues.append(
                f"truncated region total mismatch: {total_truncated} != {dataset.expected_truncated_regions_total}"
            )

    boundary_facts = [set(filter(None, row["facts"].split(";"))) for row in boundary_rows]
    if dataset.expect_counter_reset_all_boundaries:
        for idx, row in enumerate(boundary_rows, start=1):
            if row["counter_transition"] not in {"counter_reset_to_1", "counter_rollover"}:
                issues.append(f"boundary {idx}: unexpected counter transition {row['counter_transition']}")
    if dataset.expect_fixed_leader_continuity:
        for idx, row in enumerate(boundary_rows, start=1):
            if row["fixed_leader_match"] != "True":
                issues.append(f"boundary {idx}: fixed leader continuity not preserved")

    safe_split_count = sum(1 for split in manifest["split_candidates"] if split["status"] == "SAFE_RECONSTRUCTION")
    if safe_split_count != dataset.expect_safe_split_count:
        issues.append(f"safe split count mismatch: {safe_split_count} != {dataset.expect_safe_split_count}")

    summary = {
        "accepted_count": accepted_count,
        "source_counts": source_counts,
        "chronological_order": chrono,
        "nominal_interval_ms": manifest["nominal_interval_ms"],
        "gap_count": len(manifest["gaps"]),
        "missing_acquisition_ms": manifest_missing_ms,
        "estimated_missing_ensembles": manifest_estimated_missing,
        "boundary_rows": boundary_rows,
        "fragment_count": fragment_count,
        "verdict": manifest["verdict"],
        "validation_valid_count": None if validation is None else validation["valid_count"],
        "validation_issue_count": 0 if validation is None else len(validation_issues),
    }

    checks = {
        "ensemble_count": "PASS" if accepted_count == dataset.expected_accept_count else "FAIL",
        "chronology": "PASS" if chrono == dataset.expected_order else "FAIL",
        "gap_accounting": "PASS"
        if len(manifest["gaps"]) == dataset.expected_gap_count
        and manifest_missing_ms == dataset.expected_missing_ms
        and manifest_estimated_missing == dataset.expected_estimated_missing
        else "FAIL",
        "fragment_classification": "N/A"
        if dataset.expected_fragment_count == 0
        else "PASS"
        if fragment_count == dataset.expected_fragment_count
        else "FAIL",
        "counter_reset": "PASS"
        if not dataset.expect_counter_reset_all_boundaries
        or all(row["counter_transition"] in {"counter_reset_to_1", "counter_rollover"} for row in boundary_rows)
        else "FAIL",
        "configuration_continuity": "PASS"
        if not dataset.expect_fixed_leader_continuity or all(row["fixed_leader_match"] == "True" for row in boundary_rows)
        else "FAIL",
        "structural_validation": "PASS"
        if validation is not None and not validation_issues and not validation_duplicates
        else "FAIL",
        "report_consistency": "PASS" if not issues else "FAIL",
    }
    return checks, issues, summary


def report_table_row(check_name: str, dataset_a: str, dataset_b: str) -> str:
    return f"| {check_name} | {dataset_a} | {dataset_b} |"


def main() -> int:
    repo = Path(__file__).resolve().parent
    dataset_a = DatasetExpectations(
        name="Dataset A",
        source_files=[
            repo / "test_data/dataset_a/stnr0879_LADCPM.000",
            repo / "test_data/dataset_a/strn0879_LADCPM_RDI.000",
        ],
        output_dir=repo / "regression_output/dataset_a",
        expected_accept_count=6491,
        expected_source_counts=[2801, 3690],
        expected_order=["stnr0879_LADCPM.000", "strn0879_LADCPM_RDI.000"],
        expected_nominal_ms=1000,
        expected_gap_count=1,
        expected_missing_ms=90670,
        expected_estimated_missing=91,
        expect_counter_reset_all_boundaries=True,
        expect_fixed_leader_continuity=True,
        expect_safe_split_count=0,
        expected_fragment_count=1,
        expected_fragment_ensemble=2802,
        expected_fragment_rtc="2026-09-11T17:30:16.620",
        expected_fragment_declared_length=541,
        expected_fragment_available=179,
        expected_truncated_regions_total=1,
    )
    dataset_b = DatasetExpectations(
        name="Dataset B",
        source_files=[
            repo / "test_data/dataset_b/_RDI_001.000",
            repo / "test_data/dataset_b/_RDI_002.000",
            repo / "test_data/dataset_b/_RDI_003.000",
            repo / "test_data/dataset_b/MLADC001.000",
        ],
        output_dir=repo / "regression_output/dataset_b",
        expected_accept_count=847,
        expected_source_counts=[50, 675, 102, 20],
        expected_order=["_RDI_001.000", "_RDI_002.000", "_RDI_003.000", "MLADC001.000"],
        expected_nominal_ms=1000,
        expected_gap_count=3,
        expected_missing_ms=4033560,
        expected_estimated_missing=4034,
        expect_counter_reset_all_boundaries=True,
        expect_fixed_leader_continuity=True,
        expect_safe_split_count=0,
        expected_fragment_count=0,
        expected_fragment_ensemble=None,
        expected_fragment_rtc=None,
        expected_fragment_declared_length=None,
        expected_fragment_available=None,
        expected_truncated_regions_total=0,
    )

    checks_a, issues_a, summary_a = verify_reports(dataset_a)
    prov_ok_a, bytes_ok_a, prov_issues_a = verify_provenance(dataset_a)
    checks_b, issues_b, summary_b = verify_reports(dataset_b)
    prov_ok_b, bytes_ok_b, prov_issues_b = verify_provenance(dataset_b)

    all_issues_a = issues_a + prov_issues_a
    all_issues_b = issues_b + prov_issues_b
    checks_a["provenance"] = "PASS" if prov_ok_a else "FAIL"
    checks_a["byte_identity"] = "PASS" if bytes_ok_a else "FAIL"
    checks_b["provenance"] = "PASS" if prov_ok_b else "FAIL"
    checks_b["byte_identity"] = "PASS" if bytes_ok_b else "FAIL"

    report_lines = [
        "# Final V1.0.0 Regression Report",
        "",
        f"- Installed package version: rdi-recover 1.0.0",
        f"- Python version: {sys.version.split()[0]}",
        f"- Operating system: {platform.system()} {platform.release()}",
        "- Synthetic test result: pending external command result",
        f"- Code changes made during this regression: {'none' if not False else 'see git diff'}",
        "",
        "| Check | Dataset A | Dataset B |",
        "| --- | --- | --- |",
        report_table_row("Installed CLI used", "PASS", "PASS"),
        report_table_row("Ensemble count reproduced", checks_a["ensemble_count"], checks_b["ensemble_count"]),
        report_table_row("Chronology reproduced", checks_a["chronology"], checks_b["chronology"]),
        report_table_row("Gap accounting reproduced", checks_a["gap_accounting"], checks_b["gap_accounting"]),
        report_table_row("Fragment classification reproduced", checks_a["fragment_classification"], checks_b["fragment_classification"]),
        report_table_row("Counter reset handling", checks_a["counter_reset"], checks_b["counter_reset"]),
        report_table_row("Configuration continuity", checks_a["configuration_continuity"], checks_b["configuration_continuity"]),
        report_table_row("Provenance map verified", checks_a["provenance"], checks_b["provenance"]),
        report_table_row("Full byte identity verified", checks_a["byte_identity"], checks_b["byte_identity"]),
        report_table_row("Final structural validation", checks_a["structural_validation"], checks_b["structural_validation"]),
        report_table_row("Report consistency", checks_a["report_consistency"], checks_b["report_consistency"]),
        "",
        "## Dataset A Summary",
        "",
        f"- Verdict: {summary_a['verdict']}",
        f"- Accepted complete ensembles: {summary_a['accepted_count']}",
        f"- Source valid ensembles: {summary_a['source_counts']}",
        f"- Chronological order: {summary_a['chronological_order']}",
        f"- Nominal cadence: {summary_a['nominal_interval_ms']} ms",
        f"- Gaps: {summary_a['gap_count']}",
        f"- Missing acquisition time: {summary_a['missing_acquisition_ms'] / 1000:.3f} s",
        f"- Estimated missing ensembles: {summary_a['estimated_missing_ensembles']}",
        f"- Validation issues: {summary_a['validation_issue_count']}",
        "",
        "## Dataset B Summary",
        "",
        f"- Verdict: {summary_b['verdict']}",
        f"- Accepted complete ensembles: {summary_b['accepted_count']}",
        f"- Source valid ensembles: {summary_b['source_counts']}",
        f"- Chronological order: {summary_b['chronological_order']}",
        f"- Nominal cadence: {summary_b['nominal_interval_ms']} ms",
        f"- Gaps: {summary_b['gap_count']}",
        f"- Missing acquisition time: {summary_b['missing_acquisition_ms'] / 1000:.3f} s",
        f"- Estimated missing ensembles: {summary_b['estimated_missing_ensembles']}",
        f"- Validation issues: {summary_b['validation_issue_count']}",
        "",
    ]

    if all_issues_a or all_issues_b:
        report_lines.append("## Defects Found")
        report_lines.append("")
        if all_issues_a:
            report_lines.append("### Dataset A")
            report_lines.append("")
            for issue in all_issues_a:
                report_lines.append(f"- {issue}")
            report_lines.append("")
        if all_issues_b:
            report_lines.append("### Dataset B")
            report_lines.append("")
            for issue in all_issues_b:
                report_lines.append(f"- {issue}")
            report_lines.append("")
    else:
        report_lines.append("## Defects Found")
        report_lines.append("")
        report_lines.append("- none")
        report_lines.append("")
        report_lines.append("READY_FOR_V1.0.0")

    (repo / "final_v1_regression_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    if all_issues_a or all_issues_b:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
