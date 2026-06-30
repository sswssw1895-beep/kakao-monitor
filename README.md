# 카카오톡 채널 모니터링 자동화 가이드

## 1. 무엇을 자동화하나
- 르무통(자사) / 아디다스 / 나이키 / 스케쳐스(경쟁사)의 **공개 "소식" 게시물**을 매일 자동 수집
- 신규 게시물만 구글시트 `메시지히스토리`에 누적
- `통계` 시트에 브랜드별 누적 발송 건수 자동 갱신

⚠️ **1:1 전용 메시지(쿠폰함, 개인 알림)는 자동 수집 대상이 아닙니다.**
이건 카카오 공식 API/약관상 외부 수집이 불가능한 영역이라, 2번 "수동 입력 템플릿"으로 별도 운영합니다.

---

## 2. 최초 설정 (1회만)

### 2-1. 구글 서비스 계정 생성
1. https://console.cloud.google.com → 새 프로젝트 생성
2. "API 및 서비스" → "사용자 인증 정보" → "서비스 계정" 생성
3. 생성된 서비스 계정의 키(JSON) 다운로드
4. Google Sheets API, Google Drive API 활성화

### 2-2. 구글시트 준비
1. 새 스프레드시트 생성 → 이름을 `카카오채널_모니터링`으로 지정 (코드 내 `SPREADSHEET_NAME`과 동일해야 함)
2. 시트의 "공유" 버튼 → 서비스 계정 이메일(json 파일 안의 `client_email`)을 **편집자**로 추가

### 2-3. 셀렉터 보정 (가장 중요)
카카오 채널 페이지는 SPA라 실제 HTML 클래스명이 자주 바뀝니다. 최초 1회는 반드시:

```bash
pip install -r requirements.txt
playwright install chromium
python crawler.py --debug
```

→ `debug_르무통.png`, `debug_르무통.html` 등이 생성됩니다.
→ 스크린샷에서 게시물 영역을 확인하고, html에서 해당 영역의 class명을 찾아
`crawler.py` 상단의 `SELECTOR_POST_LIST`, `SELECTOR_DATE` 값을 실제 값으로 교체하세요.

(브라우저 개발자도구 F12로 직접 `pf.kakao.com/_sxjxlDj/posts` 접속해 확인하는 것이 가장 정확합니다.)

### 2-4. GitHub Actions로 자동 스케줄 등록
1. 이 폴더를 GitHub 저장소에 push
2. 저장소 Settings → Secrets and variables → Actions → New repository secret
   - Name: `GCP_SERVICE_ACCOUNT_JSON`
   - Value: 다운로드한 서비스 계정 json 파일 내용 전체 붙여넣기
3. 그러면 매일 자동 실행되며, Actions 탭에서 수동 실행(`Run workflow`)도 가능

---

## 3. 로컬에서 바로 테스트하고 싶다면

```bash
cd kakao_monitor
pip install -r requirements.txt
playwright install chromium
python crawler.py            # 실제 수집 + 시트 저장
python crawler.py --debug    # 디버그용 (저장 안 함, 화면/HTML만 저장)
```

---

## 4. 시트 구조

**메시지히스토리**
| 브랜드 | 발송(추정)일시 | 메시지내용 | 이미지URL | 원본링크 | 수집시각 | 고유ID |

**통계**
| 브랜드 | 누적 게시물 수 | 최근 업데이트 |

---

## 5. 트러블슈팅
- "신규 게시물 없음"만 계속 나온다 → 셀렉터가 안 맞아서 0건 수집되는 경우일 확률 높음 → `--debug` 모드로 재확인
- GitHub Actions에서 실패 → Actions 탭 로그 확인, 보통 secrets 등록 오류이거나 playwright 브라우저 설치 누락
