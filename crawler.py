# -*- coding: utf-8 -*-
"""
카카오톡 채널 '소식' 게시물 모니터링 크롤러 (v2 - 공개 API 직접 호출 방식)
- 브라우저 자동화 불필요. 로그인 불필요. requests만으로 동작.
- 르무통(자사) / 아디다스 / 나이키 / 스케쳐스(경쟁사) 공개 소식을 수집해 구글시트에 적재
"""

import requests
from datetime import datetime, timezone, timedelta

import gspread
from google.oauth2.service_account import Credentials

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
SERVICE_ACCOUNT_FILE = "service_account.json"

API_URL_TEMPLATE = "https://pf.kakao.com/rocket-web/web/profiles/{channel_id}/posts?includePinnedPost=true"
HEADERS = {
    "accept": "*/*",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

KST = timezone(timedelta(hours=9))
# =================================================


def fetch_channel_posts(brand: str, channel_id: str):
    """공개 API를 호출해 게시물 목록을 가져온다."""
    url = API_URL_TEMPLATE.format(channel_id=channel_id)
    posts = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])

        for item in items:
            title = item.get("title", "") or ""
            text_parts = [c.get("v", "") for c in item.get("contents", []) if c.get("t") == "text"]
            link_parts = [c.get("v", "") for c in item.get("contents", []) if c.get("t") == "link"]
            content = "\n".join(text_parts).strip() or title

            published_at_ms = item.get("published_at")
            if published_at_ms:
                dt = datetime.fromtimestamp(published_at_ms / 1000, tz=KST)
                date_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            else:
                date_str = ""

            image_url = ""
            media = item.get("media", [])
            if media and isinstance(media, list):
                image_url = media[0].get("url") or media[0].get("thumbnail", "")

            post_id = str(item.get("id", ""))
            permalink = item.get("permalink", "")
            extra_link = link_parts[0] if link_parts else ""

            posts.append({
                "id": f"{brand}|{post_id}",
                "brand": brand,
                "date": date_str,
                "content": content[:500],
                "image": image_url,
                "link": extra_link or permalink,
            })

    except Exception as e:
        print(f"[오류] {brand} API 호출 실패: {e}")

    return posts


def crawl_all():
    all_posts = []
    for brand, channel_id in CHANNELS.items():
        print(f"수집 중: {brand} ({channel_id})")
        posts = fetch_channel_posts(brand, channel_id)
        print(f"  -> {len(posts)}건 수집")
        all_posts.extend(posts)
    return all_posts


def get_sheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open(SPREADSHEET_NAME)
    try:
        ws = sh.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=1000, cols=10)
        ws.append_row(["브랜드", "발송일시", "메시지내용", "이미지URL", "원본링크", "수집시각", "고유ID"])
    return sh, ws


def save_to_sheet(posts):
    if not posts:
        print("수집된 게시물이 없습니다.")
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
            datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
            post["id"],
        ])

    if new_rows:
        ws.append_rows(new_rows)
        print(f"신규 {len(new_rows)}건 저장 완료")
    else:
        print("신규 게시물 없음 (전부 중복)")

    update_stats(sh, ws)


def update_stats(sh, ws):
    try:
        stats_ws = sh.worksheet(STATS_SHEET_NAME)
    except gspread.WorksheetNotFound:
        stats_ws = sh.add_worksheet(title=STATS_SHEET_NAME, rows=20, cols=5)

    data = ws.get_all_records()
    counts = {}
    for row in data:
        b = row.get("브랜드", "")
        counts[b] = counts.get(b, 0) + 1

    stats_ws.clear()
    stats_ws.append_row(["브랜드", "누적 게시물 수", "최근 업데이트"])
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    for brand in CHANNELS.keys():
        stats_ws.append_row([brand, counts.get(brand, 0), now])


if __name__ == "__main__":
    collected = crawl_all()
    print(f"\n총 {len(collected)}건 수집됨")
    save_to_sheet(collected)
