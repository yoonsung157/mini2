"""Playwright로 2025년 의료공백 보도를 수집한다.
실행: python hsyonii/의료공백_크롤링.py --search (뉴스 검색부터 자동 수집)
기존 검토 기사만 재수집하려면 --refresh, 저장 자료만 정리하려면 옵션 없이 실행
패키지: playwright, beautifulsoup4, pandas / 현재 PC의 Edge 사용
"""
import json
import re
import sys
import hashlib
from urllib.parse import urlencode, urlsplit
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Error as PlaywrightError

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'hsyonii' / 'csv_before' / '의료공백_2025'
OUTPUT = ROOT / 'hsyonii' / 'csv_after'
OUTPUT.mkdir(exist_ok=True)
TODAY = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
# 주소와 수동 분류는 입력 CSV에서 수정한다. 분류 내용은 웹 자동 추출값이 아니다.
sources = pd.read_csv(RAW / '수집대상.csv')
cases = pd.read_csv(RAW / '사례분류.csv').set_index('사건ID').to_dict('index')
media_names = {'science.ytn.co.kr':'YTN 사이언스','www.kwnews.co.kr':'강원일보',
               'www.donga.com':'동아일보','www.hankyung.com':'한국경제','www.yna.co.kr':'연합뉴스'}
records = []
errors = []
search_mode = '--search' in sys.argv
search_log = []

# 1. 캐시가 있으면 재사용하고, 새로 수집할 때만 브라우저를 연다.
with sync_playwright() as playwright:
    browser = None
    try:
        # 검색어마다 2페이지를 확인한다. 검색 결과는 전수자료가 아니다.
        if search_mode:
            browser = playwright.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page()
            found = {}
            for keyword in ['응급실 운영 중단', '보건지소 의사 부족', '야간 진료 축소']:
                for number in [1, 2]:
                    search_url = 'https://search.daum.net/search?' + urlencode({
                        'w':'news', 'q':keyword, 'period':'u',
                        'sd':'20250101000000', 'ed':'20251231235959', 'p':number})
                    try:
                        response = page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
                        if response is None or response.status >= 400:
                            raise ValueError('검색 페이지 접속 실패')
                        page.wait_for_selector('a[href*="v.daum.net/v/"]', timeout=10000)
                        soup = BeautifulSoup(page.content(), 'html.parser')
                        urls = set()
                        for link in soup.select('a[href]'):
                            address = urlsplit(link['href'])
                            if address.hostname != 'v.daum.net' or not address.path.startswith('/v/'):
                                continue
                            # http/https 또는 추적용 쿼리가 달라도 같은 기사로 처리한다.
                            url = 'https://v.daum.net' + address.path.rstrip('/')
                            urls.add(url)
                            if url not in found:
                                found[url] = {'수집ID':'auto_' + hashlib.sha256(url.encode()).hexdigest()[:16],
                                              '사건ID':'미분류', '원문URL':url,
                                              '검색어':keyword, '검색페이지':search_url}
                        search_log.append({'검색어':keyword, '페이지':number, '검색URL':search_url,
                                           '발견URL수':len(urls)})
                        page.wait_for_timeout(1000)
                    except (PlaywrightError, ValueError):
                        errors.append({'원문URL':search_url, '사유':'검색 접속 실패 또는 기사 링크 없음'})
            if not found:
                raise SystemExit('검색에서 기사 주소를 찾지 못했습니다. 차단 여부와 검색 화면을 확인하세요.')
            sources = pd.DataFrame(found.values())
            sources.to_csv(RAW / '자동검색_수집대상.csv', index=False, encoding='utf-8-sig')
            print(f'검색 완료: 중복 제거 후 기사 주소 {len(sources)}개', flush=True)
        for position, row in enumerate(sources.itertuples(index=False), start=1):
            if position == 1 or position % 10 == 0:
                print(f'기사 확인 중: {position}/{len(sources)}', flush=True)
            url = row.원문URL
            cache = RAW / f'{row.수집ID}.json'
            if cache.exists() and '--refresh' not in sys.argv:
                item = json.loads(cache.read_text(encoding='utf-8'))
                if search_mode:
                    item.update({'검색어':row.검색어, '검색페이지':row.검색페이지})
                records.append(item)
                continue
            if browser is None:
                browser = playwright.chromium.launch(channel='msedge', headless=True)
                page = browser.new_page()
            try:
                response = page.goto(url, wait_until='domcontentloaded', timeout=30000)
                if response is None or response.status >= 400:
                    raise ValueError('페이지 접속 실패')
                page.wait_for_selector('meta[property="og:title"]', state='attached', timeout=10000)
                soup = BeautifulSoup(page.content(), 'html.parser')
                page.wait_for_timeout(500)  # 연속 요청 간격을 둔다.
            except (PlaywrightError, ValueError):
                errors.append({'원문URL':url,'사유':'페이지 접속·로딩 실패'})
                continue

            # 2. 기사 제목·매체와 최초 게시일을 읽는다. 수정일·URL 날짜는 사용하지 않는다.
            title = soup.select_one('meta[property="og:title"]').get('content', '').strip()
            tag = soup.select_one('meta[property="og:site_name"]')
            media = tag.get('content','').replace('Daum | ', '').strip() if tag else ''
            media = media or media_names.get(page.url.split('/')[2], '')
            published = ''
            date_key = ''
            for key in ['article:published_time','og:regDate','og:pubdate','dd:published_time','article:published']:
                tag = soup.find('meta', property=key) or soup.find('meta', attrs={'name':key})
                if not tag or not tag.get('content'):
                    continue
                value = tag['content']
                if re.match(r'^\d{8}', value):
                    published = pd.to_datetime(value[:8], format='%Y%m%d').date().isoformat()
                elif re.match(r'^\d{4}-\d{2}-\d{2}', value):
                    published = value[:10]
                if published:
                    date_key = key
                    break
            # 메타데이터가 없으면 본문에 명시된 '입력일'만 확인한다.
            if not published:
                match = re.search(r'입력\s*[:：]?\s*(2025[.\-/]\d{2}[.\-/]\d{2})', soup.get_text(' ', strip=True))
                if match:
                    published = match.group(1).replace('.', '-').replace('/', '-')
                    date_key = '본문의 최초 입력일 표시'
            if not title or not media or not published.startswith('2025-'):
                errors.append({'원문URL':url,'사유':'제목·매체·2025년 게시일 확인 불가'})
                continue
            item = {'사건ID':row.사건ID,'매체':media,'제목':title,'게시일':published,
                    '게시일근거':date_key,'원문URL':url,'수집일':TODAY,
                    '수집방식':'Playwright 브라우저 + BeautifulSoup'}
            if search_mode:
                item.update({'검색어':row.검색어, '검색페이지':row.검색페이지,
                             '검토상태':'미검토: 관련성·사건 중복·원인·실제 시행 여부 확인 필요'})
            # 기사 전문·사진을 복사하지 않고 확인에 필요한 메타데이터만 저장한다.
            cache.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding='utf-8')
            records.append(item)
    finally:
        if browser is not None:
            browser.close()

if not records:
    raise SystemExit('수집한 보도가 없습니다.')
articles = pd.DataFrame(records).drop_duplicates('원문URL').sort_values('게시일')
if not pd.to_datetime(articles['게시일']).dt.year.eq(2025).all():
    raise ValueError('2025년이 아닌 자료가 포함되어 있습니다.')
if search_mode:
    # 기사 URL 중복만 제거했다. 동일 사건의 다른 기사인지는 사람이 검토해야 한다.
    articles.to_csv(OUTPUT / '2025_의료공백_자동검색_보도목록.csv', index=False, encoding='utf-8-sig')
    (RAW / '자동검색_수집기록.json').write_text(json.dumps({
        '수집일':TODAY, '검색기록':search_log, '발견URL수':len(sources),
        '2025년게시일확인보도수':len(articles), '실패':errors,
        '범위':'검색어 3개별 검색 결과 2페이지 내 다음 뉴스 기사. 전국 전수자료 아님.',
        '주의':'기사 내용의 관련성과 사건 단위 중복은 미검토. 기존 사례집과 별도 저장.'
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(articles[['게시일','매체','제목']].head(10).to_string(index=False))
    print(f'완료: 자동검색 기사 {len(articles)}개, 제외·실패 {len(errors)}개 (미검토 자료)')
    raise SystemExit()
articles.to_csv(OUTPUT / '2025_의료공백_보도목록.csv', index=False, encoding='utf-8-sig')

# 3. 같은 사건의 여러 기사를 하나로 묶고 검토한 분류 정보를 연결한다.
rows = []
for case_id, group in articles.groupby('사건ID', sort=False):
    rows.append({
        '사건ID':case_id, **cases[case_id],
        '검토방식':'사건 분류·메모는 원문 검토, 제목·게시일·매체는 웹 자동 수집',
        '최초확인보도일':group['게시일'].min(), '최종확인보도일':group['게시일'].max(),
        '확인보도수':len(group), '출처URL':' | '.join(group['원문URL']),
    })
case_df = pd.DataFrame(rows)
case_df.to_csv(OUTPUT / '2025_의료공백_사례정리.csv', index=False, encoding='utf-8-sig')
log = {'수집일':TODAY,'기준':'최초 게시일이 2025년인 공개 보도',
       '방식':'Playwright 브라우저 + BeautifulSoup HTML 크롤링. Open API 미사용.',
       '선정':'공개 검색으로 찾은 목적표집 사례. 전체 보도 또는 사건 전수 아님.',
       '대상URL수':len(sources),'확인보도수':len(articles),'중복사건통합후사례수':len(case_df),
       '실패':errors,'주의':'지역별 발생률 비교용이 아닌 서론용 사례집'}
(RAW / '수집기록.json').write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding='utf-8')

# 4. 서론에 사용할 요약과 출처를 함께 남긴다.
report = [
    '# 2025년 진료 중단·축소 보도 사례', '',
    f'수집 보도 {len(articles)}개 / 중복 사건 통합 후 {len(case_df)}개 사례 / 실패 {len(errors)}개', '',
    'Playwright로 제목·게시일·매체를 수집하고, 지역·기관·원인은 입력 CSV의 검토 정보를 연결했다.',
    '전국 전수자료가 아니므로 지역별 발생률을 비교하는 자료로 사용하지 않는다.', '',
    '| 지역 | 기관 | 내용 | 구분 |', '|---|---|---|---|',
]
for row in case_df.itertuples(index=False):
    report.append(f'| {row.시도} {row.지역} | {row.기관} | {row.제한범위} | {row.상태구분} |')
report += ['', '## 서론용 문제 제기', '',
    '의료 접근성을 이해하려면 시설과 인력의 분포뿐 아니라 필요한 시점에 진료가 가능한지도 살펴봐야 한다. '
    '2025년의 응급진료·야간수술·공공보건 진료 중단과 제한 계획 보도는 서비스 지속성도 검토할 필요성을 보여준다.', '',
    '게시일과 사건 시작일, 중단 계획과 실제 시행, 부분 제한과 전체 폐쇄를 구분해야 한다. '
    '전산·재정 문제를 인력 부족으로 단정하거나 운영예정 보도를 실제 재개로 해석하지 않는다.', '',
    '## 원문 출처', '',
]
for row in articles.itertuples(index=False):
    report.append(f'- {row.게시일} / {row.매체}: [{row.제목}]({row.원문URL})')
(OUTPUT / '2025_의료공백_서론자료.md').write_text('\n'.join(report)+'\n', encoding='utf-8')
print(f'완료: 보도 {len(articles)}개, 사례 {len(case_df)}개, 실패 {len(errors)}개')
