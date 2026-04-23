#!/usr/bin/env bash
# M2.1-10: 계정 등록 후 DRY-RUN 워커가 자동 전이를 완주하는지 확인.
# 전제: Mac 로컬 워커가 `scripts/run_mac_worker_dry.sh` 로 기동 중.
set -euo pipefail

URL="${HYDRA_URL:?HYDRA_URL required}"
EMAIL="${ADMIN_EMAIL:?ADMIN_EMAIL required}"
PW="${ADMIN_PASSWORD:?ADMIN_PASSWORD required}"

TOKEN=$(curl -s -X POST "$URL/api/admin/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PW\"}" \
    | python3 -c 'import json,sys;print(json.load(sys.stdin)["token"])')

TS=$(date +%s)
GMAIL="loopcheck-${TS}@fake.local"
PROFILE="loopcheck-${TS}"

echo "[register] $GMAIL / $PROFILE"
RESP=$(curl -s -X POST "$URL/api/admin/accounts/register" \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    -d "{\"gmail\":\"$GMAIL\",\"password\":\"p\",\"adspower_profile_id\":\"$PROFILE\"}")
ACC_ID=$(echo "$RESP" | python3 -c 'import json,sys;print(json.load(sys.stdin)["account_id"])')
echo "  account_id=$ACC_ID"

# 최대 90초간 10초 간격 polling — tasks/recent 에서 변화 관찰
DEADLINE=$(($(date +%s) + 90))
while [[ $(date +%s) -lt $DEADLINE ]]; do
    STATES=$(curl -s "$URL/api/admin/tasks/recent?limit=50" \
        -H "Authorization: Bearer $TOKEN" \
        | python3 -c "
import json, sys
items = json.load(sys.stdin)['items']
mine = [it for it in items if it['account_id'] == $ACC_ID]
types_states = [(it['task_type'], it['status']) for it in mine]
print(types_states)
")
    echo "  tasks: $STATES"

    # Account 상태 체크 — stats 의 by_type 만으로는 개별 account 상태를 알 수 없으므로
    # recent 에 이 account 의 comment/like task 가 done 으로 등장하면 Golden Path 완주
    DONE_COUNT=$(curl -s "$URL/api/admin/tasks/recent?limit=50" \
        -H "Authorization: Bearer $TOKEN" \
        | python3 -c "
import json, sys
items = json.load(sys.stdin)['items']
mine = [it for it in items if it['account_id'] == $ACC_ID]
done = [it for it in mine if it['status'] == 'done']
# onboarding + warmup x3 = 4, comment + like = 2 → 총 6
print(len(done))
")
    echo "  done count: $DONE_COUNT / 6"

    if [[ "$DONE_COUNT" -ge 6 ]]; then
        echo "✅ Golden Path 완주 — account_id=$ACC_ID (account $GMAIL)"
        exit 0
    fi
    sleep 10
done

echo "❌ 90초 내 완주 실패. 현재 상태:"
curl -s "$URL/api/admin/tasks/recent?limit=20" \
    -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
exit 1
