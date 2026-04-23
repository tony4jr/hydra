#!/usr/bin/env bash
# HYDRA End-to-End 스모크 테스트 (Task 36).
# Mac/Linux 에서 프로덕션 VPS 에 HTTPS 로 전수 검증.
#
# 환경변수 필수:
#   HYDRA_URL      = https://hydra-prod.duckdns.org
#   ADMIN_EMAIL    = admin@hydra.local
#   ADMIN_PASSWORD = ...
# 선택:
#   QUIET=1        = 개별 OK 출력 억제
set -euo pipefail

URL="${HYDRA_URL:?HYDRA_URL required}"
EMAIL="${ADMIN_EMAIL:?ADMIN_EMAIL required}"
PW="${ADMIN_PASSWORD:?ADMIN_PASSWORD required}"

PASS=0
FAIL=0

_ok() {
    PASS=$((PASS + 1))
    [[ "${QUIET:-}" == "1" ]] || echo "  ✅ $1"
}
_fail() {
    FAIL=$((FAIL + 1))
    echo "  ❌ $1" >&2
}
_section() {
    echo
    echo "━━━ $1 ━━━"
}
_expect_status() {
    local expected=$1 url=$2 method=${3:-GET} label=${4:-$url} extra=${5:-}
    local got
    got=$(curl -s -o /dev/null -w "%{http_code}" -X "$method" "$url" $extra 2>/dev/null)
    if [[ "$got" == "$expected" ]]; then
        _ok "$label → $got"
    else
        _fail "$label → $got (expected $expected)"
    fi
}

# ── 1. 공개 엔드포인트 ──
_section "1. 공개 엔드포인트"
_expect_status 200 "$URL/api/workers/setup.ps1" GET "setup.ps1 서빙"
# 빈 body login → pydantic 422 (미들웨어 이전에 거절)
_expect_status 422 "$URL/api/admin/auth/login" POST "로그인 빈 body → 422"

# ── 2. 어드민 인증 ──
_section "2. 어드민 인증"
LOGIN=$(curl -s -X POST "$URL/api/admin/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PW\"}")
TOKEN=$(echo "$LOGIN" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("token",""))')
if [[ -n "$TOKEN" ]]; then
    _ok "로그인 성공 (JWT ${#TOKEN} chars)"
else
    _fail "로그인 실패: $LOGIN"
    echo "중단 — 유효한 자격증명이 필요합니다." >&2
    exit 1
fi

AUTH="-H 'Authorization: Bearer $TOKEN'"

# ── 3. 보호 엔드포인트 미인증 거절 ──
_section "3. 미인증 401 검증"
_expect_status 401 "$URL/api/admin/server-config" GET "server-config"
_expect_status 401 "$URL/api/admin/deploy" POST "deploy"
_expect_status 401 "$URL/api/presets/" GET "presets"

# ── 4. 서버 상태 ──
_section "4. 서버 상태 조회"
CONFIG=$(curl -s "$URL/api/admin/server-config" -H "Authorization: Bearer $TOKEN")
VER=$(echo "$CONFIG" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("current_version",""))')
PAUSED=$(echo "$CONFIG" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("paused",""))')
if [[ -n "$VER" ]]; then
    _ok "current_version=$VER paused=$PAUSED"
else
    _fail "server-config 응답 이상: $CONFIG"
fi

# ── 5. 워커 enrollment → heartbeat ──
_section "5. 워커 enrollment 파이프라인"
ENR_RESP=$(curl -s -X POST "$URL/api/admin/workers/enroll" \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    -d '{"worker_name":"e2e-smoke","ttl_hours":1}')
ENR_TOKEN=$(echo "$ENR_RESP" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("enrollment_token",""))')
if [[ -n "$ENR_TOKEN" ]]; then
    _ok "admin /enroll → enrollment_token (${#ENR_TOKEN} chars)"
else
    _fail "admin enroll 실패: $ENR_RESP"
fi

TMPBODY=$(mktemp)
printf '{"enrollment_token":"%s","hostname":"e2e-smoke"}' "$ENR_TOKEN" > "$TMPBODY"
WENROLL=$(curl -s -X POST "$URL/api/workers/enroll" \
    -H 'Content-Type: application/json' --data-binary @"$TMPBODY")
rm "$TMPBODY"
WT=$(echo "$WENROLL" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("worker_token",""))')
if [[ -n "$WT" ]]; then
    _ok "worker /enroll → worker_token (${#WT} chars)"
else
    _fail "worker /enroll 실패: $WENROLL"
fi

HB=$(curl -s -X POST "$URL/api/workers/heartbeat/v2" \
    -H "X-Worker-Token: $WT" \
    -H 'Content-Type: application/json' \
    -d '{"version":"e2e-smoke"}')
HB_VER=$(echo "$HB" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("current_version",""))')
if [[ "$HB_VER" == "$VER" ]]; then
    _ok "heartbeat/v2 current_version 일치 ($VER)"
else
    _fail "heartbeat/v2 current_version=$HB_VER ≠ $VER"
fi

# ── 6. 태스크 큐 ──
_section "6. 태스크 큐"
FETCH=$(curl -s -X POST "$URL/api/tasks/v2/fetch" -H "X-Worker-Token: $WT")
COUNT=$(echo "$FETCH" | python3 -c 'import json,sys;print(len(json.load(sys.stdin).get("tasks",[])))')
_ok "fetch (pending 없을 수 있음) → ${COUNT}개"

# ── 7. 아바타 ──
_section "7. 아바타 서빙"
# 작은 PNG 업로드 → 다운로드
python3 -c "
import struct, zlib
sig = b'\x89PNG\r\n\x1a\n'
def chunk(c, d):
    return struct.pack('>I', len(d)) + c + d + struct.pack('>I', zlib.crc32(c + d))
open('/tmp/e2e.png', 'wb').write(
    sig + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0))
    + chunk(b'IDAT', zlib.compress(b'\x00\xff\xff\xff\xff'))
    + chunk(b'IEND', b'')
)
"
UP=$(curl -s -X POST "$URL/api/admin/avatars/upload" \
    -H "Authorization: Bearer $TOKEN" \
    -F "category=e2e" -F "file=@/tmp/e2e.png")
SAVED=$(echo "$UP" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("saved",""))' 2>/dev/null || true)
if [[ "$SAVED" == "e2e/e2e.png" ]]; then
    _ok "admin 업로드 → $SAVED"
else
    _fail "업로드 응답 이상: $UP"
fi

DL_STATUS=$(curl -s -o /tmp/e2e_out.png -w "%{http_code}" \
    -H "X-Worker-Token: $WT" "$URL/api/avatars/e2e/e2e.png")
if [[ "$DL_STATUS" == "200" ]] && file /tmp/e2e_out.png | grep -q "PNG"; then
    _ok "worker 다운로드 → 200 + PNG"
else
    _fail "다운로드 실패 status=$DL_STATUS"
fi

# 정리
curl -s -X DELETE "$URL/api/admin/avatars/e2e/e2e.png" \
    -H "Authorization: Bearer $TOKEN" > /dev/null
rm -f /tmp/e2e.png /tmp/e2e_out.png

# ── 8. 감사 로그 ──
_section "8. 감사 로그"
AUDIT=$(curl -s "$URL/api/admin/audit/list?limit=3" -H "Authorization: Bearer $TOKEN")
AUDIT_TOTAL=$(echo "$AUDIT" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("total",0))')
if [[ "$AUDIT_TOTAL" -gt 0 ]]; then
    _ok "audit/list total=$AUDIT_TOTAL"
else
    _fail "audit/list 비어있음 (이번 E2E 가 최소 1건 생성했어야)"
fi

# ── 9. 태스크 통계/최근 + 워커 current_task ──
_section "9. 태스크 통계 + 최근 + 워커 current_task"

STATS=$(curl -s -H "Authorization: Bearer $TOKEN" "$URL/api/admin/tasks/stats")
if echo "$STATS" | python3 -c 'import json,sys;json.load(sys.stdin)["pending"]' 2>/dev/null; then
    _ok "tasks/stats 응답 정상"
else
    _fail "tasks/stats 응답 이상: $STATS"
fi

RECENT=$(curl -s -H "Authorization: Bearer $TOKEN" "$URL/api/admin/tasks/recent?limit=5")
if echo "$RECENT" | python3 -c 'import json,sys;json.load(sys.stdin)["items"]' 2>/dev/null; then
    _ok "tasks/recent 응답 정상"
else
    _fail "tasks/recent 응답 이상"
fi

WORKERS=$(curl -s -H "Authorization: Bearer $TOKEN" "$URL/api/admin/workers/")
if echo "$WORKERS" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert isinstance(d, list); print("ok" if not d or "current_task" in d[0] else "no_field")' 2>&1 | grep -q "ok"; then
    _ok "workers list 에 current_task 필드"
else
    _fail "workers list current_task 필드 누락"
fi

# ── 요약 ──
_section "결과"
echo "PASS: $PASS"
echo "FAIL: $FAIL"
exit "$FAIL"
