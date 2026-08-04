#!/usr/bin/env bash
# 저장소의 스크립트를 /srv/diatom/scripts 로 옮겨 놓는다.
#
#   deploy/host/dbsync.sh check_db.py backup_db.py
#   deploy/host/dbsync.sh --list          # 옮겨 둔 것과 저장소가 어긋났는가
#
# 왜 곧바로 저장소를 물리지 않는가 — 편집 중인 작업 트리가 프로덕션 DB 에 곧바로
# 닿지 않게 하려는 것이다. docker-compose.yml 을 /srv 로 복사해 쓰는 것과 같은
# 갈래다: 저장소는 만들고, /srv 는 돌린다.
#
# **옆 모듈까지 따라간다.** backup_db.py 가 db_sentinel 을 부르는 것처럼 스크립트
# 들이 서로를 부른다. 하나만 옮기면 컨테이너 안에서 ModuleNotFoundError 로 죽고,
# 무엇이 빠졌는지는 스택 트레이스를 봐야 안다 — 실제로 그렇게 한 번 죽었다.
# Django 앱(viewer 등)은 따라가지 않는다. 그건 이미지 안의 /app 에서 온다.
set -euo pipefail

# /srv/diatom/bin 에 복사해 두고 부를 수도 있다 — 그때는 저장소가 어디인지
# 스스로 알 수 없으므로 DIATOM_REPO 로 알려 준다.
REPO="${DIATOM_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
[ -f "$REPO/check_db.py" ] || {
  echo "저장소를 못 찾았다: $REPO — DIATOM_REPO 로 알려 줄 것" >&2; exit 1; }
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

# 최상위 `import X` · `from X import …` 중 저장소에 X.py 가 있는 것만 고른다.
# 들여쓰기된 것(함수 안의 늦은 임포트)은 보지 않는다 — 그건 Django 를 세운 뒤에
# 부르는 것이라 /app 에서 온다.
deps_of() {
  grep -oE '^(import|from) [a-zA-Z_][a-zA-Z0-9_]*' "$1" 2>/dev/null \
    | awk '{print $2}' | sort -u
}

queue=("$@")
moved=""
while [ ${#queue[@]} -gt 0 ]; do
  n="$(basename "${queue[0]}")"; queue=("${queue[@]:1}")
  case " $moved " in *" $n "*) continue;; esac
  [ -f "$REPO/$n" ] || { echo "저장소에 없다: $n" >&2; exit 1; }
  cp -p "$REPO/$n" "$DEST/$n"
  moved="$moved $n"
  extra=""
  for m in $(deps_of "$REPO/$n"); do
    [ -f "$REPO/$m.py" ] || continue
    case " $moved " in *" $m.py "*) continue;; esac
    queue+=("$m.py"); extra="$extra $m.py"
  done
  [ -n "$extra" ] && echo "옮겼다  $n  (딸린 것:$extra)" || echo "옮겼다  $n"
done
