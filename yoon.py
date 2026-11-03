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

# ---------------------------------------------------------------------------------------------------

# 2. 비수도권 내에서도 시 지역보다 군 지역의 인구 10만 명당 종합병원·상급종합병원 수가 적을 것이다.
# 병원 수
do_short = ['강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주']

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

# 시: 0.8419903270467248
# 군: 0.28095876867634395