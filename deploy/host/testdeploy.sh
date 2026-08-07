#!/usr/bin/env bash
# 판을 **테스트 자리**(/DiaRUGATest/)에 건다 (085).
#
#   deploy/host/testdeploy.sh v0.8.3
#   deploy/host/testdeploy.sh v0.8.3 --no-pull    # 방금 로컬에서 구운 이미지로
#   deploy/host/testdeploy.sh v0.8.3 --keep-db    # DB 사본을 새로 안 뜬다
#   deploy/host/testdeploy.sh v0.8.3 --fresh-db   # 지금 시점으로 새로 뜬다
#
# 운영 `deploy.sh` 와 같은 갈래이고 순서도 같은 뜻이다. 다른 것이 셋이다:
#
#   - **DB 사본을 갈아 끼운다.** 운영은 있는 DB 를 그대로 두지만, 테스트는
#     **사본이 낡는 것이 기본 고장**이다. 옛 자료로 새 판을 보면 "고쳤는데 안
#     바뀐다" 가 나오고, 그 시간은 판을 의심하는 데 쓰인다
#   - **유지보수 안내가 없다.** 테스트가 잠깐 502 인 것은 사고가 아니다
#   - **먼저 안전 검사를 한다.** 아래 1번 — 이 스크립트가 존재하는 이유의 절반이다
#
# ## 왜 사본을 "가장 새 스냅샷" 에서 가져오나
#
# `backup_db.py` 가 시간별로 떠 두는 것을 쓴다(`--keep 24` 로 돌아간다). 그것은
# **검증을 통과한 뒤 제 이름을 받은** 파일이라 `cp` 해도 안전하다 — 도는 DB 를
# `cp` 하면 WAL 이라 불완전한 사본이 나온다. 새로 뜨고 싶으면 `--fresh-db` 다.
#
# `--fresh-db` 를 기본으로 두지 않은 이유: 손으로 뜬 것은 `manual/` 에 쌓이고
# **로테이션이 안 건드린다.** 미리보기를 돌릴 때마다 108 MB 가 영구히 는다.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEST_SRV="${DIARUGA_TEST_SRV:-/srv/DiaRUGA/test}"
PROD_SRV="${DIARUGA_SRV:-/srv/DiaRUGA}"
HEALTH="${DIARUGA_TEST_HEALTH:-http://127.0.0.1:8091/healthz}"
SITE="${DIARUGA_TEST_SITE:-http://127.0.0.1/DiaRUGATest/}"
BACKUP_DIR="${DIARUGA_BACKUP_DIR:-/data3/DiaRUGA/backup}"

VER="${1:-}"
[ -n "$VER" ] || {
    echo "쓰임새: $0 <판> [--no-pull] [--keep-db|--fresh-db]" >&2
    echo "  예: $0 v0.8.3" >&2; exit 2; }
shift

PULL=1; DBMODE=snapshot
for a in "$@"; do
    case "$a" in
        --no-pull)  PULL=0 ;;
        --keep-db)  DBMODE=keep ;;
        --fresh-db) DBMODE=fresh ;;
        *) echo "모르는 인자: $a" >&2; exit 2 ;;
    esac
done

say() { echo "[$(date '+%F %T')] $*"; }
die() { echo "✗ $*" >&2; exit 1; }

[ -f "$TEST_SRV/docker-compose.yml" ] || die "테스트 구성이 없다: $TEST_SRV/docker-compose.yml
   deploy/host/sync_test_to_srv.sh 를 먼저 돌릴 것"
[ -f "$TEST_SRV/.env" ] || die "$TEST_SRV/.env 가 없다 — sync_test_to_srv.sh 가 견본에서 만들어 준다"

say "=== 테스트 배포 → $VER ==="

# --- 1) 안전 검사. **여기서 서면 아무것도 안 건드린 것이다** ---------------
#
# 테스트가 운영 자료를 만지는 길이 셋 있고, 셋 다 조용하다. 사람이 매번
# 기억하는 대신 여기서 센다 (`tests/base.py` 가 시험에 대해 하는 일과 같다).
prod_db=$(grep -oP '^DIARUGA_DB=\K.*' "$PROD_SRV/.env" 2>/dev/null || echo "/srv/DiaRUGA/db/DiaRUGA.db")
test_db=$(grep -oP '^DIARUGA_DB=\K.*' "$TEST_SRV/.env" || true)
test_out=$(grep -oP '^DIARUGA_OUTCROP_DIR=\K.*' "$TEST_SRV/.env" || true)
test_script=$(grep -oP '^DIARUGA_SCRIPT_NAME=\K.*' "$TEST_SRV/.env" || true)

[ -n "$test_db" ] || die "테스트 .env 에 DIARUGA_DB 가 없다"
[ "$test_db" != "$prod_db" ] || die "테스트가 **운영 DB** 를 가리킨다: $test_db
   교정 7,472건은 재생성 불가다. .env 를 고칠 것"
case "$test_out" in
    /nfs/*) die "테스트가 **NAS 원본** 노두 사진을 가리킨다: $test_out
   화면에서 지우면 진짜 파일이 지워진다. 사본 경로로 고칠 것" ;;
esac
[ "$test_script" != "/DiaRUGA" ] || die "DIARUGA_SCRIPT_NAME 이 /DiaRUGA 다 — 링크가 전부 운영으로 샌다"
grep -q '^ *- */srv/DiaRUGA/db:' "$TEST_SRV/docker-compose.yml" &&
    die "테스트 compose 가 **운영 db/ 를 마운트**한다 — 지울 것"
say "안전 검사 통과 (DB·노두 사진·서브경로가 운영과 갈라져 있다)"

# --- 2) 이미지. 받다 실패하면 지금 도는 것을 안 건드리고 끝난다 -----------
if [ "$PULL" = 1 ]; then
    say "이미지를 받는다"
    docker pull "honestjung/diaruga:$VER"
else
    docker image inspect "honestjung/diaruga:$VER" >/dev/null 2>&1 ||
        die "로컬에 honestjung/diaruga:$VER 가 없다 (--no-pull 을 줬다)"
fi

# --- 3) .env 의 판만 **제자리에서**. 파일을 다시 만들지 않는다 ------------
PREV=$(grep -oP '^IMAGE_TAG=\K.*' "$TEST_SRV/.env" 2>/dev/null || echo "(없음)")
sed -i "s|^IMAGE_TAG=.*|IMAGE_TAG=$VER|" "$TEST_SRV/.env"
say "IMAGE_TAG $PREV → $VER"

# --- 4) 내린다. 쓰는 쪽이 빠져야 WAL 이 본체로 정리된다 -------------------
(cd "$TEST_SRV" && docker compose down --remove-orphans >/dev/null 2>&1) || true

# --- 5) DB 사본을 갈아 끼운다 --------------------------------------------
case "$DBMODE" in
keep)
    say "DB 사본은 그대로 둔다 (--keep-db)"
    ;;
fresh|snapshot)
    if [ "$DBMODE" = fresh ]; then
        say "스냅샷을 지금 뜬다"
        "$REPO/deploy/host/dbrun.sh" backup_db.py --note "testdeploy-$VER" >/dev/null
        src=$(ls -t "$BACKUP_DIR"/manual/DiaRUGA_*"testdeploy-$VER".db 2>/dev/null | head -n1)
    else
        # 시간별 사본 중 가장 새 것. 하위 디렉토리(manual·pre_deploy)는 안 본다.
        src=$(ls -t "$BACKUP_DIR"/DiaRUGA_*.db 2>/dev/null | head -n1)
    fi
    [ -n "${src:-}" ] && [ -f "$src" ] || die "쓸 스냅샷을 못 찾았다 ($BACKUP_DIR)
   --keep-db 로 지금 사본을 그대로 쓰거나, backup_db.py 를 먼저 돌릴 것"

    age_min=$(( ( $(date +%s) - $(stat -c %Y "$src") ) / 60 ))
    mkdir -p "$TEST_SRV/db"
    # -wal·-shm 형제를 남겨 두면 새 본체와 짝이 안 맞는다
    rm -f "$TEST_SRV/db/DiaRUGA.db" "$TEST_SRV/db/DiaRUGA.db-wal" "$TEST_SRV/db/DiaRUGA.db-shm"
    cp "$src" "$TEST_SRV/db/DiaRUGA.db"
    say "DB 사본: $(basename "$src") (${age_min}분 전)"
    ;;
esac

# 노두 사진 사본이 없으면 만들어 둔다. 있으면 안 건드린다 — 테스트에서 지운 것이
# 다시 살아나면 "지웠는데 남아 있다" 로 읽힌다.
if [ ! -d "$TEST_SRV/outcrop" ]; then
    if [ -d /nfs/temp-share/DiaRUGA/outcrop ]; then
        cp -r /nfs/temp-share/DiaRUGA/outcrop "$TEST_SRV/outcrop"
        say "노두 사진 사본을 만들었다"
    else
        mkdir -p "$TEST_SRV/outcrop"
        say "NAS 가 없어 빈 노두 사진 자리를 만들었다"
    fi
fi

# --- 6) 올리고 기동 게이트 ------------------------------------------------
(cd "$TEST_SRV" && docker compose up -d web)
say "기동 확인 중 ($HEALTH)"
for i in $(seq 1 30); do
    code=$(curl -s -o /dev/null --max-time 5 -w '%{http_code}' "$HEALTH" 2>/dev/null || true)
    [ "$code" = "200" ] && { say "정상 (${i}초)"; break; }
    [ "$i" = 30 ] && {
        echo "--- 로그 ---" >&2
        (cd "$TEST_SRV" && docker compose logs --tail 30 web) >&2
        die "30초 안에 200 이 안 나왔다"; }
    sleep 1
done

# --- 7) smoke. **테스트 자리를 보게** 환경만 갈아 끼운다 ------------------
# 운영과 같은 스크립트를 쓴다 — 검사가 둘이면 한쪽만 늙는다.
DIARUGA_SRV="$TEST_SRV" DIARUGA_HEALTH="$HEALTH" DIARUGA_SITE="$SITE" \
    "$REPO/deploy/host/smoke.sh" "$VER"

echo
say "=== 끝 ===  http://172.16.116.98/DiaRUGATest/"
