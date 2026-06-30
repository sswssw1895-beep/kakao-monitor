# -*- coding: utf-8 -*-
"""
카카오톡 채널 '소식' 게시물 모니터링 크롤러
- 대상: 르무통(자사), 아디다스/나이키/스케쳐스(경쟁사)
- 동작: 각 채널의 공개 '소식' 탭을 Playwright로 렌더링 후 게시물 텍스트/날짜/이미지 추출
- 저장: Google Sheets에 신규 게시물만 append (중복 방지)

⚠️ 주의: pf.kakao.com 채널 홈은 React 기반 SPA라 실제 DOM 구조가
주기적으로 바뀔 수 있습니다. 최초 1회는 --debug 옵션으로 실행해
스크린샷/HTML을 확인하고 SELECTOR 값을 맞춰주세요.
"""

import asyncio
import sys
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

# ===================== 설정 =====================
CHANNELS = {
    "르무통": "_sxjxlDj",
    "아디다스": "_qRuGz",
    "나이키": "_fQxhxdz",
    "스케쳐스": "_xaPRGxb",
}

SPREADSHEET_NAME = "카카오채널_모니터링"
WORKSHEET_NAME = "메시지히스토리"
STATS_SHEET_NAME = "통계"
SERVICE_ACCOUNT_FILE = "service_account.json"  # 구글 서비스 계정 키 파일

# 게시물 목록/항목/날짜/내용 영역 CSS 셀렉터 (최초 실행 후 실제 구조로 보정 필요)
SELECTOR_POST_LIST = "div[class*='feed'] li, div[class*='post_list'] li"
SELECTOR_CONTENT = "*"
SELECTOR_DATE = "time, [class*='date']"
SELECTOR_IMAGE = "img"

DEBUG = "--debug" in sys.argv
# =================================================


async def fetch_channel_posts(playwright, brand: str, channel_id: str):
    """채널 소식 페이지를 렌더링하고 게시물 목록을 추출한다."""
    url = f"https://pf.kakao.com/{channel_id}/posts"
    browser = await playwright.chromium.launch(headless=not DEBUG)
    page = await browser.new_page(viewport={"width": 480, "height": 900})

    posts = []
    try:
        await page.goto(url, wait_until="networkidle", timeout=20000)
        await page.wait_for_timeout(2000)  # SPA 렌더링 대기

        if DEBUG:
            await page.screenshot(path=f"debug_{brand}.png", full_page=True)
            html = await page.content()
            with open(f"debug_{brand}.html", "w", encoding="utf-8") as f:
                f.write(html)
            print(f"[DEBUG] {brand}: 스크린샷/HTML 저장 완료")

        items = await page.query_selector_all(SELECTOR_POST_LIST)
        for item in items:
            try:
                content_el = await item.query_selector(SELECTOR_CONTENT)
                date_el = await item.query_selector(SELECTOR_DATE)
                img_el = await item.query_selector(SELECTOR_IMAGE)

                content = (await content_el.inner_text()).strip() if content_el else ""
                date_text = (await date_el.inner_text()).strip() if date_el else ""
                img_src = (await img_el.get_attribute("src")) if img_el else ""

                if not content:
                    continue

                # 고유 식별자: 브랜드+내용 앞부분+날짜 조합 (중복 체크용)
                post_id = f"{brand}|{date_text}|{content[:30]}"

                posts.append({
                    "id": post_id,
                    "brand": brand,
                    "date": date_text,
                    "content": content[:500],
                    "image": img_src or "",
                    "link": url,
                })
            except Exception as e:
                print(f"  - 항목 파싱 오류({brand}): {e}")
                continue

    except Exception as e:
        print(f"[오류] {brand} 채널 접속 실패: {e}")
    finally:
        await browser.close()

    return posts


async def crawl_all():
    all_posts = []
    async with async_playwright() as p:
        for brand, channel_id in CHANNELS.items():
            print(f"크롤링 중: {brand} ({channel_id})")
            posts = await fetch_channel_posts(p, brand, channel_id)
            print(f"  -> {len(posts)}건 수집")
            all_posts.extend(posts)
    return all_posts


def get_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open(SPREADSHEET_NAME)
    try:
        ws = sh.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=1000, cols=10)
        ws.append_row(["브랜드", "발송(추정)일시", "메시지내용", "이미지URL", "원본링크", "수집시각", "고유ID"])
    return sh, ws


def save_to_sheet(posts):
    if not posts:
        print("신규 게시물 없음 (또는 셀렉터 보정 필요)")
        return

    sh, ws = get_sheet()
    existing = ws.col_values(7)  # 고유ID 컬럼
    existing_set = set(existing)

    new_rows = []
    for post in posts:
        if post["id"] in existing_set:
            continue
        new_rows.append([
            post["brand"],
            post["date"],
            post["content"],
            post["image"],
            post["link"],
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            post["id"],
        ])

    if new_rows:
        ws.append_rows(new_rows)
        print(f"신규 {len(new_rows)}건 저장 완료")
    else:
        print("신규 게시물 없음 (전부 중복)")

    update_stats(sh, ws)


def update_stats(sh, ws):
    """브랜드별 누적 발송 건수를 통계 시트에 갱신."""
    try:
        stats_ws = sh.worksheet(STATS_SHEET_NAME)
    except gspread.WorksheetNotFound:
        stats_ws = sh.add_worksheet(title=STATS_SHEET_NAME, rows=20, cols=5)
        stats_ws.append_row(["브랜드", "누적 게시물 수", "최근 업데이트"])

    data = ws.get_all_records()
    counts = {}
    for row in data:
        b = row.get("브랜드", "")
        counts[b] = counts.get(b, 0) + 1

    stats_ws.clear()
    stats_ws.append_row(["브랜드", "누적 게시물 수", "최근 업데이트"])
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    for brand in CHANNELS.keys():
        stats_ws.append_row([brand, counts.get(brand, 0), now])


if __name__ == "__main__":
    collected = asyncio.run(crawl_all())
    print(f"\n총 {len(collected)}건 수집됨")
    if not DEBUG:
        save_to_sheet(collected)
    else:
        print("DEBUG 모드: 시트 저장 생략. debug_*.png / debug_*.html 확인 후 SELECTOR 값을 수정하세요.")
