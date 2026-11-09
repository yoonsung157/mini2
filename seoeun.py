import pandas as pd
import matplotlib.pyplot as plt

plt.rc("font", family="Malgun Gothic")
plt.rcParams["axes.unicode_minus"] = False


data_list = []
for quarter in range(1, 5):
    file_path = rf"C:\Users\gmgd0\mini2\data\지역별종별_전문과목별전문의수_2025년{quarter}분기.csv"
    data = pd.read_csv(file_path, encoding="utf-8-sig", header=2)
    data.columns = data.columns.str.strip()
    data["분기"] = quarter
    data_list.append(data)
df = pd.concat(data_list, ignore_index=True)

# 종합병원과 상급종합병원 선택
df["시도"] = df["시도"].astype("string").str.strip()
df["요양기관종별"] = (
    df["요양기관종별"].astype("string").str.strip()
)

hospital_types = ["종합병원", "상급종합병원"]
df = df[df["요양기관종별"].isin(hospital_types)].copy()

# 분석할 전문과목 선택
specialties = [
    "내과", "신경과", "정신건강의학과", "외과", "정형외과",
    "신경외과", "심장혈관흉부외과", "성형외과", "마취통증의학과",
    "산부인과", "소아청소년과", "안과", "이비인후과", "피부과",
    "비뇨의학과", "영상의학과", "방사선종양학과", "병리과",
    "진단검사의학과", "결핵과", "재활의학과", "핵의학과",
    "가정의학과", "응급의학과", "직업환경의학과", "예방의학과"
]

numeric_columns = ["합계"] + specialties
key_columns = ["시도", "요양기관종별", "분기"]

df = df[key_columns + numeric_columns].copy()

for column in numeric_columns:
    values = (
        df[column]
        .astype("string")
        .str.replace(",", "", regex=False)
        .str.strip()
    )

    numbers = pd.to_numeric(values, errors="coerce")
    df[column] = numbers.mask(numbers < 0)

# 중복 및 지역 누락 확인
if df.duplicated(key_columns).any():
    raise ValueError("같은 시도·기관종별·분기 자료가 중복됩니다.")

expected_regions = {
    "서울", "부산", "인천", "대구", "광주", "대전", "울산",
    "경기", "강원", "충북", "충남", "전북", "전남",
    "경북", "경남", "제주", "세종"
}

for quarter in range(1, 5):
    actual_regions = set(
        df.loc[df["분기"] == quarter, "시도"]
    )

    if actual_regions != expected_regions:
        raise ValueError(f"{quarter}분기의 시도 목록을 확인하세요.")


# 결측값이 포함되면 합계도 결측으로 유지
def complete_sum(values):
    return values.sum(skipna=False)


# 수도권·비수도권 구분
capital_regions = ["서울", "인천", "경기"]

df["권역"] = "비수도권"
df.loc[
    df["시도"].isin(capital_regions),
    "권역"
] = "수도권"

# 가설 3 — 권역별 소아청소년과 비중
regional_quarterly_totals = (
    df.groupby(["권역", "분기"])[["합계", "소아청소년과"]]
    .agg(complete_sum)
)

if regional_quarterly_totals.isna().any().any():
    raise ValueError(
        "가설 3에 필요한 합계 또는 소아청소년과 값에 결측이 있습니다."
    )

regional_annual_means = (
    regional_quarterly_totals.groupby("권역").mean()
)

if regional_annual_means["합계"].le(0).any():
    raise ValueError("권역별 전체 전문의 합계가 0 이하입니다.")

pediatric_share = (
    regional_annual_means["소아청소년과"]
    / regional_annual_means["합계"] * 100
).reindex(["수도권", "비수도권"])

if pediatric_share["수도권"] <= 0:
    raise ValueError("수도권 비중이 0이라 상대적 차이를 계산할 수 없습니다.")

relative_gap = (
    (pediatric_share["수도권"] - pediatric_share["비수도권"])
    / pediatric_share["수도권"] * 100
)

print("권역별 소아청소년과 전문의 비중(%)")
print(pediatric_share.round(2).to_string())
print(f"수도권 대비 비수도권의 상대적 차이: {relative_gap:.2f}%")

# 가설 3 시각화 
fig, ax = plt.subplots(figsize=(7, 5))

bars = ax.bar(
    pediatric_share.index,
    pediatric_share.values,
    color=["#4472C4", "#ED7D31"]
)

ax.bar_label(bars, fmt="%.2f%%", padding=4)
ax.set_ylim(0, pediatric_share.max() * 1.2)
ax.set_ylabel("전체 전문의 집계 수 중 소아청소년과 비중(%)")
ax.set_title(
    "2025년 종합병원·상급종합병원의 소아청소년과 비중"
)

fig.tight_layout()
fig.savefig(
    r"C:\Users\gmgd0\mini2\data\소아청소년과_권역별비중.png",
    dpi=200
)
plt.show()

# 가설 4 — 전국 전문과목별 감소율
national_totals = (
    df.groupby("분기")[specialties]
    .agg(complete_sum)
)

q1_totals = national_totals.loc[1]
q4_totals = national_totals.loc[4]

# 양수는 감소, 음수는 증가
decline_rate = (
    (q1_totals - q4_totals)
    / q1_totals.where(q1_totals > 0)
    * 100
)

results = pd.DataFrame({
    "1분기(명)": q1_totals,
    "4분기(명)": q4_totals,
    "감소율(%)": decline_rate
}).sort_values("감소율(%)", ascending=False)

# 감소한 과목만 순위 계산
declining_specialties = results[
    results["감소율(%)"] > 0
].copy()

declining_specialties["순위"] = (
    declining_specialties["감소율(%)"]
    .rank(ascending=False, method="min")
    .astype(int)
)

# 공동 5위가 있으면 모두 포함
top_five = declining_specialties[
    declining_specialties["순위"] <= 5
]

print("\n전문과목별 감소율")
print(results.round(2).to_string())

print("\n계산 가능한 과목 중 감소율 상위 5위")
print(top_five.round(2).to_string())

print("\n소아청소년과 변화")
print(results.loc[["소아청소년과"]].round(2).to_string())

unavailable_specialties = results.index[
    results["감소율(%)"].isna()
].tolist()

if unavailable_specialties:
    print(
        "\n결측 또는 1분기 0명으로 계산할 수 없는 과목:",
        ", ".join(unavailable_specialties)
    )
    print("전체 과목의 순위는 해당 자료 확인 후 확정합니다.")

# 가설 4 시각화 
plot_values = results["감소율(%)"].dropna()

if not plot_values.empty:
    colors = [
        "#D9534F" if specialty == "소아청소년과" else "#4472C4"
        for specialty in plot_values.index
    ]

    fig, ax = plt.subplots(figsize=(11, 9))

    bars = ax.barh(
        plot_values.index,
        plot_values.values,
        color=colors
    )

    ax.bar_label(bars, fmt="%.2f%%", padding=5, fontsize=9)
    ax.invert_yaxis()
    ax.axvline(0, color="gray", linewidth=1)
    ax.margins(x=0.25)

    ax.set_xlabel("1분기 대비 4분기 감소율(%) — 음수는 증가")
    ax.set_ylabel("전문과목")
    ax.set_title(
        "2025년 종합병원·상급종합병원 전문과목별 감소율"
    )
    ax.grid(axis="x", alpha=0.3)
    ax.set_axisbelow(True)

    fig.tight_layout()
    fig.savefig(
        r"C:\Users\gmgd0\mini2\data\전문과목별_감소율_막대그래프.png",
        dpi=200
    )
    plt.show()