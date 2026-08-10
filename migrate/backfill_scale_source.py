#!/usr/bin/env python3
"""zen_meta.py 도입 이전에 만든 검출 JSON 에 픽셀 크기의 출처를 채운다.

전량 배치(124 시야)는 `zen_meta.py` 가 생기기 전에 돌아서, 하드코딩된 상수로
계산됐다. 이 데이터셋에서는 그 상수가 XML 값과 같아 **계측값은 어긋나지 않았지만**
`um_per_pixel_source` 가 없어 나중에 의심할 수가 없다. 재추론 없이 그 출처만
채운다.

원본 사진은 옆의 XML 을 읽으면 되고, 합성본은 ZEN XML 이 따라오지 않으므로
`focus_stack.py:carry_scaling()` 이 하는 일을 그룹 정의에서 되짚어
`<tag>_focused.jpg_scale.json` 사이드카를 먼저 만든다.

**기록된 값과 XML 값이 다르면 그 파일은 건드리지 않고 알린다.** 계측값(면적·장단축)
전체가 그 배율로 계산돼 있어서, 여기서 숫자만 갈아 두면 앞뒤가 맞지 않게 된다.
그 경우는 재검출이 답이다.

    python backfill_scale_source.py out/ --dry-run   # 무엇이 채워질지만 본다
    python backfill_scale_source.py out/

zen_meta 도입 이후의 산출물에는 필요 없다. 한 번 쓰고 지워도 되는 스크립트다.
"""
import argparse
import json
import sys
from pathlib import Path

from PIL import Image

# **`pipeline/zen_meta.py` 를 함께 쓴다.** 촬영 XML 을 읽는 규칙이 하나여야
# 한다 — 둘이면 배율의 출처가 갈린다. `/srv/DiaRUGA/scripts` 는 평평해서 이
# 줄이 없어도 되지만, 저장소에서는 디렉토리가 갈려 있어 알려 줘야 한다.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

from zen_meta import scaling_for, scale_sidecar, write_scale_sidecar  # noqa: E402

# 같은 배율로 볼 수 있는 상대 오차. zen_meta·focus_stack 이 쓰는 값과 같다.
TOL = 1e-3


def group_frames(groups_files):
    """`stacked/<tag>_focused.jpg` 의 tag → 원본 프레임 경로.

    tag 규칙은 focus_stack.py 와 같다: `g{id:03d}_{첫장}-{마지막번호}`.
    """
    out = {}
    for gf in groups_files:
        spec = json.loads(Path(gf).read_text(encoding="utf-8"))
        base = Path(spec["dir"])
        for g in spec["groups"]:
            tag = f"g{g['id']:03d}_{g['images'][0]}-{g['images'][-1].split('-')[-1]}"
            out[tag] = [base / f"{stem}.jpg" for stem in g["images"]]
    return out


def infer_resize_scale(stacked_img, frames):
    """합성 당시의 `--scale`. 기록이 없으므로 합성본과 원본의 폭에서 되짚는다."""
    with Image.open(stacked_img) as im:
        sw = im.width
    with Image.open(frames[0]) as im:
        ow = im.width
    ratio = sw / ow
    return 1.0 if abs(ratio - 1.0) < 2e-3 else ratio


def ensure_sidecar(stacked_img, frames, dry_run):
    """합성본 옆에 픽셀 크기를 남긴다. focus_stack.carry_scaling() 과 같은 내용."""
    side = scale_sidecar(stacked_img)
    scalings = [scaling_for(p) for p in frames]
    native = scalings[0]["um_per_pixel"]
    mixed = any(abs(s["um_per_pixel"] - native) > native * TOL for s in scalings)

    resize = infer_resize_scale(stacked_img, frames)
    um = native / resize

    if side.exists():
        return um, native, resize, mixed, "있음"
    if dry_run:
        return um, native, resize, mixed, "만들 것"
    write_scale_sidecar(stacked_img, um,
                        source=scalings[0]["source"],
                        native_um_per_pixel=native,
                        resize_scale=resize,
                        stacked_from=[p.name for p in frames],
                        # 합성 시점이 아니라 나중에 되짚어 만든 사이드카다.
                        # resize_scale 은 기록이 아니라 이미지 폭에서 추론했다.
                        backfilled=True)
    return um, native, resize, mixed, "만들었다"


def fill(payload, native, source):
    """`um_per_pixel` 바로 뒤에 출처를 끼운다 — 새 산출물과 키 순서를 맞춘다."""
    out = {}
    for k, v in payload.items():
        out[k] = v
        if k == "um_per_pixel":
            out["um_per_pixel_native"] = native
            out["um_per_pixel_source"] = source
            # 이 실행이 읽은 값이 아니라 뒤늦게 채운 값임을 남긴다
            out["um_per_pixel_backfilled"] = True
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", nargs="?", default="out",
                    help="검출 JSON 파일 또는 디렉토리 (기본 out/)")
    ap.add_argument("--groups", nargs="*", default=None,
                    help="그룹 정의 (기본 groups_*.json 전부)")
    ap.add_argument("--dry-run", action="store_true", help="확인만, 저장 안 함")
    args = ap.parse_args()

    target = Path(args.target)
    files = sorted(target.glob("*_candidates.json")) if target.is_dir() else [target]
    if not files:
        raise SystemExit(f"검출 JSON 을 찾지 못했다: {target}")

    gfiles = args.groups if args.groups else sorted(Path(".").glob("groups_*.json"))
    frames_of = group_frames(gfiles)

    n_done = n_skip = n_bad = 0
    sources = {}
    mismatches, missing = [], []

    for f in files:
        payload = json.loads(f.read_text(encoding="utf-8"))
        if "um_per_pixel_source" in payload:
            n_skip += 1
            continue

        img = Path(payload["image"])
        recorded = payload["um_per_pixel"]
        seg_scale = payload.get("scale", 1.0)

        if img.name.endswith("_focused.jpg"):
            tag = img.name[: -len("_focused.jpg")]
            frames = frames_of.get(tag)
            if not frames:
                missing.append(f"{f.name}: 그룹 정의에 {tag} 가 없다")
                n_bad += 1
                continue
            if not all(p.exists() for p in frames) or not img.exists():
                missing.append(f"{f.name}: 원본 또는 합성본이 없다 ({tag})")
                n_bad += 1
                continue
            source = "sidecar"      # 사이드카를 만들어 두면 재검출도 이쪽을 읽는다
            um, native, resize, mixed, note = ensure_sidecar(img, frames, args.dry_run)
            if mixed:
                print(f"{f.stem}: 경고 — 그룹 안에서 픽셀 크기가 다르다. "
                      f"첫 장 기준으로 남긴다")
            detail = f"사이드카 {note}, resize={resize:g}"
            native_for_json = um       # 합성본 입장에서는 이것이 native 다
        else:
            if not img.exists():
                missing.append(f"{f.name}: 원본이 없다 ({img})")
                n_bad += 1
                continue
            sc = scaling_for(img)
            um, source = sc["um_per_pixel"], sc["source"]
            native_for_json = um
            detail = Path(sc["path"]).name if sc["path"] else "-"

        # 기록된 계측 기준과 지금 읽은 값이 같은가. 다르면 손대지 않는다.
        expect = um / seg_scale
        if abs(expect - recorded) > max(abs(recorded), abs(expect)) * TOL:
            mismatches.append(f"{f.name}: 기록 {recorded:.8f} != XML {expect:.8f}")
            n_bad += 1
            continue

        if source == "default":
            missing.append(f"{f.name}: 메타데이터를 찾지 못해 출처가 default 다")
            n_bad += 1
            continue

        sources[source] = sources.get(source, 0) + 1
        n_done += 1
        print(f"{f.stem}: {source} ({detail})")

        if not args.dry_run:
            f.write_text(json.dumps(fill(payload, native_for_json, source),
                                    indent=2, ensure_ascii=False),
                         encoding="utf-8")

    print(f"\n{len(files)}개 중 {n_done}개 채움 "
          f"({', '.join(f'{k} {v}' for k, v in sorted(sources.items())) or '-'}), "
          f"이미 있던 것 {n_skip}, 손대지 않음 {n_bad}")
    for line in mismatches:
        print(f"  [불일치] {line}")
    for line in missing:
        print(f"  [확인필요] {line}")
    if mismatches:
        print("불일치는 계측값 전체가 그 배율로 계산돼 있으므로 재검출이 답이다.")
    if args.dry_run:
        print("dry-run — 파일은 변경하지 않았다.")


if __name__ == "__main__":
    main()
