import os

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

sns.set_theme(font='Malgun Gothic', rc={'axes.unicode_minus': False}, style='whitegrid')
os.makedirs('./images', exist_ok=True)

# ===================================================================================================
# 데이터 불러오기
# ===================================================================================================
df = pd.read_csv('./data/병원정보.csv', encoding='cp949')
population = pd.read_csv('./data/인구수.csv', encoding='cp949', thousands=',')
population2 = pd.read_csv('./data/시군구단위인구수.csv', encoding='cp949', thousands=',')

CAPITAL = ['서울', '인천', '경기']
# 병원정보의 시도코드명은 '전남'이 아니라 '전남광주'
DO_SHORT = ['강원', '충북', '충남', '전북', '전남광주', '경북', '경남', '제주']
DO_FULL = ['강원특별자치도', '충청북도', '충청남도', '전북특별자치도',
           '전남광주통합특별시', '경상북도', '경상남도', '제주특별자치도']
HOSPITAL = ['상급종합', '종합병원']
PUBLIC = ['보건소', '보건지소', '보건진료소', '보건의료원']


def per_100k(count, pop):
    return count / pop * 100000


def non_capital_do(data):
    """비수도권 도 지역만 남기고, 전남광주에 포함된 광주 자치구는 제외"""
    data = data[data['시도코드명'].isin(DO_SHORT)]
    gu = (data['시도코드명'] == '전남광주') & data['시군구코드명'].str.endswith('구', na=False)
    return data[~gu]


# ===================================================================================================
# 인구 수
# ===================================================================================================
# 수도권 / 비수도권
pop = population.set_index('행정구역')['총인구수']
capital_pop = pop['서울특별시'] + pop['인천광역시'] + pop['경기도']
other_pop = pop['전국'] - capital_pop

# 비수도권 시 / 군
name = population2['행정구역'].str.replace(r'\s*\(.*\)', '', regex=True).str.split()
sido = name.str[0]
sigungu = name.str[1]

# '창원시 의창구'처럼 구가 붙은 행은 시 인구와 중복되므로 제외
use = sido.isin(DO_FULL) & (name.str.len() == 2)
pop_col = '2026년09월_총인구수'

si_pop = population2.loc[use & sigungu.str.endswith('시', na=False), pop_col].sum()
gun_pop = population2.loc[use & sigungu.str.endswith('군', na=False), pop_col].sum()

# ===================================================================================================
# 1. 수도권은 비수도권보다, 시 지역은 군 지역보다
#    인구 10만 명당 종합병원·상급종합병원 수가 많을 것이다.
# ===================================================================================================
a = df[df['종별코드명'].isin(HOSPITAL)]
is_capital = a['시도코드명'].isin(CAPITAL)

# 1-1. 수도권 vs 비수도권
capital_hospital = is_capital.sum()
other_hospital = len(a) - capital_hospital

print('[1-1] 수도권:', per_100k(capital_hospital, capital_pop))
print('[1-1] 비수도권:', per_100k(other_hospital, other_pop))
# 수도권: 0.59  (153곳)
# 비수도권: 0.93  (231곳)
# -> 오히려 비수도권이 인구 대비 병원 수가 더 많다

# 1-2. 비수도권 시 vs 군
b = non_capital_do(a)
print(b['시도코드명'].value_counts())   # 필터 후 시도별 병원 수 확인

gun_hospital = b['시군구코드명'].str.endswith('군', na=False).sum()
si_hospital = len(b) - gun_hospital

print('[1-2] 시:', per_100k(si_hospital, si_pop))
print('[1-2] 군:', per_100k(gun_hospital, gun_pop))
# 시: 0.99  (118곳 / 인구 11,876,621명)
# 군: 0.56  (18곳 / 인구 3,203,317명)
# -> 군 지역이 시 지역보다 약 1.8배 적다

# 1-3. (보충) 인구 10만 명당 의사 수
capital_doctor = a.loc[is_capital, '총의사수'].sum()
other_doctor = a['총의사수'].sum() - capital_doctor

print('[1-3] 수도권 의사:', per_100k(capital_doctor, capital_pop))
print('[1-3] 비수도권 의사:', per_100k(other_doctor, other_pop))
# 수도권 의사: 103.0
# 비수도권 의사: 75.6
# -> 병원 수는 비수도권이 많지만 병원 규모 차이 때문에 의사 수는 수도권이 더 많다


# ===================================================================================================
# 2. 비수도권 군 지역은 종합병원이 부족한 대신, 인구 10만 명당 공공보건기관
#    (보건소·보건지소·보건진료소·보건의료원) 수가 시 지역보다 많을 것이다.
# ===================================================================================================
c = non_capital_do(df[df['종별코드명'].isin(PUBLIC)])
is_gun = c['시군구코드명'].str.endswith('군', na=False)

gun_public = is_gun.sum()
si_public = len(c) - gun_public

print('[2] 시 공공보건기관:', per_100k(si_public, si_pop))
print('[2] 군 공공보건기관:', per_100k(gun_public, gun_pop))
# 시: 10.3  (1,228곳)
# 군: 52.0  (1,666곳)

# 종류별 개수
print(c.assign(지역=is_gun.map({True: '군', False: '시'}))
       .groupby(['종별코드명', '지역']).size().unstack(fill_value=0))
# 보건진료소 시 709 / 군 951, 보건지소 시 455 / 군 642, 보건소 시 64 / 군 58, 보건의료원 군에만 15

# -> 채택: 군 지역은 종합병원은 시의 약 57% 수준이지만, 공공보건기관은 약 5배 많아
#    공공의료 의존도가 높다

# ===================================================================================================
# 시각화
# ===================================================================================================
BLUE, ORANGE = '#2a78d6', '#eb6834'   # 수도권·시 / 비수도권·군
INK, MUTED = '#0b0b0b', '#52514e'


def style(ax, title, ymax):
    ax.set_title(title, fontsize=13, color=INK, loc='left')
    ax.set_ylim(0, ymax)
    ax.tick_params(colors=MUTED)
    ax.grid(axis='x', visible=False)
    sns.despine(ax=ax, left=True)


def label(ax, bar, text):
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), text,
            ha='center', va='bottom', fontsize=11, color=INK, linespacing=1.5)


def bar_panel(ax, labels, values, title, fmt, notes=None):
    bars = ax.bar(labels, values, color=[BLUE, ORANGE], width=0.5)
    for i, (bar, v) in enumerate(zip(bars, values)):
        label(ax, bar, fmt.format(v) + (f'\n({notes[i]})' if notes else ''))
    style(ax, title, max(values) * 1.25)


# 그림 1. 수도권 vs 비수도권: 병원 수와 의사 수 (인구 10만 명당)
fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
bar_panel(axes[0], ['수도권', '비수도권'],
          [per_100k(capital_hospital, capital_pop), per_100k(other_hospital, other_pop)],
          '인구 10만 명당 종합·상급종합병원 수', '{:.2f}곳',
          [f'{capital_hospital}곳', f'{other_hospital}곳'])
bar_panel(axes[1], ['수도권', '비수도권'],
          [per_100k(capital_doctor, capital_pop), per_100k(other_doctor, other_pop)],
          '인구 10만 명당 종합·상급종합병원 의사 수', '{:.1f}명')
fig.suptitle('병원 수는 비수도권이 많지만, 의사 수는 수도권이 많다', fontsize=15, x=0.02, ha='left')
fig.tight_layout()
fig.savefig('./images/1_수도권_병원수_의사수.png', dpi=200)

# 그림 2. 병원 1곳당 평균 의사 수 (병원 규모 차이)
size = (a.assign(권역=is_capital.map({True: '수도권', False: '비수도권'}))
         .groupby(['종별코드명', '권역'])['총의사수'].mean()
         .unstack()[['수도권', '비수도권']]
         .loc[['종합병원', '상급종합']])

fig, ax = plt.subplots(figsize=(8, 4.5))
w = 0.35
for j, (col, color) in enumerate([('수도권', BLUE), ('비수도권', ORANGE)]):
    pos = [i + (j - 0.5) * (w + 0.02) for i in range(len(size))]
    for bar, v in zip(ax.bar(pos, size[col], width=w, color=color, label=col), size[col]):
        label(ax, bar, f'{v:.0f}명')
ax.set_xticks(range(len(size)), size.index)
ax.legend(frameon=False, loc='upper left')
style(ax, '병원 1곳당 평균 의사 수: 수도권 병원이 약 2배 크다', size.values.max() * 1.15)
fig.tight_layout()
fig.savefig('./images/2_병원당_의사수.png', dpi=200)

# 그림 3. 비수도권 시 vs 군: 종합병원 수와 공공보건기관 수 (인구 10만 명당)
fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
bar_panel(axes[0], ['시 지역', '군 지역'],
          [per_100k(si_hospital, si_pop), per_100k(gun_hospital, gun_pop)],
          '인구 10만 명당 종합·상급종합병원 수', '{:.2f}곳',
          [f'{si_hospital}곳', f'{gun_hospital}곳'])
bar_panel(axes[1], ['시 지역', '군 지역'],
          [per_100k(si_public, si_pop), per_100k(gun_public, gun_pop)],
          '인구 10만 명당 공공보건기관 수', '{:.1f}곳',
          [f'{si_public:,}곳', f'{gun_public:,}곳'])
fig.suptitle('군 지역은 종합병원 대신 공공보건기관이 의료를 떠받친다', fontsize=15, x=0.02, ha='left')
fig.tight_layout()
fig.savefig('./images/3_시군_종합병원_공공보건기관.png', dpi=200)

plt.show()
