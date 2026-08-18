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
    # **카탈로그 번호의 꼬리** (`catalog.py`). `RS23-GC03-071-g03-…-S1` 의 `S1`.
    #
    # **라벨에서 자동으로 뽑지 않는다.** `yolo-3차`·`yolo-4차` 가 같은 글자로
    # 누우면 **두 회차의 번호가 겹치고**, 그 번호는 이미 논문·표에 적힌 뒤다.
    # 관리 화면이 빈 칸에 첫 제안(`catalog.batch_code_seed`)만 채워 주고 정하는
    # 것은 사람이다. 라벨을 고쳐도 번호가 안 움직이는 것도 갈라 둔 덕이다.
    #
    # 비어 있으면 그 묶음의 개체는 **번호가 없다** — 화면이 그것을 적는다.
    # 조용히 `M`(손그림) 이나 라벨로 대신하면 엔진이 낸 것이 다른 것으로 기록된다.
    code = models.CharField(max_length=8, blank=True, default="", db_default="")
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
            # **묶음 코드가 겹치면 두 회차의 카탈로그 번호가 겹친다.** 빈 것은
            # 여럿일 수 있다 — 아직 안 정한 묶음이고, 그때는 번호가 아예 안 난다.
            models.UniqueConstraint(fields=["code"], condition=~models.Q(code=""),
                                    name="uniq_batch_code"),
            # **`M` 은 손그림 자리다** (`catalog.MANUAL_CODE`). 묶음이 그것을
            # 가져가면 사람이 그린 개체와 그 묶음의 개체가 한 번호 아래 섞인다.
            models.CheckConstraint(condition=~models.Q(code__in=["M", "m"]),
                                   name="batch_code_not_manual"),
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
    있다. 시추코어는 깊이로, 노두는 단면상의 위치로 잡힌다(`Sample`).
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
    """개체 단위 교정 — **그 판에서 그 마스크를 어떻게 봤는가.** 재생성 불가한 자료다.

    `candidate` 는 바인딩 결과일 뿐이고 진짜 키는 **`(image, batch, mask_key)`**
    다. `geom` 에 기하를 스스로 들고 있어 검출기가 바뀌어도 읽을 수 있다 —
    지운 것까지 전부 저장한다(학습의 어려운 음성 표본이다).

    **회차가 돌면 이 표가 사실상 정답 자료 표가 된다** (P09 1).

    ## 이름이 빗나가 있다 — 알고 두는 것이다

    **뜻으로는 `MaskJudgement` 다.** 남은 칸이 전부 *사람이 그 마스크에 대해 한
    일*이기 때문이다 — 지움·되살림·확인·코멘트·기하 수정·손그림·대표 고르기.
    "이것이 무엇인가"(분류·종명)는 P12 에서 `DiatomObject` 로 나갔다.

    P12 전에는 이 표가 판정과 동정을 겸해서 이름이 *좁을* 뿐이었는데, 지금은
    *빗나간* 상태다. **그래도 안 바꾼다** — 재생성 불가 7,914행을 개명
    마이그레이션에 태우는 것이 이 저장소에서 가장 비싼 위험이고(`Core`→`Locality`
    때 Django 가 **옛 표를 지우고 새 빈 표를 만드는 순서**를 냈다, 063), 이름은
    그만한 값이 아니다.

    ## 무엇이 무엇에 속하는가 (P09 5.2 · P12 에서 자리를 갈랐다)

    | 칸 | 무엇에 대한 판단인가 | 사는 곳 |
    |---|---|---|
    | `removed`·`accepted`·`geom` | 그 batch 가 낸 그 마스크가 틀렸다/맞다 | **여기** |
    | `note` | 이 판에서는 초점이 안 맞는다 | **여기** — 판마다 따로 적는다 |
    | `label`·`species` | 이 규조각이 Eucampia 다 | **`DiatomObject`** |
    | 사람이 그린 마스크 | 여기 규조각이 있다 | 이미지 — **어느 batch 에도 없다** |

    **분류·종명은 여기 없다.** 개체의 성질이지 판의 성질이 아니라서 `DiatomObject`
    로 올렸다 — 그래서 묶인 판들 사이에 어긋날 수가 없고, 104 가 저장할 때마다
    번지게 하던 코드(`_spread_link_labels`)와 그것을 지키던 검사가 사라졌다.
    **진실이 하나면 전파할 것이 없다.**
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

    # **이 판정이 가리키는 개체** (P12). 여러 프레임에 걸쳐 잡힌 같은 규조각이
    # 이 FK 로 하나가 된다 — 예전의 `ObjectLink` + `ObjectLinkMember` 가 하던
    # 일인데, 그때는 **묶은 것에만** 있어서 분류·종명의 집이 둘이 됐다.
    #
    # **비어 있지 않다.** 판정 행이 생기는 순간 개체도 함께 생긴다(대개 1:1 이고,
    # 사람이 묶으면 N:1 이 된다). 조건부로 두면 읽는 자리 79곳이 전부 "개체가
    # 없으면 빈 값" 갈래를 타야 하고, 안 고친 자리는 예외 없이 조용히 다르게
    # 굴러간다(038·040 의 모양).
    #
    # **지운 마스크도 개체를 갖는다.** "규조각이 아니다" 라고 판정한 것에 개체가
    # 서는 것이 어색해 보이지만, 뗐다가는 **지웠다 되살리는 사이에 묶음이
    # 깨진다** — 102 가 만든 "탈락 후보를 되살려 묶는다" 흐름과 정면으로
    # 부딪힌다. 지워진 판정이 여럿인 묶음에 남아 있는 것은 저장 쪽이 막고
    # `check_db.py` 8번이 센다.
    #
    # `CASCADE` 다 — 개체를 지우는 길은 판정을 전부 걷어낼 때뿐이고, 그때 남은
    # 판정 행은 뜻이 없다.
    diatom_object = models.ForeignKey("DiatomObject", on_delete=models.CASCADE,
                                      related_name="members")
    # 이 개체의 얼굴 — 학습 자료로 뽑을 때, 목록에 보일 때 이 판을 쓴다.
    # 개체마다 정확히 하나(0 은 저장 쪽이 막는다. DB 제약은 "둘 이상" 만 막는다).
    is_rep = models.BooleanField(default=False, db_default=False)

    # 둘을 한 칼럼으로 합치지 않는다 — 되살렸다가 다시 지운 개체가 있고,
    # "사람이 지웠다가 이긴다" 는 규칙이 두 값의 조합으로 표현된다.
    removed = models.BooleanField(default=False)
    accepted = models.BooleanField(default=False)
    # **검토 완료가 자동으로 붙이는 확인** (2026-08-11). "이 마스크는 규조각이
    # 맞다" 를 사람이 확인한 것인데, **마스크마다 누른 것이 아니라 완료 한 번이
    # 남은 것 전부에 퍼진 것**이다 — 이름이 그 사실을 말한다.
    #
    # 그래서 **`label`·`species` 와 무게가 다르다.** 저것들은 재생성 불가지만
    # 이것은 `완료 표시 AND 남는다` 로 다시 계산할 수 있다. 그래도 저장하는
    # 것은 **사람이 그때 본 것을 얼려 두기 위해서다** — `refilter` 로 문턱을
    # 바꾸면 "남는다" 의 뜻이 달라진다.
    #
    # **학습에서 손그림과 같은 무게로 쓰면 안 된다.** 사람이 그린 마스크는
    # "여기 규조각이 있다" 를 손으로 말한 것이고 이것은 "안 지웠다" 에 가깝다.
    #
    # `data.confirm_kept` 가 적는다.
    #
    # **`accepted` 와 축이 다르다.** 저쪽은 *엔진이 떨어뜨린 것을 사람이 되살린*
    # 사건이고 이쪽은 *엔진이 통과시킨 것을 사람이 확인한* 사건이다. 하나로
    # 뭉치면 화면의 "복구 N" 이 통과분 수백 개로 부풀고, 무엇보다 **"엔진이
    # 놓친 것 몇 건" 을 다시 못 센다** — 회차 성적을 읽는 근거가 그것이다.
    #
    # **화면은 이 칸을 모른다.** `/review` payload 에 없으므로 `save_review` 의
    # 청소가 지우지 않도록 `keys` 에 얹는다 — 종명·`geom_edited` 와 같은 갈래다.
    auto_confirmed = models.BooleanField(default=False, db_default=False)
    # **코멘트도 `DiatomObject` 로 갔다** (0036, 2026-08-12 사용자). 등급과 같은
    # 이야기의 나머지 반쪽이다. 여기 있던 근거는 *"이 판에서는 초점이 안
    # 맞는다" 는 판마다 다른 말이다* 였는데, **사람이 실제로 적은 것은 그
    # 규조각에 대한 말이었다** — "가장자리가 깨졌다" · "다시 봤다".
    #
    # 그리고 번지기(106)가 그 전제를 깼다: 한 번 그린 규조각이 판 넷에 퍼지는데
    # 같은 말을 네 번 적게 할 이유가 없고, 판에만 두면 **어느 판에서 적었는지를
    # 사람이 기억해야** 코멘트를 다시 찾는다.
    #
    # 판마다 다른 말이 정말 필요해지면 그때는 *판의 상태*를 적는 칸을 따로
    # 세운다 — 코멘트를 겸하게 하지 않는다(한 낱말이 두 뜻을 겸하지 않게 한다).

    # **등급은 `DiatomObject` 로 갔다** (0035, 2026-08-12 사용자). 하루 만에
    # 뒤집은 자리라 근거를 남긴다 — 처음에는 *같은 규조각도 초점면마다 areolae 가
    # 보이고 안 보인다* 를 들어 판에 두었고, 그래야 **어느 판을 학습에 쓸지**
    # 고를 수 있다고 봤다. **그 일은 `is_rep`(대표)이 이미 하고 있었다.**
    # 축을 이렇게 가르면 겹치지 않는다: 등급은 *이 규조각이 얼마나 좋은
    # 표본인가*(개체), 대표는 *그중 어느 판으로 보여줄까*(판).
    #
    # 그리고 번지기(106)가 들어오면서 실무가 갈렸다 — 한 번 그린 규조각이 판
    # 넷에 퍼지는데 등급을 네 번 매기게 할 이유가 없다.
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # **한 개체는 한 이미지에서 하나다** — 같은 프레임의 마스크 둘이 같은
            # 규조각일 수 없다 (옛 `uniq_linkmember_image`).
            models.UniqueConstraint(fields=["diatom_object", "image"],
                                    name="uniq_objreview_object_image"),
            # 대표는 개체마다 하나 (옛 `uniq_linkmember_rep`)
            models.UniqueConstraint(fields=["diatom_object"],
                                    condition=models.Q(is_rep=True),
                                    name="uniq_objreview_rep"),
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
            models.Index(fields=["diatom_object"]),
        ]

    # **읽기 전용 통로다.** 분류·종명은 `DiatomObject` 에 살지만, 읽는 자리가
    # 79곳이라 전부 `o.diatom_object.label` 로 고치면 그만큼 밟을 곳이 는다.
    # 진실은 여전히 한 곳이고 여기서는 비추기만 한다.
    #
    # **쓰기는 막혀 있다** — `o.label = …` 은 `AttributeError` 다. 조용히 안
    # 먹히는 것보다 시끄럽게 죽는 편이 낫다 (setter 를 달면 어느 개체에 쓸지가
    # 애매해지고, 묶인 판들에 번지는 것을 여기가 몰래 하게 된다).
    #
    # **조인이 숨는다는 것이 값이다.** 부르는 쪽은 `select_related("diatom_object")`
    # 를 걸어야 한다 — 안 걸면 판정 수만큼 질의가 난다. 목록 화면이 그 실수로
    # 1.3초였던 적이 있다.
    @property
    def label(self) -> str:
        return self.diatom_object.label

    @property
    def species(self) -> str:
        return self.diatom_object.species

    @property
    def note(self) -> str:
        return self.diatom_object.note

    def __str__(self):
        marks = [n for n, v in (("삭제", self.removed), ("복구", self.accepted),
                                ("메모", self.note)) if v]
        return f"{self.mask_key}{' ★' if self.is_rep else ''} {'·'.join(marks) or '-'}"


class DiatomObject(models.Model):
    """규조각 하나 — **사람이 하나로 보는 대상** (P12. 옛 이름은 `ObjectLink`).

    초점면 3~5장에 같은 규조각이 서너 번 잡히는데, 그것이 하나라는 것을 이 표가
    말한다. 판정(`ObjectReview`)이 여기에 매달리고, **분류·종명은 여기 산다** —
    "이것이 Eucampia 다" 는 개체의 성질이지 어느 판에서 봤느냐의 성질이 아니다.

    ## 왜 갈랐나 (P12)

    예전에는 `ObjectReview` 가 판정과 동정을 겸하고, 묶음(`ObjectLink`)이
    **묶은 것에만** 따로 있었다. 그래서 분류의 집이 둘이 되어 104 가 저장할
    때마다 번지게 해야 했고, 규칙이 생기기 전에 붙은 판단은 소급이 안 돼
    묶음 셋 중 둘이 어긋나 있었다. 진실을 한 자리로 모아 그 계열을 닫는다.

    ## 모든 판정이 개체를 갖는다

    묶이지 않은 마스크도 개체가 하나 생긴다(1:1). "묶였나?" 를 조건으로 삼는
    순간 읽는 쪽이 두 갈래가 되고, 안 고친 자리가 옛 값을 보여준다 — P12 가
    B안을 버린 이유가 그것이다. 그래서 **묶기 = 개체 둘을 합치는 것**,
    **풀기 = 개체를 가르는 것**이 된다.

    **개체가 곧 규조각 수는 아니다.** 아무 표시 없이 통과시킨 마스크는 판정 행이
    없어 개체도 없다 — 집계는 여전히 `Candidate` 에서 나오고, 이 표는 그 위에서
    **프레임에 겹쳐 잡힌 것을 하나로 세게** 해 준다.

    **시야를 못 넘는다.** 다른 시야는 스테이지가 움직인 뒤라 "같은 자리" 라는
    근거 자체가 없다. **회차도 안 넘는다** — 한 회차의 검토 결과로 학습 자료를
    만들어 다음 회차를 돌리면 그 이전 회차는 더 볼 일이 없는 자료다(사용자 방침
    2026-08-11). 그래서 `batch` 가 여기 그대로 남아 있다.
    """

    viewpoint = models.ForeignKey(Viewpoint, on_delete=models.CASCADE,
                                  related_name="diatom_objects")
    # **어느 묶음의 검출을 보며 묶었나.** PROTECT 다 — RunBatch 를 지우려면
    # 그 검출을 보며 만든 사람의 묶음부터 지워야 한다. SET_NULL 로 조용히
    # 잃으면 "어느 검출에 대한 판단인지" 가 사라진다 (drop_batch.py 가 문이다).
    batch = models.ForeignKey(RunBatch, on_delete=models.PROTECT,
                              null=True, blank=True,
                              related_name="diatom_objects")
    # **분류** — `ClassDef` 가 정한 목록에서 고른다 (원형·봉상·Eucampia).
    # 예전에는 `ObjectReview.label` 이었고 묶음마다 번지게 해야 했다 (104).
    label = models.CharField(max_length=32, blank=True)
    # **동정 결과** — 사람이 적는 종명 (개체 카탈로그 화면). `label` 과 축이 다르다:
    # 저쪽은 목록에서 고르는 것이고 이쪽은 **자유 입력**이다. 종은 목록으로 못
    # 가둔다 — `var.`·`f.`·명명자까지 붙고, 검토 중에 이름이 바뀐다. 굳으면 그때
    # 테이블로 옮긴다.
    #
    # **재생성 불가다.** 현미경을 보며 적는 것이고 `export_review.py` 가 내보낸다.
    species = models.CharField(max_length=120, blank=True, default="",
                               db_default="")
    # **자세는 개체의 성질이다** (2026-08-11 사용자 결정). 스테이지가 안 움직이니
    # 초점을 옮겨도 누운 자세는 그대로다 — 그래서 `label`·`species` 와 같은 자리이고
    # **묶인 판들이 이 값을 나눠 갖는다.** 등급(`ObjectReview.grade`)과 축이 반대다.
    #
    # 번지게 할 코드는 없다 — 진실이 여기 하나뿐이라 P12 뒤로 그럴 것이 없다.
    # 대신 **묶을 때 값이 엇갈리면 거절한다**(108): 개체가 값을 하나만 들 수 있어
    # "그대로" 가 성립하지 않는다. 107 의 팝업이 물어야 한다.
    #
    # `label` 과 달리 목록이 짧고 안 는다 — `valve`/`girdle`/`other` 셋이고
    # 순서가 없다. 등급과 함께 적어 두면 나중에 *"C 인 것들이 자세 때문인가"* 를
    # 물을 수 있다 (대면관으로 누우면 판면의 동정키가 안 보여 B·C 가 된다).
    #
    # **완형에만 매긴다** — 등급과 같은 규칙이다.
    POSE = [("valve", "valve view"), ("girdle", "girdle view"),
            ("other", "other position")]
    pose = models.CharField(max_length=8, choices=POSE, blank=True,
                            default="", db_default="")
    # **등급 — 이 규조각이 얼마나 좋은 표본인가** (0035 로 판정에서 옮겨 왔다).
    # 우수한 개체를 골라 먼저 학습시키기 위한 것이고, 순서가 있다(A > B > C).
    # 자세와 같은 자리다 — **묶인 판들이 한 값을 함께 본다.**
    #
    # **어느 판이 잘 보이는가는 `is_rep` 가 말한다.** 처음에는 등급을 판정에
    # 두어 그것까지 겸하게 했는데, 대표가 이미 그 일을 하고 있었다(`ObjectReview`
    # 의 그 자리 주석). 두 축을 갈라 두면 *"C 인데 대표 판은 어느 것인가"* 를
    # 물을 수 있다.
    #
    # **`A` 는 종명까지 동정된 것을 뜻한다** — 다만 **매기는 사람의 기준이지
    # 시스템이 막는 규칙이 아니다**(2026-08-11 사용자). 등급을 먼저 매기고 종명은
    # 나중에 적는 것이 실제 순서라, 저장 때 거절하면 그 순서를 막는다.
    # `check_db` 도 이것은 안 센다.
    #
    # **완형에만 매긴다** — 파편(`counted=0`)은 완형을 유추할 수 있어도 확실하지
    # 않고, 무엇보다 *한 개체로 인정하는 규칙을 만족하지 못한 것*이라 우수성을
    # 물을 자리가 아니다. 화면이 칸을 감추고 **서버가 다시 검사한다**(063).
    #
    # **빈 값이 "안 매겼다" 다.** 값이 셋뿐이라 `ClassDef` 처럼 테이블로 두지
    # 않는다 (038 의 여덟 칸 + CSS 비용을 여기서 치를 이유가 없다).
    GRADE = [("A", "A — 동정키도 완형도 잘 드러난다"),
             ("B", "B — 완형이나 형태가 덜 드러난다 · 또는 상태가 나쁘나 동정키가 남았다"),
             ("C", "C — 완형도 동정키도 잘 안 드러난다")]
    grade = models.CharField(max_length=1, choices=GRADE, blank=True,
                             default="", db_default="")
    # **코멘트 — 이 규조각을 두고 사람이 적는 말** (0036 으로 판정에서 옮겨 왔다).
    # "가장자리가 깨졌다" · "다시 봐야 한다" 처럼 **개체에 대한 말**이라 분류·
    # 종명·등급·자세와 같은 자리다 — 묶인 판들이 한 값을 함께 본다.
    #
    # **재생성 불가다.** 현미경을 보며 적는 것이고 `export_review.py` 가 감사
    # 기록으로 내보낸다. 그래서 **묶을 때 엇갈려도 거절하지 않고 잇는다**
    # (`data.merge_into_object`) — 분류·종명은 값을 하나 골라야 뜻이 서지만
    # (`Eucampia` 와 `Chaetoceros` 를 이어 붙일 수는 없다) 글은 이어도 글이다.
    #
    # 예전에는 `ObjectLink.note`("묶음에 대한 메모")였고 **아무도 읽지도 쓰지도
    # 않았다** — 0032 가 자리만 옮겨 놓은 칸이다. 0036 이 그 자리를 채운다.
    # `TextField` 인 것은 화면 상한이 500자(`views.NOTE_MAX`)라 옛 200자로는
    # 잘리고, 이어 붙이면 그보다 길어질 수 있어서다.
    note = models.TextField(blank=True, default="", db_default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["viewpoint"]),
                   models.Index(fields=["viewpoint", "batch"])]

    def __str__(self):
        return f"obj#{self.pk} vp={self.viewpoint_id} ({self.members.count()})"


# `ObjectLinkMember` 는 P12 에서 `ObjectReview` 로 흡수됐다. 둘은 열쇠가 같고
# (`(image, batch, mask_key)`) `geom` 스냅샷을 각자 들고 `Candidate` 에 FK 로
# 안 매달리는 규약도 같았다 — 다른 것은 무엇을 말하느냐뿐이었고(하나는 판정,
# 하나는 소속), 그래서 한 마스크에 대해 행이 둘로 갈려 있었다.


# ─────────────────────────────────────────────────────── 도감 (P15 · 128 · 130)

# 표제어가 어느 수준까지 내려갔나. **`genus_only` 와 `unreadable` 을 가른다** —
# 앞엣것은 도감이 속까지만 동정한 것이고(`Navicula sp.`), 뒤엣것은 **이름이
# 상해서 우리가 못 읽는 것**이다(`Synedra cyclopиm` — 종소명에 키릴 и 가 섞였다).
# 한 칸에 담으면 화면이 둘을 같은 말로 하게 된다 (P15 8.4).
ATLAS_RANK = [(k, k) for k in
              ("species", "infraspecies", "genus_only", "unreadable")]


class Atlas(models.Model):
    """도감 하나. 지금 셋이고 늘어도 몇 개다 (P15 4.1).

    **원본은 `Diadiction/md/*.md` 이고 이 세 표는 사본이다** (P15 4.2).
    `tools/parse_atlas.py` 가 JSON 으로 뽑고 `ops/import_atlas.py` 가 넣는다.
    **언제든 통째로 지우고 다시 만들 수 있어야 한다** — 그래서 여기에는
    사람이 만든 것이 한 칸도 없다.

    **학명 유효성 판정은 이 표에 안 담는다** (P15 4.3). 그것은 사람이
    AlgaeBase 를 열어 내린 판단이라 재생성 불가이고, 반입이 덮으면 사라진다.
    자리가 따로다 — `Diadiction/md/name_validity_log.md` 가 원본이고 뒤에
    `TaxonName` 으로 들어온다. **한 칸이라도 이 표에 들어오는 순간
    "지우고 다시 만들어도 안전하다" 가 거짓이 된다.**
    """

    # 도감 코드. **JSON 이름·`/data3/DiaRUGA/atlas/<코드>/` 의 이미지 폴더·
    # 화면 URL 이 전부 이 값이다** (`korean`·`schmidt`·`east-antarctic`).
    key = models.CharField(max_length=32, unique=True)
    title = models.CharField(max_length=200)
    # 화면에 놓이는 짧은 이름 ("Schmidt Atlas")
    short = models.CharField(max_length=40)
    # 어느 md 에서 왔나 (`Diadiction` 아래 상대 경로)
    source = models.CharField(max_length=200, blank=True, default="", db_default="")
    # **그 md 의 해시.** 지금 행이 어느 판의 색인에서 왔는지가 이 칸에 있다 —
    # 색인이 바뀌면 값이 달라져 다시 반입할 자리가 눈에 띈다
    source_sha256 = models.CharField(max_length=64, blank=True, default="", db_default="")
    # 인용할 때 알아야 할 것 (OCR·발췌·원문 오류). **화면이 함께 말한다** (P15 9절)
    note = models.TextField(blank=True, default="", db_default="")
    sort_order = models.IntegerField(default=0, db_default=0)

    class Meta:
        ordering = ["sort_order", "key"]
        verbose_name_plural = "atlases"

    def __str__(self):
        return self.short


class AtlasEntry(models.Model):
    """도감의 항목 하나. 표제어 2,059개가 여기 온다.

    **표제어를 고치지 않는다.** 색인은 OCR 산물이라 기계가 고쳐 쓰면 인용이
    원문과 어긋난다 — `Triceratium venustun` 은 원문이 그렇게 찍혀 있다(126).
    `name` 은 색인에 적힌 그대로이고, **맞추는 데 쓸 이름은 `binomial` 이
    따로 든다**(`harvest_worms.binomial` 이 만든다 — 그 규칙은 하나뿐이다).

    **열쇠는 `(atlas, seq)` 다.** 이름은 한국 도감에서 한 번 겹치고
    (`Cocconeis placentula EHRENBERG` 가 항목번호를 달리해 둘), 항목번호는
    나머지 둘에 없다. **이 행은 언제든 지우고 다시 만드는 것이라 살아야 하는
    것을 여기에 FK 로 매달지 않는다** — 이름으로 짚는다.
    """

    atlas = models.ForeignKey(Atlas, on_delete=models.CASCADE, related_name="entries")
    # 색인 파일에서의 순서. 반입의 열쇠다
    seq = models.PositiveIntegerField()
    # 도감이 매긴 항목번호. 한국 도감만 있다 (169–680)
    item_no = models.CharField(max_length=16, blank=True, default="", db_default="")
    # **색인에 적힌 그대로.** 저자까지 붙어 있다
    name = models.CharField(max_length=200)
    # 표제어의 첫 낱말. **여기도 색인 표기 그대로다** — 속명이 잘못 펴진
    # 자리가 있는데(119) 파서는 안 고친다. `ClassDef` 와 맞추는 열쇠 층이라
    # `ops/check_db.py` 가 "안 맞는 속" 을 센다 (P15 8.2)
    genus = models.CharField(max_length=64, blank=True, default="", db_default="")
    # 맞추기용 이명법. 속은 소문자 종소명과 짝지어 정규화한다. 못 뽑으면 빈 칸
    binomial = models.CharField(max_length=120, blank=True, default="", db_default="")
    rank = models.CharField(max_length=16, choices=ATLAS_RANK,
                            default="species", db_default="species")
    # `var. ovata IWAHASHI` 처럼 종 아래 표기 (한국 도감 117건)
    infra = models.CharField(max_length=120, blank=True, default="", db_default="")
    authority = models.CharField(max_length=200, blank=True, default="", db_default="")
    # **`(속명 추정)` 표시가 있는가** (46건). **없다고 확정이 아니다** — 표시가
    # 없는데 잘못 펴진 것이 있다는 것이 119 의 요점이고, 확인된 것만 다섯 쪽이다.
    # 화면이 이 칸을 "확정" 으로 말하면 안 된다
    genus_guess = models.BooleanField(default=False, db_default=False)
    # 도감마다 다른 것. 한국 `ecology`·`distribution`·`note`·`section`,
    # 동남극 `samples[]`(그림마다 구간·깊이 cm·배율)·`original_note`·`notes[]`.
    # **칸을 도감 수만큼 늘리는 쪽은 버렸다** — 넷째 도감이 오면 또 는다 (P15 4.1)
    extra = models.JSONField(default=dict, blank=True, db_default={})
    # 색인 md 의 몇 번째 줄에서 왔나. 근거를 되짚는 자리다
    line = models.PositiveIntegerField(default=0, db_default=0)

    class Meta:
        ordering = ["atlas", "seq"]
        constraints = [models.UniqueConstraint(
            fields=["atlas", "seq"], name="atlasentry_unique_seq")]
        indexes = [models.Index(fields=["atlas", "genus"]),
                   models.Index(fields=["binomial"]),
                   models.Index(fields=["genus"])]

    def __str__(self):
        return self.name


class AtlasPlacement(models.Model):
    """그 항목이 도감의 어디에 놓여 있나. **항목당 여럿이다.**

    P15 4.1 은 이것을 `AtlasEntry` 의 칸으로 두려 했는데, 자료를 다 뽑고 보니
    **Schmidt 254건이 자리를 여럿 갖는다**(최다 11 · 동남극 13건 · 한국 0건).
    칸으로 두면 254건이 첫 자리만 남거나 JSON 으로 밀려나고, 밀려나면
    **"이 Tafel 에 무엇이 있나"·"이 쪽을 열어라" 를 질의로 못 한다.**

    **자리 표기가 도감마다 다르다** — 공통으로 뽑히는 것만 칸으로 두었다.

        한국    항목번호 · pl. · 책 p. · PDF p.
        Schmidt Tafel · fig. · Band · PDF p.N/N+1
        동남극  Plate · fig. · PDF p.N/N+1 (시료는 `AtlasEntry.extra`)

    **빈 것을 채우지 않는다** (P15 9절). 한국 항목 680 은 도판이 없고 PDF 쪽도
    없다 — `null` 이다. 0 으로 두면 그것이 자료가 된다.
    """

    entry = models.ForeignKey(AtlasEntry, on_delete=models.CASCADE,
                              related_name="placements")
    seq = models.PositiveSmallIntegerField(default=0, db_default=0)
    # 도판 번호. 한국 `pl.` · Schmidt `Tafel` · 동남극 `Plate`.
    # **Tafel 은 열쇠가 아니다** — 해설 OCR 이 번호를 묶음째로 잘못 읽어 114건이
    # 틀려 있었다(126). 쪽으로 짚는다
    plate = models.PositiveIntegerField(null=True, blank=True)
    # 번호가 없는 도판 자리 (동남극 `SEM Figures`)
    plate_label = models.CharField(max_length=16, blank=True, default="", db_default="")
    # 범위·목록이 섞여 원문 그대로 든다 (`11–13` · `1—8` · `4, 6`)
    figures = models.CharField(max_length=120, blank=True, default="", db_default="")
    book_page = models.PositiveIntegerField(null=True, blank=True)
    # 해설면 / 도판면. **도판 이미지를 짚는 것이 이 둘이다**
    # (`/data3/DiaRUGA/atlas/<도감>/<권>/p####.png`)
    pdf_page = models.PositiveIntegerField(null=True, blank=True)
    pdf_plate_page = models.PositiveIntegerField(null=True, blank=True)
    # Schmidt 만 (`Band1`~`Band4`). **쪽 번호가 권마다 다시 센다** — 이미지를
    # 짚을 때 권이 없으면 다른 쪽이 열린다. 경로용 소문자는 화면이 만든다
    volume = models.CharField(max_length=16, blank=True, default="", db_default="")
    # 색인이 이 자리에 단 주석. Schmidt 21건의 `Tafel 아님 · 권 뒤
    # Verzeichnis(색인) 쪽에서 왔다` 가 여기 온다 — **`plate` 는 색인에 적힌
    # 그대로 두고 주석이 그것을 뒤집는다.** `pdf_page` 는 성하다
    note = models.TextField(blank=True, default="", db_default="")

    class Meta:
        ordering = ["entry", "seq"]
        indexes = [models.Index(fields=["volume", "pdf_page"]),
                   models.Index(fields=["plate"])]

    def __str__(self):
        where = f"pl.{self.plate}" if self.plate else (self.plate_label or "?")
        return f"{where} p.{self.pdf_page}"
