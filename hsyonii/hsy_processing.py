"""전국 시도 단위 의료이용 원자료를 분석용 CSV로 정리합니다."""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
DATA_DIR = ROOT_DIR / "data"
OUTPUT_DIR = SCRIPT_DIR / "processed_data"

REGIONS = (
    "서울",
    "부산",
    "대구",
    "인천",
    "광주",
    "대전",
    "울산",
    "세종",
    "경기",
    "강원",
    "충북",
    "충남",
    "전북",
    "전남",
    "경북",
    "경남",
    "제주",
)
DISEASES = ("고혈압", "당뇨")


def _find_source(data_dir: Path) -> Path:
    sources = sorted(data_dir.glob("01*.xlsx"))
    if len(sources) != 1:
        raise FileNotFoundError(
            f"{data_dir}에서 전국 시도 원자료 '01*.xlsx'를 하나 찾을 수 없습니다."
        )
    return sources[0]


def _find_sheet(workbook: Workbook, prefix: str) -> Worksheet:
    matches = [
        worksheet
        for worksheet in workbook.worksheets
        if worksheet.title.startswith(prefix)
    ]
    if len(matches) != 1:
        raise ValueError(
            f"'{prefix}'로 시작하는 시트를 하나 찾을 수 없습니다: "
            f"{[worksheet.title for worksheet in matches]}"
        )
    return matches[0]


def _region_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    name = re.sub(r"\s+", "", value.splitlines()[0])
    return name if name in REGIONS else None


def _number(value: Any, context: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{context} 값이 숫자가 아닙니다: {value!r}")
    if not math.isfinite(value):
        raise ValueError(f"{context} 값이 유한한 숫자가 아닙니다: {value!r}")
    return value


def _require_regions(values: dict[str, Any], dataset_name: str) -> None:
    missing = [region for region in REGIONS if region not in values]
    if missing:
        raise ValueError(f"{dataset_name}에서 지역을 찾지 못했습니다: {missing}")


def _population_by_region(sheet: Worksheet) -> dict[str, int | float]:
    result: dict[str, int | float] = {}
    for row_number, row in enumerate(sheet.iter_rows(min_row=10, values_only=True), 10):
        region = _region_name(row[0] if row else None)
        if region is None:
            continue
        if region in result:
            raise ValueError(f"{sheet.title} {row_number}행에 {region}이 중복됩니다.")
        result[region] = _number(row[1], f"{sheet.title} {row_number}행 적용인구")
    _require_regions(result, "적용인구")
    return result


def _summary_by_region(sheet: Worksheet) -> dict[str, dict[str, int | float]]:
    result: dict[str, dict[str, int | float]] = {}
    for row_number, row in enumerate(sheet.iter_rows(min_row=10, values_only=True), 10):
        region = _region_name(row[0] if row else None)
        category = row[2] if len(row) > 2 else None
        if region is None or category != "계":
            continue
        if region in result:
            raise ValueError(f"{sheet.title} {row_number}행에 {region}이 중복됩니다.")
        result[region] = {
            "진료실인원": _number(row[4], f"{sheet.title} {row_number}행 진료실인원"),
            "진료비": int(round(_number(row[7], f"{sheet.title} {row_number}행 진료비"))),
            "급여비": int(round(_number(row[8], f"{sheet.title} {row_number}행 급여비"))),
        }
    _require_regions(result, "regional_summary")
    return result


def _flow_by_region(sheet: Worksheet) -> dict[str, int | float]:
    result: dict[str, int | float] = {}
    for row_number, row in enumerate(sheet.iter_rows(min_row=10, values_only=True), 10):
        region = _region_name(row[0] if row else None)
        category = row[1] if len(row) > 1 else None
        if (
            region is None
            or not isinstance(category, str)
            or "subtotal" not in category.casefold()
        ):
            continue
        if region in result:
            raise ValueError(f"{sheet.title} {row_number}행에 {region}이 중복됩니다.")
        result[region] = _number(row[2], f"{sheet.title} {row_number}행 진료실인원")
    _require_regions(result, sheet.title)
    return result


def _chronic_disease_by_region(
    sheet: Worksheet,
) -> dict[str, dict[str, int | float]]:
    result: dict[str, dict[str, int | float]] = {}
    blocks = ((0, 2, 4), (9, 11, 13))
    active_regions: list[str | None] = [None, None]

    for row_number, row in enumerate(sheet.iter_rows(min_row=10, values_only=True), 10):
        for block_index, (region_column, disease_column, patient_column) in enumerate(
            blocks
        ):
            region_value = row[region_column] if len(row) > region_column else None
            region = _region_name(region_value)
            if region is not None:
                active_regions[block_index] = region
            elif isinstance(region_value, str) and region_value.strip():
                active_regions[block_index] = None

            disease_value = row[disease_column] if len(row) > disease_column else None
            disease = (
                re.sub(r"\s+", "", disease_value)
                if isinstance(disease_value, str)
                else ""
            )
            active_region = active_regions[block_index]
            if active_region is not None and disease in DISEASES:
                region_values = result.setdefault(active_region, {})
                if disease in region_values:
                    raise ValueError(
                        f"{sheet.title} {row_number}행에 "
                        f"{active_region}/{disease}가 중복됩니다."
                    )
                region_values[disease] = _number(
                    row[patient_column],
                    f"{sheet.title} {row_number}행 "
                    f"{active_region} {disease} 진료실인원",
                )

    for region in REGIONS:
        missing = [disease for disease in DISEASES if disease not in result.get(region, {})]
        if missing:
            raise ValueError(
                f"chronic_disease에서 {region} 질환을 찾지 못했습니다: {missing}"
            )
    return result


def _write_csv(
    output_path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, Any]]
) -> None:
    with output_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def process_data(data_dir: Path = DATA_DIR, output_dir: Path = OUTPUT_DIR) -> list[Path]:
    """원자료를 세 개의 지역 단위 CSV로 변환하고 생성 경로를 반환합니다."""
    source_path = _find_source(data_dir)
    workbook = load_workbook(source_path, read_only=True, data_only=True)
    try:
        population = _population_by_region(_find_sheet(workbook, "10p"))
        summary = _summary_by_region(_find_sheet(workbook, "18p"))
        internal = _flow_by_region(_find_sheet(workbook, "20p"))
        external = _flow_by_region(_find_sheet(workbook, "22p"))
        chronic = _chronic_disease_by_region(_find_sheet(workbook, "42p"))
    finally:
        workbook.close()

    summary_rows = [
        {"지역명": region, "적용인구": population[region], **summary[region]}
        for region in REGIONS
    ]
    flow_rows = [
        {
            "지역명": region,
            "전체_진료실인원": summary[region]["진료실인원"],
            "관내_진료실인원": internal[region],
            "관외_진료실인원": external[region],
        }
        for region in REGIONS
    ]
    chronic_rows = [
        {
            "지역명": region,
            "고혈압_진료실인원": chronic[region]["고혈압"],
            "당뇨_진료실인원": chronic[region]["당뇨"],
        }
        for region in REGIONS
    ]

    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = [
        (
            output_dir / "regional_summary.csv",
            ("지역명", "적용인구", "진료실인원", "진료비", "급여비"),
            summary_rows,
        ),
        (
            output_dir / "regional_in_out.csv",
            ("지역명", "전체_진료실인원", "관내_진료실인원", "관외_진료실인원"),
            flow_rows,
        ),
        (
            output_dir / "chronic_disease.csv",
            ("지역명", "고혈압_진료실인원", "당뇨_진료실인원"),
            chronic_rows,
        ),
    ]
    for output_path, fieldnames, rows in outputs:
        _write_csv(output_path, fieldnames, rows)
    return [output_path for output_path, _, _ in outputs]


if __name__ == "__main__":
    for output_path in process_data():
        print(f"생성 완료: {output_path}")