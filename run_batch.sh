#!/usr/bin/env bash
# 전 그룹 초점 합성 + 합성본 검출 일괄 실행.
#
#   ./run_batch.sh groups_RS23.json
#   ./run_batch.sh                      # 인자 없으면 groups_*.json 전부
#
# 형태 필터는 아직 segment_diatoms.py 에 들어가 있지 않다. 여기서 돌리는 것은
# 크기 기준(10~150 µm)만 적용한 기본 검출이며, 뷰어에 그대로 붙는다.
#
# 파이썬은 PY 로 준다. 컨테이너 안에서는 그냥 python 이고, 호스트에서는:
#   PY=~/venv/DiaRUGA/bin/python ./run_batch.sh
#
# **호스트에서 돌릴 때는 뷰어 컨테이너를 내리고 할 것.** 라이브 DB 에 두 곳에서
# 쓰면 안 된다 (.guides/web/data-safety.md). 컨테이너로 돌리는 것이 정석이다:
#   cd /srv/DiaRUGA && docker compose run --rm pipeline ./run_batch.sh
set -u

cd "$(dirname "$0")"
PY="${PY:-python}"
export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0}

# 사진과 산출물이 어디 있는지는 .env 가 안다 (저장소 밖이다 — P03)
DATA_ROOT="${DIARUGA_DATA_ROOT:-$(sed -n 's/^DIARUGA_DATA_ROOT=//p' .env 2>/dev/null)}"
DATA_ROOT="${DATA_ROOT:-.}"
STACKED="$DATA_ROOT/stacked"
OUT="$DATA_ROOT/out"

targets=("$@")
if [ ${#targets[@]} -eq 0 ]; then
    targets=(groups_*.json)
fi

for gj in "${targets[@]}"; do
    echo "=============== $gj ==============="

    # 1) 합성. 이미 합성된 시야는 focus_stack.py 가 스스로 건너뛴다
    #    (Stack 행이 있는지 DB 에 묻는다 — 예전에는 이 셸이 파일 존재로 판단했다).
    $PY focus_stack.py "$gj" 2>&1 | grep -viE 'warn|futurew'

    # 2) 검출 대상 모으기.
    #    합성본이 원칙이다 — 초점 흐림 잔해가 줄어 20 µm 이상 구간에서 더 잘 잡힌다.
    #    다만 싱글턴 그룹(n=1)은 합성본이 없으므로 그 한 장을 그대로 쓴다.
    #
    #    아직 JSON 을 읽는다. segment_diatoms.py 가 P02 6단계의 다음 차례이고,
    #    그것이 끝나면 이 블록도 DB 질의로 바뀐다.
    mapfile -t shots < <($PY - "$gj" <<'EOF'
import json, os, sys, django
from pathlib import Path
sys.path.insert(0, "web"); sys.path.insert(0, ".")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "diarugaweb.settings")
django.setup()
from django.conf import settings
from focus_stack import resolve_slide

meta = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
# groups.json 의 dir 은 사진을 옮기면 낡는다 — 어디 있는지는 DB 가 안다
slide = resolve_slide(meta["dir"], None)
data = Path(settings.DATA_ROOT)
stacked = data / settings.STACK_DIR
root = data / slide.image_dir
for g in meta["groups"]:
    if g["n"] >= 2:
        tag = f"g{g['id']:03d}_{g['images'][0]}-{g['images'][-1].split('-')[-1]}"
        p = stacked / f"{tag}_focused.jpg"
        if p.exists():
            print(p)
    else:
        print(root / f"{g['images'][0]}.jpg")
EOF
)

    for f in "${shots[@]}"; do
        [ -e "$f" ] || continue
        stem=$(basename "$f" .jpg)
        # 이미 검출한 것은 건너뛴다 (재실행 시 이어서 진행)
        if [ -f "$OUT/${stem}_candidates.json" ]; then
            echo "skip  $stem"
            continue
        fi
        # points-per-batch 는 이 장비(RTX 3060 Ti, 8 GB)에 맞춘 값이다.
        # 스크립트가 만들어진 RTX 8000 은 48 GB 라 64 로 돌았지만 여기서는 OOM 난다.
        # 검출 결과에는 영향이 없다 — 배치로 나눠 넣을 뿐이다.
        $PY segment_diatoms.py "$f" -o "$OUT" \
            --scale 1.0 --points-per-side 48 \
            --points-per-batch "${PPB:-16}" \
            --min-um 10 --max-um 150 2>&1 | grep -viE 'warn|futurew' | grep ':'
    done
done

echo "=============== 완료 ==============="
ls "$OUT"/*_candidates.json 2>/dev/null | wc -l | xargs echo "검출 완료 이미지 수:"
