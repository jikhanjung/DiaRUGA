#!/usr/bin/env bash
# 전 그룹 초점 합성 + 합성본 검출 일괄 실행.
#
# 형태 필터는 아직 segment_diatoms.py 에 들어가 있지 않다. 여기서 돌리는 것은
# 크기 기준(10~150 µm)만 적용한 기본 검출이며, 뷰어에 그대로 붙는다.
#
#   ./run_batch.sh groups_RS23.json
#   ./run_batch.sh            # 인자 없으면 groups_*.json 전부
set -u

cd "$(dirname "$0")"
PY=.venv/bin/python
export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0}

targets=("$@")
if [ ${#targets[@]} -eq 0 ]; then
    targets=(groups_*.json)
fi

for gj in "${targets[@]}"; do
    echo "=============== $gj ==============="

    # 1) 합성. n>=2 인 그룹만 (기본 --min-n 2).
    #    이미 합성된 그룹은 건너뛴다 — 그룹당 17초라 재실행 비용이 크다.
    todo=$($PY - "$gj" <<'EOF'
import json, sys
from pathlib import Path
meta = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
out = []
for g in meta["groups"]:
    if g["n"] < 2:
        continue
    tag = f"g{g['id']:03d}_{g['images'][0]}-{g['images'][-1].split('-')[-1]}"
    if not Path(f"stacked/{tag}_focused.jpg").exists():
        out.append(str(g["id"]))
print(" ".join(out))
EOF
)
    if [ -n "$todo" ]; then
        echo "합성 대상 그룹: $todo"
        $PY focus_stack.py "$gj" -o stacked/ --only $todo 2>&1 | grep -viE 'warn|futurew'
    else
        echo "합성 완료 상태 — 건너뜀"
    fi

    # 2) 검출 대상 모으기.
    #    합성본이 원칙이다 — 초점 흐림 잔해가 줄어 20 µm 이상 구간에서 더 잘 잡힌다.
    #    다만 싱글턴 그룹(n=1)은 합성본이 없으므로 그 한 장을 그대로 쓴다.
    mapfile -t shots < <($PY - "$gj" <<'EOF'
import json, sys
from pathlib import Path
meta = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
root = Path(meta["dir"])
for g in meta["groups"]:
    if g["n"] >= 2:
        tag = f"g{g['id']:03d}_{g['images'][0]}-{g['images'][-1].split('-')[-1]}"
        p = Path(f"stacked/{tag}_focused.jpg")
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
        if [ -f "out/${stem}_candidates.json" ]; then
            echo "skip  $stem"
            continue
        fi
        $PY segment_diatoms.py "$f" -o out \
            --scale 1.0 --points-per-side 48 --points-per-batch 64 \
            --min-um 10 --max-um 150 2>&1 | grep -viE 'warn|futurew' | grep ':'
    done
done

echo "=============== 완료 ==============="
ls out/*_candidates.json 2>/dev/null | wc -l | xargs echo "검출 완료 이미지 수:"
