# 데이터 전처리
import pandas as pd

# 1. 시,도 별
file_path = "data/data_hsyonii/전국시도별_보험적용현황.xlsx"
excel = pd.ExcelFile(file_path)
# 시트별로 csv 파일변환
for sheet in excel.sheet_names:
    # pd.read_excel( 파일, sheet_name=시트이름 )
    # : 엑셀에서 sheet_name과 일치하는 시트를읽어 데이터프레임으로 반환
    df=pd.read_excel(
        file_path,
        sheet_name=sheet
    )
    # .to_csv( 경로, index=True or False, encoding="utf-8-sig") : 데이터 프레임을 지정한 경로에 csv파일로 변환하여 저장
    # *index= True면 행인덱스 포함, False는 불포함
    df.to_csv(
        f"data/{sheet}.csv",
        index=False,
        encoding="utf-8-sig"
    )
    print(f"{sheet}.csv 생성됨.")
