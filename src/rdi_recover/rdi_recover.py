#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import struct
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

from ._version import __version__


SYNC = b"\x7f\x7f"
FIXED_LEADER_ID = b"\x00\x00"
VARIABLE_LEADER_ID = b"\x80\x00"
VELOCITY_ID = b"\x00\x01"
CORRELATION_MAGNITUDE_ID = b"\x00\x02"
ECHO_INTENSITY_ID = b"\x00\x03"
PERCENT_GOOD_ID = b"\x00\x04"
BOTTOM_TRACK_ID = b"\x00\x06"

BIN_DEPENDENT_BLOCKS = {
    VELOCITY_ID: ("Velocity", 2),
    CORRELATION_MAGNITUDE_ID: ("Correlation Magnitude", 1),
    ECHO_INTENSITY_ID: ("Echo Intensity", 1),
    PERCENT_GOOD_ID: ("Percent Good", 1),
}
SUPPORTED_BIN_TRIM_BLOCKS = {FIXED_LEADER_ID, VARIABLE_LEADER_ID, *BIN_DEPENDENT_BLOCKS, BOTTOM_TRACK_ID}

BOUNDARY_STATUS_ORDER = [
    "CONFLICT",
    "AMBIGUOUS",
    "SAFE_SPLIT_RECONSTRUCTION",
    "CONFIGURATION_CHANGE",
    "EXACT_OVERLAP",
    "PARTIAL_OVERLAP",
    "GAP",
    "CLEAN_WITH_COUNTER_RESET",
    "CLEAN_CONTIGUOUS",
    "TRUNCATED_PREVIOUS_FILE",
    "TRUNCATED_NEXT_FILE",
    "UNRECOVERABLE_FRAGMENT",
]

FINAL_VERDICTS = [
    "PASS",
    "PASS_WITH_GAPS",
    "PASS_WITH_UNRECOVERABLE_FRAGMENTS",
    "MANUAL_REVIEW_REQUIRED",
    "FAIL",
]

AUTO_EXCLUDED_DIR_NAMES = {"output", "output_multi", "recovered_output"}
AUTO_EXCLUDED_FILE_NAMES = {"recovered.000"}


@dataclass(frozen=True)
class Ensemble:
    file_label: str
    start: int
    total_bytes: int
    byte_count: int
    number_of_data_types: int
    offsets: tuple[int, ...]
    ensemble_number_lsb: int
    ensemble_number_msb: int
    ensemble_number: int
    rtc_text: str
    rtc_valid: bool
    rtc_dt: datetime | None
    fixed_leader_sha256: str
    fixed_leader_hex: str
    ensemble_sha256: str
    stored_checksum: int
    calculated_checksum: int
    ids: tuple[str, ...]

    @property
    def end_exclusive(self) -> int:
        return self.start + self.total_bytes


@dataclass(frozen=True)
class SliceEnsemble:
    """A complete ensemble addressed by its physical, 1-based file position."""

    physical_index: int
    start: int
    end_exclusive: int
    length: int
    rdi_ensemble_number: int | None
    structural_status: str
    checksum_status: str


@dataclass(frozen=True)
class SlicePlan:
    input_path: Path
    inventory: FileInventory
    ensembles: list[SliceEnsemble]
    removed_indexes: tuple[int, ...]
    retained_indexes: tuple[int, ...]
    unparsed_bytes: int
    trailing_bytes: int


@dataclass(frozen=True)
class SliceValidation:
    valid_count: int
    issues: list[str]
    retained_bytes_match: bool


@dataclass(frozen=True)
class BinTrimBlock:
    block_id: bytes
    name: str
    offset: int
    length: int
    bytes_per_bin: int | None


@dataclass(frozen=True)
class BinTrimPlan:
    input_path: Path
    inventory: FileInventory
    remove_last: int
    source_cells: int
    resulting_cells: int
    beam_count: int
    cell_size_cm: int
    blocks: tuple[BinTrimBlock, ...]
    source_ensemble_bytes: int
    resulting_ensemble_bytes: int
    removed_bytes_per_ensemble: int
    expected_output_bytes: int


@dataclass(frozen=True)
class BinTrimValidation:
    valid_count: int
    issues: list[str]


@dataclass(frozen=True)
class Region:
    file_label: str
    start: int
    end_exclusive: int
    classification: str
    reason: str
    candidate_sync: bool = False
    declared_total_bytes: int | None = None

    @property
    def length(self) -> int:
        return self.end_exclusive - self.start


@dataclass(frozen=True)
class FragmentInfo:
    file_label: str
    byte_offset: int
    available_byte_count: int
    declared_complete_length: int | None
    candidate_ensemble_number: int | None
    candidate_rtc: str | None
    decoded_offsets: tuple[int, ...]
    checksum_bytes_present: bool
    structural_status: str
    reason: str
    boundary_side: str


@dataclass(frozen=True)
class FileInventory:
    path: Path
    size_bytes: int
    ensembles: list[Ensemble]
    regions: list[Region]
    fragments: list[FragmentInfo]
    nominal_interval_ms: int | None
    fixed_leader_counts: dict[str, int]


@dataclass(frozen=True)
class BoundaryAnalysis:
    previous_file: str
    next_file: str
    facts: tuple[str, ...]
    primary_status: str
    previous_last_ensemble: int | None
    next_first_ensemble: int | None
    previous_last_rtc: str | None
    next_first_rtc: str | None
    elapsed_ms: int | None
    nominal_interval_ms: int | None
    missing_acquisition_ms: int | None
    estimated_missing_ensembles: int | None
    counter_transition: str
    fixed_leader_match: bool | None
    exact_duplicate_overlap: int
    conflicting_time_overlap: int
    trailing_bytes_previous: int
    leading_bytes_next: int
    trailing_region_previous: str
    leading_region_next: str
    configuration_changed: bool
    notes: tuple[str, ...]


@dataclass(frozen=True)
class SplitReconstruction:
    previous_file: str
    next_file: str
    previous_offset: int
    previous_available_bytes: int
    next_consumed_bytes: int
    declared_total_bytes: int
    candidate_ensemble_number: int | None
    candidate_rtc: str | None
    status: str
    reason: str
    stored_checksum_validates: bool
    fixed_leader_sha256: str | None
    ensemble_sha256: str | None
    bytes_data: bytes = field(repr=False, compare=False)


@dataclass(frozen=True)
class GapRecord:
    before_rtc: str
    after_rtc: str
    elapsed_ms: int
    expected_interval_ms: int
    missing_acquisition_ms: int
    estimated_missing_ensembles: int
    before_ensemble: int
    after_ensemble: int
    before_source: str
    after_source: str
    location: str


@dataclass(frozen=True)
class OutputRecord:
    source_file: str
    source_offset: int
    source_length: int
    ensemble_number: int
    rtc_text: str
    rtc_dt: datetime | None
    ensemble_sha256: str
    fixed_leader_sha256: str
    stored_checksum: int
    bytes_data: bytes = field(repr=False, compare=False)
    reconstructed: bool = False
    continuation_file: str | None = None
    continuation_offset: int | None = None
    continuation_length: int | None = None


@dataclass(frozen=True)
class ValidationResult:
    valid_count: int
    issues: list[str]
    duplicate_hashes: list[str]
    gaps: list[GapRecord]
    nominal_interval_ms: int | None


@dataclass(frozen=True)
class DatasetAnalysis:
    discovered_files: list[Path]
    ordered_files: list[FileInventory]
    boundaries: list[BoundaryAnalysis]
    split_candidates: list[SplitReconstruction]
    nominal_interval_ms: int | None
    configuration_changes: list[str]


@dataclass(frozen=True)
class CandidateDatasetGroup:
    group_id: int
    files: list[Path]
    discovery_basis: str


@dataclass(frozen=True)
class RecoveryResult:
    analysis: DatasetAnalysis
    accepted_records: list[OutputRecord]
    duplicate_removed: int
    conflict_messages: list[str]
    gaps: list[GapRecord]
    validation: ValidationResult | None
    verdict: str
    recovered_path: Path | None


def checksum_rdi(ensemble_bytes_without_checksum: bytes) -> int:
    return sum(ensemble_bytes_without_checksum) & 0xFFFF


def decode_bcd_or_binary_year(year_byte: int) -> int:
    year = 2000 + year_byte
    if year > 2050:
        year -= 100
    return year


def format_rtc(vl: bytes) -> tuple[str, bool, datetime | None]:
    try:
        year = decode_bcd_or_binary_year(vl[4])
        month = vl[5]
        day = vl[6]
        hour = vl[7]
        minute = vl[8]
        second = vl[9]
        hundredths = vl[10]
        stamp = datetime(year, month, day, hour, minute, second, hundredths * 10000)
        return stamp.isoformat(timespec="milliseconds"), True, stamp
    except (IndexError, ValueError):
        values = list(vl[4:11]) + [0] * max(0, 7 - len(vl[4:11]))
        return (
            f"raw:{values[0]:02d}-{values[1]:02d}-{values[2]:02d}T{values[3]:02d}:{values[4]:02d}:{values[5]:02d}.{values[6]:02d}",
            False,
            None,
        )


def parse_candidate(data: bytes, start: int, file_label: str) -> tuple[Ensemble | None, str, int | None]:
    if start + 6 > len(data):
        return None, "TRUNCATED_ENSEMBLE: incomplete header", None
    if data[start : start + 2] != SYNC:
        return None, "NON_PD0_DATA: missing sync", None
    byte_count = struct.unpack_from("<H", data, start + 2)[0]
    total_bytes = byte_count + 2
    if byte_count < 6:
        return None, f"NON_PD0_DATA: implausible byte count {byte_count}", total_bytes
    if start + total_bytes > len(data):
        return None, f"TRUNCATED_ENSEMBLE: declared {total_bytes} bytes beyond EOF", total_bytes
    number_of_data_types = data[start + 5]
    if number_of_data_types < 2 or number_of_data_types > 64:
        return None, f"NON_PD0_DATA: implausible data type count {number_of_data_types}", total_bytes
    header_len = 6 + 2 * number_of_data_types
    if header_len > byte_count:
        return None, "POSSIBLE_FRAGMENT: header length exceeds ensemble byte count", total_bytes
    offsets = tuple(struct.unpack_from("<" + "H" * number_of_data_types, data, start + 6))
    if offsets[0] != header_len:
        return None, f"POSSIBLE_FRAGMENT: first offset {offsets[0]} != header length {header_len}", total_bytes
    if any(off >= byte_count for off in offsets):
        return None, "POSSIBLE_FRAGMENT: data-type offset beyond checksum coverage", total_bytes
    if any(offsets[i] >= offsets[i + 1] for i in range(len(offsets) - 1)):
        return None, "POSSIBLE_FRAGMENT: data-type offsets not strictly increasing", total_bytes
    if data[start + offsets[0] : start + offsets[0] + 2] != FIXED_LEADER_ID:
        return None, "POSSIBLE_FRAGMENT: missing fixed leader at first offset", total_bytes
    if data[start + offsets[1] : start + offsets[1] + 2] != VARIABLE_LEADER_ID:
        return None, "POSSIBLE_FRAGMENT: missing variable leader at second offset", total_bytes
    fixed_leader_len = offsets[1] - offsets[0]
    if fixed_leader_len < 40:
        return None, f"POSSIBLE_FRAGMENT: short fixed leader length {fixed_leader_len}", total_bytes
    variable_leader_len = (offsets[2] - offsets[1]) if len(offsets) > 2 else (byte_count - offsets[1])
    if variable_leader_len < 18:
        return None, f"POSSIBLE_FRAGMENT: short variable leader length {variable_leader_len}", total_bytes
    ensemble_covered = data[start : start + byte_count]
    stored_checksum = struct.unpack_from("<H", data, start + byte_count)[0]
    calculated_checksum = checksum_rdi(ensemble_covered)
    if stored_checksum != calculated_checksum:
        return None, f"BAD_CHECKSUM: stored 0x{stored_checksum:04x} != calculated 0x{calculated_checksum:04x}", total_bytes
    vl = data[start + offsets[1] : start + offsets[1] + max(variable_leader_len, 13)]
    ensemble_number_lsb = struct.unpack_from("<H", vl, 2)[0]
    ensemble_number_msb = vl[11]
    ensemble_number = (ensemble_number_msb << 16) | ensemble_number_lsb
    rtc_text, rtc_valid, rtc_dt = format_rtc(vl)
    fixed_leader = data[start + offsets[0] : start + offsets[0] + fixed_leader_len]
    full_ensemble = data[start : start + total_bytes]
    return (
        Ensemble(
            file_label=file_label,
            start=start,
            total_bytes=total_bytes,
            byte_count=byte_count,
            number_of_data_types=number_of_data_types,
            offsets=offsets,
            ensemble_number_lsb=ensemble_number_lsb,
            ensemble_number_msb=ensemble_number_msb,
            ensemble_number=ensemble_number,
            rtc_text=rtc_text,
            rtc_valid=rtc_valid,
            rtc_dt=rtc_dt,
            fixed_leader_sha256=hashlib.sha256(fixed_leader).hexdigest(),
            fixed_leader_hex=fixed_leader.hex(),
            ensemble_sha256=hashlib.sha256(full_ensemble).hexdigest(),
            stored_checksum=stored_checksum,
            calculated_checksum=calculated_checksum,
            ids=tuple(data[start + off : start + off + 2].hex() for off in offsets),
        ),
        "VALID_ENSEMBLE",
        total_bytes,
    )


def merge_regions(regions: Iterable[Region]) -> list[Region]:
    ordered = sorted(regions, key=lambda r: (r.start, r.end_exclusive, r.classification, r.reason, r.candidate_sync))
    if not ordered:
        return []
    merged = [ordered[0]]
    for region in ordered[1:]:
        prev = merged[-1]
        if (
            prev.file_label == region.file_label
            and prev.classification == region.classification
            and prev.reason == region.reason
            and prev.candidate_sync == region.candidate_sync
            and prev.declared_total_bytes == region.declared_total_bytes
            and prev.end_exclusive == region.start
            and prev.classification != "VALID_ENSEMBLE"
        ):
            merged[-1] = Region(
                prev.file_label,
                prev.start,
                region.end_exclusive,
                prev.classification,
                prev.reason,
                prev.candidate_sync,
                prev.declared_total_bytes,
            )
        else:
            merged.append(region)
    return merged


def inspect_fragment_bytes(
    data: bytes,
    file_label: str,
    start: int,
    end_exclusive: int,
    structural_status: str,
    reason: str,
    boundary_side: str,
) -> FragmentInfo:
    available = max(0, end_exclusive - start)
    declared_total_bytes = None
    candidate_ensemble_number = None
    candidate_rtc = None
    decoded_offsets: tuple[int, ...] = ()
    checksum_bytes_present = False
    if available >= 4 and data[start : start + 2] == SYNC:
        byte_count = struct.unpack_from("<H", data, start + 2)[0]
        declared_total_bytes = byte_count + 2
        checksum_bytes_present = available >= declared_total_bytes
        if available >= 6:
            number_of_data_types = data[start + 5]
            header_len = 6 + 2 * number_of_data_types
            if 2 <= number_of_data_types <= 64 and available >= header_len:
                decoded_offsets = tuple(struct.unpack_from("<" + "H" * number_of_data_types, data, start + 6))
                if len(decoded_offsets) > 1:
                    vl_offset = decoded_offsets[1]
                    if available >= vl_offset + 13:
                        vl = data[start + vl_offset : start + vl_offset + 32]
                        candidate_ensemble_number = (vl[11] << 16) | struct.unpack_from("<H", vl, 2)[0]
                        candidate_rtc = format_rtc(vl)[0]
    return FragmentInfo(
        file_label=file_label,
        byte_offset=start,
        available_byte_count=available,
        declared_complete_length=declared_total_bytes,
        candidate_ensemble_number=candidate_ensemble_number,
        candidate_rtc=candidate_rtc,
        decoded_offsets=decoded_offsets,
        checksum_bytes_present=checksum_bytes_present,
        structural_status=structural_status,
        reason=reason,
        boundary_side=boundary_side,
    )


def collect_edge_fragments(data: bytes, regions: list[Region]) -> list[FragmentInfo]:
    fragments: list[FragmentInfo] = []
    if not regions:
        return fragments

    leading_candidates = [
        region
        for region in regions
        if region.classification != "VALID_ENSEMBLE" and region.start == 0
    ]
    if leading_candidates:
        best = min(
            leading_candidates,
            key=lambda region: (0 if region.classification == "TRUNCATED_ENSEMBLE" else 1, region.end_exclusive),
        )
        fragments.append(
            inspect_fragment_bytes(
                data,
                best.file_label,
                best.start,
                best.end_exclusive,
                best.classification,
                best.reason,
                "leading",
            )
        )

    trailing_candidates = [
        region
        for region in regions
        if region.classification != "VALID_ENSEMBLE" and region.end_exclusive == len(data)
    ]
    if trailing_candidates:
        best = min(
            trailing_candidates,
            key=lambda region: (0 if region.classification == "TRUNCATED_ENSEMBLE" else 1, -region.start),
        )
        fragments.append(
            inspect_fragment_bytes(
                data,
                best.file_label,
                best.start,
                best.end_exclusive,
                best.classification,
                best.reason,
                "trailing",
            )
        )
    return fragments


def median_positive_step_ms(ensembles: list[Ensemble]) -> int | None:
    deltas = []
    ordered = sorted(ensembles, key=lambda e: e.start)
    for prev, curr in zip(ordered, ordered[1:]):
        if prev.rtc_dt and curr.rtc_dt:
            delta = round((curr.rtc_dt - prev.rtc_dt).total_seconds() * 1000)
            if delta > 0:
                deltas.append(delta)
    if not deltas:
        return None
    return int(statistics.median(deltas))


def robust_nominal_interval_ms(deltas: list[int]) -> int | None:
    if not deltas:
        return None
    counts = Counter(deltas)
    median_value = statistics.median(deltas)
    return max(counts.items(), key=lambda item: (item[1], -abs(item[0] - median_value), -item[0]))[0]


def inventory_file(path: Path) -> FileInventory:
    data = path.read_bytes()
    valid: list[Ensemble] = []
    regions: list[Region] = []
    pos = 0
    while pos < len(data):
        hit = data.find(SYNC, pos)
        if hit == -1:
            if pos < len(data):
                regions.append(Region(path.name, pos, len(data), "NON_PD0_DATA", "no further sync bytes"))
            break
        if hit > pos:
            regions.append(Region(path.name, pos, hit, "NON_PD0_DATA", "bytes between validated candidates"))
        parsed, status, declared_total_bytes = parse_candidate(data, hit, path.name)
        if parsed is not None:
            valid.append(parsed)
            regions.append(Region(path.name, hit, parsed.end_exclusive, "VALID_ENSEMBLE", status, True, parsed.total_bytes))
            pos = parsed.end_exclusive
            continue
        classification, _, reason = status.partition(": ")
        if classification == "TRUNCATED_ENSEMBLE" and declared_total_bytes is not None:
            end = min(len(data), hit + declared_total_bytes)
        else:
            end = min(len(data), hit + 2)
        regions.append(Region(path.name, hit, end, classification, reason or status, True, declared_total_bytes))
        pos = hit + 1

    merged_regions = merge_regions(regions)
    return FileInventory(
        path=path,
        size_bytes=len(data),
        ensembles=valid,
        regions=merged_regions,
        fragments=collect_edge_fragments(data, merged_regions),
        nominal_interval_ms=median_positive_step_ms(valid),
        fixed_leader_counts=dict(Counter(e.fixed_leader_sha256 for e in valid)),
    )


def first_valid(inv: FileInventory) -> Ensemble | None:
    return inv.ensembles[0] if inv.ensembles else None


def last_valid(inv: FileInventory) -> Ensemble | None:
    return inv.ensembles[-1] if inv.ensembles else None


def leading_non_valid_bytes(inv: FileInventory) -> tuple[int, str]:
    if not inv.regions:
        return 0, "NONE"
    first_region = inv.regions[0]
    if first_region.classification == "VALID_ENSEMBLE" and first_region.start == 0:
        return 0, "NONE"
    if first_region.start == 0:
        return first_region.length, f"{first_region.classification}:{first_region.reason}"
    return first_region.start, "NON_PD0_DATA: bytes before first valid ensemble"


def trailing_non_valid_bytes(inv: FileInventory) -> tuple[int, str]:
    if not inv.regions:
        return 0, "NONE"
    last_region = inv.regions[-1]
    if last_region.classification == "VALID_ENSEMBLE" and last_region.end_exclusive == inv.size_bytes:
        return 0, "NONE"
    if last_region.end_exclusive == inv.size_bytes:
        return last_region.length, f"{last_region.classification}:{last_region.reason}"
    return inv.size_bytes - last_region.end_exclusive, "NON_PD0_DATA: bytes after last valid ensemble"


def sort_inventories_chronologically(inventories: list[FileInventory]) -> list[FileInventory]:
    def key(inv: FileInventory) -> tuple:
        first = first_valid(inv)
        if first and first.rtc_dt:
            return (0, first.rtc_dt, inv.path.name)
        if first:
            return (1, first.rtc_text, inv.path.name)
        return (2, inv.path.name, inv.path.name)

    return sorted(inventories, key=key)


def observed_global_nominal_interval(inventories: list[FileInventory]) -> int | None:
    deltas = []
    for inv in inventories:
        ordered = sorted(inv.ensembles, key=lambda e: e.start)
        for prev, curr in zip(ordered, ordered[1:]):
            if prev.rtc_dt and curr.rtc_dt:
                delta = round((curr.rtc_dt - prev.rtc_dt).total_seconds() * 1000)
                if delta > 0:
                    deltas.append(delta)
    return robust_nominal_interval_ms(deltas)


def choose_nominal_interval(a: FileInventory, b: FileInventory, global_nominal: int | None) -> int | None:
    candidates = [v for v in (a.nominal_interval_ms, b.nominal_interval_ms, global_nominal) if v is not None]
    return robust_nominal_interval_ms(candidates)


def classify_counter_transition(prev: Ensemble | None, curr: Ensemble | None) -> str:
    if prev is None or curr is None:
        return "unknown"
    if (
        prev.ensemble_number_lsb == 0xFFFF
        and curr.ensemble_number_lsb == 0
        and curr.ensemble_number_msb == (prev.ensemble_number_msb + 1) % 256
    ):
        return "counter_rollover"
    if curr.ensemble_number == prev.ensemble_number + 1:
        return "normal_increment"
    if curr.rtc_dt and prev.rtc_dt and curr.rtc_dt > prev.rtc_dt and curr.ensemble_number < prev.ensemble_number:
        if curr.ensemble_number == 1:
            return "counter_reset_to_1"
        return f"counter_reset_to_{curr.ensemble_number}"
    if curr.ensemble_number < prev.ensemble_number:
        return "backward_jump"
    if curr.ensemble_number > prev.ensemble_number + 1:
        return "forward_jump"
    return "nonstandard_transition"


def exact_overlap_pairs(first: FileInventory, second: FileInventory) -> list[tuple[Ensemble, Ensemble]]:
    by_hash = {e.ensemble_sha256: e for e in second.ensembles}
    return [(e, by_hash[e.ensemble_sha256]) for e in first.ensembles if e.ensemble_sha256 in by_hash]


def conflicting_time_overlaps(first: FileInventory, second: FileInventory) -> list[tuple[Ensemble, Ensemble]]:
    second_by_time: dict[str, list[Ensemble]] = defaultdict(list)
    for ensemble in second.ensembles:
        if ensemble.rtc_valid:
            second_by_time[ensemble.rtc_text].append(ensemble)
    overlaps = []
    for ensemble in first.ensembles:
        if not ensemble.rtc_valid:
            continue
        for other in second_by_time.get(ensemble.rtc_text, []):
            if other.ensemble_sha256 != ensemble.ensemble_sha256:
                overlaps.append((ensemble, other))
    return overlaps


def select_primary_status(facts: set[str]) -> str:
    for status in BOUNDARY_STATUS_ORDER:
        if status in facts:
            return status
    return "AMBIGUOUS"


def classify_boundary(
    a: FileInventory,
    b: FileInventory,
    global_nominal: int | None,
    split_candidates: list[SplitReconstruction],
) -> BoundaryAnalysis:
    prev = last_valid(a)
    curr = first_valid(b)
    elapsed_ms = None
    if prev and curr and prev.rtc_dt and curr.rtc_dt:
        elapsed_ms = round((curr.rtc_dt - prev.rtc_dt).total_seconds() * 1000)
    nominal_interval_ms = choose_nominal_interval(a, b, global_nominal)
    missing_acquisition_ms = None
    estimated_missing_ensembles = None
    if elapsed_ms is not None and nominal_interval_ms is not None:
        missing_acquisition_ms = max(0, elapsed_ms - nominal_interval_ms)
        estimated_missing_ensembles = max(0, round(missing_acquisition_ms / nominal_interval_ms))

    duplicates = exact_overlap_pairs(a, b)
    conflicting_overlaps = conflicting_time_overlaps(a, b)
    trailing_bytes_previous, trailing_region_previous = trailing_non_valid_bytes(a)
    leading_bytes_next, leading_region_next = leading_non_valid_bytes(b)
    fixed_match = None if prev is None or curr is None else (prev.fixed_leader_sha256 == curr.fixed_leader_sha256)
    counter_transition = classify_counter_transition(prev, curr)
    facts: set[str] = set()
    notes: list[str] = []

    if prev is None or curr is None:
        facts.add("UNRECOVERABLE_FRAGMENT")
        notes.append("one side has no valid complete ensembles")

    if duplicates and len(duplicates) == min(len(a.ensembles), len(b.ensembles)):
        facts.add("EXACT_OVERLAP")
        notes.append("all ensembles in the smaller side duplicate by full-record SHA256")
    elif duplicates:
        facts.add("PARTIAL_OVERLAP")
        notes.append(f"{len(duplicates)} exact duplicate complete ensembles overlap")

    if conflicting_overlaps:
        facts.add("CONFLICT")
        notes.append(f"{len(conflicting_overlaps)} RTC-identical but hash-different valid records overlap")

    if fixed_match is False:
        facts.add("CONFIGURATION_CHANGE")
        notes.append("fixed leader fingerprint changed across the boundary")

    if elapsed_ms is not None and nominal_interval_ms is not None:
        if abs(elapsed_ms - nominal_interval_ms) <= 20 and fixed_match:
            facts.add("CLEAN_CONTIGUOUS")
            notes.append("timestamps join at the observed nominal cadence")
        elif elapsed_ms > nominal_interval_ms:
            facts.add("GAP")
            notes.append("elapsed time exceeds the observed nominal cadence")

    if counter_transition.startswith("counter_reset") or counter_transition == "counter_rollover":
        facts.add("CLEAN_WITH_COUNTER_RESET")
        notes.append(f"counter transition classified as {counter_transition}")

    if trailing_region_previous.startswith("TRUNCATED_ENSEMBLE"):
        facts.add("TRUNCATED_PREVIOUS_FILE")
        notes.append("previous file ends with a truncated candidate")
    if leading_region_next.startswith("TRUNCATED_ENSEMBLE"):
        facts.add("TRUNCATED_NEXT_FILE")
        notes.append("next file begins with a truncated candidate")

    if any(candidate.status == "SAFE_RECONSTRUCTION" for candidate in split_candidates):
        facts.add("SAFE_SPLIT_RECONSTRUCTION")
        notes.append("cross-file split reconstruction validated with the original stored checksum")
    elif trailing_bytes_previous > 0 or leading_bytes_next > 0:
        facts.add("UNRECOVERABLE_FRAGMENT")
        notes.append("boundary damage remains after conservative split testing")

    if not facts:
        facts.add("AMBIGUOUS")
        notes.append("boundary does not fit a stronger structural classification")

    facts_tuple = tuple(sorted(facts, key=lambda item: BOUNDARY_STATUS_ORDER.index(item) if item in BOUNDARY_STATUS_ORDER else len(BOUNDARY_STATUS_ORDER)))
    return BoundaryAnalysis(
        previous_file=a.path.name,
        next_file=b.path.name,
        facts=facts_tuple,
        primary_status=select_primary_status(facts),
        previous_last_ensemble=None if prev is None else prev.ensemble_number,
        next_first_ensemble=None if curr is None else curr.ensemble_number,
        previous_last_rtc=None if prev is None else prev.rtc_text,
        next_first_rtc=None if curr is None else curr.rtc_text,
        elapsed_ms=elapsed_ms,
        nominal_interval_ms=nominal_interval_ms,
        missing_acquisition_ms=missing_acquisition_ms,
        estimated_missing_ensembles=estimated_missing_ensembles,
        counter_transition=counter_transition,
        fixed_leader_match=fixed_match,
        exact_duplicate_overlap=len(duplicates),
        conflicting_time_overlap=len(conflicting_overlaps),
        trailing_bytes_previous=trailing_bytes_previous,
        leading_bytes_next=leading_bytes_next,
        trailing_region_previous=trailing_region_previous,
        leading_region_next=leading_region_next,
        configuration_changed=(fixed_match is False),
        notes=tuple(notes),
    )


def cache_file_bytes(paths: Sequence[Path]) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in paths}


def last_complete_before(inv: FileInventory, offset: int) -> Ensemble | None:
    prior = [ensemble for ensemble in inv.ensembles if ensemble.end_exclusive <= offset]
    return prior[-1] if prior else None


def leading_prefix_limit(inv: FileInventory) -> int:
    if not inv.regions:
        return 0
    first_region = inv.regions[0]
    if first_region.classification == "VALID_ENSEMBLE":
        return first_region.start
    if first_region.start == 0:
        first_valid_ensemble = first_valid(inv)
        if first_valid_ensemble is not None:
            return first_valid_ensemble.start
        return first_region.end_exclusive
    return first_region.start


def attempt_cross_file_join(a: FileInventory, b: FileInventory, bytes_by_file: dict[str, bytes]) -> list[SplitReconstruction]:
    data_a = bytes_by_file[a.path.name]
    data_b = bytes_by_file[b.path.name]
    results: list[SplitReconstruction] = []
    prefix_limit = leading_prefix_limit(b)
    if prefix_limit <= 0:
        return results
    for region_a in a.regions:
        if region_a.classification != "TRUNCATED_ENSEMBLE" or region_a.end_exclusive != a.size_bytes:
            continue
        declared = region_a.declared_total_bytes
        if declared is None:
            continue
        available = len(data_a) - region_a.start
        missing = declared - available
        if missing <= 0 or missing > prefix_limit:
            results.append(
                SplitReconstruction(
                    previous_file=a.path.name,
                    next_file=b.path.name,
                    previous_offset=region_a.start,
                    previous_available_bytes=available,
                    next_consumed_bytes=max(0, missing),
                    declared_total_bytes=declared,
                    candidate_ensemble_number=None,
                    candidate_rtc=None,
                    status="REJECTED",
                    reason="required continuation bytes are not confined to the next file's leading fragment region",
                    stored_checksum_validates=False,
                    fixed_leader_sha256=None,
                    ensemble_sha256=None,
                    bytes_data=b"",
                )
            )
            continue
        candidate_bytes = data_a[region_a.start:] + data_b[:missing]
        parsed, status, _ = parse_candidate(candidate_bytes, 0, f"{a.path.name}+{b.path.name}")
        if parsed is None:
            results.append(
                SplitReconstruction(
                    previous_file=a.path.name,
                    next_file=b.path.name,
                    previous_offset=region_a.start,
                    previous_available_bytes=available,
                    next_consumed_bytes=missing,
                    declared_total_bytes=declared,
                    candidate_ensemble_number=None,
                    candidate_rtc=None,
                    status="REJECTED",
                    reason=status,
                    stored_checksum_validates=False,
                    fixed_leader_sha256=None,
                    ensemble_sha256=None,
                    bytes_data=b"",
                )
            )
            continue

        prev_complete = last_complete_before(a, region_a.start)
        next_complete = first_valid(b)
        chronology_ok = True
        if prev_complete and prev_complete.rtc_dt and parsed.rtc_dt and parsed.rtc_dt < prev_complete.rtc_dt:
            chronology_ok = False
        if next_complete and next_complete.rtc_dt and parsed.rtc_dt and parsed.rtc_dt > next_complete.rtc_dt:
            chronology_ok = False
        fixed_ok = True
        if prev_complete and parsed.fixed_leader_sha256 != prev_complete.fixed_leader_sha256:
            fixed_ok = False
        if next_complete and parsed.fixed_leader_sha256 != next_complete.fixed_leader_sha256:
            fixed_ok = False
        if not chronology_ok or not fixed_ok:
            reason_parts = []
            if not chronology_ok:
                reason_parts.append("candidate RTC is not plausible relative to neighboring complete ensembles")
            if not fixed_ok:
                reason_parts.append("candidate fixed leader does not match neighboring complete ensembles")
            results.append(
                SplitReconstruction(
                    previous_file=a.path.name,
                    next_file=b.path.name,
                    previous_offset=region_a.start,
                    previous_available_bytes=available,
                    next_consumed_bytes=missing,
                    declared_total_bytes=declared,
                    candidate_ensemble_number=parsed.ensemble_number,
                    candidate_rtc=parsed.rtc_text,
                    status="REJECTED",
                    reason="; ".join(reason_parts),
                    stored_checksum_validates=True,
                    fixed_leader_sha256=parsed.fixed_leader_sha256,
                    ensemble_sha256=parsed.ensemble_sha256,
                    bytes_data=b"",
                )
            )
            continue

        results.append(
            SplitReconstruction(
                previous_file=a.path.name,
                next_file=b.path.name,
                previous_offset=region_a.start,
                previous_available_bytes=available,
                next_consumed_bytes=missing,
                declared_total_bytes=declared,
                candidate_ensemble_number=parsed.ensemble_number,
                candidate_rtc=parsed.rtc_text,
                status="SAFE_RECONSTRUCTION",
                reason="declared length, offsets, IDs, chronology, and original stored checksum all validate",
                stored_checksum_validates=True,
                fixed_leader_sha256=parsed.fixed_leader_sha256,
                ensemble_sha256=parsed.ensemble_sha256,
                bytes_data=candidate_bytes,
            )
        )
    return results


def analyze_dataset(paths: Sequence[Path]) -> DatasetAnalysis:
    discovered_files = sorted(paths, key=lambda path: path.name)
    inventories = [inventory_file(path) for path in discovered_files]
    ordered_files = sort_inventories_chronologically(inventories)
    bytes_by_file = cache_file_bytes(discovered_files)
    global_nominal = observed_global_nominal_interval(ordered_files)
    split_candidates: list[SplitReconstruction] = []
    boundaries: list[BoundaryAnalysis] = []
    configuration_changes: list[str] = []
    for previous, next_file in zip(ordered_files, ordered_files[1:]):
        boundary_splits = attempt_cross_file_join(previous, next_file, bytes_by_file)
        split_candidates.extend(boundary_splits)
        boundary = classify_boundary(previous, next_file, global_nominal, boundary_splits)
        boundaries.append(boundary)
        if boundary.configuration_changed:
            configuration_changes.append(f"{boundary.previous_file} -> {boundary.next_file}")
    return DatasetAnalysis(
        discovered_files=discovered_files,
        ordered_files=ordered_files,
        boundaries=boundaries,
        split_candidates=split_candidates,
        nominal_interval_ms=global_nominal,
        configuration_changes=configuration_changes,
    )


def build_output_records(analysis: DatasetAnalysis) -> tuple[list[OutputRecord], int, list[str]]:
    bytes_by_file = cache_file_bytes([inv.path for inv in analysis.ordered_files])
    records: list[OutputRecord] = []
    for inventory in analysis.ordered_files:
        data = bytes_by_file[inventory.path.name]
        for ensemble in inventory.ensembles:
            records.append(
                OutputRecord(
                    source_file=inventory.path.name,
                    source_offset=ensemble.start,
                    source_length=ensemble.total_bytes,
                    ensemble_number=ensemble.ensemble_number,
                    rtc_text=ensemble.rtc_text,
                    rtc_dt=ensemble.rtc_dt,
                    ensemble_sha256=ensemble.ensemble_sha256,
                    fixed_leader_sha256=ensemble.fixed_leader_sha256,
                    stored_checksum=ensemble.stored_checksum,
                    bytes_data=data[ensemble.start : ensemble.end_exclusive],
                )
            )
    for split in analysis.split_candidates:
        if split.status != "SAFE_RECONSTRUCTION":
            continue
        parsed, _, _ = parse_candidate(split.bytes_data, 0, f"{split.previous_file}+{split.next_file}")
        if parsed is None:
            continue
        records.append(
            OutputRecord(
                source_file=split.previous_file,
                source_offset=split.previous_offset,
                source_length=split.previous_available_bytes,
                ensemble_number=parsed.ensemble_number,
                rtc_text=parsed.rtc_text,
                rtc_dt=parsed.rtc_dt,
                ensemble_sha256=parsed.ensemble_sha256,
                fixed_leader_sha256=parsed.fixed_leader_sha256,
                stored_checksum=parsed.stored_checksum,
                bytes_data=split.bytes_data,
                reconstructed=True,
                continuation_file=split.next_file,
                continuation_offset=0,
                continuation_length=split.next_consumed_bytes,
            )
        )

    records.sort(key=lambda record: (record.rtc_dt is None, record.rtc_dt or datetime.max, record.source_file, record.source_offset))
    seen_hashes: set[str] = set()
    seen_rtc_hashes: dict[str, set[str]] = defaultdict(set)
    accepted: list[OutputRecord] = []
    duplicate_removed = 0
    conflicts: list[str] = []
    for record in records:
        if record.ensemble_sha256 in seen_hashes:
            duplicate_removed += 1
            continue
        if not record.reconstructed and record.rtc_text in seen_rtc_hashes and seen_rtc_hashes[record.rtc_text] and record.ensemble_sha256 not in seen_rtc_hashes[record.rtc_text]:
            conflicts.append(
                f"conflicting valid overlap at RTC {record.rtc_text}: {record.source_file} offset {record.source_offset} differs from earlier accepted record(s)"
            )
        elif record.reconstructed and record.rtc_text in seen_rtc_hashes and seen_rtc_hashes[record.rtc_text] and record.ensemble_sha256 not in seen_rtc_hashes[record.rtc_text]:
            conflicts.append(
                f"conflicting reconstructed overlap at RTC {record.rtc_text}: {record.source_file} offset {record.source_offset} + {record.continuation_file} prefix differs from earlier accepted record(s)"
            )
        seen_rtc_hashes[record.rtc_text].add(record.ensemble_sha256)
        seen_hashes.add(record.ensemble_sha256)
        accepted.append(record)
    return accepted, duplicate_removed, conflicts


def build_gap_records_from_records(records: list[OutputRecord], nominal_interval_ms: int | None) -> list[GapRecord]:
    gaps: list[GapRecord] = []
    if nominal_interval_ms is None:
        return gaps
    for prev, curr in zip(records, records[1:]):
        if prev.rtc_dt is None or curr.rtc_dt is None:
            continue
        elapsed_ms = round((curr.rtc_dt - prev.rtc_dt).total_seconds() * 1000)
        if elapsed_ms <= nominal_interval_ms:
            continue
        missing_acquisition_ms = elapsed_ms - nominal_interval_ms
        estimated_missing_ensembles = max(0, round(missing_acquisition_ms / nominal_interval_ms))
        gaps.append(
            GapRecord(
                before_rtc=prev.rtc_text,
                after_rtc=curr.rtc_text,
                elapsed_ms=elapsed_ms,
                expected_interval_ms=nominal_interval_ms,
                missing_acquisition_ms=missing_acquisition_ms,
                estimated_missing_ensembles=estimated_missing_ensembles,
                before_ensemble=prev.ensemble_number,
                after_ensemble=curr.ensemble_number,
                before_source=prev.source_file,
                after_source=curr.source_file,
                location="within_file" if prev.source_file == curr.source_file else "file_boundary",
            )
        )
    return gaps


def validate_recovered_file(path: Path) -> ValidationResult:
    data = path.read_bytes()
    ensembles: list[Ensemble] = []
    issues: list[str] = []
    pos = 0
    while pos < len(data):
        parsed, status, _ = parse_candidate(data, pos, path.name)
        if parsed is None:
            issues.append(f"validation stopped at byte {pos}: {status}")
            break
        ensembles.append(parsed)
        pos = parsed.end_exclusive
    if pos != len(data):
        issues.append(f"validation did not consume file to EOF: stopped at {pos}, file size {len(data)}")
    duplicate_hashes = [digest for digest, count in Counter(e.ensemble_sha256 for e in ensembles).items() if count > 1]
    if duplicate_hashes:
        issues.append(f"duplicate full-record hashes present: {len(duplicate_hashes)}")
    nominal_interval = observed_global_nominal_interval([FileInventory(path, len(data), ensembles, [], [], median_positive_step_ms(ensembles), {})])
    gaps = build_gap_records_from_records(
        [
            OutputRecord(
                source_file=path.name,
                source_offset=ensemble.start,
                source_length=ensemble.total_bytes,
                ensemble_number=ensemble.ensemble_number,
                rtc_text=ensemble.rtc_text,
                rtc_dt=ensemble.rtc_dt,
                ensemble_sha256=ensemble.ensemble_sha256,
                fixed_leader_sha256=ensemble.fixed_leader_sha256,
                stored_checksum=ensemble.stored_checksum,
                bytes_data=b"",
            )
            for ensemble in ensembles
        ],
        nominal_interval,
    )
    return ValidationResult(
        valid_count=len(ensembles),
        issues=issues,
        duplicate_hashes=duplicate_hashes,
        gaps=gaps,
        nominal_interval_ms=nominal_interval,
    )


def determine_verdict(analysis: DatasetAnalysis, conflicts: list[str], gaps: list[GapRecord], validation: ValidationResult | None) -> str:
    if conflicts:
        return "MANUAL_REVIEW_REQUIRED"
    if any(boundary.primary_status == "AMBIGUOUS" for boundary in analysis.boundaries):
        return "MANUAL_REVIEW_REQUIRED"
    if validation is not None and validation.issues:
        return "FAIL"
    has_unrecoverable_fragments = any(
        "UNRECOVERABLE_FRAGMENT" in boundary.facts or "TRUNCATED_PREVIOUS_FILE" in boundary.facts or "TRUNCATED_NEXT_FILE" in boundary.facts
        for boundary in analysis.boundaries
    ) or any(inv.fragments for inv in analysis.ordered_files)
    if has_unrecoverable_fragments:
        return "PASS_WITH_UNRECOVERABLE_FRAGMENTS"
    if gaps:
        return "PASS_WITH_GAPS"
    return "PASS"


def should_exclude_discovered_path(path: Path, output_dir: Path | None) -> bool:
    resolved = path.resolve()
    if output_dir is not None:
        resolved_output = output_dir.resolve()
        if resolved == resolved_output or resolved_output in resolved.parents:
            return True
    if path.name in AUTO_EXCLUDED_FILE_NAMES:
        return True
    if any(parent.name in AUTO_EXCLUDED_DIR_NAMES for parent in path.parents):
        return True
    return False


def discover_directory_files(directory: Path, recursive: bool, output_dir: Path | None) -> list[Path]:
    iterator = directory.rglob("*.000") if recursive else directory.glob("*.000")
    discovered: dict[Path, Path] = {}
    for file_path in sorted(iterator):
        if should_exclude_discovered_path(file_path, output_dir):
            continue
        discovered[file_path.resolve()] = file_path
    return sorted(discovered.values(), key=lambda path: (str(path.parent), path.name))


def resolve_input_mode(inputs: Sequence[str]) -> tuple[list[Path], list[Path]]:
    explicit_files: list[Path] = []
    directories: list[Path] = []
    for raw in inputs:
        candidate = Path(raw)
        if candidate.is_dir():
            directories.append(candidate)
        elif candidate.is_file() and candidate.suffix.lower() == ".000":
            explicit_files.append(candidate)
    return explicit_files, directories


def discover_candidate_groups(inputs: Sequence[str], recursive: bool, output_dir: Path | None = None) -> list[CandidateDatasetGroup]:
    explicit_files, directories = resolve_input_mode(inputs)
    groups: list[CandidateDatasetGroup] = []
    next_group_id = 1

    if explicit_files:
        unique_files = sorted({path.resolve(): path for path in explicit_files}.values(), key=lambda path: path.name)
        groups.append(CandidateDatasetGroup(next_group_id, unique_files, "explicit_files"))
        next_group_id += 1

    grouped_by_parent: dict[Path, list[Path]] = defaultdict(list)
    for directory in directories:
        for file_path in discover_directory_files(directory, recursive=recursive, output_dir=output_dir):
            grouped_by_parent[file_path.parent.resolve()].append(file_path)

    for parent in sorted(grouped_by_parent, key=lambda path: str(path)):
        unique_files = sorted({path.resolve(): path for path in grouped_by_parent[parent]}.values(), key=lambda path: path.name)
        if not unique_files:
            continue
        basis = "directory_recursive_parent" if recursive else "directory_non_recursive"
        groups.append(CandidateDatasetGroup(next_group_id, unique_files, basis))
        next_group_id += 1

    return groups


def select_single_group_or_status(groups: list[CandidateDatasetGroup]) -> tuple[CandidateDatasetGroup | None, str | None]:
    if not groups:
        return None, "NO_INPUT_FILES_FOUND"
    if len(groups) > 1:
        return None, "MULTIPLE_CANDIDATE_DATASETS"
    return groups[0], None


def render_candidate_groups(groups: list[CandidateDatasetGroup]) -> str:
    lines = ["## Candidate Dataset Groups", ""]
    for group in groups:
        lines.append(f"- Group {group.group_id}: basis=`{group.discovery_basis}`, files={len(group.files)}")
        for path in group.files:
            lines.append(f"-   `{path}`")
    if not groups:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def write_source_inventory(path: Path, inventories: list[FileInventory]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "file",
                "size_bytes",
                "valid_ensembles",
                "first_valid_ensemble_number",
                "last_valid_ensemble_number",
                "first_valid_rtc",
                "last_valid_rtc",
                "first_valid_fixed_leader_sha256",
                "checksum_error_regions",
                "non_pd0_regions",
                "truncated_regions",
                "leading_fragment_bytes",
                "trailing_fragment_bytes",
                "nominal_interval_ms",
                "fragments",
            ]
        )
        for inv in inventories:
            first = first_valid(inv)
            last = last_valid(inv)
            leading_bytes, _ = leading_non_valid_bytes(inv)
            trailing_bytes, _ = trailing_non_valid_bytes(inv)
            writer.writerow(
                [
                    inv.path.name,
                    inv.size_bytes,
                    len(inv.ensembles),
                    "" if first is None else first.ensemble_number,
                    "" if last is None else last.ensemble_number,
                    "" if first is None else first.rtc_text,
                    "" if last is None else last.rtc_text,
                    "" if first is None else first.fixed_leader_sha256,
                    sum(1 for region in inv.regions if region.classification == "BAD_CHECKSUM"),
                    sum(1 for region in inv.regions if region.classification in {"NON_PD0_DATA", "POSSIBLE_FRAGMENT"}),
                    sum(1 for region in inv.regions if region.classification == "TRUNCATED_ENSEMBLE"),
                    leading_bytes,
                    trailing_bytes,
                    "" if inv.nominal_interval_ms is None else inv.nominal_interval_ms,
                    " | ".join(
                        f"{fragment.boundary_side}:{fragment.byte_offset}:{fragment.available_byte_count}:{fragment.structural_status}"
                        for fragment in inv.fragments
                    ),
                ]
            )


def write_boundary_csv(path: Path, boundaries: list[BoundaryAnalysis]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "previous_file",
                "next_file",
                "primary_status",
                "facts",
                "previous_last_ensemble",
                "next_first_ensemble",
                "previous_last_rtc",
                "next_first_rtc",
                "elapsed_ms",
                "nominal_interval_ms",
                "missing_acquisition_ms",
                "estimated_missing_ensembles",
                "counter_transition",
                "fixed_leader_match",
                "exact_duplicate_overlap",
                "conflicting_time_overlap",
                "trailing_bytes_previous",
                "leading_bytes_next",
                "trailing_region_previous",
                "leading_region_next",
                "configuration_changed",
                "notes",
            ]
        )
        for boundary in boundaries:
            writer.writerow(
                [
                    boundary.previous_file,
                    boundary.next_file,
                    boundary.primary_status,
                    ";".join(boundary.facts),
                    boundary.previous_last_ensemble,
                    boundary.next_first_ensemble,
                    boundary.previous_last_rtc,
                    boundary.next_first_rtc,
                    boundary.elapsed_ms,
                    boundary.nominal_interval_ms,
                    boundary.missing_acquisition_ms,
                    boundary.estimated_missing_ensembles,
                    boundary.counter_transition,
                    boundary.fixed_leader_match,
                    boundary.exact_duplicate_overlap,
                    boundary.conflicting_time_overlap,
                    boundary.trailing_bytes_previous,
                    boundary.leading_bytes_next,
                    boundary.trailing_region_previous,
                    boundary.leading_region_next,
                    boundary.configuration_changed,
                    " | ".join(boundary.notes),
                ]
            )


def write_gap_csv(path: Path, gaps: list[GapRecord]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "before_rtc",
                "after_rtc",
                "elapsed_seconds",
                "expected_interval_seconds",
                "missing_acquisition_seconds",
                "estimated_missing_ensembles",
                "before_ensemble",
                "after_ensemble",
                "before_source",
                "after_source",
                "location",
            ]
        )
        for gap in gaps:
            writer.writerow(
                [
                    gap.before_rtc,
                    gap.after_rtc,
                    f"{gap.elapsed_ms / 1000:.3f}",
                    f"{gap.expected_interval_ms / 1000:.3f}",
                    f"{gap.missing_acquisition_ms / 1000:.3f}",
                    gap.estimated_missing_ensembles,
                    gap.before_ensemble,
                    gap.after_ensemble,
                    gap.before_source,
                    gap.after_source,
                    gap.location,
                ]
            )


def write_recovered_ensemble_map(path: Path, accepted_records: list[OutputRecord]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "output_byte_offset",
                "source_file",
                "source_offset",
                "source_length",
                "continuation_file",
                "continuation_offset",
                "continuation_length",
                "reconstructed",
                "ensemble_sha256",
                "rtc",
                "ensemble_number",
            ]
        )
        output_offset = 0
        for record in accepted_records:
            writer.writerow(
                [
                    output_offset,
                    record.source_file,
                    record.source_offset,
                    record.source_length,
                    record.continuation_file or "",
                    "" if record.continuation_offset is None else record.continuation_offset,
                    "" if record.continuation_length is None else record.continuation_length,
                    record.reconstructed,
                    record.ensemble_sha256,
                    record.rtc_text,
                    record.ensemble_number,
                ]
            )
            output_offset += len(record.bytes_data)


def write_recovered_file(path: Path, accepted_records: list[OutputRecord]) -> None:
    with path.open("wb") as fh:
        for record in accepted_records:
            fh.write(record.bytes_data)


def split_to_dict(split: SplitReconstruction) -> dict[str, object]:
    return {
        "previous_file": split.previous_file,
        "next_file": split.next_file,
        "previous_offset": split.previous_offset,
        "previous_available_bytes": split.previous_available_bytes,
        "next_consumed_bytes": split.next_consumed_bytes,
        "declared_total_bytes": split.declared_total_bytes,
        "candidate_ensemble_number": split.candidate_ensemble_number,
        "candidate_rtc": split.candidate_rtc,
        "status": split.status,
        "reason": split.reason,
        "stored_checksum_validates": split.stored_checksum_validates,
        "fixed_leader_sha256": split.fixed_leader_sha256,
        "ensemble_sha256": split.ensemble_sha256,
    }


def fragment_to_dict(fragment: FragmentInfo) -> dict[str, object]:
    return asdict(fragment)


def boundary_to_dict(boundary: BoundaryAnalysis) -> dict[str, object]:
    result = asdict(boundary)
    result["facts"] = list(boundary.facts)
    result["notes"] = list(boundary.notes)
    return result


def gap_to_dict(gap: GapRecord) -> dict[str, object]:
    result = asdict(gap)
    result["elapsed_seconds"] = gap.elapsed_ms / 1000
    result["expected_interval_seconds"] = gap.expected_interval_ms / 1000
    result["missing_acquisition_seconds"] = gap.missing_acquisition_ms / 1000
    return result


def write_manifest(path: Path, result: RecoveryResult) -> None:
    validation = None
    if result.validation is not None:
        validation = {
            "valid_count": result.validation.valid_count,
            "issues": result.validation.issues,
            "duplicate_hashes": result.validation.duplicate_hashes,
            "nominal_interval_ms": result.validation.nominal_interval_ms,
            "gaps": [gap_to_dict(gap) for gap in result.validation.gaps],
        }
    payload = {
        "verdict": result.verdict,
        "discovered_files": [str(path_item) for path_item in result.analysis.discovered_files],
        "chronological_order": [inv.path.name for inv in result.analysis.ordered_files],
        "nominal_interval_ms": result.analysis.nominal_interval_ms,
        "configuration_changes": result.analysis.configuration_changes,
        "source_files": [
            {
                "file": inv.path.name,
                "size_bytes": inv.size_bytes,
                "valid_ensembles": len(inv.ensembles),
                "first_rtc": first_valid(inv).rtc_text if first_valid(inv) else None,
                "last_rtc": last_valid(inv).rtc_text if last_valid(inv) else None,
                "first_ensemble_number": first_valid(inv).ensemble_number if first_valid(inv) else None,
                "last_ensemble_number": last_valid(inv).ensemble_number if last_valid(inv) else None,
                "fixed_leader_fingerprints": inv.fixed_leader_counts,
                "fragments": [fragment_to_dict(fragment) for fragment in inv.fragments],
            }
            for inv in result.analysis.ordered_files
        ],
        "boundaries": [boundary_to_dict(boundary) for boundary in result.analysis.boundaries],
        "split_candidates": [split_to_dict(split) for split in result.analysis.split_candidates],
        "duplicate_removed": result.duplicate_removed,
        "conflicts": result.conflict_messages,
        "accepted_records": [
            {
                "source_file": record.source_file,
                "source_offset": record.source_offset,
                "source_length": record.source_length,
                "continuation_file": record.continuation_file,
                "continuation_offset": record.continuation_offset,
                "continuation_length": record.continuation_length,
                "reconstructed": record.reconstructed,
                "ensemble_sha256": record.ensemble_sha256,
                "fixed_leader_sha256": record.fixed_leader_sha256,
                "rtc": record.rtc_text,
                "ensemble_number": record.ensemble_number,
            }
            for record in result.accepted_records
        ],
        "gaps": [gap_to_dict(gap) for gap in result.gaps],
        "validation": validation,
        "recovered_path": None if result.recovered_path is None else str(result.recovered_path),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_recovery_report(path: Path, result: RecoveryResult) -> None:
    analysis = result.analysis
    lines: list[str] = []
    lines.append("# WorkHorse PD0 Recovery Report")
    lines.append("")
    lines.append(f"- Final verdict: `{result.verdict}`")
    lines.append(f"- Source files analysed: {len(analysis.discovered_files)}")
    lines.append(f"- Chronological order: {', '.join(inv.path.name for inv in analysis.ordered_files)}")
    lines.append(f"- Accepted complete ensembles: {len(result.accepted_records)}")
    lines.append(f"- Exact duplicate ensembles removed by SHA256: {result.duplicate_removed}")
    lines.append("")
    lines.append("## Source Inventory")
    lines.append("")
    for inv in analysis.ordered_files:
        first = first_valid(inv)
        last = last_valid(inv)
        lines.append(f"### `{inv.path.name}`")
        lines.append("")
        lines.append(f"- Size: {inv.size_bytes} bytes")
        lines.append(f"- Valid ensembles: {len(inv.ensembles)}")
        lines.append(f"- First RTC: {'' if first is None else first.rtc_text}")
        lines.append(f"- Last RTC: {'' if last is None else last.rtc_text}")
        lines.append(f"- First ensemble number: {'' if first is None else first.ensemble_number}")
        lines.append(f"- Last ensemble number: {'' if last is None else last.ensemble_number}")
        lines.append(f"- Nominal interval: {inv.nominal_interval_ms} ms")
        lines.append(f"- Fixed leader fingerprints: {json.dumps(inv.fixed_leader_counts, sort_keys=True)}")
        lines.append(f"- Checksum error regions: {sum(1 for region in inv.regions if region.classification == 'BAD_CHECKSUM')}")
        lines.append(f"- Truncated regions: {sum(1 for region in inv.regions if region.classification == 'TRUNCATED_ENSEMBLE')}")
        lines.append(f"- Non-PD0 / fragment regions: {sum(1 for region in inv.regions if region.classification in {'NON_PD0_DATA', 'POSSIBLE_FRAGMENT'})}")
        if inv.fragments:
            lines.append("- Edge fragments:")
            for fragment in inv.fragments:
                lines.append(
                    f"- {fragment.boundary_side} fragment at byte {fragment.byte_offset}: available={fragment.available_byte_count}, declared={fragment.declared_complete_length}, ensemble={fragment.candidate_ensemble_number}, rtc={fragment.candidate_rtc}, offsets={list(fragment.decoded_offsets)}, checksum_bytes_present={fragment.checksum_bytes_present}, status={fragment.structural_status} ({fragment.reason})"
                )
        lines.append("")
    lines.append("## Boundary Analysis")
    lines.append("")
    for boundary in analysis.boundaries:
        lines.append(f"### `{boundary.previous_file}` -> `{boundary.next_file}`")
        lines.append("")
        lines.append(f"- Primary status: `{boundary.primary_status}`")
        lines.append(f"- Facts: {', '.join(boundary.facts)}")
        lines.append(f"- Previous last RTC / ensemble: `{boundary.previous_last_rtc}` / `{boundary.previous_last_ensemble}`")
        lines.append(f"- Next first RTC / ensemble: `{boundary.next_first_rtc}` / `{boundary.next_first_ensemble}`")
        lines.append(f"- Counter transition: `{boundary.counter_transition}`")
        lines.append(f"- Fixed leader match: {boundary.fixed_leader_match}")
        lines.append(f"- Elapsed time: {None if boundary.elapsed_ms is None else f'{boundary.elapsed_ms / 1000:.3f} s'}")
        lines.append(f"- Expected interval: {None if boundary.nominal_interval_ms is None else f'{boundary.nominal_interval_ms / 1000:.3f} s'}")
        lines.append(f"- Missing acquisition time: {None if boundary.missing_acquisition_ms is None else f'{boundary.missing_acquisition_ms / 1000:.3f} s'}")
        lines.append(f"- Estimated missing ensembles: {boundary.estimated_missing_ensembles}")
        lines.append(f"- Exact duplicate overlaps: {boundary.exact_duplicate_overlap}")
        lines.append(f"- Conflicting same-RTC overlaps: {boundary.conflicting_time_overlap}")
        lines.append(f"- Trailing region previous: {boundary.trailing_bytes_previous} bytes ({boundary.trailing_region_previous})")
        lines.append(f"- Leading region next: {boundary.leading_bytes_next} bytes ({boundary.leading_region_next})")
        lines.append(f"- Notes: {'; '.join(boundary.notes) if boundary.notes else 'none'}")
        lines.append("")
    lines.append("## Split Reconstruction")
    lines.append("")
    if analysis.split_candidates:
        for split in analysis.split_candidates:
            lines.append(
                f"- {split.previous_file} byte {split.previous_offset} + {split.next_file} prefix {split.next_consumed_bytes} bytes: `{split.status}`; ensemble={split.candidate_ensemble_number}, rtc={split.candidate_rtc}, declared={split.declared_total_bytes}, checksum_valid={split.stored_checksum_validates}; {split.reason}"
            )
    else:
        lines.append("- No cross-file split candidates were found.")
    lines.append("")
    lines.append("## Gaps")
    lines.append("")
    lines.append(f"- Observed nominal interval: {analysis.nominal_interval_ms} ms")
    lines.append(f"- Remaining gaps: {len(result.gaps)}")
    for gap in result.gaps:
        lines.append(
            f"- {gap.before_rtc} ({gap.before_source} #{gap.before_ensemble}) -> {gap.after_rtc} ({gap.after_source} #{gap.after_ensemble}): elapsed={gap.elapsed_ms / 1000:.3f}s expected={gap.expected_interval_ms / 1000:.3f}s missing={gap.missing_acquisition_ms / 1000:.3f}s estimated_missing_ensembles={gap.estimated_missing_ensembles} location={gap.location}"
        )
    lines.append("")
    lines.append("## Recovery Decision")
    lines.append("")
    if result.conflict_messages:
        lines.append("- Recovery output was withheld because scientifically meaningful ambiguity was detected.")
        for message in result.conflict_messages:
            lines.append(f"- {message}")
    else:
        lines.append("- Only trustworthy complete ensembles were accepted.")
        lines.append("- Accepted complete ensembles retain their original stored checksum and original bytes.")
        lines.append("- No measurement bytes were fabricated and no replacement checksum was generated.")
        if result.recovered_path is not None:
            lines.append(f"- Recovered file written to `{result.recovered_path}`")
    if result.validation is not None:
        lines.append(f"- Validation issues: {len(result.validation.issues)}")
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_validation_report(path: Path, result: RecoveryResult) -> None:
    lines: list[str] = []
    lines.append("# recovered.000 Validation")
    lines.append("")
    lines.append(f"- Final verdict: `{result.verdict}`")
    lines.append("")
    if result.recovered_path is None or result.validation is None:
        lines.append("- recovered.000 was withheld because manual review is required.")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return
    validation = result.validation
    lines.append(f"- Valid ensembles parsed sequentially from byte 0 to EOF: {validation.valid_count}")
    lines.append(f"- Structural validation issues: {len(validation.issues)}")
    lines.append(f"- Duplicate full-record hashes: {len(validation.duplicate_hashes)}")
    lines.append(f"- Validation nominal interval: {validation.nominal_interval_ms} ms")
    lines.append(f"- Validation gaps: {len(validation.gaps)}")
    if validation.issues:
        lines.append("")
        lines.append("## Issues")
        lines.append("")
        for issue in validation.issues:
            lines.append(f"- {issue}")
    else:
        lines.append("")
        lines.append("- recovered.000 reparses cleanly from byte 0 to EOF with zero malformed headers, zero bad checksums, zero invalid offsets, and zero unexplained bytes.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def recover_dataset(paths: Sequence[Path], output_dir: Path) -> RecoveryResult:
    analysis = analyze_dataset(paths)
    accepted_records, duplicate_removed, conflicts = build_output_records(analysis)
    gaps = build_gap_records_from_records(accepted_records, analysis.nominal_interval_ms)
    output_dir.mkdir(parents=True, exist_ok=True)

    recovered_path: Path | None = None
    validation: ValidationResult | None = None
    provisional_verdict = determine_verdict(analysis, conflicts, gaps, None)
    if provisional_verdict not in {"MANUAL_REVIEW_REQUIRED", "FAIL"}:
        recovered_path = output_dir / "recovered.000"
        write_recovered_file(recovered_path, accepted_records)
        validation = validate_recovered_file(recovered_path)
    verdict = determine_verdict(analysis, conflicts, gaps, validation)
    result = RecoveryResult(
        analysis=analysis,
        accepted_records=accepted_records,
        duplicate_removed=duplicate_removed,
        conflict_messages=conflicts,
        gaps=gaps,
        validation=validation,
        verdict=verdict,
        recovered_path=recovered_path,
    )
    write_source_inventory(output_dir / "source_inventory.csv", analysis.ordered_files)
    write_boundary_csv(output_dir / "boundary_analysis.csv", analysis.boundaries)
    write_gap_csv(output_dir / "recovered_gaps.csv", result.gaps)
    write_recovery_report(output_dir / "recovery_report.md", result)
    write_validation_report(output_dir / "recovered_validation.md", result)
    write_recovered_ensemble_map(output_dir / "recovered_ensemble_map.csv", accepted_records)
    write_manifest(output_dir / "recovery_manifest.json", result)
    return result


def render_inspect_report(analysis: DatasetAnalysis) -> str:
    lines: list[str] = []
    lines.append("# WorkHorse PD0 Inspection")
    lines.append("")
    lines.append("## Discovered Source Files")
    lines.append("")
    for path_item in analysis.discovered_files:
        lines.append(f"- `{path_item}`")
    lines.append("")
    lines.append(f"- Chronological order: {', '.join(inv.path.name for inv in analysis.ordered_files)}")
    lines.append(f"- Observed nominal interval: {analysis.nominal_interval_ms} ms")
    lines.append("")
    lines.append("## Per-File Summary")
    lines.append("")
    for inv in analysis.ordered_files:
        first = first_valid(inv)
        last = last_valid(inv)
        lines.append(f"### `{inv.path.name}`")
        lines.append("")
        lines.append(f"- File size: {inv.size_bytes} bytes")
        lines.append(f"- Valid ensemble count: {len(inv.ensembles)}")
        lines.append(f"- First RTC: {'' if first is None else first.rtc_text}")
        lines.append(f"- Last RTC: {'' if last is None else last.rtc_text}")
        lines.append(f"- First ensemble number: {'' if first is None else first.ensemble_number}")
        lines.append(f"- Last ensemble number: {'' if last is None else last.ensemble_number}")
        lines.append(f"- Fixed Leader fingerprints: {json.dumps(inv.fixed_leader_counts, sort_keys=True)}")
        lines.append(f"- Checksum errors: {sum(1 for region in inv.regions if region.classification == 'BAD_CHECKSUM')}")
        lines.append(f"- Non-PD0 regions: {sum(1 for region in inv.regions if region.classification in {'NON_PD0_DATA', 'POSSIBLE_FRAGMENT'})}")
        lines.append(f"- Truncated records: {sum(1 for region in inv.regions if region.classification == 'TRUNCATED_ENSEMBLE')}")
        if inv.fragments:
            for fragment in inv.fragments:
                lines.append(
                    f"- {fragment.boundary_side} fragment: offset={fragment.byte_offset}, available={fragment.available_byte_count}, declared={fragment.declared_complete_length}, ensemble={fragment.candidate_ensemble_number}, rtc={fragment.candidate_rtc}, offsets={list(fragment.decoded_offsets)}, checksum_bytes_present={fragment.checksum_bytes_present}, status={fragment.structural_status}"
                )
        lines.append("")
    lines.append("## Boundaries")
    lines.append("")
    for boundary in analysis.boundaries:
        lines.append(
            f"- `{boundary.previous_file}` -> `{boundary.next_file}`: primary={boundary.primary_status}; facts={','.join(boundary.facts)}; elapsed={None if boundary.elapsed_ms is None else f'{boundary.elapsed_ms / 1000:.3f}s'}; expected={None if boundary.nominal_interval_ms is None else f'{boundary.nominal_interval_ms / 1000:.3f}s'}; missing={None if boundary.missing_acquisition_ms is None else f'{boundary.missing_acquisition_ms / 1000:.3f}s'}; duplicates={boundary.exact_duplicate_overlap}; conflicts={boundary.conflicting_time_overlap}; counter={boundary.counter_transition}; config_change={boundary.configuration_changed}"
        )
    lines.append("")
    lines.append("## Split Candidates")
    lines.append("")
    if analysis.split_candidates:
        for split in analysis.split_candidates:
            lines.append(
                f"- `{split.previous_file}` -> `{split.next_file}` at previous byte {split.previous_offset}: {split.status}; declared={split.declared_total_bytes}; previous_available={split.previous_available_bytes}; next_consumed={split.next_consumed_bytes}; ensemble={split.candidate_ensemble_number}; rtc={split.candidate_rtc}; reason={split.reason}"
            )
    else:
        lines.append("- none")
    lines.append("")
    if analysis.configuration_changes:
        lines.append(f"- Configuration changes detected at: {', '.join(analysis.configuration_changes)}")
    return "\n".join(lines) + "\n"


def inspect_inputs(inputs: Sequence[str], recursive: bool, output_dir: Path | None = None) -> tuple[str, int]:
    groups = discover_candidate_groups(inputs, recursive=recursive, output_dir=output_dir)
    if not groups:
        return "NO_INPUT_FILES_FOUND\n", 1
    if len(groups) > 1:
        lines = ["MULTIPLE_CANDIDATE_DATASETS", "", render_candidate_groups(groups).rstrip(), ""]
        for group in groups:
            lines.append(f"### Group {group.group_id}")
            lines.append("")
            lines.append(render_inspect_report(analyze_dataset(group.files)).rstrip())
            lines.append("")
        return "\n".join(lines), 0
    group = groups[0]
    lines = [render_candidate_groups(groups).rstrip(), "", render_inspect_report(analyze_dataset(group.files)).rstrip(), ""]
    return "\n".join(lines), 0


def parse_slice_range(value: str) -> tuple[int, int]:
    start_text, separator, end_text = value.partition(":")
    if separator != ":" or not start_text or not end_text:
        raise ValueError("--range must use inclusive 1-based physical indexes in A:B form")
    try:
        start, end = int(start_text), int(end_text)
    except ValueError as error:
        raise ValueError("--range must use integer physical indexes in A:B form") from error
    return start, end


def build_slice_plan(
    input_path: Path,
    *,
    first: int | None = None,
    last: int | None = None,
    range_spec: str | None = None,
) -> SlicePlan:
    """Index one PD0 file in physical byte order and select complete records to remove."""
    selection_count = sum(value is not None for value in (first, last, range_spec))
    if selection_count != 1:
        raise ValueError("exactly one of --first, --last, or --range is required")
    inventory = inventory_file(input_path)
    ensembles = [
        SliceEnsemble(
            physical_index=index,
            start=ensemble.start,
            end_exclusive=ensemble.end_exclusive,
            length=ensemble.total_bytes,
            rdi_ensemble_number=ensemble.ensemble_number,
            structural_status="VALID_ENSEMBLE",
            checksum_status="VALID",
        )
        for index, ensemble in enumerate(inventory.ensembles, start=1)
    ]
    total = len(ensembles)
    if total == 0:
        raise ValueError("input contains no complete, checksum-valid PD0 ensembles")

    if first is not None:
        if first <= 0 or first > total:
            raise ValueError(f"--first must be between 1 and {total}")
        removed_indexes = tuple(range(1, first + 1))
    elif last is not None:
        if last <= 0 or last > total:
            raise ValueError(f"--last must be between 1 and {total}")
        removed_indexes = tuple(range(total - last + 1, total + 1))
    else:
        start, end = parse_slice_range(range_spec or "")
        if start <= 0 or end <= 0 or start > end or end > total:
            raise ValueError(f"--range must be an inclusive range within 1:{total}")
        removed_indexes = tuple(range(start, end + 1))

    removed_set = set(removed_indexes)
    retained_indexes = tuple(index for index in range(1, total + 1) if index not in removed_set)
    unparsed_bytes = sum(region.length for region in inventory.regions if region.classification != "VALID_ENSEMBLE")
    trailing_bytes, _ = trailing_non_valid_bytes(inventory)
    return SlicePlan(
        input_path=input_path,
        inventory=inventory,
        ensembles=ensembles,
        removed_indexes=removed_indexes,
        retained_indexes=retained_indexes,
        unparsed_bytes=unparsed_bytes,
        trailing_bytes=trailing_bytes,
    )


def format_slice_indexes(indexes: Sequence[int]) -> str:
    if not indexes:
        return "none"
    ranges: list[str] = []
    start = previous = indexes[0]
    for index in indexes[1:]:
        if index == previous + 1:
            previous = index
            continue
        ranges.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = index
    ranges.append(str(start) if start == previous else f"{start}-{previous}")
    return ", ".join(ranges)


def render_slice_report(plan: SlicePlan) -> str:
    by_index = {ensemble.physical_index: ensemble for ensemble in plan.ensembles}
    lines = [
        "# PD0 Ensemble Slice",
        "",
        f"- Input file: `{plan.input_path}`",
        f"- Complete ensembles found: {len(plan.ensembles)}",
        "- User-facing ensemble indexes are physical file order and 1-based; RDI ensemble numbers are informational only.",
        f"- Remove physical indexes: {format_slice_indexes(plan.removed_indexes)} ({len(plan.removed_indexes)} ensemble(s))",
        f"- Retain: {len(plan.retained_indexes)} ensemble(s)",
        f"- Unparsed/non-ensemble bytes: {plan.unparsed_bytes}",
        f"- Trailing/unparsed bytes after final complete ensemble: {plan.trailing_bytes}",
        "",
        "## Ensembles To Remove",
        "",
    ]
    for index in plan.removed_indexes:
        ensemble = by_index[index]
        lines.append(
            f"- physical={index}; bytes={ensemble.start}:{ensemble.end_exclusive}; length={ensemble.length}; "
            f"RDI ensemble={ensemble.rdi_ensemble_number}; structural={ensemble.structural_status}; checksum={ensemble.checksum_status}"
        )
    if plan.unparsed_bytes:
        lines.extend(
            [
                "",
                "WARNING: output is blocked because copying only complete retained ensembles would discard unparsed source bytes.",
            ]
        )
    return "\n".join(lines) + "\n"


def validate_slice_output(output_path: Path, retained_bytes: list[bytes]) -> SliceValidation:
    validation = validate_recovered_file(output_path)
    output_inventory = inventory_file(output_path)
    output_bytes = output_path.read_bytes()
    expected_bytes = b"".join(retained_bytes)
    # Duplicate records are valid input for slicing; unlike recovery, slicing never deduplicates.
    issues = [issue for issue in validation.issues if not issue.startswith("duplicate full-record hashes present:")]
    if len(output_inventory.ensembles) != len(retained_bytes):
        issues.append(f"output inventory found {len(output_inventory.ensembles)} complete ensembles; expected {len(retained_bytes)}")
    if any(region.classification != "VALID_ENSEMBLE" for region in output_inventory.regions):
        issues.append("output inventory contains unparsed or malformed bytes")
    retained_bytes_match = output_bytes == expected_bytes
    if not retained_bytes_match:
        issues.append("output bytes do not exactly match the concatenated retained input ensembles")
    return SliceValidation(validation.valid_count, issues, retained_bytes_match)


def write_slice_output(plan: SlicePlan, output_path: Path) -> SliceValidation:
    if plan.unparsed_bytes:
        raise ValueError("refusing to discard unparsed source bytes; no output was written")
    if output_path.resolve() == plan.input_path.resolve():
        raise ValueError("output path must not overwrite the input file")
    if output_path.exists():
        raise ValueError(f"refusing to overwrite existing output file: {output_path}")

    source_data = plan.input_path.read_bytes()
    by_index = {ensemble.physical_index: ensemble for ensemble in plan.ensembles}
    retained_bytes = [source_data[by_index[index].start : by_index[index].end_exclusive] for index in plan.retained_indexes]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f".{output_path.name}.slice-tmp")
    if temporary_path.exists():
        raise ValueError(f"refusing to replace temporary slice file: {temporary_path}")
    try:
        with temporary_path.open("wb") as handle:
            for ensemble_bytes in retained_bytes:
                handle.write(ensemble_bytes)
        validation = validate_slice_output(temporary_path, retained_bytes)
        if validation.issues:
            raise ValueError("output validation failed: " + "; ".join(validation.issues))
        temporary_path.replace(output_path)
        return validation
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def bin_trim_blocks(data: bytes, ensemble: Ensemble) -> tuple[BinTrimBlock, ...]:
    blocks: list[BinTrimBlock] = []
    for index, offset in enumerate(ensemble.offsets):
        end = ensemble.offsets[index + 1] if index + 1 < len(ensemble.offsets) else ensemble.byte_count
        block_id = data[ensemble.start + offset : ensemble.start + offset + 2]
        name, element_width = BIN_DEPENDENT_BLOCKS.get(block_id, (block_id.hex(), None))
        blocks.append(BinTrimBlock(block_id, name, offset, end - offset, element_width))
    return tuple(blocks)


def build_bin_trim_plan(input_path: Path, remove_last: int) -> BinTrimPlan:
    """Prove a PD0 file can be rewritten by removing final depth cells only."""
    if remove_last <= 0:
        raise ValueError("--last must be greater than zero")
    inventory = inventory_file(input_path)
    if not inventory.ensembles:
        raise ValueError("input contains no complete, checksum-valid PD0 ensembles")
    if any(region.classification != "VALID_ENSEMBLE" for region in inventory.regions):
        raise ValueError("refusing bin trim: input contains unparsed, malformed, or checksum-invalid bytes")

    data = input_path.read_bytes()
    first = inventory.ensembles[0]
    first_blocks = bin_trim_blocks(data, first)
    if any(block.block_id not in SUPPORTED_BIN_TRIM_BLOCKS for block in first_blocks):
        unknown = next(block.block_id.hex() for block in first_blocks if block.block_id not in SUPPORTED_BIN_TRIM_BLOCKS)
        raise ValueError(f"refusing bin trim: unsupported or unknown data block 0x{unknown}")
    block_ids = tuple(block.block_id for block in first_blocks)
    required = tuple(BIN_DEPENDENT_BLOCKS)
    if any(block_ids.count(block_id) != 1 for block_id in required):
        raise ValueError("refusing bin trim: each standard bin-dependent block must occur exactly once")
    if block_ids.count(FIXED_LEADER_ID) != 1 or block_ids.count(VARIABLE_LEADER_ID) != 1 or block_ids.count(BOTTOM_TRACK_ID) > 1:
        raise ValueError("refusing bin trim: repeated leader or Bottom Track block creates an unsupported layout")

    fixed = data[first.start + first.offsets[0] : first.start + first.offsets[1]]
    if len(fixed) < 16:
        raise ValueError("refusing bin trim: fixed leader is too short for depth-cell configuration")
    beam_count = fixed[8]
    source_cells = fixed[9]
    cell_size_cm = struct.unpack_from("<H", fixed, 12)[0]
    if beam_count <= 0 or source_cells <= 0 or cell_size_cm <= 0:
        raise ValueError("refusing bin trim: invalid fixed-leader beam, depth-cell, or cell-size configuration")
    if remove_last >= source_cells:
        raise ValueError(f"--last must be between 1 and {source_cells - 1} for this file")

    expected_blocks: list[BinTrimBlock] = []
    for block in first_blocks:
        if block.block_id in BIN_DEPENDENT_BLOCKS:
            name, element_width = BIN_DEPENDENT_BLOCKS[block.block_id]
            expected_length = 2 + source_cells * beam_count * element_width
            if block.length != expected_length:
                raise ValueError(
                    f"refusing bin trim: {name} block length {block.length} does not match "
                    f"{source_cells} cells x {beam_count} beams x {element_width}-byte elements"
                )
            expected_blocks.append(BinTrimBlock(block.block_id, name, block.offset, block.length, beam_count * element_width))
        else:
            expected_blocks.append(block)

    expected_layout = tuple((block.block_id, block.offset, block.length) for block in expected_blocks)
    for ensemble in inventory.ensembles[1:]:
        blocks = bin_trim_blocks(data, ensemble)
        layout = tuple((block.block_id, block.offset, block.length) for block in blocks)
        if layout != expected_layout:
            raise ValueError("refusing bin trim: ensemble data-block ordering, offsets, or lengths vary")
        fixed = data[ensemble.start + ensemble.offsets[0] : ensemble.start + ensemble.offsets[1]]
        if len(fixed) < 16 or fixed[8] != beam_count or fixed[9] != source_cells or struct.unpack_from("<H", fixed, 12)[0] != cell_size_cm:
            raise ValueError("refusing bin trim: fixed-leader beam or depth-cell configuration varies")

    removed_bytes_per_ensemble = sum(remove_last * (block.bytes_per_bin or 0) for block in expected_blocks)
    resulting_ensemble_bytes = first.total_bytes - removed_bytes_per_ensemble
    if resulting_ensemble_bytes <= 2:
        raise ValueError("refusing bin trim: resulting ensemble would be invalid")
    return BinTrimPlan(
        input_path=input_path,
        inventory=inventory,
        remove_last=remove_last,
        source_cells=source_cells,
        resulting_cells=source_cells - remove_last,
        beam_count=beam_count,
        cell_size_cm=cell_size_cm,
        blocks=tuple(expected_blocks),
        source_ensemble_bytes=first.total_bytes,
        resulting_ensemble_bytes=resulting_ensemble_bytes,
        removed_bytes_per_ensemble=removed_bytes_per_ensemble,
        expected_output_bytes=resulting_ensemble_bytes * len(inventory.ensembles),
    )


def trim_ensemble_bins(source_data: bytes, ensemble: Ensemble, plan: BinTrimPlan) -> bytes:
    header_length = 6 + 2 * ensemble.number_of_data_types
    output_blocks: list[bytes] = []
    for block in plan.blocks:
        source_block = source_data[ensemble.start + block.offset : ensemble.start + block.offset + block.length]
        if block.block_id == FIXED_LEADER_ID:
            rewritten = bytearray(source_block)
            rewritten[9] = plan.resulting_cells
            output_blocks.append(bytes(rewritten))
        elif block.bytes_per_bin is not None:
            retained_length = 2 + plan.resulting_cells * block.bytes_per_bin
            output_blocks.append(source_block[:retained_length])
        else:
            output_blocks.append(source_block)

    byte_count = header_length + sum(len(block) for block in output_blocks)
    if byte_count > 0xFFFF:
        raise ValueError("refusing bin trim: rewritten ensemble byte count exceeds PD0 header capacity")
    header = bytearray(source_data[ensemble.start : ensemble.start + header_length])
    struct.pack_into("<H", header, 2, byte_count)
    offset = header_length
    offsets = []
    for block in output_blocks:
        offsets.append(offset)
        offset += len(block)
    struct.pack_into("<" + "H" * len(offsets), header, 6, *offsets)
    payload = bytes(header) + b"".join(output_blocks)
    return payload + struct.pack("<H", checksum_rdi(payload))


def validate_bin_trim_output(output_path: Path, source_data: bytes, plan: BinTrimPlan) -> BinTrimValidation:
    output_inventory = inventory_file(output_path)
    output_data = output_path.read_bytes()
    issues: list[str] = []
    if len(output_data) != plan.expected_output_bytes:
        issues.append(f"output size {len(output_data)} does not match expected {plan.expected_output_bytes}")
    if len(output_inventory.ensembles) != len(plan.inventory.ensembles):
        issues.append(f"output contains {len(output_inventory.ensembles)} complete ensembles; expected {len(plan.inventory.ensembles)}")
    if any(region.classification != "VALID_ENSEMBLE" for region in output_inventory.regions):
        issues.append("output contains unparsed, malformed, or checksum-invalid bytes")
    if len(output_inventory.ensembles) == len(plan.inventory.ensembles):
        for source, output in zip(plan.inventory.ensembles, output_inventory.ensembles):
            output_blocks = bin_trim_blocks(output_data, output)
            if tuple(block.block_id for block in output_blocks) != tuple(block.block_id for block in plan.blocks):
                issues.append(f"ensemble {source.ensemble_number}: output data-block ordering changed")
                break
            output_fixed = output_data[output.start + output.offsets[0] : output.start + output.offsets[1]]
            if len(output_fixed) < 16 or output_fixed[9] != plan.resulting_cells:
                issues.append(f"ensemble {source.ensemble_number}: output depth-cell count is incorrect")
                break
            for source_block, output_block in zip(plan.blocks, output_blocks):
                original = source_data[source.start + source_block.offset : source.start + source_block.offset + source_block.length]
                rewritten = output_data[output.start + output_block.offset : output.start + output_block.offset + output_block.length]
                if source_block.bytes_per_bin is not None:
                    retained = 2 + plan.resulting_cells * source_block.bytes_per_bin
                    if rewritten != original[:retained]:
                        issues.append(f"ensemble {source.ensemble_number}: retained {source_block.name} bin payload changed")
                        break
                elif source_block.block_id == FIXED_LEADER_ID:
                    expected = bytearray(original)
                    expected[9] = plan.resulting_cells
                    if rewritten != expected:
                        issues.append(f"ensemble {source.ensemble_number}: fixed leader changed outside depth-cell count")
                        break
                elif rewritten != original:
                    issues.append(f"ensemble {source.ensemble_number}: non-bin block {source_block.name} changed")
                    break
            if issues:
                break
    return BinTrimValidation(len(output_inventory.ensembles), issues)


def render_bin_trim_report(plan: BinTrimPlan) -> str:
    removed_range_m = plan.remove_last * plan.cell_size_cm / 100
    return "\n".join(
        [
            "# PD0 Depth-Cell Trim",
            "",
            f"- Input file: `{plan.input_path}`",
            f"- Complete ensembles: {len(plan.inventory.ensembles)}",
            f"- Source depth cells: {plan.source_cells}",
            f"- Remove final depth cells: {plan.remove_last}",
            f"- Resulting depth cells: {plan.resulting_cells}",
            f"- Beams/components per cell: {plan.beam_count}",
            f"- Depth-cell size: {plan.cell_size_cm / 100:.2f} m",
            f"- Nominal removed outer range: {removed_range_m:.2f} m",
            f"- Source ensemble bytes: {plan.source_ensemble_bytes}",
            f"- Removed bytes per ensemble: {plan.removed_bytes_per_ensemble}",
            f"- Resulting ensemble bytes: {plan.resulting_ensemble_bytes}",
            f"- Expected output bytes: {plan.expected_output_bytes}",
            "",
        ]
    )


def write_bin_trim_output(plan: BinTrimPlan, output_path: Path) -> BinTrimValidation:
    if output_path.resolve() == plan.input_path.resolve():
        raise ValueError("output path must not overwrite the input file")
    if output_path.exists():
        raise ValueError(f"refusing to overwrite existing output file: {output_path}")
    source_data = plan.input_path.read_bytes()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f".{output_path.name}.bin-trim-tmp")
    if temporary_path.exists():
        raise ValueError(f"refusing to replace temporary bin-trim file: {temporary_path}")
    try:
        with temporary_path.open("wb") as handle:
            for ensemble in plan.inventory.ensembles:
                handle.write(trim_ensemble_bins(source_data, ensemble, plan))
        validation = validate_bin_trim_output(temporary_path, source_data, plan)
        if validation.issues:
            raise ValueError("output validation failed: " + "; ".join(validation.issues))
        temporary_path.replace(output_path)
        return validation
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Conservative Teledyne RDI WorkHorse PD0 inspection, recovery, and ensemble slicing tool")
    parser.add_argument("--version", action="version", version=f"rdi-recover {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect .000 sources without writing recovered output")
    inspect_parser.add_argument("inputs", nargs="+", help="Input .000 files or directories")
    inspect_parser.add_argument("--recursive", action="store_true", help="Recursively search directory inputs for .000 files")

    recover_parser = subparsers.add_parser("recover", help="Recover trustworthy complete ensembles into recovered.000")
    recover_parser.add_argument("inputs", nargs="+", help="Input .000 files or directories")
    recover_parser.add_argument("--output-dir", required=True, help="Directory for recovered outputs")
    recover_parser.add_argument("--recursive", action="store_true", help="Recursively search directory inputs for .000 files")

    slice_parser = subparsers.add_parser("slice", help="Remove complete PD0 ensembles by physical file order without rewriting retained bytes")
    slice_parser.add_argument("input", help="Input .000 file")
    selection = slice_parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--first", type=int, help="Remove the first N complete ensembles")
    selection.add_argument("--last", type=int, help="Remove the last N complete ensembles")
    selection.add_argument("--range", dest="range_spec", help="Remove inclusive 1-based physical ensemble indexes A:B")
    slice_parser.add_argument("--output", help="New output .000 file (required unless --dry-run is used)")
    slice_parser.add_argument("--dry-run", action="store_true", help="Analyze and report the slice without writing a file")

    bin_trim_parser = subparsers.add_parser("slice-bins", help="Remove final depth cells from proven standard PD0 profile blocks")
    bin_trim_parser.add_argument("input", help="Input .000 file")
    bin_trim_parser.add_argument("--last", required=True, type=int, help="Remove the final N depth cells from every ensemble")
    bin_trim_parser.add_argument("--output", help="New output .000 file (required unless --dry-run is used)")
    bin_trim_parser.add_argument("--dry-run", action="store_true", help="Analyze and report the bin trim without writing a file")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir) if args.command == "recover" else None
    if args.command == "inspect":
        report, exit_code = inspect_inputs(args.inputs, recursive=args.recursive, output_dir=output_dir)
        sys.stdout.write(report)
        return exit_code
    if args.command == "slice":
        try:
            plan = build_slice_plan(Path(args.input), first=args.first, last=args.last, range_spec=args.range_spec)
            sys.stdout.write(render_slice_report(plan))
            if args.dry_run:
                sys.stdout.write("DRY RUN: no output file written.\n")
                return 0
            if not args.output:
                raise ValueError("--output is required unless --dry-run is used")
            validation = write_slice_output(plan, Path(args.output))
            sys.stdout.write(f"SLICE VALIDATION PASS: {validation.valid_count} ensembles reparsed; retained bytes match exactly.\n")
            return 0
        except (OSError, ValueError) as error:
            sys.stderr.write(f"SLICE FAILED: {error}\n")
            return 1
    if args.command == "slice-bins":
        try:
            plan = build_bin_trim_plan(Path(args.input), args.last)
            sys.stdout.write(render_bin_trim_report(plan))
            if args.dry_run:
                sys.stdout.write("DRY RUN: no output file written.\n")
                return 0
            if not args.output:
                raise ValueError("--output is required unless --dry-run is used")
            validation = write_bin_trim_output(plan, Path(args.output))
            sys.stdout.write(f"BIN TRIM VALIDATION PASS: {validation.valid_count} ensembles reparsed and retained payloads match exactly.\n")
            return 0
        except (OSError, ValueError) as error:
            sys.stderr.write(f"BIN TRIM FAILED: {error}\n")
            return 1
    groups = discover_candidate_groups(args.inputs, recursive=args.recursive, output_dir=output_dir)
    selected_group, status = select_single_group_or_status(groups)
    if status is not None:
        sys.stdout.write(f"{status}\n\n")
        sys.stdout.write(render_candidate_groups(groups))
        return 1
    result = recover_dataset(selected_group.files, output_dir)
    sys.stdout.write(f"{result.verdict}\n")
    sys.stdout.write(f"Recovered outputs written to {output_dir}\n")
    return 0 if result.verdict in {"PASS", "PASS_WITH_GAPS", "PASS_WITH_UNRECOVERABLE_FRAGMENTS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
