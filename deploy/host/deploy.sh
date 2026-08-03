#!/usr/bin/env bash
# 판을 갈아 끼운다 (.guides/web/deployment.md §5).
#
#   /srv/diatom/bin/deploy.sh v0.1.1
#   /srv/diatom/bin/deploy.sh v0.1.1 --no-pull    # 이미 로컬에 있는 이미지로
#
# 순서가 곧 안전장치다:
#
#   1. 이미지를 받는다        받다 실패하면 지금 도는 것을 안 건드리고 끝난다
#   2. .env 의 IMAGE_TAG 만   통째로 다시 만들지 않는다 — 비밀키가 날아간다
#   3. 유지보수 플래그        내리는 동안 사람이 502 를 안 본다
#   4. 내린다                 쓰는 쪽이 빠져야 WAL 이 정리된다
#   5. 배포 전 스냅샷         새 판이 DB 를 건드렸을 때 돌아올 지점
#   6. 올리고 health 게이트   200 이 안 나오면 실패로 끝낸다
#   7. 플래그 해제            trap 이라 중간에 죽어도 풀린다
#
# **이 머신은 개발·운영·백업을 겸한다.** 가이드는 빌드를 prod 밖에서 하라고
# 하지만 여기서는 성립하지 않는다(devlog 016). 그래서 이 스크립트는 빌드하지
# 않는다 — 레지스트리에 올라간 것을 받아 갈아 끼우기만 한다. 굽는 것은
# `deploy/docker-compose.yml` 의 몫이다.
set -euo pipefail

SRV="${DIATOM_SRV:-/srv/diatom}"
HEALTH="${DIATOM_HEALTH:-http://127.0.0.1:8090/healthz}"
SERVICE="${DIATOM_SERVICE:-web}"
FLAG="$SRV/maintenance.flag"
SNAP_DIR="${DIATOM_BACKUP_DIR:-/data3/diatom/backup}/pre_deploy"

VER="${1:-}"
[ -n "$VER" ] || { echo "쓰임새: $0 <판> [--no-pull]   예: $0 v0.1.1" >&2; exit 1; }
PULL=1; [ "${2:-}" = "--no-pull" ] && PULL=0

cd "$SRV"
say() { echo "[$(date '+%F %T')] $*"; }

# 지금 무엇이 도는지 먼저 적는다 — 되돌릴 때 이 줄을 본다
PREV=$(grep -oP '^IMAGE_TAG=\K.*' .env 2>/dev/null || echo "(없음)")
say "=== 배포 $PREV → $VER ==="

# 1) 받는다. 실패하면 여기서 끝 — 도는 것을 안 건드린다.
if [ "$PULL" = 1 ]; then
    say "이미지를 받는다"
    docker pull "honestjung/diatom:$VER"
fi

# 2) .env 의 판만 **제자리에서** 고친다. 파일을 다시 만들지 않는다.
if grep -q '^IMAGE_TAG=' .env; then
    sed -i "s|^IMAGE_TAG=.*|IMAGE_TAG=$VER|" .env
else
    printf '\nIMAGE_TAG=%s\n' "$VER" >> .env
fi
say ".env 의 IMAGE_TAG 를 $VER 로"

# 3) 유지보수 플래그. trap 이라 중간에 죽어도 풀린다.
touch "$FLAG"
trap 'rm -f "$FLAG"' EXIT
say "유지보수 모드"

# 4) 내린다. 쓰는 쪽이 빠져야 WAL 이 본체로 정리된다.
docker compose down

# 5) 배포 전 스냅샷. 새 판의 마이그레이션이 DB 를 건드렸을 때 돌아올 지점이다.
#    backup_db.py 를 쓴다 — cp 는 WAL 때문에 불완전한 사본이 된다.
mkdir -p "$SNAP_DIR"
REPO="${DIATOM_REPO:-$HOME/projects/diatom}"
PY="${DIATOM_PY:-$HOME/venv/diatom/bin/python}"
# -f 로 본다. -x 로 보면 실행 권한이 없는 것만으로 건너뛴다 — 실제로 그래서
# 첫 배포에서 스냅샷 없이 지나갔다. 어차피 python 으로 부르므로 권한은 상관없다.
if [ -f "$REPO/backup_db.py" ] && [ -x "$PY" ]; then
    DIATOM_BACKUP_DIR="$SNAP_DIR" "$PY" "$REPO/backup_db.py" \
        --note "pre-deploy-$VER" --keep 20
else
    # 스냅샷은 되돌아올 지점이다. 없이 진행하는 것은 사람이 정할 일이지
    # 스크립트가 조용히 넘길 일이 아니다.
    say "스냅샷을 뜰 수 없다 — backup_db.py($REPO) 또는 python($PY) 을 못 찾았다" >&2
    say "  그래도 진행하려면 DIATOM_SKIP_SNAPSHOT=1 을 주고 다시 돌린다" >&2
    [ "${DIATOM_SKIP_SNAPSHOT:-}" = "1" ] || exit 1
fi

# 6) 올리고 health 게이트. 200 이 안 나오면 실패다.
docker compose up -d "$SERVICE"
say "기동 확인 중 ($HEALTH)"
for i in $(seq 1 30); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$HEALTH" || true)
    if [ "$code" = "200" ]; then
        say "정상 ($((i * 2))초)"
        docker compose ps --format '  {{.Name}}  {{.Image}}  {{.Status}}'
        say "=== 끝 ==="
        exit 0
    fi
    sleep 2
done

say "실패 — $HEALTH 가 200 을 안 낸다. 되돌리려면:" >&2
say "  $0 $PREV --no-pull" >&2
docker compose logs --tail 30 "$SERVICE" >&2
exit 1
