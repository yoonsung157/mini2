"""02~05 원본 엑셀에서 필요한 표를 추출하고 연속 페이지를 하나의 CSV로 합친다.

실행: python hsyonii/파일변환.py
입력: data/*.xlsx / 출력: hsyonii/csv_before
원본 각주는 JSON으로, 표별 출처와 행 수는 변환목록.csv로 보관한다.
"""
import csv
import json
import re
from pathlib import Path

import openpyxl

# 실행 위치와 무관하게 소스 파일 기준으로 프로젝트 경로를 찾는다.
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'hsyonii' / 'csv_before'
# 각 파일 번호의 페이지 묶음은 아래 NAMES와 같은 순서다.
# [74, 76]처럼 여러 페이지가 있으면 한 CSV로 이어 붙인다.
PLAN = {
    '02': [[74, 76], [128, 130], *[[p, p + 2] for p in range(146, 168, 4)], [248, 250], [252, 254], [256, 258], [260, 262]],
    '03': [[266], [292], *[[p] for p in range(302, 314, 2)], *[[p] for p in range(356, 364, 2)]],
    '04': [[366], [394], *[[p] for p in range(404, 416, 2)], *[[p] for p in range(458, 466, 2)]],
    '05': [[468, 470], [514, 516], *[[p, p + 2] for p in range(532, 554, 4)], [634, 636], [637, 638], [640, 642], [644, 645]],
}
NAMES = ['적용인구', '진료현황_계', '관내_계', '관내_입원', '관내_외래',
         '관외_계', '관외_입원', '관외_외래', '주요질환_고혈압_당뇨',
         '주요질환_치주질환_관절염', '주요질환_정신질환_감염병', '주요질환_간질환']


def clean(value):
    """빈 셀은 빈 문자열로, 줄바꿈과 연속 공백은 한 칸으로 정리한다."""
    return re.sub(r'\s+', ' ', str(value)).strip() if value is not None else ''


def extract(sheet):
    """표에서 열 이름, 데이터 행, 하단 각주를 분리해 반환한다."""
    rows = list(sheet.values)
    # 5행의 영문 지역명(Division) 열까지가 실제 표 영역이다.
    width = next(i + 1 for i, v in enumerate(rows[4]) if clean(v) == 'Division')
    # 10행부터 지역명과 수치가 있는 행만 선택한다.
    # 첫 값이 미집계(-)여도 다른 열에 수치가 있으면 보존한다.
    data = []
    for i, row in enumerate(rows):
        if i < 9 or not clean(row[0]):
            continue
        has_number = isinstance(row[1], (int, float))
        has_other_number = any(isinstance(v, (int, float)) for v in row[2:width-1])
        if has_number or (clean(row[1]) == '-' and has_other_number):
            data.append((i, list(row[:width])))
    assert data, f'No data: {sheet.title}'
    # 원본 행 번호로 머리글과 본문의 경계를 구분한다.
    first = data[0][0]
    header_grid = [[clean(v) for v in row[:width]] for row in rows[4:first]]
    # 병합 셀의 제목을 가로로 펼쳐 각 열에 상위 제목을 붙인다.
    for merged in sheet.merged_cells.ranges:
        if merged.min_row < 5 or merged.min_row > first:
            continue
        value = clean(sheet.cell(merged.min_row, merged.min_col).value)
        for col in range(merged.min_col, min(merged.max_col, width) + 1):
            header_grid[merged.min_row - 5][col - 1] = value
    # 여러 줄의 열 제목을 합치면서 중복 제목은 한 번만 넣는다.
    headers = []
    for col in range(width):
        parts = list(dict.fromkeys(row[col] for row in header_grid if row[col]))
        headers.append(' / '.join(parts) or f'column_{col+1}')
    assert len(set(headers)) == width, (sheet.title, headers)
    # 표 아래 단위 설명과 주의사항은 데이터와 분리하여 보관한다.
    notes = [[clean(v) for v in row[:width]] for row in rows[data[-1][0]+1:]
             if any(v is not None for v in row[:width])]
    return headers, [[clean(v) if isinstance(v, str) else v for v in row] for _, row in data], notes


# 원본별로 표를 추출하고 출처 목록과 각주를 저장한다.
OUTPUT.mkdir(parents=True, exist_ok=True)
manifest = []
notes = []
for prefix, groups in PLAN.items():
    # 원본이 없거나 여러 개면 임의로 선택하지 않고 중단한다.
    paths = list((ROOT / 'data').glob(prefix + '*.xlsx'))
    assert len(paths) == 1, paths
    path = paths[0]
    # 수식 대신 엑셀에 저장된 계산 결과를 읽는다.
    book = openpyxl.load_workbook(path, data_only=True)
    # 시트 순서 대신 시트 이름 앞의 페이지 번호로 조회한다.
    pages = {int(m.group(1)): sheet for sheet in book
             if (m := re.match(r'^(\d+)p', sheet.title))}
    folder = OUTPUT / path.stem
    folder.mkdir(exist_ok=True)
    for name, numbers in zip(NAMES, groups, strict=True):
        combined = []
        headers = None
        for number in numbers:
            sheet = pages[number]
            current, data, footnotes = extract(sheet)
            if headers is None:
                headers = current
            assert len(current) == len(headers), (path.name, sheet.title)
            # 제목에 오타가 있을 수 있어 질환명 셀로 연속 페이지의 일치를 확인한다.
            if name.startswith('주요질환'):
                assert clean(sheet.cell(5, 2).value) == clean(pages[numbers[0]].cell(5, 2).value)
            combined.extend(data)
            notes.append({'file': path.name, 'sheet': sheet.title, 'notes': footnotes})
            manifest.append([path.name, name, sheet.title, len(data), str((folder / (name + '.csv')).relative_to(OUTPUT))])
        # 엑셀에서 한글이 깨지지 않도록 BOM이 있는 UTF-8로 저장한다.
        with (folder / (name + '.csv')).open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(combined)
    book.close()
# 원본 시트와 데이터 행 수를 남겨 변환 결과를 추적한다.
with (OUTPUT / '변환목록.csv').open('w', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['원본파일', '표구분', '원본시트', '데이터행수', 'CSV경로'])
    writer.writerows(manifest)
(OUTPUT / '원본주석.json').write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'변환 완료: CSV {len(set(row[4] for row in manifest))}개, 원본 시트 {len(manifest)}개')
