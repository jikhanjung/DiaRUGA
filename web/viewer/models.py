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


class Run(models.Model):
    """실행 이력. 지금까지 아무 데도 없어서 stack_report.json 이 덮어써졌다."""

    KIND = [(k, k) for k in
            ("group", "stack", "detect", "refilter", "reconcile", "ingest", "export")]
    STATUS = [(s, s) for s in ("running", "done", "failed")]

    kind = models.CharField(max_length=16, choices=KIND)
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
    """

    code = models.CharField(max_length=32, unique=True)     # RS23
    name = models.CharField(max_length=200, blank=True)     # 사람이 채운다
    region = models.CharField(max_length=200, blank=True)   # 로스해 / 웨델해 …
    lat = models.FloatField(null=True, blank=True)
    lon = models.FloatField(null=True, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.name or self.code


class Core(models.Model):
    """시추코어 하나. 폴더명의 가운데 토막(GC03, GC47)이다.

    깊이별 슬라이드가 이 아래 달리므로, **같은 코어에서 깊이에 따른 군집 변화**를
    질의할 수 있다. 지역별 차이는 Site 로 묶어 본다.
    """

    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="cores")
    code = models.CharField(max_length=32)                  # GC03
    # GC = gravity core 처럼 앞 글자가 채취 방식을 뜻하는 일이 많지만,
    # 코드마다 다를 수 있어 사람이 채우도록 둔다.
    kind = models.CharField(max_length=64, blank=True)
    lat = models.FloatField(null=True, blank=True)
    lon = models.FloatField(null=True, blank=True)
    water_depth_m = models.FloatField(null=True, blank=True)
    collected_at = models.DateField(null=True, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["site", "code"]
        constraints = [models.UniqueConstraint(fields=["site", "code"],
                                               name="uniq_core_code")]

    def __str__(self):
        return f"{self.site.code}-{self.code}"


class Slide(models.Model):
    """슬라이드글라스 하나 = 폴더 하나. 그 안에 여러 시야가 들어 있다.

    이름은 `<지역>-<코어> <깊이>cm` 꼴이다(RS23-GC03 71cm). 통짜 문자열로 두면
    깊이순 정렬도 지역별 묶음도 안 되므로 갈라서 담는다.
    """

    STATE = [(s, s) for s in
             ("pending", "copying", "processing", "done", "failed")]

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=120, unique=True)
    image_dir = models.CharField(max_length=500)
    core = models.ForeignKey(Core, null=True, blank=True,
                             on_delete=models.SET_NULL, related_name="slides")
    # 기준점(해저면)에서부터의 깊이. 코어 안에서 이 값으로 정렬한다.
    depth_cm = models.FloatField(null=True, blank=True)
    corr_thresh = models.FloatField(null=True, blank=True)
    # NAS 로 폴더가 계속 들어오면 상태 관리가 필요해진다 (P01 §1)
    state = models.CharField(max_length=12, choices=STATE, default="done")
    state_note = models.TextField(blank=True)
    discovered_at = models.DateTimeField(null=True, blank=True)
    copied_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # 코어 안에서는 깊이순 — 깊이에 따른 변화를 볼 때 그 순서가 자연스럽다
        ordering = ["core", "depth_cm", "name"]
        indexes = [models.Index(fields=["core", "depth_cm"])]

    def __str__(self):
        return self.name


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


class ThresholdSet(models.Model):
    """판정 문턱. 지금은 11개 값이 결과 JSON 마다 복사돼 있다.

    표로 두면 이름을 붙여 비교할 수 있다 — "1500 vs 2000 을 같은 시야에 걸고
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

    표로 두면 분류를 더할 때 배포가 필요 없다 — Eucampia 를 넣은 것이 코드
    수정이었는데, 속은 계속 늘어난다.
    """

    key = models.CharField(max_length=32, unique=True)
    label = models.CharField(max_length=64)
    badge = models.CharField(max_length=16, blank=True)
    color = models.CharField(max_length=24, blank=True)   # "255,110,190"
    # 형태 칸과 분류학 칸은 성격이 다르다 — 메뉴에서 줄을 그어 나눈다
    is_taxon = models.BooleanField(default=False)
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


class Detection(models.Model):
    """이미지 한 장에 대한 검출 실행.

    재실행마다 새 행을 쌓는다 — 덮어쓰면 엔진 교체 전후를 비교할 수 없다.
    뷰어는 `is_current=True` 인 것만 본다.
    """

    TARGET = [("stack", "stack"), ("frame", "frame")]

    viewpoint = models.ForeignKey(Viewpoint, on_delete=models.CASCADE,
                                 related_name="detections")
    target = models.CharField(max_length=8, choices=TARGET)
    # target=frame 일 때만 (싱글턴 시야는 합성본이 없어 그 한 장으로 돌린다)
    frame = models.ForeignKey(Frame, null=True, blank=True,
                              on_delete=models.SET_NULL,
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

    def __str__(self):
        return f"{self.image_path} ({'현재' if self.is_current else '이전'})"


class Candidate(models.Model):
    """개체 하나. 통과분·탈락분을 한 표에 담고 `passed` 로 가른다.

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
    """시야 단위 교정 상태. review/*.json 의 done·note."""

    viewpoint = models.OneToOneField(Viewpoint, on_delete=models.CASCADE,
                                     related_name="review")
    # 고칠 것이 없어 교정이 비어도 검토는 끝났을 수 있다 — 따로 남긴다
    done = models.BooleanField(default=False)
    note = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.viewpoint} {'완료' if self.done else '미완'}"


class ObjectReview(models.Model):
    """개체 단위 교정. **재생성 불가한 자료다.**

    `candidate` 는 바인딩 결과일 뿐이고 진짜 키는 `(viewpoint, mask_key)` 다.
    `geom` 에 기하를 스스로 들고 있어 검출기가 바뀌어도 읽을 수 있다 —
    지운 것까지 전부 저장한다(학습의 어려운 음성 표본이다).
    """

    BIND = [(b, b) for b in ("exact", "iou", "manual", "orphan")]

    viewpoint = models.ForeignKey(Viewpoint, on_delete=models.CASCADE,
                                 related_name="object_reviews")
    mask_key = models.CharField(max_length=64)
    candidate = models.ForeignKey(Candidate, null=True, blank=True,
                                  on_delete=models.SET_NULL,
                                  related_name="reviews")
    bind_method = models.CharField(max_length=8, choices=BIND, default="orphan")
    bind_score = models.FloatField(null=True, blank=True)
    # {"bbox": [x,y,w,h], "polygon": [...]}
    geom = models.JSONField(default=dict, blank=True)

    # 둘을 한 칼럼으로 합치지 않는다 — 되살렸다가 다시 지운 개체가 있고,
    # "사람이 지웠다가 이긴다" 는 규칙이 두 값의 조합으로 표현된다.
    removed = models.BooleanField(default=False)
    accepted = models.BooleanField(default=False)
    label = models.CharField(max_length=32, blank=True)
    note = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["viewpoint", "mask_key"],
                                               name="uniq_objreview_key")]
        indexes = [
            models.Index(fields=["viewpoint", "bind_method"]),
            models.Index(fields=["bind_method"]),
        ]

    def __str__(self):
        marks = [n for n, v in (("삭제", self.removed), ("복구", self.accepted),
                                ("분류", self.label), ("메모", self.note)) if v]
        return f"{self.mask_key} {'·'.join(marks) or '-'}"
