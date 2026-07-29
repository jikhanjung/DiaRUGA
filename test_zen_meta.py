#!/usr/bin/env python3
"""zen_meta 테스트. 촬영 데이터 없이 돌아간다 — 의존성도 표준 라이브러리뿐이다.

    python3 test_zen_meta.py

ZEN XML 을 손에 넣기 어려운 환경에서도 파서가 상하지 않았는지 확인할 수 있게
합성 XML 로 검증한다. 구조는 실제 파일의 Scaling/Items/Distance 를 따랐다.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zen_meta as zm

_tmp = tempfile.TemporaryDirectory()
TMP = Path(_tmp.name)

ZEN = """<?xml version="1.0" encoding="utf-8"?>
<ImageMetadata>
  <Information><Image>
    <AcquisitionDateAndTime>2026-07-29T04:51:43.1234567Z</AcquisitionDateAndTime>
    <SizeX>2752</SizeX>
  </Image></Information>
  <Scaling>
    <AutoScaling><CameraPixelDistance>4.54,4.54</CameraPixelDistance></AutoScaling>
    <Items>
      <Distance Id="X"><Value>1.1259920634920635E-07</Value>
        <DefaultUnitFormat>&#181;m</DefaultUnitFormat></Distance>
      <Distance Id="Y"><Value>1.1259920634920635E-07</Value></Distance>
    </Items>
  </Scaling>
</ImageMetadata>
"""

ok = fail = 0


def check(name, got, want):
    global ok, fail
    if got == want:
        ok += 1
        print(f"  ok   {name}: {got}")
    else:
        fail += 1
        print(f"  FAIL {name}: got {got!r}, want {want!r}")


def write(name, xml=None, jpg=True):
    img = TMP / name
    if jpg:
        img.write_bytes(b"notarealjpeg")
    if xml is not None:
        zm.xml_sidecar(img).write_text(xml, encoding="utf-8")
    return img


print("1. 정상 ZEN XML")
img = write("Snap-21365.jpg", ZEN)
sc = zm.scaling_for(img)
check("um_per_pixel", round(sc["um_per_pixel"], 8), 0.11259921)
check("source", sc["source"], "xml")
check("timestamp", str(zm.read_timestamp(img))[:19], "2026-07-29 04:51:43")

print("2. 다른 배율 (63x 상당) — 하드코딩이었다면 놓쳤을 값")
img2 = write("Snap-99999.jpg", ZEN.replace("1.1259920634920635E-07", "7.15E-08"))
check("um_per_pixel", round(zm.scaling_for(img2)["um_per_pixel"], 6), 0.0715)

print("3. 네임스페이스가 붙은 XML")
img3 = write("ns.jpg", ZEN.replace("<ImageMetadata>", '<ImageMetadata xmlns="http://zeiss">'))
sc3 = zm.scaling_for(img3)
check("source", sc3["source"], "xml")   # 기본값과 값이 같아 source 로 구분해야 한다
check("um_per_pixel", round(sc3["um_per_pixel"], 8), 0.11259921)

print("4. 잘린 XML — 정규식 폴백")
img4 = write("broken.jpg", ZEN[: ZEN.index("</Items>")] + "  <!-- 여기서 잘림")
check("source", zm.scaling_for(img4)["source"], "xml")
check("um_per_pixel", round(zm.scaling_for(img4)["um_per_pixel"], 8), 0.11259921)

print("5. XML 없음 → 기본값")
img5 = write("noxml.jpg")
sc5 = zm.scaling_for(img5)
check("source", sc5["source"], "default")
check("um_per_pixel", sc5["um_per_pixel"], zm.DEFAULT_UM_PER_PIXEL)

print("6. 사이드카 (합성본 경로)")
img6 = write("g000_focused.jpg")
zm.write_scale_sidecar(img6, 0.2251984, source="xml", resize_scale=0.5)
sc6 = zm.scaling_for(img6)
check("source", sc6["source"], "sidecar")
check("um_per_pixel", sc6["um_per_pixel"], 0.2251984)

print("7. XML 이 사이드카보다 우선한다")
img7 = write("both.jpg", ZEN)
zm.write_scale_sidecar(img7, 9.99)
check("um_per_pixel", round(zm.scaling_for(img7)["um_per_pixel"], 8), 0.11259921)

print("8. 말도 안 되는 값 → 거부하고 기본값")
img8 = write("crazy.jpg", ZEN.replace("1.1259920634920635E-07", "1.0"))
check("source", zm.scaling_for(img8)["source"], "default")

print("9. Scaling 블록이 없음 → 기본값")
img9 = write("noscaling.jpg", "<ImageMetadata><Information/></ImageMetadata>")
check("source", zm.scaling_for(img9)["source"], "default")

print("10. X/Y 가 다름 → 경고하고 X 사용")
img10 = write("aniso.jpg", ZEN.replace(
    '<Distance Id="Y"><Value>1.1259920634920635E-07</Value>',
    '<Distance Id="Y"><Value>2.0E-07</Value>'))
check("um_per_pixel", round(zm.scaling_for(img10)["um_per_pixel"], 8), 0.11259921)

print("11. ScaleLog — 섞이면 경고")
log = zm.ScaleLog()
log.add("a.jpg", 0.1126)
log.add("b.jpg", 0.1126)   # 조용
log.add("c.jpg", 0.0715)   # 경고 1회
log.add("d.jpg", 0.0715)   # 중복 억제
check("seen", len(log.seen), 1)

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
