#!/usr/bin/env bash
# 저장소의 배포 파일을 /srv/diatom 으로 옮긴다 (.guides/web/deployment.md §2).
#
#   ./deploy/host/sync_to_srv.sh
#
# `git pull` 뒤에 돌린다. **매번 돌려도 해롭지 않다** — cp 뿐이다. 잊으면 배포
# 파일 변경이 한 판 미뤄질 뿐이다.
#
# ## 왜 스크립트인가
#
# 손으로 `cp` 하면 어느 파일을 옮겨야 하는지를 사람이 기억해야 한다. 파일이
# 늘면 하나를 빠뜨리고, 빠뜨린 것은 다음 배포에서야 드러난다.
#
# ## 무엇을 옮기지 않는가
#
# **`.env` 는 건드리지 않는다.** prod 전용 상태다 — 비밀키와 지금 도는 판이
# 거기 있다. 통째로 덮어쓰면 그것들이 날아간다. 형제 프로젝트가 그렇게 크롤러
# 자격증명을 잃고 3.5개월을 몰랐다 (data-safety.md §13).
#
# 없을 때만 견본에서 만들어 준다.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRV="${DIATOM_SRV:-/srv/diatom}"

[ -d "$SRV" ] || { echo "배포 디렉토리가 없다: $SRV" >&2; exit 1; }

# 배포용 compose 와 호스트 스크립트. 판(IMAGE_TAG)은 .env 에 있으므로 이 파일들은
# 저장소의 것과 글자 그대로 같다 — diff 가 나면 누가 손으로 고친 것이다.
copy() {
    local src="$REPO/$1" dst="$SRV/$2"
    if [ -f "$dst" ] && cmp -s "$src" "$dst"; then
        echo "  = $2"
        return
    fi
    cp -p "$src" "$dst"
    echo "  → $2"
}

echo "$REPO → $SRV"
copy deploy/srv/docker-compose.yml docker-compose.yml
mkdir -p "$SRV/bin"
for f in deploy.sh; do
    copy "deploy/host/$f" "bin/$f"
    chmod +x "$SRV/bin/$f"
done

# nginx 가 배포 중에 낼 안내 페이지. nginx(www-data)가 읽어야 하므로 권한을 연다.
mkdir -p "$SRV/www"
copy deploy/nginx/maintenance.html www/diatom-maintenance.html
copy deploy/nginx/unavailable.html www/diatom-unavailable.html
chmod 755 "$SRV/www"; chmod 644 "$SRV/www"/*.html

# .env 는 없을 때만 만든다. 있으면 손대지 않는다.
if [ ! -f "$SRV/.env" ]; then
    cp -p "$REPO/deploy/srv/env.template" "$SRV/.env"
    chmod 600 "$SRV/.env"
    echo "  + .env (견본에서 만들었다 — DIATOM_SECRET_KEY 를 채울 것)"
else
    # 견본에 새 항목이 생겼는데 .env 에 없으면 알려만 준다. 채우는 것은 사람 몫이다.
    missing=$(comm -23 \
        <(grep -oE '^[A-Z_]+=' "$REPO/deploy/srv/env.template" | sort -u) \
        <(grep -oE '^[A-Z_]+=' "$SRV/.env" | sort -u) || true)
    if [ -n "$missing" ]; then
        echo "  ! .env 에 없는 항목: $(echo "$missing" | tr -d '=' | tr '\n' ' ')" >&2
    fi
fi

echo "완료."
