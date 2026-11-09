"""표별 CSV를 지역별로 합치고 의료이용 지표를 계산한다.
실행: python hsyonii/의료이용_전처리.py / 필요한 패키지: pandas
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / 'hsyonii' / 'csv_before'
OUTPUT = ROOT / 'hsyonii' / 'csv_after'
OUTPUT.mkdir(exist_ok=True)
PROVINCES = '서울 부산 대구 인천 광주 대전 울산 세종 경기 강원 충북 충남 전북 전남 경북 경남 제주'.split()
METRICS = ['진료실인원수', '입내원일수', '진료비']
CHRONIC = ['고혈압', '당뇨', '관절염', '간질환']
KEYS = ['시도', '지역']

# 1. 숫자로 시작하는 원본 폴더의 표만 읽는다. 크롤링 입력 CSV는 제외된다.
tables = []
populations = []
for path in sorted(INPUT.glob('[0-9][0-9]*/*.csv')):
    raw = pd.read_csv(path)
    region = raw.iloc[:, 0].str.replace(r'\s+', '', regex=True)
    # 시도 합계 행의 이름을 아래 시군구 행까지 채운다.
    table = pd.DataFrame({'시도': region.where(region.isin(PROVINCES)).ffill(), '지역': region})
    if table['시도'].isna().any() or table.duplicated(KEYS).any():
        raise ValueError(f'시도 누락 또는 지역 중복: {path}')

    if path.stem == '적용인구':
        table['적용인구'] = pd.to_numeric(raw.iloc[:, 1], errors='raise')
        populations.append(table)
        continue

    for column in raw.columns[1:]:
        parts = column.split(' / ')
        metric = parts[-1].split()[0] if parts[-1].split() else ''
        if metric not in METRICS:
            continue
        # 인당·일당 비율 열은 제외하고, 질환 표의 하위 제목은 질환명으로 사용한다.
        category = path.stem
        if len(parts) > 1:
            if not category.startswith('주요질환_'):
                continue
            category = '주요질환_' + parts[0].split('(')[0].strip()
        name = f'{category}_{metric}'
        if name in table:
            raise ValueError(f'중복된 지표: {path}, {name}')
        # 미집계(-)는 0이 아닌 결측치로 보존한다.
        values = raw[column].astype('string').str.replace(',', '', regex=False).replace('-', pd.NA)
        dtype = 'Float64' if metric == '진료비' else 'Int64'
        table[name] = pd.to_numeric(values, errors='raise').astype(dtype)
    if len(table.columns) == 2:
        raise ValueError(f'진료 항목이 없는 표: {path}')
    tables.append(table)

if not tables or not populations:
    raise SystemExit('먼저 python hsyonii/파일변환.py를 실행하세요.')
# 같은 지역의 서로 다른 항목을 한 행으로 모은다. 수치를 합산하지 않는다.
medical = pd.concat(tables).groupby(KEYS, as_index=False).first()
population = pd.concat(populations, ignore_index=True)
source = medical.merge(population, on=KEYS, how='left', validate='one_to_one')
if source['적용인구'].isna().any() or source['적용인구'].le(0).any():
    raise ValueError('적용인구가 누락되었거나 0 이하입니다.')

# 2. 시도 합계와 세부지역을 분리한다. 세종은 하위지역이 없어 양쪽에 포함한다.
province_mask = source['시도'].eq(source['지역'])
# 세종은 하위지역이 없으므로 세부지역 비교에 한 번 포함한다.
subsets = {
    '지역별': source.loc[~province_mask | source['시도'].eq('세종')],
    '시도별': source.loc[province_mask],
}
for name, subset in subsets.items():
    # 3. 총량과 인구 천명당 이용량을 계산한다. 진료비 단위는 천원이다.
    df = subset.copy()
    df['권역'] = df['시도'].isin(['서울', '경기', '인천']).map({True: '수도권', False: '비수도권'})
    for metric in METRICS:
        total = df[f'진료현황_계_{metric}']
        df[f'총의료이용_{metric}'] = total
        df[f'인구천명당_{metric}'] = total.div(df['적용인구']).mul(1000)
    # 관내·관외 환자는 겹칠 수 있어 실인원 합계로 이용률을 계산하지 않는다.
    # 입내원일수 기준을 대표 이용률로, 진료비 기준은 보조 지표로 사용한다.
    for metric in ('입내원일수', '진료비'):
        inside = df[f'관내_계_{metric}']
        outside = df[f'관외_계_{metric}']
        # 분모가 0이면 이용률을 0으로 단정하지 않고 결측치로 둔다.
        denominator = (inside + outside).replace(0, float('nan'))
        df[f'관외이용률_{metric}'] = outside / denominator
        # 원본 전체와 관내+관외 사이의 차이를 숨기지 않고 검토용으로 남긴다.
        df[f'관내외합계차이_{metric}'] = df[f'진료현황_계_{metric}'] - inside - outside
    # 여러 질환의 환자는 겹칠 수 있으므로 질환별로 따로 계산한다.
    for disease in CHRONIC:
        for metric in METRICS:
            df[f'{disease}_인구천명당_{metric}'] = (
                df[f'주요질환_{disease}_{metric}'] / df['적용인구'] * 1000
            )
    # 큰 값이 1위다. 동점은 같은 순위로 처리한다.
    df['총의료이용량_순위'] = df['총의료이용_입내원일수'].rank(method='min', ascending=False).astype('Int64')
    df['인구대비이용량_순위'] = df['인구천명당_입내원일수'].rank(method='min', ascending=False).astype('Int64')

    # 4. 순위·검토용 차이를 제외한 각 지표를 0~1로 정규화한다.
    columns = [column for column in df.select_dtypes(include='number')
               if not column.endswith('_순위') and not column.startswith('관내외합계차이_')]
    values = df[columns]
    low, high = values.min(), values.max()
    # 상수열은 0으로 변환하고 결측치는 그대로 남긴다.
    scaled = (values - low) / (high - low).replace(0, 1)
    normalized = pd.concat([df, scaled.add_suffix('_정규화')], axis=1)
    ranges = pd.DataFrame({'최솟값': low, '최댓값': high, '상수열': high.eq(low)})
    ranges = ranges.rename_axis('지표').reset_index()

    # 5. 수도권·비수도권별로 합계와 이용률을 비교한다.
    records = []
    # 지역평균은 모든 지역에 같은 가중치, 일수가중 비율은 이용 일수에 비례한다.
    # 인구당 권역 지표도 지역별 비율의 평균 대신 권역 전체 합계로 계산한다.
    for group, part in df.groupby('권역'):
        records.append({
            '권역': group, '지역수': len(part), '적용인구': part['적용인구'].sum(),
            '총입내원일수': part['총의료이용_입내원일수'].sum(),
            '총진료비_천원': part['총의료이용_진료비'].sum(),
            '인구천명당_입내원일수': part['총의료이용_입내원일수'].sum() / part['적용인구'].sum() * 1000,
            '관외이용률_지역평균': part['관외이용률_입내원일수'].mean(),
            '관외이용률_지역중앙값': part['관외이용률_입내원일수'].median(),
            '관외이용률_일수가중': part['관외_계_입내원일수'].sum() / (
                part['관외_계_입내원일수'].sum() + part['관내_계_입내원일수'].sum()),
        })
    summary = pd.DataFrame(records)

    # 6. 원래 지표와 정규화값·비교표를 저장한다.
    normalized.to_csv(OUTPUT / f'{name}_지표.csv', index=False, encoding='utf-8-sig')
    ranges.to_csv(OUTPUT / f'{name}_정규화범위.csv', index=False, encoding='utf-8-sig')
    summary.to_csv(OUTPUT / f'{name}_권역비교.csv', index=False, encoding='utf-8-sig')
    # 총량 순위와 인구당 순위는 서로 다른 질문이므로 둘 다 제공한다.
    comparison = ['시도', '지역', '권역', '적용인구'] + [
        f'{prefix}_{metric}' for prefix in ('총의료이용', '인구천명당') for metric in METRICS
    ] + ['관외이용률_입내원일수', '관외이용률_진료비', '총의료이용량_순위', '인구대비이용량_순위']
    df[comparison].sort_values('총의료이용량_순위').to_csv(
        OUTPUT / f'{name}_총의료이용량비교.csv', index=False, encoding='utf-8-sig')
    print(f'{name}: {len(df)}행 저장')
