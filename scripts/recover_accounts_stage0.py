#!/usr/bin/env python3
"""M2.2 Stage 0 — .recover 에서 확보된 3개 계정을 VPS 로 import.

Gmail ↔ AdsPower profile_id 매핑은 hydra.db.malformed 의 sqlite .recover 결과
(lost_and_found 테이블) 에서 수동 추출. 나머지 46개는 별도 작업.

사용:
    export HYDRA_URL=https://hydra-prod.duckdns.org
    export ADMIN_EMAIL=admin@hydra.local
    export ADMIN_PASSWORD='...'
    python scripts/recover_accounts_stage0.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request


# 복구된 매핑 — .recover → lost_and_found 에서 확인됨
RECOVERED = [
    {
        "gmail": "phuoclocphan36@gmail.com",
        "password": "$Ethelbert87",
        "adspower_profile_id": "k1bmpnnw",
        "recovery_email": "trangiathi310881@911panel.us",
        "youtube_channel_id": "UCFmSMnPWr1t3y_e6gJCOerg",
        "notes": "recovered from malformed DB 2026-04-22 | purchased 2020",
    },
    {
        "gmail": "phuonganhlethi21@gmail.com",
        "password": "$Drusilla319",
        "adspower_profile_id": "k1bmpnpk",
        "recovery_email": "dangbinhvi101085@911panel.us",
        "youtube_channel_id": "UCqMrXCjWFsPTzuZsXqldIiA",
        "notes": "recovered from malformed DB 2026-04-22 | purchased 2020",
    },
    {
        "gmail": "phuonganhtranthi308@gmail.com",
        "password": "$Calantha13",
        "adspower_profile_id": "k1bmpnry",
        "recovery_email": "hoanghoaihau040200@911panel.us",
        "youtube_channel_id": "UCwa9WzBNkxbq82rZHGX8Kpw",
        "notes": "recovered from malformed DB 2026-04-22 | purchased 2020",
    },
]


def main() -> int:
    url = os.environ["HYDRA_URL"].rstrip("/")
    email = os.environ["ADMIN_EMAIL"]
    password = os.environ["ADMIN_PASSWORD"]

    # 1. admin login
    login = urllib.request.Request(
        f"{url}/api/admin/auth/login",
        data=json.dumps({"email": email, "password": password}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    token = json.load(urllib.request.urlopen(login))["token"]
    print(f"admin login OK")

    # 2. import
    req = urllib.request.Request(
        f"{url}/api/admin/accounts/import-recovered",
        data=json.dumps({"accounts": RECOVERED}).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    result = json.load(urllib.request.urlopen(req))
    print(f"imported: {result['imported']}")
    for sk in result["skipped"]:
        print(f"  skipped: {sk}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
