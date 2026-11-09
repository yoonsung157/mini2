"""의료이용 지도 6개와 관외 이용률 상위 지역 막대그래프를 표시한다.
실행: python hsyonii/시각화.py / 패키지: pandas, geopandas, matplotlib, requests
"""
import json
from pathlib import Path
import requests
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'data' / 'maps'
FOLDER.mkdir(exist_ok=True)
YEAR = 2025  # 원본 파일명 기준. 실제 통계연도와 같은지 확인해야 한다.
CODES = {'서울':'11','부산':'21','대구':'22','인천':'23','광주':'24','대전':'25',
         '울산':'26','세종':'29','경기':'31','강원':'32','충북':'33','충남':'34',
         '전북':'35','전남':'36','경북':'37','경남':'38','제주':'39'}

# 1. 저장된 경계를 읽는다. 없는 시도만 인증 후 내려받는다.
features = []
token = None
for province, code in CODES.items():
    path = FOLDER / f'{YEAR}_{province}.geojson'
    if not path.exists():
        if token is None:
            from access_token import access_token
            token = access_token
        try:
            response = requests.get(
                'https://sgisapi.mods.go.kr/OpenAPI3/boundary/hadmarea.geojson',
                params={'accessToken':token,'year':YEAR,'adm_cd':code,'low_search':1}, timeout=90,
            )
            response.raise_for_status()
            boundary = response.json()
        except (requests.RequestException, ValueError):
            raise SystemExit(f'{province} 경계 다운로드에 실패했습니다.') from None
        if boundary.get('errCd') != 0 or not boundary.get('features'):
            raise SystemExit(f'{province} 경계 응답을 확인하세요.')
        # 토큰은 저장하지 않고 도형만 캐시에 남긴다.
        path.write_text(json.dumps({'type':'FeatureCollection','features':boundary['features']},
                                   ensure_ascii=False), encoding='utf-8')
    boundary = json.loads(path.read_text(encoding='utf-8'))
    for feature in boundary['features']:
        # '경기도 수원시 장안구'를 CSV의 '경기 / 수원시장안구'에 맞춘다.
        feature['properties']['시도'] = province
        feature['properties']['지역'] = '세종' if province == '세종' else ''.join(
            feature['properties']['adm_nm'].split()[1:])
        features.append(feature)

# 2. 지역명으로 지표를 연결한다. 원본 경계는 미터 단위 EPSG:5179다.
df = pd.read_csv(ROOT / 'hsyonii' / 'csv_after' / '지역별_지표.csv')
geo = gpd.GeoDataFrame.from_features(features, crs=5179)
geo = geo.merge(df, on=['시도','지역'], how='outer', validate='one_to_one', indicator=True)
if not geo['_merge'].eq('both').all():
    print(geo.loc[geo['_merge'].ne('both'), ['시도','지역','_merge']])
    raise SystemExit('경계와 CSV의 지역이 일치하지 않습니다.')
# 원본 도형의 자기교차를 복구하고 화면용 경계만 50m 이내에서 단순화한다.
geo['geometry'] = geo.geometry.make_valid().simplify(50, preserve_topology=True)
if not geo.geometry.is_valid.all():
    raise SystemExit('경계 도형을 확인하세요.')

# 3. 관외 비율과 인구당 이용량을 한 창의 2행 3열 지도에 표시한다.
plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False
maps = [
    ('관외 의료 이용률','관외이용률_입내원일수','입내원일수 기준 관외 이용률'),
    ('인구 대비 총의료 이용량','인구천명당_입내원일수_정규화','인구 천명당 입내원일수 · 정규화'),
]
for disease in ['고혈압','당뇨','관절염','간질환']:
    maps.append((f'{disease} 의료 이용량', f'{disease}_인구천명당_입내원일수_정규화',
                 '인구 천명당 질환 입내원일수 · 정규화'))
fig, axes = plt.subplots(2, 3, figsize=(16, 11))
fig.canvas.manager.set_window_title('지역별 의료이용 지도')
for ax, (title, column, label) in zip(axes.flat, maps):
    legend = {'label':label, 'shrink':0.7}
    if column == '관외이용률_입내원일수':
        legend['format'] = PercentFormatter(xmax=1)
    geo.plot(column=column, ax=ax, cmap='YlOrRd', vmin=0, vmax=1,
             edgecolor='#666666', linewidth=0.25, legend=True, legend_kwds=legend,
             missing_kwds={'color':'lightgrey'})
    ax.set_title(title)
    ax.set_axis_off()
fig.suptitle(f'지역별 의료이용 비교 · SGIS {YEAR} 경계 · {len(geo)}개 지역', fontsize=18)
fig.text(0.5, 0.03, '관외는 거주 시군구 밖 이용 · 고령인구·거리의 영향은 아직 검증하지 않음',
         ha='center')
fig.tight_layout(rect=[0, 0.06, 1, 0.94])

# 4. 원래 관외 이용률이 높은 지역을 표시한다. 동명 지역은 시도명으로 구분한다.
TOP_N = 15
rate_column = '관외이용률_입내원일수'
top_regions = df.dropna(subset=[rate_column]).sort_values(
    [rate_column,'시도','지역'], ascending=[False,True,True]).head(TOP_N).copy()
top_regions['지역명'] = top_regions['시도'] + ' ' + top_regions['지역']
bar_fig, bar_ax = plt.subplots(figsize=(10, 8))
bar_fig.canvas.manager.set_window_title('관외 의료 이용률 상위 지역')
bars = bar_ax.barh(top_regions['지역명'], top_regions[rate_column], color='#4477AA')
bar_ax.invert_yaxis()
bar_ax.set_xlim(0, 1)  # 0~100%를 표시해 지역 간 차이를 과장하지 않는다.
bar_ax.xaxis.set_major_formatter(PercentFormatter(xmax=1))
bar_ax.set_title(f'관외 의료 이용률 상위 {len(top_regions)}개 지역')
bar_ax.set_xlabel('입내원일수 기준 관외 의료 이용률')
bar_ax.grid(axis='x', alpha=0.25)
bar_ax.set_axisbelow(True)
bar_ax.bar_label(bars, labels=[f'{value:.2%}' for value in top_regions[rate_column]], padding=4)
bar_fig.tight_layout()

# 파일을 자동 저장하지 않고 두 개의 창을 함께 연다.
print('지도와 막대그래프 창을 닫으면 실행이 종료됩니다.')
plt.show()
