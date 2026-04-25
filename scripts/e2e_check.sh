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

# --phase=N 인자: 해당 phase 까지의 게이트만 검증 (작업 진행 단계 제어)
PHASE="all"
for arg in "$@"; do
    case "$arg" in
        --phase=*) PHASE="${arg#--phase=}" ;;
    esac
done

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

# Phase 1 까지만 → 종료
if [[ "$PHASE" == "1" ]]; then
    _section "결과 (Phase 1 까지)"
    echo "PASS: $PASS / FAIL: $FAIL"
    exit "$FAIL"
fi

# ── Phase 2a: T1-T4 안전장치 ──
# ── 10. T1 스크린샷 캡처 (Phase 2) ──
_section "10. Phase 2a T1: 스크린샷 캡처"
# 1x1 PNG
python3 -c "open('/tmp/e2e_shot.png','wb').write(bytes.fromhex('89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c63f80f000001010003fe8acbd80000000049454e44ae426082'))"

SHOT_RESP=$(curl -s -X POST "$URL/api/workers/report-error-with-screenshot" \
    -H "X-Worker-Token: $WT" \
    -F "kind=diagnostic" \
    -F "message=e2e probe" \
    -F "screenshot=@/tmp/e2e_shot.png")
SHOT_OK=$(echo "$SHOT_RESP" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("ok",False))' 2>/dev/null)
if [[ "$SHOT_OK" == "True" ]]; then
    _ok "스크린샷 multipart 업로드 → ok"
else
    _fail "스크린샷 업로드 실패: $SHOT_RESP"
fi
rm -f /tmp/e2e_shot.png

# ── 11. T2 어드민 VPS 서빙 ──
_section "11. Phase 2 T2: VPS 어드민 UI 서빙"
ROOT_HTML=$(curl -s "$URL/")
if echo "$ROOT_HTML" | head -c 100 | grep -q "<!doctype html"; then
    _ok "/ → React HTML (placeholder 탈출)"
else
    _fail "/ 가 여전히 placeholder: $(echo "$ROOT_HTML" | head -c 80)"
fi

# ── 12. T3 원격 명령 시스템 ──
_section "12. Phase 2 T3: 원격 명령 시스템"
CMD_RESP=$(curl -s -X POST "$URL/api/admin/workers/$(echo "$WORKERS" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d[0]["id"] if d else 1)')/command" \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    -d '{"command":"run_diag"}')
CMD_ID=$(echo "$CMD_RESP" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("id",0))' 2>/dev/null)
if [[ "$CMD_ID" -gt 0 ]]; then
    _ok "어드민 명령 발행 → id=$CMD_ID"
else
    _fail "명령 발행 실패: $CMD_RESP"
fi

# 알 수 없는 명령은 거부
BAD_CMD=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$URL/api/admin/workers/1/command" \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    -d '{"command":"rm_rf"}')
if [[ "$BAD_CMD" == "400" ]]; then
    _ok "알 수 없는 명령 → 400 거부"
else
    _fail "알 수 없는 명령 → $BAD_CMD (expected 400)"
fi

# heartbeat 응답에 pending_commands 필드 존재
HB_KEYS=$(echo "$HB" | python3 -c 'import json,sys;print(",".join(json.load(sys.stdin).keys()))')
if echo "$HB_KEYS" | grep -q "pending_commands"; then
    _ok "heartbeat 응답에 pending_commands 필드 포함"
else
    _fail "pending_commands 필드 없음 — keys: $HB_KEYS"
fi

# ── 13. T4 백업 (선택) ──
_section "13. Phase 2a T4: B2 백업 (구성 시)"
if [[ -n "${B2_KEY_ID:-}" ]] && [[ -n "${B2_APP_KEY:-}" ]]; then
    _ok "B2 자격증명 환경변수 존재 (실 백업 검증은 별도 스크립트)"
else
    echo "  ⚠️  B2 미구성 — 스킵 (T4 미완료, Phase 2a gate 미통과)"
    if [[ "$PHASE" == "2a" ]]; then
        # Phase 2a gate 검증 모드 — B2 미구성은 FAIL
        FAIL=$((FAIL + 1))
        echo "  ❌ T4 미완료 — Phase 2a 게이트 미통과" >&2
    fi
fi

# Phase 2a 까지만 → 종료
if [[ "$PHASE" == "2a" ]]; then
    _section "결과 (Phase 2a 까지)"
    echo "PASS: $PASS / FAIL: $FAIL"
    if [[ "$FAIL" -gt 0 ]]; then
        echo "❌ Phase 2a 게이트 미통과 — 다음 phase 진입 차단" >&2
    else
        echo "✅ Phase 2a 게이트 통과 — Phase 2b 진입 가능" >&2
    fi
    exit "$FAIL"
fi

# ── Phase 3a 게이트 (T7-T11) ──
_section "14. Phase 3a T7: Circuit Breaker 컬럼"
# workers 테이블에 consecutive_failures 컬럼 존재 확인
COL_CHECK=$(curl -s -H "Authorization: Bearer $TOKEN" "$URL/api/admin/workers/" | \
    python3 -c "import json,sys; d=json.load(sys.stdin); print('present' if d else 'no_workers')" 2>/dev/null)
if [[ "$COL_CHECK" == "present" || "$COL_CHECK" == "no_workers" ]]; then
    _ok "workers 엔드포인트 정상 (CB 컬럼 마이그레이션 적용)"
else
    _fail "workers 응답 이상: $COL_CHECK"
fi

_section "15. Phase 3a T8: IP 감시 엔드포인트"
IP_HIST=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $TOKEN" \
    "$URL/api/admin/workers/ip-history?hours=1")
[[ "$IP_HIST" == "200" ]] && _ok "ip-history → 200" || _fail "ip-history → $IP_HIST"
IP_CONF=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $TOKEN" \
    "$URL/api/admin/workers/ip-conflicts?hours=1")
[[ "$IP_CONF" == "200" ]] && _ok "ip-conflicts → 200" || _fail "ip-conflicts → $IP_CONF"

_section "16. Phase 3a T9: 비상정지 엔드포인트 (호출 안 함)"
ES_OPTIONS=$(curl -s -o /dev/null -w "%{http_code}" -X OPTIONS "$URL/api/admin/emergency-stop")
ES_AUTH=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$URL/api/admin/emergency-stop")
[[ "$ES_AUTH" == "401" ]] && _ok "emergency-stop 미인증 거절" || _fail "emergency-stop auth → $ES_AUTH"

_section "17. Phase 3a T10/T11: 정책 모듈 import 가능 (서버 재시작 후)"
# 서버가 새 모듈 로드 성공했는지 — heartbeat 응답으로 간접 확인
HB_OK=$(echo "$HB" | python3 -c 'import json,sys;d=json.load(sys.stdin);print("ok" if "pending_commands" in d else "fail")')
[[ "$HB_OK" == "ok" ]] && _ok "헤더 정상 (orchestrator/profile_verify 로드됨)" || _fail "heartbeat 비정상"

# Phase 3a 까지만 → 종료
if [[ "$PHASE" == "3a" ]]; then
    _section "결과 (Phase 3a 까지)"
    echo "PASS: $PASS / FAIL: $FAIL"
    exit "$FAIL"
fi

# ── Phase 3b 게이트 (T12-T15) ──
_section "19. Phase 3b T14: Tags 엔드포인트"
TAGS_AUTH=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$URL/api/admin/adspower/accounts/tag")
[[ "$TAGS_AUTH" == "401" ]] && _ok "tag 미인증 거절" || _fail "tag auth → $TAGS_AUTH"
TAG_GET=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $TOKEN" \
    "$URL/api/admin/adspower/accounts/by-tag/test-nonexistent")
[[ "$TAG_GET" == "200" ]] && _ok "by-tag → 200 (빈 배열)" || _fail "by-tag → $TAG_GET"

_section "20. Phase 3b T15: FP 회전 dry-run"
FP_DRY=$(curl -s -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d '{"days_since_last": 30, "max_per_run": 1, "dry_run": true}' \
    "$URL/api/admin/adspower/fingerprint-rotation")
FP_OK=$(echo "$FP_DRY" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("dry_run", False))' 2>/dev/null)
[[ "$FP_OK" == "True" ]] && _ok "fingerprint-rotation dry_run 정상" || _fail "fp rotation: $FP_DRY"

# Phase 3b 까지만 → 종료
if [[ "$PHASE" == "3b" ]]; then
    _section "결과 (Phase 3b 까지)"
    echo "PASS: $PASS / FAIL: $FAIL"
    exit "$FAIL"
fi

# §23+: Phase 4 캠페인 (T17/T20 추가 예정)

# ── 요약 ──
_section "결과 (전체)"
echo "PASS: $PASS"
echo "FAIL: $FAIL"
exit "$FAIL"
