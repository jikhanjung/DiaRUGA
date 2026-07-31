#!/usr/bin/env bash
# NAS 를 주기적으로 보고, 복사가 끝난 새 슬라이드를 끝까지 돌린다 (P03 5단계).
#
#   * * * * * /home/paleoadmin/projects/diatom/deploy/poll_nas.sh
#
# ## 1분마다 돌아도 되는 이유
#
# 할 일이 없으면 컨테이너 하나를 띄워 NAS 를 훑고 끝난다(1~2초). 정찰은 torch 를
# 임포트하지 않으므로 **GPU 를 건드리지 않고 VRAM 은 0 그대로다.**
#
# 한 슬라이드 처리에 한 시간 반이 걸리므로 겹쳐 도는 것이 정상이다 — `flock` 으로
# 뒤 실행이 조용히 물러난다.
#
# ## 아무 일도 없으면 아무것도 적지 않는다
#
# 1분 주기면 하루 1,440번이다. 매번 "새것 없음" 을 적으면 정작 사고가 났을 때
# 그 줄을 못 찾는다. **할 일이 있거나 실패했을 때만 적는다.**
#
# ## 복사가 끝났다고 어떻게 판단하는가
#
# `scan_nas.py` 가 폴더의 (사진 수·XML 수·바이트) 지문을 기억해 두고, `--stable-min`
# 동안 한 번도 안 바뀌었을 때만 "새것" 으로 넘긴다. mtime 만 보면 `rsync -a` 가
# 원본 시각을 보존해서 **한창 들어오는 중인데도 조용해 보인다.**
#
# ## 왜 호스트 cron 인가
#
# 컨테이너에 docker.sock 을 물리는 방식(DooD)은 사실상 root 를 주는 것이라 피했다.
# 트리거만 호스트가 맡고 실제 작업은 전부 컨테이너 안에서 돈다.
set -euo pipefail

DEPLOY_DIR=/srv/diatom
LOG_DIR=/data3/diatom/logs
LOCK=/tmp/diatom-poll.lock
STABLE_MIN="${STABLE_MIN:-5}"   # 이만큼(분) 폴더가 안 변해야 가져온다
PPB="${PPB:-16}"                # points-per-batch — 이 장비(3060 Ti 8 GB) 기준
# NAS 가 hard 마운트라 내려가면 무한 대기한다. 단계마다 상한을 건다.
T_SCAN=600                      # 10분
T_INGEST=3600                   # 1시간 — 슬라이드 하나가 1.4 GB 다
T_PIPE=21600                    # 6시간 — 74 시야 검출에 1시간 반쯤 걸렸다

mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/poll.log"
say() { echo "[$(date '+%F %T')] $*" >>"$LOG"; }

# 겹쳐 돌면 같은 슬라이드를 둘이 검출한다. 물러나는 것이 정상이라 적지 않는다.
exec 9>"$LOCK"
flock -n 9 || exit 0

cd "$DEPLOY_DIR"
run() { timeout "$1" docker compose run --rm -T pipeline "${@:2}"; }

# 1) 정찰. 조용히 돌리고, 실패하거나 할 일이 있을 때만 남긴다.
SCAN_JSON="$LOG_DIR/last_scan.json"
SCAN_OUT=$(mktemp); trap 'rm -f "$SCAN_OUT"' EXIT
if ! run "$T_SCAN" python scan_nas.py --stable-min "$STABLE_MIN" \
        --json "$SCAN_JSON" >"$SCAN_OUT" 2>&1; then
    say "정찰 실패 — NAS 가 내려갔는가"
    sed 's/^/    /' "$SCAN_OUT" >>"$LOG"
    exit 1
fi

NEW=$(python3 -c "
import json
d=json.load(open('$SCAN_JSON'))
print(sum(1 for r in d['slides'] if r['state']=='new'))" 2>/dev/null || echo 0)

# 2) 새것이 있으면 가져온다
if [ "$NEW" -gt 0 ]; then
    say "새 슬라이드 $NEW 개 — 가져온다"
    sed 's/^/    /' "$SCAN_OUT" >>"$LOG"
    if ! run "$T_INGEST" python ingest_nas.py --stable-min "$STABLE_MIN" >>"$LOG" 2>&1; then
        say "반입 실패"
        exit 1
    fi
fi

# 3) 밀린 슬라이드를 이어서 돌린다. 앞 실행이 끊겼거나 OOM 으로 죽었을 때
#    다음 주기가 마무리한다. failed 는 건드리지 않는다 — 사람이 봐야 한다.
TODO=$(run "$T_SCAN" python - <<'PY' 2>/dev/null | tr -d '\r'
import os, sys, django
sys.path.insert(0, "web"); sys.path.insert(0, ".")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "diatomweb.settings")
django.setup()
from viewer.models import Slide
for s in Slide.objects.filter(state__in=("pending", "processing")).order_by("pk"):
    print(f"{s.slug}\t{s.state}\t{s.image_dir}")
PY
)

[ -n "$TODO" ] || exit 0        # 할 일 없음 — 조용히 끝낸다

say "=== 처리 시작 ==="
echo "$TODO" | while IFS=$'\t' read -r slug state image_dir; do
    [ -n "$slug" ] || continue
    say "--- $slug ($state) ---"

    # 그룹핑 — 시야가 없을 때만. 이미 있으면 재그룹핑이 그 아래를 어긋내므로
    # group_focus_series.py 가 스스로 거부한다.
    if [ "$state" = "pending" ]; then
        if ! run "$T_PIPE" python group_focus_series.py \
                "/data3/diatom/$image_dir" >>"$LOG" 2>&1; then
            say "$slug: 그룹핑 실패"
            continue
        fi
    fi

    # 합성·검출은 이미 끝난 시야를 스스로 건너뛴다
    # (Stack 행 / 현재 Detection 유무를 DB 에 묻는다)
    if ! run "$T_PIPE" python focus_stack.py --slide "$slug" >>"$LOG" 2>&1; then
        say "$slug: 합성 실패"
        continue
    fi
    if ! run "$T_PIPE" python segment_diatoms.py --slide "$slug" \
            --scale 1.0 --points-per-side 48 --points-per-batch "$PPB" \
            --min-um 10 --max-um 150 >>"$LOG" 2>&1; then
        say "$slug: 검출 실패"
        continue
    fi
    say "$slug: 끝"
done
say "=== 처리 끝 ==="
