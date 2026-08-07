"""데이터와 설정을 담는 스키마. 설계 근거는 devlog/20260730_P02_db-schema.md.

이 파일을 읽을 때 알아 둘 두 가지:

**1. 교정은 `Candidate` 가 아니라 `mask_key` 에 붙는다.** 검출을 다시 돌리면 후보
행이 새로 생기므로 FK 로 매면 사람의 판단이 조인 실패로 사라진다. `mask_key`(bbox
문자열)를 진짜 키로 두고 `candidate` 는 바인딩 결과로 채운다. 실측으로 같은 설정이면
100% 붙지만, 엔진을 갈면 거의 0 이 된다 — 그래서 교정 행은 `geom` 에 기하를 스스로
들고 있어 검출기와 독립적으로 읽힌다.

**2. 검출은 덮어쓰지 않고 쌓는다.** `Detection.is_current` 가 뷰어가 볼 것을 가리킨다.
교체 전후를 같은 시야로 비교해야 하기 때문이다(P01 §3).
"""
from django.db import models

# 폴더 이름 규칙은 `naming.py` 하나뿐이다 — 뷰어·파이프라인·마이그레이션이 같은
# 것을 본다. 예전에는 `group_focus_series` 와 `import_json` 에 두 벌이 있었다.
from .naming import base_name as _base_name

# 실행 종류. RunBatch 와 Run 이 함께 쓰므로 위로 뺀다.
RUN_KIND = [(k, k) for k in
            ("group", "stack", "detect", "refilter", "reconcile",
             "ingest", "export")]


class RunBatch(models.Model):
    """한 번의 작업을 묶는다. `Run` 은 슬라이드마다 하나씩 생긴다.

    파이프라인은 **슬라이드 단위로 돈다** — 폴러가 새 슬라이드 하나를 받으면
    그것만 처리하기 때문이고, 그 단위가 맞다. 그런데 "전체를 한 번 훑었다" 는
    작업은 그 실행 여럿으로 흩어져 남는다. 엔진을 비교하려면 **그 한 번을 한
    덩어리로** 볼 수 있어야 한다 (YOLO 전체 대 SAM2 전체).

    `Run` 에 부모를 다는 대신 따로 둔 이유: 부모 `Run` 은 자기 `started_at`·
    `counts` 를 갖게 되어 뜻이 겹친다. 묶음은 실행이 아니라 **이름표**다.
    """

    kind = models.CharField(max_length=16, choices=RUN_KIND)
    # 사람이 고르는 이름. "yolo-v1seg" 처럼 무엇을 돌렸는지가 드러나야 한다
    label = models.CharField(max_length=120)
    note = models.TextField(blank=True)
    # **뷰어가 검토 대상으로 삼는 묶음** (P10). 서버 설정이다 — 관리 화면에서
    # 고르고, 모두가 같은 것을 본다.
    #
    # **`Detection.is_current` 와 다른 것을 말한다.** 겹치는 이름을 쓰면 읽는
    # 사람이 반드시 헷갈려서 일부러 다르게 붙였다:
    #
    #   Detection.is_current   그 묶음 **안에서** 이 이미지의 최신 검출
    #   RunBatch.for_review    뷰어가 **검토 대상**으로 삼는 묶음
    #
    # 화면이 보여줄 검출은 **둘 다 켜진 것**이다 — 이 묶음을 검토하고 있고,
    # 그 묶음 안에서 최신인 검출 (`Detection.objects.reviewing()`).
    #
    # **URL·쿠키가 아니라 서버 설정인 이유** (P10 §2): 사람마다 다른 묶음을
    # 보면 `/review` 가 017·027·053 계열의 사고를 새로 만든다. 그 POST 는 범위를
    # 갈아치우고, 셋 다 "화면과 저장 대상이 어긋난" 사고였다.
    for_review = models.BooleanField(default=False, db_default=False)
    # **새 자료가 들어왔을 때 이 묶음을 어떻게 채우는가** (P10 6단계 · 079).
    #
    # 묶음이 여럿인 것이 기본이 됐다 — `sam2-전수` · `yolo-3차` · `yolo-4차` 가
    # 나란히 있고, 새 슬라이드는 **그 전부에** 들어가야 한다. 지금 보고 있는
    # 묶음만 따라가면 나머지는 뒤처지고, 갈아타는 순간 빈 화면이 된다.
    #
    # 담는 것은 `segment_diatoms.py` 의 인자다:
    # `{"backend": "yolo", "weights": "models/…​.pt", "scale": 1.0,
    #   "all_images": true, "min_um": 10, "max_um": 150, …}`
    #
    # **비어 있으면 자동으로 안 돈다.** 끝난 회차를 그대로 두는 것이 기본이고,
    # 돌릴 것은 사람이 적어 준다 — 묶음이 늘 때마다 GPU 시간이 곱으로 는다.
    recipe = models.JSONField(default=dict, blank=True, db_default={})
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        constraints = [
            models.UniqueConstraint(fields=["kind", "label"],
                                    name="uniq_batch_label"),
            # **검토 대상은 하나뿐이다.** 둘이면 화면이 어느 것을 그릴지 모르고,
            # 그 상태는 예외가 안 나고 그냥 틀린다 — DB 가 막는다.
            models.UniqueConstraint(fields=["for_review"],
                                    condition=models.Q(for_review=True),
                                    name="uniq_batch_for_review"),
        ]

    def __str__(self):
        return f"{self.label} ({self.kind})"


class Run(models.Model):
    """실행 이력. 지금까지 아무 데도 없어서 stack_report.json 이 덮어써졌다."""

    KIND = RUN_KIND
    # `partial` — 돌긴 했는데 일부를 건너뛴 것. `done` 과 갈라야 한다.
    # GPU 를 다른 작업이 침범해 9장이 조용히 빠졌는데 실행은 done 이었고,
    # 나중에 프레임 수를 세어 보고서야 알았다.
    STATUS = [(s, s) for s in ("running", "done", "partial", "failed")]

    kind = models.CharField(max_length=16, choices=KIND)
    # 여러 슬라이드에 걸친 한 번의 작업을 묶는 이름표. 비어 있어도 된다 —
    # 폴러가 슬라이드 하나만 처리하는 평소 실행에는 묶을 것이 없다.
    batch = models.ForeignKey("RunBatch", null=True, blank=True,
                              on_delete=models.SET_NULL, related_name="runs")
    slide = models.ForeignKey("Slide", null=True, blank=True,
                              on_delete=models.SET_NULL, related_name="runs")
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=8, choices=STATUS, default="running")
    error = models.TextField(blank=True)
    # 무슨 설정으로 돌렸나 — {"scale":1.0,"points_per_side":48,...}
    params = models.JSONField(default=dict, blank=True)
    counts = models.JSONField(default=dict, blank=True)
    host = models.CharField(max_length=64, blank=True)
    gpu = models.CharField(max_length=64, blank=True)
    code_version = models.CharField(max_length=64, blank=True)

    class Meta:
        indexes = [models.Index(fields=["kind", "-started_at"])]

    def __str__(self):
        return f"{self.kind} #{self.pk} ({self.status})"


class Site(models.Model):
    """채취 지역. 폴더명의 앞 토막(RS23, WAP13)이다.

    지역 코드의 정식 명칭은 사람이 채운다 — 코드만으로는 단정할 수 없다.

    **`area` 와 `region` 은 다른 칸이다.** `region` 은 이미 "로스해"·"Bigo Bay"
    같은 세부 지명으로 채워져 있어서, 목록을 가르는 상위 칸을 거기에 겸할 수 없다.
    `area` 가 그 위 단계다 — 지금은 남극과 한국 둘뿐이다.
    """

    AREA = [("kr", "한국"), ("ant", "남극")]

    code = models.CharField(max_length=32, unique=True)     # RS23
    name = models.CharField(max_length=200, blank=True)     # 사람이 채운다
    # 목록을 가르는 상위 구분. 기본이 남극인 것은 지금 자료가 전부 남극이라서다.
    #
    # **`db_default` 를 함께 준다.** `default` 는 파이썬 쪽이라 이 모델을 아는
    # 코드에만 붙는다. 이 DB 는 뷰어 이미지와 파이프라인 이미지가 함께 쓰는데
    # 판이 따로 돌아서, 파이프라인이 옛 코드일 때 `Site` 를 새로 만들면 이 칸을
    # 아예 안 보내고 `NOT NULL constraint failed` 로 죽는다 — 실제로 NAS 반입이
    # 그렇게 막혔다(BP09-0901). DB 가 스스로 채우게 두면 옛 코드도 그대로 돈다.
    area = models.CharField(max_length=8, choices=AREA,
                            default="ant", db_default="ant")
    region = models.CharField(max_length=200, blank=True)   # 로스해 / 웨델해 …
    lat = models.FloatField(null=True, blank=True)
    lon = models.FloatField(null=True, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.name or self.code


class Locality(models.Model):
    """지점 하나 — **시추코어 하나이거나 노두 하나다.**

    예전 이름은 `Core` 였다. 북평분지가 들어오면서 육상 시료가 이 층에 앉는데
    "코어" 라는 말이 안 맞았다 — 노두는 시추한 것이 아니다. 지점은 둘을 함께
    담는 넓은 말이고, **어느 쪽인지는 `kind` 가 말한다** (사용자 판단 2026-08-06).

    **육상은 지점 = 노두 = 단면이 하나다.** 단면을 따로 층으로 두지 않는다
    (사용자 확인 2026-08-06) — `BP09` 의 `09` 가 곧 그 노두이자 단면이다.

    시료가 이 아래 달리므로 **한 지점에서 위치에 따른 군집 변화**를 질의할 수
    있다. 시추코어는 깊이로, 노두는 단면상의 위치로 선다(`Sample`).
    """

    # 시추코어에서 뜬 것인가, 노두(outcrop)에서 뜬 것인가.
    #
    # **예전에는 `Slide.sample_kind` 였다.** 관찰마다 따로 들고 있어서 같은
    # 지점의 관찰 둘이 다른 값을 가질 수 있었다 — 한 지점이 코어이면서 노두일
    # 수는 없으므로 여기가 제자리다 (사용자 동의 2026-08-06). 실측에서 지점
    # 다섯 곳 전부 한 가지로 모여 그대로 올렸다.
    #
    # **왜 이 칸이 필요한가.** 노두 시료에는 깊이가 없다. `depth_cm` 을 비워
    # 두는 수밖에 없었는데, 그러면 화면에 `—` 로 나와 **"깊이가 없는 시료" 와
    # "아직 안 채운 시료" 가 구별되지 않는다.** 화면은 이 값을 보고 `OC` 를 쓴다.
    KIND = [("core", "시추코어"), ("outcrop", "노두")]

    site = models.ForeignKey(Site, on_delete=models.CASCADE,
                             related_name="localities")
    code = models.CharField(max_length=32)                  # GC03 · BP09
    # `db_default` 를 함께 준다 — 파이프라인 이미지는 굽는 주기가 달라 판이
    # 같아질 일이 없고, 옛 이미지의 INSERT 에는 이 칼럼이 안 들어간다.
    kind = models.CharField(max_length=12, choices=KIND,
                            default="core", db_default="core")
    # **채취 방식은 따로다** (`gravity core` · `outcrop sample`). 위의 `kind` 는
    # "코어냐 노두냐" 라는 두 갈래이고 이쪽은 사람이 적는 자유 문자열이다.
    # GC = gravity core 처럼 코드 앞 글자가 뜻을 갖는 일이 많지만 단정하지 않는다.
    collect_kind = models.CharField(max_length=64, blank=True)
    lat = models.FloatField(null=True, blank=True)
    lon = models.FloatField(null=True, blank=True)
    water_depth_m = models.FloatField(null=True, blank=True)
    collected_at = models.DateField(null=True, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        verbose_name = "지점"
        ordering = ["site", "code"]
        constraints = [models.UniqueConstraint(fields=["site", "code"],
                                               name="uniq_locality_code")]

    def __str__(self):
        return f"{self.site.code}-{self.code}"

    @property
    def is_outcrop(self) -> bool:
        return self.kind == "outcrop"


class Sample(models.Model):
    """시료 하나 — 지점에서 한 자리를 떠 온 것.

    **관찰의 위가 여기다.** 예전에는 `Slide` 하나가 시료와 관찰을 겸했다
    (`core`·`depth_cm`·`sample_kind` 가 관찰 행마다 앉아 있었다). 그래서 같은
    시료의 관찰 둘이 **서로 다른 소속을 가질 수 있었고**, 실제로 그렇게 됐다 —
    `BP09-0901` 은 지점에 붙어 있는데 `BP09-0901 (1)` 은 아무 데도 안 붙어
    화면에서 사라졌다. 시료 행이 있으면 관찰은 그것을 가리키기만 하므로 애초에
    어긋날 수가 없다.

    **위치 칸이 둘이고 지점 유형에 따라 하나만 쓴다.** 한 칸에 몰지 않는 이유는
    `depth_cm` 을 문자열로 안 바꾼 것과 같다 — 뜻이 다른 두 값이 한 칸에 앉으면
    "369cm" 와 "단면 9번" 을 같은 축에 그리게 된다. 지점은 코어이거나 노두이거나
    둘 중 하나라 정렬할 때는 어차피 한 칸만 본다.
    """

    locality = models.ForeignKey(Locality, on_delete=models.CASCADE,
                                 related_name="samples")
    # 폴더에서 온 시료 코드. `71cm` · `0901`. **화면에 그대로 쓴다** — 사람이
    # 부르는 이름이라 숫자로 다시 만들면(`71.0cm`) 폴더와 안 맞아 보인다.
    code = models.CharField(max_length=64)
    # 기준점(해저면)에서부터의 깊이. **시추코어 지점에만 있다.**
    depth_cm = models.FloatField(null=True, blank=True)
    # 단면상의 위치. **노두 지점에만 있다.** 사람이 부여한 숫자 코드에서 지점
    # 번호가 되풀이되는 자리를 뗀 것이다 — `BP09` + `0901` → `1`
    # (`naming.sample_no_from`).
    sample_no = models.PositiveIntegerField(null=True, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    class Meta:
        verbose_name = "시료"
        # 지점 안에서는 위치순 — 깊이에 따른 변화를 보는 것이 분석 목적이다.
        # 노두는 깊이가 없어 `sample_no` 가 그 자리를 대신한다.
        ordering = ["locality", "depth_cm", "sample_no", "code"]
        constraints = [models.UniqueConstraint(fields=["locality", "code"],
                                               name="uniq_sample_code")]
        indexes = [models.Index(fields=["locality", "depth_cm"])]

    def __str__(self):
        return f"{self.locality}-{self.code}"

    @property
    def position(self):
        """정렬·축에 쓰는 값 하나. 지점 유형이 어느 칸을 쓸지 정한다."""
        return self.depth_cm if self.depth_cm is not None else self.sample_no


class Slide(models.Model):
    """관찰 하나 = 폴더 하나 = 슬라이드글라스 하나. 그 안에 여러 시야가 있다.

    **이 표는 관찰만 담는다.** 시료가 어느 지점의 몇 cm 인가는 `Sample` 이
    안다 — 예전에는 `core`·`depth_cm`·`sample_kind` 가 여기 앉아 있어서 같은
    시료의 관찰 둘이 서로 다른 소속을 가질 수 있었다(`Sample` 머리말).

    **이름을 `Observation` 으로 안 바꾼다.** 슬라이드글라스라는 물건이 실재하고
    폴더 하나가 그것 하나다 — 관찰은 그 위에 얹힌 뜻이지 다른 물건이 아니다.
    """

    STATE = [(s, s) for s in
             ("pending", "copying", "processing", "done", "failed")]

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=120, unique=True)
    image_dir = models.CharField(max_length=500)
    # **`SET_NULL` 이다.** 시료를 지워도 관찰과 그 아래 검토가 남아야 한다 —
    # 소속은 다시 붙일 수 있지만 교정은 재생성 불가다. 소속을 잃은 관찰은
    # 관리 화면이 잡아낸다.
    sample = models.ForeignKey("Sample", null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="slides")

    # --- 관찰 -------------------------------------------------------------
    # 시료 하나를 **처리 방법이나 관찰 회차를 달리해 여러 번 본 것**.
    # 폴더 이름 뒤에 `(1)`·`(2)` 를 붙여 올리고, 접미사가 없는 기존 것은 `0` 이다.
    #
    # **지점 유형(`Locality.kind`)과 헷갈리지 말 것.** 그쪽은 "시추코어냐
    # 노두냐" 이고 이쪽은 "같은 시료를 몇 번째로 달리 관찰한 것이냐" 다.
    #
    # **재촬영과도 다른 축이다.** 같은 폴더명을 다른 날 올리면 슬러그가 촬영일로
    # 갈리는데(`slide_slug`) 그것은 "같은 관찰을 다시 찍은 것" 이다. 접미사는
    # "다른 관찰" 이다 — 두 축을 한 칸에 섞지 않는다.
    #
    # **관찰끼리는 동등하다** (사용자 방침 2026-08-06). "대표 관찰" 을 두지 않고
    # 이름표로 구분하며, 통계에 무엇을 넣을지는 아래 두 칸으로 사람이 고른다.
    #
    # **왜 칸이 둘인가.** 한 칸에 두면 폴더에서 다시 읽을 때 자동값이 사람이 적은
    # 것을 덮는다. 반입·그룹핑은 `obs_no` 만 쓰고 `obs_label` 은 절대 안 건드린다
    # (`update_or_create` 의 `defaults` 에서 뺀다).
    #
    # `db_default` 를 함께 주는 이유는 다른 칸과 같다 — 파이프라인 이미지는
    # 판이 따로 돌아 옛 INSERT 에 이 칼럼이 안 들어간다.
    obs_no = models.PositiveSmallIntegerField(default=0, db_default=0)
    # 사람이 붙이는 뜻(`산처리` · `체 20µm`). **폴더는 안 건드린다** — 이름표는
    # 여기에만 앉고, 화면이 불러올 때 폴더의 `(1)` 자리에 대신 보인다.
    #
    # **10자다** (사용자 판단 2026-08-05). 애초에 길게 적을 것이 아니고 —
    # 한글 5자면 넉넉하다 — 짧게 못 박아 두면 배지 하나가 목록의 슬라이드 열을
    # 통째로 미는 일이 아예 안 생긴다. 길이를 화면에서 잘라 감추는 것보다
    # 들어올 수 없게 하는 쪽이 낫다.
    obs_label = models.CharField(max_length=10, blank=True, default="",
                                 db_default="")

    # 같은 시료의 관찰이 여럿이면 **합계가 조용히 두 배가 된다.** 어느 관찰이
    # 대표인지는 코드가 정할 수 없으므로(비교하려고 만든 것이다) 사람이 고른다.
    #
    # **둘을 가른 이유**: 안 보여도 조성에는 들어가야 하는 관찰이 있고, 보이되
    # 합계에서는 빠져야 하는 관찰이 있다. 한 칸으로 묶으면 둘 중 하나를 못 한다.
    #
    # **합계는 `exclude_from_totals` 만 본다 — `hide_in_list` 는 안 본다.**
    # 섞으면 보기 토글 한 번에 같은 자료가 다른 숫자를 낸다. 대신 숨긴 행이
    # 합계에 들어 있으면 화면이 그것을 적는다(안 적으면 "보이는 것의 합 ≠ 합계"
    # 가 이유 없는 어긋남으로 보인다).
    hide_in_list = models.BooleanField(default=False, db_default=False)
    exclude_from_totals = models.BooleanField(default=False, db_default=False)
    # 사람이 적는 설명. state_note 와 갈라 둔다 — 그쪽은 자동 처리가 덮어쓴다.
    description = models.TextField(blank=True, default="")
    # 배율을 사람이 못 박는다. 비어 있으면 zen_meta 가 40x 로 가정해 계산한다.
    # ZEN 이 소프트웨어에서 선택된 대물렌즈로 적어서 실제와 어긋난 적이 있다
    # (260731 이 100x 로 기록돼 µm/px 가 2.5배 작았다 — devlog 015).
    um_per_pixel_override = models.FloatField(null=True, blank=True)
    corr_thresh = models.FloatField(null=True, blank=True)
    # NAS 로 폴더가 계속 들어오면 상태 관리가 필요해진다 (P01 §1)
    state = models.CharField(max_length=12, choices=STATE, default="done")
    state_note = models.TextField(blank=True)
    discovered_at = models.DateTimeField(null=True, blank=True)
    copied_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # 마지막으로 이 행이 바뀐 때. 사람이 속성을 고쳤는지, 파이프라인이 상태를
    # 옮겼는지를 구분하지는 못한다 — "언제 마지막으로 손댔나" 만 답한다.
    # **이 칸이 생기기 전의 행은 비어 있다.** 지난 일을 지어내지 않는다.
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = "관찰"
        # 시료순(그 안이 위치순이다 — `Sample.Meta.ordering`), 그 다음 관찰
        # 번호순. **이름으로 가르지 않는다** — `(10)` 이 `(2)` 앞에 온다.
        ordering = ["sample", "obs_no", "name"]
        indexes = [models.Index(fields=["sample", "obs_no"])]

    def __str__(self):
        return self.name

    # --- 시료를 거쳐 가는 지름길 -------------------------------------------
    #
    # **화면과 질의가 이것을 자주 쓴다.** 매번 `slide.sample.locality.site` 를
    # 쓰면 `sample` 이 없는 슬라이드(소속을 잃은 관찰)에서 터진다 — 여기서 한 번만
    # 막는다. `select_related("sample__locality__site")` 를 함께 걸 것.
    @property
    def locality(self):
        return self.sample.locality if self.sample_id else None

    @property
    def site(self):
        return self.sample.locality.site if self.sample_id else None

    @property
    def depth_cm(self):
        """시료의 깊이. **시추코어 지점에만 있다.**"""
        return self.sample.depth_cm if self.sample_id else None

    @property
    def sample_kind(self) -> str:
        """지점 유형. 예전에는 이 표의 칸이었다 — 부르는 자리가 많아 남겨 둔다."""
        return self.sample.locality.kind if self.sample_id else "core"

    @property
    def obs_badge(self) -> str:
        """화면에 낼 관찰 이름표. 낼 것이 없으면 빈 문자열.

        **관찰이 하나뿐인 시료는 아무것도 안 낸다**(사용자 판단 2026-08-05) —
        검토가 끝난 347 시야가 지금 모습 그대로 남는다. 사람이 이름표를 적었다면
        `0` 이라도 낸다("원본" 이라고 적을 수 있다).
        """
        return self.obs_label or (f"#{self.obs_no}" if self.obs_no else "")

    @property
    def base_name(self) -> str:
        """관찰 접미사를 뗀 폴더 이름 — 같은 시료의 관찰들이 공유하는 것이다.

        **슬러그가 아니라 이름으로 짚는다.** 슬러그에는 촬영일이 붙어
        (`group_focus_series.slide_slug`) 같은 시료를 다른 날 올린 관찰끼리
        안 맞는다.
        """
        return _base_name(self.name)

    def sibling_observations(self):
        """같은 시료의 다른 관찰들. 번호순이다.

        **`Sample` 이 생기고부터는 조인 한 번이다.** 예전에는 시료 행이 없어서
        폴더 이름을 짐작으로 맞춰야 했다(`name__startswith` 로 좁히고 접미사를
        떼어 비교) — 이름이 규칙에 안 맞으면 그대로 못 찾았다.

        **시료가 없는 관찰은 이름으로 되짚는다.** 소속을 잃은 것을 관리 화면이
        어디에 붙일지 추천해야 하는데, 그때는 이름밖에 근거가 없다.
        """
        if self.sample_id:
            return list(self.sample.slides.exclude(pk=self.pk)
                        .order_by("obs_no", "id"))
        base = self.base_name
        if not base:
            return []
        qs = (Slide.objects.filter(name__startswith=base).exclude(pk=self.pk)
              .select_related("sample__locality__site").order_by("obs_no", "id"))
        return [s for s in qs if s.base_name == base]


class Viewpoint(models.Model):
    """시야 하나 (지금까지 "그룹" 이라 부른 것).

    Group 이라 하지 않는다 — SQL·Django 양쪽에서 뜻이 겹친다.
    """

    slide = models.ForeignKey(Slide, on_delete=models.CASCADE,
                              related_name="viewpoints")
    idx = models.IntegerField()                 # URL 의 g0
    tag = models.CharField(max_length=120)      # g000_Snap-21365-21370
    n_frames = models.IntegerField(default=0)
    span_sec = models.FloatField(null=True, blank=True)
    sharpest_frame = models.ForeignKey("Frame", null=True, blank=True,
                                       on_delete=models.SET_NULL,
                                       related_name="sharpest_of")
    grouping_run = models.ForeignKey(Run, null=True, blank=True,
                                     on_delete=models.SET_NULL,
                                     related_name="viewpoints")

    class Meta:
        ordering = ["slide", "idx"]
        constraints = [models.UniqueConstraint(fields=["slide", "idx"],
                                               name="uniq_viewpoint_idx")]

    def __str__(self):
        return f"{self.slide.slug} g{self.idx}"


class Frame(models.Model):
    """사진 한 장. 촬영 메타데이터(µm/px, 시각)는 옆의 XML 에서 읽는다."""

    SOURCE = [(s, s) for s in ("xml", "sidecar", "default", "cli")]

    slide = models.ForeignKey(Slide, on_delete=models.CASCADE,
                              related_name="frames")
    # 그룹핑 전에는 비어 있다
    viewpoint = models.ForeignKey(Viewpoint, null=True, blank=True,
                                 on_delete=models.SET_NULL,
                                 related_name="frames")
    name = models.CharField(max_length=120)     # Snap-21365
    path = models.CharField(max_length=500)
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    um_per_pixel = models.FloatField(null=True, blank=True)
    um_per_pixel_source = models.CharField(max_length=8, choices=SOURCE, blank=True)
    acquired_at = models.DateTimeField(null=True, blank=True)
    sharpness = models.FloatField(null=True, blank=True)
    is_sharpest = models.BooleanField(default=False)
    seq = models.IntegerField(default=0)        # 폴더 안 순서
    # 이 행이 DB 에 들어온 때. **촬영 시각(`acquired_at`)과 다르다** — 그쪽은
    # 사진에 딸린 XML 이 알려 주는 것이고, 이쪽은 우리 시스템이 받은 때다.
    # 반입 이력을 되짚을 때 필요하다.
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)
    # 광학계 정보는 전 사진 동일하고 지금 쓰는 곳이 없다. 칼럼 20개를 미리
    # 만들면 대부분 비므로 필요해질 때 여기 담는다.
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["slide", "seq"]
        constraints = [models.UniqueConstraint(fields=["slide", "name"],
                                               name="uniq_frame_name")]

    def __str__(self):
        return self.name


class Stack(models.Model):
    """all-in-focus 합성본. *_scale.json 과 stack_report.json 을 합친 것."""

    viewpoint = models.OneToOneField(Viewpoint, on_delete=models.CASCADE,
                                     related_name="stack")
    focused_path = models.CharField(max_length=500)
    depth_path = models.CharField(max_length=500, blank=True)
    depth_npz_path = models.CharField(max_length=500, blank=True)
    um_per_pixel = models.FloatField(null=True, blank=True)
    native_um_per_pixel = models.FloatField(null=True, blank=True)
    resize_scale = models.FloatField(default=1.0)
    um_per_pixel_source = models.CharField(max_length=8, blank=True)
    ref_frame = models.ForeignKey(Frame, null=True, blank=True,
                                  on_delete=models.SET_NULL,
                                  related_name="ref_of")
    align_failed = models.IntegerField(default=0)
    object_px_frac = models.FloatField(null=True, blank=True)
    sharpness_best_single = models.FloatField(null=True, blank=True)
    sharpness_fused = models.FloatField(null=True, blank=True)
    gain = models.FloatField(null=True, blank=True)
    run = models.ForeignKey(Run, null=True, blank=True,
                            on_delete=models.SET_NULL, related_name="stacks")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.focused_path


class Image(models.Model):
    """**검출을 돌릴 수 있는 이미지 한 장.** (P06 2단계, 2026-08-05)

    ## 왜 만드는가

    `시야 1:N 프레임 1:N 검출` 이 이 스키마에서 성립하지 않았다 — **합성본은
    프레임이 아니기 때문이다.** 검출이 도는 이미지가 `Stack.focused_path` 아니면
    `Frame.path` 라 테이블이 둘이고, 그래서 `Detection` 이 `target`(`stack|frame`)
    + nullable `frame` 으로 **다형 연관을 흉내 내고** 있었다.

    그 흉내가 실제로 값을 치렀다. `ObjectReview` 의 열쇠가 `(viewpoint, mask_key)`
    인데 이것은 **시야마다 볼 이미지가 한 장**일 때만 성립한다. YOLO 처럼 프레임
    마다 검출을 내면 깨진다 — 실측으로 시야 452개 중 203개(45%)에서 프레임끼리
    `mask_key` 가 겹친다. 고치려고 `(viewpoint, frame, mask_key)` 로 가면 합성본의
    `frame` 이 NULL 이라 **유일 제약이 82%에 대해 조용히 작동을 멈춘다**(NULL 은
    서로 다른 값으로 친다).

    이 테이블이 생기면 그 문제가 **사라진다.** `(image, mask_key)` 하나면 되고,
    판별자 문자열도 `__stack__` 센티널도 NULL 규칙도 필요 없다.

    ## 열쇠는 `path` 다

    `DATA_ROOT` 기준 상대경로이고 **파일 하나에 행 하나**다. 실측으로 프레임
    1,318 · 합성본 317 · 깊이맵 317 = 1,952개가 전부 겹치지 않는다. 자연 열쇠가
    있는데 대리 열쇠를 만들 이유가 없고, `viewpoint` 를 넣으면 그룹핑 전 프레임
    (viewpoint 가 비어 있다)에서 다시 NULL 문제가 생긴다.

    ## 무엇을 담지 않는가

    **촬영·합성 메타는 그대로 `Frame`·`Stack` 에 둔다.** 이 테이블은 정체(identity)만
    맡는다 — `Frame` 은 선명도·촬영시각·`seq`, `Stack` 은 정렬 실패·품질 지표처럼
    **합성 실행의 산물**을 들고 있고, 그것들은 이미지가 아니라 그 이미지를 만든
    일에 대한 기록이다.

    ## `kind="depth"` 는 검출이 붙지 않는다

    깊이맵은 Z 좌표가 없는 상대값이라 볼 것은 되지만 검출 대상이 아니다(실측으로
    검출 0건). 지금까지는 **관행으로만** 그랬는데, 이제 종류가 스키마에 적힌다.

    ## 지금은 아무도 안 쓴다

    P06 은 넓히고(2) → 채우고(3) → 파이프라인을 옮기고(4) → 조인다(5). 지금은
    2단계라 이 테이블이 서 있기만 하고 `Detection.image`·`ObjectReview.image` 는
    **nullable** 이다 — 옛 파이프라인 이미지의 INSERT 가 죽으면 안 되기 때문이다
    (뷰어와 파이프라인은 판이 따로 돈다).
    """

    KIND = [("stack", "합성본"), ("frame", "프레임"), ("depth", "깊이맵")]

    # 그룹핑 전 프레임은 시야가 없다 — `Frame.viewpoint` 와 같은 사정이고
    # `SET_NULL` 인 것도 같은 이유다.
    #
    # **`CASCADE` 로 두면 안 된다.** 시야 가르기(`regroup.apply_split`)는 시야를
    # 지우고 다시 만드는데 **프레임은 살아남는다** — 그 사이에 이미지 행이 같이
    # 죽으면 디스크에 파일이 그대로 있는데 테이블에서만 사라진다.
    # **이 테이블은 디스크의 파일을 비추는 것**이고, 시야는 그 파일에 붙는 이름표다.
    viewpoint = models.ForeignKey(Viewpoint, null=True, blank=True,
                                  on_delete=models.SET_NULL,
                                  related_name="images")
    kind = models.CharField(max_length=8, choices=KIND)
    path = models.CharField(max_length=500, unique=True)
    # 어디서 왔는가. **둘의 `on_delete` 가 다르다 — 성격이 다르기 때문이다.**
    #
    # **프레임은 원본 사진이다.** 시야를 갈라도 그 자리에 그대로 있고 다른 시야로
    # 묶일 뿐이다 — 그래서 `SET_NULL` 이고 이미지 행도 살아남는다.
    #
    # **합성본·깊이맵은 그 묶음에서 나온 것이다.** 묶음이 갈리면 무효다 — 서로
    # 다른 시야가 된 프레임들을 합쳐 놓은 그림이라 아무것도 아닌 것이 된다.
    # 그래서 `CASCADE` 로 `Stack` 과 함께 죽는다. 다시 합성하면 새로 생긴다.
    frame = models.OneToOneField(Frame, null=True, blank=True,
                                 on_delete=models.SET_NULL,
                                 related_name="image")
    stack = models.ForeignKey(Stack, null=True, blank=True,
                              on_delete=models.CASCADE,
                              related_name="images")
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["viewpoint", "kind", "path"]
        indexes = [models.Index(fields=["viewpoint", "kind"])]

    def __str__(self):
        return f"{self.kind}:{self.path}"


class ThresholdSet(models.Model):
    """판정 문턱. 지금은 11개 값이 결과 JSON 마다 복사돼 있다.

    테이블로 두면 이름을 붙여 비교할 수 있다 — "1500 vs 2000 을 같은 시야에 걸고
    개수를 나란히" 가 가능해진다.
    """

    name = models.CharField(max_length=120, blank=True)
    min_um = models.FloatField(default=10.0)
    max_um = models.FloatField(default=150.0)
    texture_min = models.FloatField(default=1000.0)
    round_max_elong = models.FloatField(default=1.4)
    round_min_iou = models.FloatField(default=0.85)
    round_min_solidity = models.FloatField(default=0.92)
    # 원형은 areolae 를 더 무겁게 본다 — 형태로는 밋밋한 원반을 가려낼 수 없다
    round_texture_min = models.FloatField(default=1500.0)
    rod_min_elong = models.FloatField(default=2.0)
    rod_max_elong = models.FloatField(default=20.0)
    rod_min_iou = models.FloatField(default=0.72)
    rod_min_solidity = models.FloatField(default=0.85)
    is_default = models.BooleanField(default=False)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    FIELDS = ("min_um", "max_um", "texture_min",
              "round_max_elong", "round_min_iou", "round_min_solidity",
              "round_texture_min",
              "rod_min_elong", "rod_max_elong", "rod_min_iou", "rod_min_solidity")

    def as_dict(self):
        return {f: getattr(self, f) for f in self.FIELDS}

    def __str__(self):
        return self.name or f"문턱 #{self.pk}"


class ClassDef(models.Model):
    """분류 정의. 지금 data.py 의 CLASS_LABELS + CSS 에 흩어진 색.

    테이블로 두면 분류를 더할 때 배포가 필요 없다 — Eucampia 를 넣은 것이 코드
    수정이었는데, 속은 계속 늘어난다.

    **분류를 더할 때 채울 것.** 하나라도 비면 예외는 안 나고 그 분류만 화면에서
    조용히 다르게 굴러간다 — Chaetoceros 를 넣으며 실제로 겪은 것들이다(038·040):

        label       전체 이름
        short       약칭. 자리가 좁은 곳에서 쓴다. 비면 label 을 쓴다
        badge       배지 CSS 클래스. `base.html` 에 `.badge.<badge>` 규칙이 있어야 한다
        color       "R,G,B". **`base.html` 의 CSS 도 함께 고쳐야 한다** — 색은
                    아직 테이블에서 뿜어내지 않는다. 비면 마스크가 투명해진다
        hotkey      검토 화면 단축키. 비면 그 분류만 메뉴로만 지정된다
        counted     개체 수로 세는가 (파편은 False)
        is_taxon    형태가 아니라 분류학으로 알아본 것인가 (메뉴에서 줄로 갈린다)
        sort_order  열·메뉴·단축키 순환의 차례

    `check_db.py` 의 "4. 분류" 가 hotkey·color 가 빈 것을 잡는다.
    """

    key = models.CharField(max_length=32, unique=True)
    label = models.CharField(max_length=64)
    # 자리가 좁은 곳에서 쓰는 약칭. 비어 있으면 `label` 을 그대로 쓴다.
    # 속명은 길다 — `Chaetoceros` 하나가 목록 표의 열 하나를 두 배로 넓힌다.
    # **뜻이 달라지는 자리에는 쓰지 않는다**: 분류를 고르는 메뉴는 전체 이름이다.
    short = models.CharField(max_length=16, blank=True)
    badge = models.CharField(max_length=16, blank=True)
    color = models.CharField(max_length=24, blank=True)   # "255,110,190"
    # 형태 칸과 분류학 칸은 성격이 다르다 — 메뉴에서 줄을 그어 나눈다
    is_taxon = models.BooleanField(default=False)
    # 개체 수로 세는가. 파편은 개체가 아니다 — 깨진 조각 하나를 규조 한 개로
    # 세면 밀도가 부풀고, 그 숫자가 보고서에 실린다. 목록의 "검출" 칸은 이것이
    # 참인 분류만 더한 값이다(미분류는 분류 자체가 없어 애초에 빠진다).
    # 기본값이 True 인 것은 새 속을 넣으면 세는 것이 보통이기 때문이다.
    counted = models.BooleanField(default=True)
    # 검토 화면의 단축키. **분류를 더할 때 여기도 채운다** — 안 채우면 그 분류만
    # 메뉴로만 지정할 수 있어, 시야 하나를 훑는 속도가 분류마다 달라진다.
    # 같은 키를 나눠 가지면 순환한다: q → 원형 → 원형 파편 → 원형 …
    # 순환 차례는 `sort_order` 다. 화살표·Ctrl+Z·Esc 는 이미 쓰고 있으니 피한다.
    hotkey = models.CharField(max_length=8, blank=True)
    sort_order = models.IntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "key"]

    def __str__(self):
        return self.label


class Setting(models.Model):
    """그 밖의 설정. 경로처럼 배포마다 다른 값은 여기 두지 않는다(환경변수)."""

    key = models.CharField(max_length=64, unique=True)
    value = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.key


class DetectionQuerySet(models.QuerySet):

    def reviewing(self):
        """**뷰어가 보여줄 검출** (P10). 검토 대상 묶음의, 그 묶음 안 최신 것.

        `is_current=True` 를 코드 여기저기에 적지 않고 여기 하나로 모은다.
        예전에는 12개 파일에 흩어져 있었고, **뜻이 바뀌는데 자리가 흩어져 있으면
        전부 틀린다 — 그런데 예외가 안 난다.**

        **묻는 것이 둘로 갈린다.** 이 메서드를 쓸 자리와 아닌 자리가 있다:

        | 무엇을 묻는가 | 무엇을 쓰는가 |
        |---|---|
        | 뷰어가 보여줄 검출 (화면·집계·문턱) | **`reviewing()`** |
        | 이 묶음 안의 최신 (파이프라인·prune·rebind) | `is_current` 그대로 |

        뒤엣것까지 바꾸면 파이프라인이 **검토 대상이 아닌 묶음에 쌓을 때** 자기
        검출을 못 찾는다.
        """
        return self.filter(is_current=True, run__batch__for_review=True)


class Detection(models.Model):
    """이미지 한 장에 대한 검출 실행.

    재실행마다 새 행을 쌓는다 — 덮어쓰면 엔진 교체 전후를 비교할 수 없다.

    **뷰어가 보는 것은 `Detection.objects.reviewing()` 이다** (P10) —
    `is_current` 하나가 아니라 **묶음의 `for_review` 와 함께 봐야** 한다.
    `is_current` 는
    "그 묶음 **안에서** 최신" 이라는 좁은 뜻이고, 어느 묶음을 볼지는
    `RunBatch.for_review` 가 정한다.
    """

    objects = DetectionQuerySet.as_manager()

    viewpoint = models.ForeignKey(Viewpoint, on_delete=models.CASCADE,
                                 related_name="detections")
    # **어느 이미지에 대한 검출인가.** 예전에는 `target`(`stack|frame`) +
    # nullable `frame` 으로 다형 연관을 흉내 냈다 — 합성본이 `Frame` 이 아니라
    # 테이블이 둘이었기 때문이다. `Image` 가 그것을 없앴다 (P06 5a).
    # 무엇에 붙은 검출인가는 `image.kind` 가, 어느 프레임인가는 `image.frame`
    # 이 말한다.
    image = models.ForeignKey("Image", on_delete=models.CASCADE,
                              related_name="detections")
    image_path = models.CharField(max_length=500)
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    scale = models.FloatField(default=1.0)
    um_per_pixel = models.FloatField(null=True, blank=True)
    um_per_pixel_native = models.FloatField(null=True, blank=True)
    um_per_pixel_source = models.CharField(max_length=8, blank=True)
    um_per_pixel_backfilled = models.BooleanField(default=False)
    n_raw_masks = models.IntegerField(default=0)
    n_sized = models.IntegerField(default=0)
    thresholds = models.ForeignKey(ThresholdSet, null=True, blank=True,
                                   on_delete=models.SET_NULL,
                                   related_name="detections")
    run = models.ForeignKey(Run, null=True, blank=True,
                            on_delete=models.SET_NULL, related_name="detections")
    is_current = models.BooleanField(default=True)
    superseded_by = models.ForeignKey("self", null=True, blank=True,
                                      on_delete=models.SET_NULL,
                                      related_name="supersedes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["viewpoint", "is_current"])]

    @property
    def batch(self):
        """이 검출이 속한 묶음. **교정의 열쇠에 들어간다** (P09 5.1).

        `run` 도 `Run.batch` 도 없을 수 있어 `None` 이 나온다 — 묶음에 안 든
        `detect` 실행이 70개 있고 전부 검출을 하나도 안 남긴 것들이다. 그런
        검출에 교정이 앉으면 batch 없는 교정이 되므로 `check_db.py` 가 센다.

        조인이 둘 걸린다 — 여럿을 돌 때는 `select_related("run__batch")`.
        """
        return self.run.batch if self.run_id else None

    def __str__(self):
        return f"{self.image_path} ({'현재' if self.is_current else '이전'})"


class Candidate(models.Model):
    """개체 하나. 통과분·탈락분을 한 테이블에 담고 `passed` 로 가른다.

    문턱을 바꾸면 개체가 무리를 옮겨 다니므로(지금은 두 배열 사이로 옮기느라
    파일을 다시 쓴다) `passed` 칼럼 하나면 refilter 가 UPDATE 한 번이다.
    """

    detection = models.ForeignKey(Detection, on_delete=models.CASCADE,
                                  related_name="candidates")
    # bbox 로 만든 키. 교정 기록이 이것으로 붙는다.
    mask_key = models.CharField(max_length=64)
    # SAM 이 낸 원시 마스크의 순번. 판정으로 재부여되는 표시용 id 와 다르다 —
    # 이것이 있어야 out/*.json 을 그대로 재현할 수 있다(내보내기).
    raw_id = models.IntegerField(null=True, blank=True)

    bbox_x = models.IntegerField()
    bbox_y = models.IntegerField()
    bbox_w = models.IntegerField()
    bbox_h = models.IntegerField()
    center_x = models.IntegerField(null=True, blank=True)
    center_y = models.IntegerField(null=True, blank=True)
    area_px = models.IntegerField(default=0)
    area_um2 = models.FloatField(null=True, blank=True)
    major_um = models.FloatField(null=True, blank=True)
    minor_um = models.FloatField(null=True, blank=True)
    long_side_um = models.FloatField(null=True, blank=True)
    short_side_um = models.FloatField(null=True, blank=True)
    aspect_ratio = models.FloatField(null=True, blank=True)
    fill_ratio = models.FloatField(null=True, blank=True)

    shape_ok = models.BooleanField(default=False)
    circularity = models.FloatField(null=True, blank=True)
    convexity = models.FloatField(null=True, blank=True)
    solidity = models.FloatField(null=True, blank=True)
    elongation = models.FloatField(null=True, blank=True)
    ellipse_iou = models.FloatField(null=True, blank=True)

    texture = models.FloatField(null=True, blank=True)
    predicted_iou = models.FloatField(null=True, blank=True)
    stability_score = models.FloatField(null=True, blank=True)

    # [x0,y0,x1,y1,...] 평탄 배열. 용량의 대부분이지만 마스크를 그리는 근거다.
    # rle 은 지금도 항상 null 이라 옮기지 않는다.
    polygon = models.JSONField(default=list, blank=True)

    passed = models.BooleanField(default=False)
    cls = models.CharField(max_length=32, blank=True)
    reject = models.CharField(max_length=64, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["detection", "mask_key"],
                                               name="uniq_candidate_key")]
        indexes = [
            models.Index(fields=["detection", "passed"]),
            models.Index(fields=["cls"]),
            models.Index(fields=["major_um"]),
            models.Index(fields=["texture"]),
        ]

    @property
    def bbox_xywh(self):
        return [self.bbox_x, self.bbox_y, self.bbox_w, self.bbox_h]

    def __str__(self):
        return f"{self.mask_key} ({self.cls or '미분류'})"


class ViewpointReview(models.Model):
    """시야 단위 교정 상태. review/*.json 의 done·note.

    ## 완료는 묶음마다, 코멘트는 시야마다다 (073)

    `ObjectReview` 와 같은 가름이다(P09 5.2) — **무엇에 대한 판단인가**로 나눈다.

    | 칸 | 무엇에 대한 판단인가 | 속하는 곳 |
    |---|---|---|
    | `done` | 이 묶음이 낸 검출을 여기서 다 봤다 | **batch** |
    | `note` | 이 시야가 이러이러하다 | 시야 — batch 를 갈아도 참이다 |

    `done` 을 시야에 매달아 두었더니 `sam2-전수` 를 검토하고 붙인 완료 표시가
    `yolo-3차` 로 갈아탄 화면에도 그대로 붙어 있었다 — **아직 아무도 안 본
    검출이 "검토 완료" 로 보인다.** 그 시야는 다시 열리지 않는다("다음 미검토"
    가 건너뛴다).

    **`batch` 가 `NULL` 인 행이 시야 코멘트를 든다.** 사람이 쓴 글이라
    재생성 불가이고, 행 전체를 묶음에 매달면 묶음을 갈 때마다 사라진다.
    `ObjectReview` 에서 사람이 그린 개체를 `batch=NULL` 로 두는 것과 같은 자리다.
    """

    viewpoint = models.ForeignKey(Viewpoint, on_delete=models.CASCADE,
                                  related_name="reviews")
    # `PROTECT` — 묶음을 지우면 그 회차의 검토 기록이 통째로 날아간다
    batch = models.ForeignKey("RunBatch", null=True, blank=True,
                              on_delete=models.PROTECT,
                              related_name="viewpoint_reviews")
    # 고칠 것이 없어 교정이 비어도 검토는 끝났을 수 있다 — 따로 남긴다
    done = models.BooleanField(default=False)
    note = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["viewpoint", "batch"],
                condition=models.Q(batch__isnull=False),
                name="uniq_vpreview_batch"),
            # **NULL 끼리는 안 부딪힌다** — 시야 코멘트 행이 여럿 서는 것을
            # 막으려면 조건을 뒤집은 제약이 따로 있어야 한다 (P09 0단계와 같다)
            models.UniqueConstraint(
                fields=["viewpoint"],
                condition=models.Q(batch__isnull=True),
                name="uniq_vpreview_note"),
        ]

    def __str__(self):
        if self.batch_id is None:
            return f"{self.viewpoint} 코멘트"
        return f"{self.viewpoint} [{self.batch}] {'완료' if self.done else '미완'}"


class ObjectReview(models.Model):
    """개체 단위 교정. **재생성 불가한 자료다.**

    `candidate` 는 바인딩 결과일 뿐이고 진짜 키는 **`(image, batch, mask_key)`**
    다. `geom` 에 기하를 스스로 들고 있어 검출기가 바뀌어도 읽을 수 있다 —
    지운 것까지 전부 저장한다(학습의 어려운 음성 표본이다).

    **회차가 돌면 이 표가 사실상 정답 자료 표가 된다** (P09 1). 이름이 뜻보다
    좁아진 것이지 구조가 틀린 것은 아니다.

    ## 무엇이 무엇에 속하는가 (P09 5.2)

    | 칸 | 무엇에 대한 판단인가 | 속하는 곳 |
    |---|---|---|
    | `removed`·`accepted` | 그 batch 가 낸 그 마스크가 틀렸다/맞다 | **batch** |
    | `label`·`note` | 이 규조각이 Eucampia 다 | 개체 — batch 를 갈아도 참이다 |
    | 사람이 그린 마스크 | 여기 규조각이 있다 | 이미지 — **어느 batch 에도 없다** |

    그래서 batch 를 갈 때 `removed`·`accepted` 는 안 따라가고 `label`·`note` 는
    IoU 로 물려주되 **사람이 확인한다.** 옮기는 것을 안 가리고 통째로 잠그면
    막아야 할 것과 살려야 할 것을 함께 막는다.
    """

    BIND = [(b, b) for b in ("exact", "iou", "manual", "orphan")]
    SOURCE = [(s, s) for s in ("engine", "manual")]

    # **편의용으로 남는다.** 진짜 열쇠는 `(image, mask_key)` 다 — 화면·목록이
    # 시야로 묶어 보는 일이 많아 조인을 줄이려고 둔다. `image.viewpoint` 와
    # 어긋나면 안 되고, `backfill_images.py --verify` 가 그것을 본다.
    viewpoint = models.ForeignKey(Viewpoint, on_delete=models.CASCADE,
                                 related_name="object_reviews")
    # **어느 이미지를 보고 한 판단인가** (P06 5a). 예전 열쇠 `(viewpoint,
    # mask_key)` 는 **시야마다 볼 이미지가 한 장**일 때만 성립했다 — 프레임별
    # 검출을 검토하면 깨진다(실측으로 시야의 45%에서 `mask_key` 가 프레임끼리
    # 겹친다).
    #
    # `CASCADE` 다. 이미지가 지워지는 길은 **시야가 지워질 때**뿐이고
    # (`Image.stack` 은 CASCADE, `Image.viewpoint` 는 SET_NULL), 그때 교정은
    # `viewpoint` 를 타고도 어차피 지워진다 — 새로 생기는 삭제 길이 아니다.
    image = models.ForeignKey("Image", on_delete=models.CASCADE,
                              related_name="object_reviews")
    # **어느 검출을 보고 한 판단인가** (P09 5.1). 열쇠에 들어간다.
    #
    # 없이 두면 엔진을 갈 때 옛 판단이 새 검출에 IoU 로 옮겨 붙는다 — 실측으로
    # SAM2 → YOLO 에서 **`removed` 1,076건이 YOLO 의 통과 후보에 얹혔다**.
    # 사람은 자기가 지우지 않은 것이 지워져 있는 것을 보게 된다.
    #
    # **`Candidate` 에 매는 것과 다르다.** `Candidate` 는 회차마다 새로 생기고
    # 옛 것은 뒤로 밀리지만, `RunBatch` 는 검출을 쌓아 두므로 **지나가면 안
    # 바뀌는 사건의 이름**이다 — "교정을 재생성 가능한 것에 매지 않는다" 는
    # 규칙을 어기지 않는다.
    #
    # **`NULL` 은 사람이 그린 개체다.** 엔진에 대한 판단이 아니라 이미지에 대한
    # 사실이라 어느 batch 에도 속하지 않는다 — 그래서 batch 를 갈아도 안 사라진다.
    # `PROTECT` 인 것은 batch 를 지우면 그 회차의 교정이 통째로 날아가서다.
    batch = models.ForeignKey("RunBatch", null=True, blank=True,
                              on_delete=models.PROTECT,
                              related_name="object_reviews")
    mask_key = models.CharField(max_length=64)
    candidate = models.ForeignKey(Candidate, null=True, blank=True,
                                  on_delete=models.SET_NULL,
                                  related_name="reviews")
    bind_method = models.CharField(max_length=8, choices=BIND, default="orphan")
    bind_score = models.FloatField(null=True, blank=True)
    # {"bbox": [x,y,w,h], "polygon": [...]}
    geom = models.JSONField(default=dict, blank=True)

    # 사람이 그린 개체인가 (P09 5.2). `batch is None` 에서 파생시킬 수도 있지만
    # 두 칸을 따로 두어 **검사가 둘을 대조할 수 있게** 한다 — 한쪽만 맞는 행은
    # 어딘가에서 잘못 만든 것이다 (`check_db.py` 8번).
    #
    # **`db_default` 를 함께 준다.** `rebind` 가 파이프라인 컨테이너에서 이 표를
    # 쓰는데 뷰어와 파이프라인은 판이 다르다 — Django 의 `default` 는 파이썬
    # 쪽이라 옛 판의 INSERT 에는 칼럼이 아예 안 들어간다 (HANDOFF 3.7).
    source = models.CharField(max_length=8, choices=SOURCE, default="engine",
                              db_default="engine")
    # 엔진이 낸 기하를 사람이 고쳤다 (P09 5.7). **회차별 수렴 지표가 된다** —
    # "사람이 손댄 비율" 이 줄면 그것이 수렴이다. 기하만 조용히 덮어쓰면 다음
    # 회차에 엔진이 얼마나 나아졌는지를 못 잰다.
    geom_edited = models.BooleanField(default=False, db_default=False)

    # 둘을 한 칼럼으로 합치지 않는다 — 되살렸다가 다시 지운 개체가 있고,
    # "사람이 지웠다가 이긴다" 는 규칙이 두 값의 조합으로 표현된다.
    removed = models.BooleanField(default=False)
    accepted = models.BooleanField(default=False)
    label = models.CharField(max_length=32, blank=True)
    note = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # **batch 가 열쇠에 들어간다** (P09 5.1). 같은 이미지의 같은 마스크라도
            # 어느 검출을 보고 한 판단인지가 다르면 다른 행이다.
            models.UniqueConstraint(
                fields=["image", "batch", "mask_key"],
                condition=models.Q(batch__isnull=False),
                name="uniq_objreview_key"),
            # **사람이 그린 것은 `batch` 가 NULL 이라 위 제약이 안 잡는다** —
            # SQLite 는 NULL 끼리 부딪히지 않는다고 보므로 같은 키가 여럿 설 수
            # 있다. 조건을 뒤집은 부분 제약을 따로 둔다.
            models.UniqueConstraint(
                fields=["image", "mask_key"],
                condition=models.Q(batch__isnull=True),
                name="uniq_objreview_manual"),
        ]
        indexes = [
            models.Index(fields=["viewpoint", "bind_method"]),
            models.Index(fields=["bind_method"]),
            # 삭제 범위와 화면 조회가 전부 이 짝으로 짚는다 (P09 5.1)
            models.Index(fields=["image", "batch"]),
            models.Index(fields=["source"]),
        ]

    def __str__(self):
        marks = [n for n, v in (("삭제", self.removed), ("복구", self.accepted),
                                ("분류", self.label), ("메모", self.note)) if v]
        return f"{self.mask_key} {'·'.join(marks) or '-'}"
