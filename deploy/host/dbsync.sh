#!/usr/bin/env bash
# 저장소의 스크립트를 /srv/diatom/scripts 로 옮겨 놓는다.
#
#   deploy/host/dbsync.sh check_db.py backup_db.py
#   deploy/host/dbsync.sh --list          # 옮겨 둔 것과 저장소가 어긋났는가
#
# 왜 곧바로 저장소를 물리지 않는가 — 편집 중인 작업 트리가 프로덕션 DB 에 곧바로
# 닿지 않게 하려는 것이다. docker-compose.yml 을 /srv 로 복사해 쓰는 것과 같은
# 갈래다: 저장소는 만들고, /srv 는 돌린다.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEST="${DIATOM_SCRIPTS_DIR:-/srv/diatom/scripts}"
mkdir -p "$DEST"

if [ $# -eq 0 ] || [ "${1:-}" = "--list" ]; then
  shopt -s nullglob
  found=0
  for f in "$DEST"/*.py; do
    found=1
    n="$(basename "$f")"
    if [ ! -f "$REPO/$n" ]; then
      echo "  $n  — 저장소에 없다"
    elif cmp -s "$f" "$REPO/$n"; then
      echo "  $n  같다"
    else
      echo "  $n  ** 저장소와 다르다 ** (dbsync.sh $n 로 맞출 것)"
    fi
  done
  [ "$found" = 1 ] || echo "  (아직 옮겨 둔 것이 없다)"
  exit 0
fi

for n in "$@"; do
  n="$(basename "$n")"
  [ -f "$REPO/$n" ] || { echo "저장소에 없다: $n" >&2; exit 1; }
  cp -p "$REPO/$n" "$DEST/$n"
  echo "옮겼다  $n"
done
