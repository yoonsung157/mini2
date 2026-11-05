import pandas as pd
import matplotlib.pyplot as plt

import seaborn as sns
sns.set_theme(font='Malgun Gothic', rc={'axes.unicode_minus': False}, style='whitegrid')

df = pd.read_csv('./data/병원정보.csv', encoding='cp949')
population = pd.read_csv('./data/인구수.csv', encoding='cp949', thousands=',')
# 1. 수도권은 비수도권보다 인구 10만 명당 종합병원·상급종합병원 수가 많을 것이다. 
# 병원 수
a = df[df['종별코드명'].isin(['상급종합', '종합병원'])]
capital_hospital = a['시도코드명'].isin(['서울', '인천', '경기']).sum()
other_hospital = len(a) - capital_hospital

# 인구 수
pop = population.set_index('행정구역')['총인구수']
capital_pop = pop['서울특별시'] + pop['인천광역시'] + pop['경기도']
other_pop = pop['전국'] - capital_pop

# 인구 10만 명당 병원 수
print('수도권:', capital_hospital / capital_pop * 100000)
print('비수도권:', other_hospital / other_pop * 100000)

# 수도권: 0.585637526734066
# 비수도권: 0.9255899413777009
# 오히려 수도권이 인구수대비 병원 수가 더 적다

# 인구 10만 명당 의사 수 (종합·상급종합)
capital_doctor = a.loc[a['시도코드명'].isin(['서울', '인천', '경기']), '총의사수'].sum()
other_doctor = a['총의사수'].sum() - capital_doctor

print('수도권 의사:', capital_doctor / capital_pop * 100000)
print('비수도권 의사:', other_doctor / other_pop * 100000)

# 수도권 의사: 103.0
# 비수도권 의사: 75.6

# 병원 수는 비수도권이 더 많지만 규모차이때문에 의사 수는 수도권이 더 많다.
# ---------------------------------------------------------------------------------------------------

# 2. 비수도권 내에서도 시 지역보다 군 지역의 인구 10만 명당 종합병원·상급종합병원 수가 적을 것이다.
# 병원 수
# 병원정보의 시도코드명은 '전남'이 아니라 '전남광주'
do_short = ['강원', '충북', '충남', '전북', '전남광주', '경북', '경남', '제주']

b = df[df['종별코드명'].isin(['상급종합', '종합병원']) & df['시도코드명'].isin(do_short)]

# 전남광주에 포함된 광주의 구 제외
gu = (b['시도코드명'] == '전남광주') & b['시군구코드명'].str.endswith('구', na=False)
b = b[~gu]

gun_hospital = b['시군구코드명'].str.endswith('군', na=False).sum()
si_hospital = len(b) - gun_hospital

# 인구 수
population2 = pd.read_csv('./data/시군구단위인구수.csv', encoding='cp949', thousands=',')

name = population2['행정구역'].str.replace(r'\s*\(.*\)', '', regex=True).str.split()
sido = name.str[0]
sigungu = name.str[1]

do_full = ['강원특별자치도', '충청북도', '충청남도', '전북특별자치도',
           '전남광주통합특별시', '경상북도', '경상남도', '제주특별자치도']

# '창원시 의창구'처럼 구가 붙은 행은 시 인구와 중복되므로 제외
use = sido.isin(do_full) & (name.str.len() == 2)
pop_col = '2026년09월_총인구수'

gun_pop = population2.loc[use & sigungu.str.endswith('군', na=False), pop_col].sum()
si_pop = population2.loc[use & sigungu.str.endswith('시', na=False), pop_col].sum()

# 인구 10만 명당 병원 수
print('시:', si_hospital / si_pop * 100000)
print('군:', gun_hospital / gun_pop * 100000)

# 시: 0.9935485859151353  (병원 118곳 / 인구 11,876,621명)
# 군: 0.5619175373526879  (병원 18곳 / 인구 3,203,317명)
# 군 지역이 시 지역보다 인구 대비 병원 수가 적다 (약 1.8배 차이)
# ---------------------------------------------------------------------------------------------------
# 시각화
import os
os.makedirs('./images', exist_ok=True)

BLUE, ORANGE = '#2a78d6', '#eb6834'   # 수도권·시 / 비수도권·군
INK, MUTED = '#0b0b0b', '#52514e'


def bar_panel(ax, labels, values, colors, title, fmt, notes=None):
    bars = ax.bar(labels, values, color=colors, width=0.5)
    for i, (bar, v) in enumerate(zip(bars, values)):
        text = fmt.format(v) + (f'\n({notes[i]})' if notes else '')
        ax.text(bar.get_x() + bar.get_width() / 2, v, text,
                ha='center', va='bottom', fontsize=11, color=INK, linespacing=1.5)
    ax.set_title(title, fontsize=13, color=INK, loc='left')
    ax.set_ylim(0, max(values) * 1.25)
    ax.tick_params(colors=MUTED)
    ax.grid(axis='x', visible=False)
    sns.despine(ax=ax, left=True)


# 그림 1. 수도권 vs 비수도권: 병원 수와 의사 수 (인구 10만 명당)
fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
bar_panel(axes[0], ['수도권', '비수도권'],
          [capital_hospital / capital_pop * 1e5, other_hospital / other_pop * 1e5],
          [BLUE, ORANGE], '인구 10만 명당 종합·상급종합병원 수', '{:.2f}곳',
          [f'{capital_hospital}곳', f'{other_hospital}곳'])
bar_panel(axes[1], ['수도권', '비수도권'],
          [capital_doctor / capital_pop * 1e5, other_doctor / other_pop * 1e5],
          [BLUE, ORANGE], '인구 10만 명당 종합·상급종합병원 의사 수', '{:.1f}명')
fig.suptitle('병원 수는 비수도권이 많지만, 의사 수는 수도권이 많다', fontsize=15, x=0.02, ha='left')
fig.tight_layout()
fig.savefig('./images/1_수도권_병원수_의사수.png', dpi=200)

# 그림 2. 병원 1곳당 의사 수 (병원 규모 차이)
capital = a['시도코드명'].isin(['서울', '인천', '경기'])
size = (a.assign(권역=capital.map({True: '수도권', False: '비수도권'}))
         .groupby(['종별코드명', '권역'])['총의사수'].mean()
         .unstack()[['수도권', '비수도권']]
         .loc[['종합병원', '상급종합']])

fig, ax = plt.subplots(figsize=(8, 4.5))
x = range(len(size))
w = 0.35
for j, (col, color) in enumerate([('수도권', BLUE), ('비수도권', ORANGE)]):
    pos = [i + (j - 0.5) * (w + 0.02) for i in x]
    bars = ax.bar(pos, size[col], width=w, color=color, label=col)
    for bar, v in zip(bars, size[col]):
        ax.text(bar.get_x() + bar.get_width() / 2, v, f'{v:.0f}명',
                ha='center', va='bottom', fontsize=11, color=INK, linespacing=1.5)
ax.set_xticks(list(x), size.index)
ax.set_ylim(0, size.values.max() * 1.15)
ax.set_title('병원 1곳당 평균 의사 수: 수도권 병원이 약 2배 크다', fontsize=14, color=INK, loc='left')
ax.legend(frameon=False, loc='upper left')
ax.tick_params(colors=MUTED)
ax.grid(axis='x', visible=False)
sns.despine(ax=ax, left=True)
fig.tight_layout()
fig.savefig('./images/2_병원당_의사수.png', dpi=200)

# 그림 3. 비수도권 시 vs 군 (인구 10만 명당 병원 수)
fig, ax = plt.subplots(figsize=(6, 4.5))
bar_panel(ax, ['시 지역', '군 지역'],
          [si_hospital / si_pop * 1e5, gun_hospital / gun_pop * 1e5],
          [BLUE, ORANGE], '비수도권 인구 10만 명당 종합·상급종합병원 수', '{:.2f}곳',
          [f'{si_hospital}곳', f'{gun_hospital}곳'])
fig.tight_layout()
fig.savefig('./images/3_시군_병원수.png', dpi=200)

plt.show()
