#!/usr/bin/env bash
# DB 를 만지는 스크립트를 **컨테이너 안에서** 돌린다.
#
#   deploy/host/dbrun.sh check_db.py
#   deploy/host/dbrun.sh check_db.py --slide rs23 -v
#   deploy/host/dbrun.sh backup_db.py --note before-refilter
#   deploy/host/dbrun.sh prune_detections.py --apply
#
# 왜 굳이 컨테이너인가 — 같은 DB 를 두 벌의 환경이 만지지 않게 하려는 것이다.
# 호스트 venv 와 컨테이너는 라이브러리도 코드 판도 따로 논다. 그 어긋남으로
# 반입이 죽은 적도, 파일 소유자가 바뀐 적도 있다 (compose 의 dbtool 주석).
#
# 코드는 작업 트리를 그대로 쓴다(저장소를 /app 에 물린다). 그래서 새 스크립트를
# 쓸 때마다 이미지를 다시 구울 필요가 없다.
set -euo pipefail

DEPLOY_DIR="${DIATOM_DEPLOY_DIR:-/srv/diatom}"
[ -f "$DEPLOY_DIR/docker-compose.yml" ] || {
  echo "배포 구성이 없다: $DEPLOY_DIR/docker-compose.yml" >&2; exit 1; }
[ $# -gt 0 ] || { echo "쓰임: $(basename "$0") <스크립트> [인자...]" >&2; exit 2; }

cd "$DEPLOY_DIR"
exec docker compose run --rm dbtool "$@"
