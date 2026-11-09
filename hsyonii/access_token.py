"""SGIS 인증 후 access_token을 제공한다. 시각화 코드에서 자동으로 사용한다."""
import requests

url = "https://sgisapi.mods.go.kr/OpenAPI3/auth/authentication.json"

params = {
    "consumer_key": "8356ca90284d412d8261",
    "consumer_secret": "3b78b01492a64ac2aa1c"
}

# 인증값이 포함된 요청 주소와 응답 전체를 출력하지 않는다.
# 다른 파일에서는 access_token 변수만 가져와 사용한다.
try:
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    auth = response.json()
except (requests.RequestException, ValueError):
    raise SystemExit('SGIS 인증 요청 실패: 네트워크 연결과 인증 설정을 확인하세요.') from None

if auth.get('errCd') != 0:
    raise SystemExit(f"SGIS 인증 실패 (오류 코드: {auth.get('errCd')})")
access_token = auth['result']['accessToken']
if __name__ == '__main__':
    print('SGIS 인증 성공')
