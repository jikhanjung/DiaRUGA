#!/usr/bin/env bash
# 저장소의 **테스트 배포** 파일을 /srv/DiaRUGA/test 로 옮긴다 (085).
# 운영 쪽은 `sync_to_srv.sh` 다 — 같은 갈래이고 같은 규칙이다.
#
#   ./deploy/host/sync_test_to_srv.sh
#
# **매번 돌려도 해롭지 않다** — cp 뿐이다.
#
# ## `.env` 는 건드리지 않는다
#
# 운영과 같은 이유다. 비밀키와 지금 미리 보는 판이 거기 있고, 통째로 덮어쓰면
# 날아간다. 없을 때만 견본에서 만들어 주고, 견본에 새 항목이 생기면 알리기만 한다.
#
# ## 자료(db/ · outcrop/)는 여기서 안 만진다
#
# **사본을 갈아 끼우는 것은 `testdeploy.sh` 의 일이다.** 여기서 함께 하면
# "파일을 맞춘다" 와 "자료를 갈아 끼운다" 가 한 명령에 섞여, 설정만 고치려던
# 사람이 검토 중이던 사본을 잃는다.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEST_SRV="${DIARUGA_TEST_SRV:-/srv/DiaRUGA/test}"

mkdir -p "$TEST_SRV"

copy() {
    local src="$REPO/$1" dst="$TEST_SRV/$2"
    if [ -f "$dst" ] && cmp -s "$src" "$dst"; then
        echo "  = $2"
        return
    fi
    cp -p "$src" "$dst"
    echo "  → $2"
}

echo "$REPO → $TEST_SRV"
copy deploy/test/docker-compose.yml docker-compose.yml

# .env 는 없을 때만 만든다. 있으면 손대지 않는다.
if [ ! -f "$TEST_SRV/.env" ]; then
    cp -p "$REPO/deploy/test/env.template" "$TEST_SRV/.env"
    chmod 600 "$TEST_SRV/.env"
    echo "  + .env (견본에서 만들었다 — DIARUGA_SECRET_KEY 를 채울 것)"
else
    missing=$(comm -23 \
        <(grep -oE '^[A-Z_]+=' "$REPO/deploy/test/env.template" | sort -u) \
        <(grep -oE '^[A-Z_]+=' "$TEST_SRV/.env" | sort -u) || true)
    if [ -n "$missing" ]; then
        echo "  ! .env 에 없는 항목: $(echo "$missing" | tr -d '=' | tr '\n' ' ')" >&2
    fi
    if grep -q '^DIARUGA_SECRET_KEY=여기를_채울_것' "$TEST_SRV/.env"; then
        echo "  ! .env 의 DIARUGA_SECRET_KEY 가 아직 견본 값이다" >&2
    fi
fi

echo "완료.  다음: deploy/host/testdeploy.sh <판>"
