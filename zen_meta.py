#!/usr/bin/env python3
"""사진에 딸려 오는 ZEISS ZEN 메타데이터(`<파일명>.jpg_metadata.xml`)를 읽는다.

µm/픽셀에는 계측값(면적·장단축)·크기 관문(10~150 µm)·텍스처 대역(0.4~1.6 µm)이
모두 걸려 있다. 상수로 박아 두면 **촬영 조건이 바뀌었을 때 예외도 경고도 없이
결과 전체가 배율만큼 어긋난다.** 그래서 XML 이 곁에 있으면 언제나 그쪽을 읽고,
없을 때만 기본값으로 물러난다.

합성본처럼 XML 이 없는 파생 이미지를 위해 `<파일명>_scale.json` 사이드카를
쓴다(`write_scale_sidecar`). ZEN 의 명명 규칙을 그대로 따라 원본과 같은 자리에서
찾을 수 있게 했다.
"""
import datetime as dt
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# 40x/0.95 + 1.6x optovar + 0.63x adapter, Axiocam 506 (4.54 µm pixel) 기준.
# XML 도 사이드카도 없을 때만 쓰는 최후의 기본값이다.
DEFAULT_UM_PER_PIXEL = 0.11259920634920635

# 광학현미경에서 나올 수 있는 범위. 이 밖의 값이면 파싱을 잘못한 것으로 본다.
PLAUSIBLE_UM_PER_PIXEL = (0.001, 100.0)

_warned = set()


def _warn(key, msg):
    """같은 원인의 경고는 한 번만 — 배치에서 수백 줄이 쏟아지지 않게."""
    if key in _warned:
        return
    _warned.add(key)
    print(f"[scale] {msg}", file=sys.stderr)


def xml_sidecar(img) -> Path:
    """`Snap-21365.jpg` → `Snap-21365.jpg_metadata.xml` (ZEN 이 만든다)."""
    img = Path(img)
    return img.with_name(img.name + "_metadata.xml")


def scale_sidecar(img) -> Path:
    """`..._focused.jpg` → `..._focused.jpg_scale.json` (우리가 만든다)."""
    img = Path(img)
    return img.with_name(img.name + "_scale.json")


def _read_text(path: Path):
    try:
        return path.read_text(encoding="utf-8-sig", errors="ignore")
    except OSError:
        return None


def _to_float(s):
    try:
        return float(str(s).strip())
    except (TypeError, ValueError):
        return None


def _iter_local(root, name):
    """네임스페이스가 붙어 있어도 태그 이름으로 찾는다."""
    for el in root.iter():
        if el.tag.rsplit("}", 1)[-1] == name:
            yield el


def _distances(text):
    """Scaling/Items/Distance 에서 축별 픽셀 크기(m)를 뽑는다."""
    out = {}
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        # 잘린 XML 이어도 값만 건지면 된다
        for axis, val in re.findall(
            r'<Distance[^>]*Id="([XY])"[^>]*>\s*<Value>([^<]+)</Value>', text
        ):
            v = _to_float(val)
            if v is not None:
                out.setdefault(axis.upper(), v)
        return out

    # Scaling 아래에 있는 것만 본다 — 다른 곳의 Distance 와 섞이지 않게.
    scopes = list(_iter_local(root, "Scaling")) or [root]
    for scope in scopes:
        for dist in _iter_local(scope, "Distance"):
            axis = (dist.attrib.get("Id") or "X").upper()
            node = next(_iter_local(dist, "Value"), None)
            v = _to_float(node.text if node is not None else dist.text)
            if v is not None:
                out.setdefault(axis, v)
    return out


def read_um_per_pixel(img):
    """XML 에 기록된 픽셀 크기(µm). XML 이 없거나 값이 이상하면 None."""
    xml = xml_sidecar(img)
    text = _read_text(xml)
    if text is None:
        return None

    d = _distances(text)
    if not d:
        _warn(f"noscaling:{xml.parent}",
              f"{xml.name}: Scaling/Items/Distance 를 찾지 못했다")
        return None

    m = d.get("X", next(iter(d.values())))       # 값은 미터 단위
    um = m * 1e6
    lo, hi = PLAUSIBLE_UM_PER_PIXEL
    if not (lo <= um <= hi):
        _warn(f"implausible:{xml.parent}",
              f"{xml.name}: {um:g} µm/px 는 광학현미경 범위 밖이라 쓰지 않는다")
        return None

    y = d.get("Y")
    if y is not None and abs(y * 1e6 - um) > um * 0.01:
        _warn(f"anisotropic:{xml.parent}",
              f"{xml.name}: X({um:.6f})와 Y({y * 1e6:.6f}) 픽셀 크기가 다르다 "
              "— X 를 쓴다")
    return um


def read_timestamp(img):
    """AcquisitionDateAndTime. 사진마다 유일하게 의미 있게 달라지는 값이다."""
    text = _read_text(xml_sidecar(img))
    if text is None:
        return None
    m = re.search(r"<AcquisitionDateAndTime>(.*?)</AcquisitionDateAndTime>", text)
    if not m:
        return None
    try:
        return dt.datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
    except ValueError:
        return None


def scaling_for(img, default=DEFAULT_UM_PER_PIXEL):
    """이미지 하나의 µm/픽셀을 정한다. XML > 사이드카 > 기본값.

    항상 dict 를 반환한다: `um_per_pixel`, `source`("xml"/"sidecar"/"default"),
    `path`. source 를 결과 JSON 에 같이 남겨 두면 나중에 계측값을 의심할 때
    어디서 온 값인지 바로 알 수 있다.
    """
    img = Path(img)

    um = read_um_per_pixel(img)
    if um is not None:
        return {"um_per_pixel": um, "source": "xml", "path": str(xml_sidecar(img))}

    side = scale_sidecar(img)
    text = _read_text(side)
    if text is not None:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {}
        v = _to_float(data.get("um_per_pixel"))
        if v is not None:
            return {"um_per_pixel": v, "source": "sidecar", "path": str(side)}
        _warn(f"badsidecar:{side}", f"{side.name}: um_per_pixel 을 읽지 못했다")

    _warn(f"default:{img.parent}",
          f"{img.name}: 메타데이터가 없어 기본값 {default:g} µm/px 를 쓴다 "
          "— 촬영 조건이 다르면 계측값이 통째로 틀린다")
    return {"um_per_pixel": float(default), "source": "default", "path": None}


def write_scale_sidecar(img, um_per_pixel, **extra):
    """파생 이미지 옆에 픽셀 크기를 남긴다. 원본 XML 이 없는 합성본용."""
    path = scale_sidecar(img)
    payload = {"um_per_pixel": um_per_pixel, **extra}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    return path


class ScaleLog:
    """한 번의 실행에서 픽셀 크기가 섞이면 알린다.

    시료마다 배율이 다른 폴더를 한꺼번에 돌리면 계측값을 서로 비교할 수 없게
    되는데, 숫자만 봐서는 알아채기 어렵다. 값이 바뀌는 순간에 알린다.
    """

    def __init__(self):
        self.first = None       # (이름, µm/px)
        self.seen = set()

    def add(self, name, um_per_pixel):
        if self.first is None:
            self.first = (name, um_per_pixel)
            return
        ref_name, ref = self.first
        if abs(um_per_pixel - ref) <= ref * 1e-3:
            return
        key = round(um_per_pixel, 9)
        if key in self.seen:
            return
        self.seen.add(key)
        print(f"[scale] 경고: {name} 은 {um_per_pixel:.6f} µm/px 로 "
              f"{ref_name}({ref:.6f})와 다르다 — 촬영 조건이 섞였다. "
              "계측값을 한데 모아 비교하면 안 된다.", file=sys.stderr)
