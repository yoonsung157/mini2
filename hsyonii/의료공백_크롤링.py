"""Playwright로 2025년 의료공백 보도를 수집한다.
실행: python hsyonii/의료공백_크롤링.py --search (뉴스 검색부터 자동 수집)
옵션 없이 실행하면 마지막 자동검색 주소와 저장된 기사 정보를 재사용한다.
--search --refresh는 검색과 기사 정보 수집을 모두 새로 진행한다.
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
# 처음에는 검색부터 실행하고, 이후에는 자동으로 찾았던 주소를 재사용할 수 있다.
targets = RAW / '자동검색_수집대상.csv'
search_mode = '--search' in sys.argv or not targets.exists()
sources = pd.read_csv(targets) if targets.exists() else pd.DataFrame()
records = []
errors = []
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
# 기사 URL 중복만 제거했다. 동일 사건의 다른 기사인지는 사람이 검토해야 한다.
articles.to_csv(OUTPUT / '2025_의료공백_자동검색_보도목록.csv', index=False, encoding='utf-8-sig')
if search_mode:
    (RAW / '자동검색_수집기록.json').write_text(json.dumps({
        '수집일':TODAY, '검색기록':search_log, '발견URL수':len(sources),
        '2025년게시일확인보도수':len(articles), '실패':errors,
        '범위':'검색어 3개별 검색 결과 2페이지 내 다음 뉴스 기사. 전국 전수자료 아님.',
        '주의':'기사 내용의 관련성과 사건 단위 중복은 미검토.'
    }, ensure_ascii=False, indent=2), encoding='utf-8')
print(articles[['게시일','매체','제목']].head(10).to_string(index=False))
print(f'완료: 자동검색 기사 {len(articles)}개, 제외·실패 {len(errors)}개 (미검토 자료)')
