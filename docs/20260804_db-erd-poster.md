# DiaRUGA DB ERD — 한눈에

**2026-08-04** (`Image` 반영 2026-08-05 — P06 · devlog 055 ·
**층 개편 2026-08-06 — `Locality`·`Sample`, devlog 063**) · A3 가로

도표만 모았다. 칸의 뜻은 [DB 명세](20260804_db-specification.md), 관계 하나하나의
방향·`on_delete`·`related_name` 은 [ERD 문서](20260804_db-erd.md)에 있다.

원본은 `web/viewer/models.py` 이고, 이 그림들은 그 두 문서와 **같은 mermaid 원본**
에서 나온다 — 한쪽만 고쳐져 어긋나는 일이 없다.

**굽는 명령에 용지를 함께 준다.** `md2docx.py` 의 기본은 A4 세로라, 안 주면
머리말에 "A3 가로" 라고 적어 놓고 A4 세로가 나온다(실제로 그러고 있었다).

```bash
NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt npm i --no-save @mermaid-js/mermaid-cli
MMDC=$(pwd)/node_modules/.bin/mmdc python md2docx.py \
    docs/20260804_db-erd-poster.md --paper a3 --landscape
```

---

## 전체 그림

파랑이 줄기(시료 계통), 초록이 검출, 빨강이 사람의 교정, 회색이 설정과 이력이다.
실선은 소유(FK — 지우면 따라 지워진다), 점선은 참조이거나 FK 가 아예 아닌 것이다.

```mermaid
flowchart LR
    Site[Site<br/>지역] --> Loc[Locality<br/>지점] --> Smp[Sample<br/>시료] --> Slide[Slide<br/>관찰]
    Slide --> VP[Viewpoint<br/>시야] --> Frame[Frame<br/>사진]
    VP --> Stack[Stack<br/>합성본 1:1]
    VP --> Img[Image<br/>stack·frame·depth] --> Det[Detection<br/>is_current] --> Cand[Candidate<br/>개체]
    VP --> VR[ViewpointReview<br/>시야 검토 1:1]
    Img --> OR[ObjectReview<br/>개체 교정]
    Cand -. "mask_key 로 느슨히" .-> OR
    Cand -. "cls 문자열" .-> CD[ClassDef<br/>분류 정의]
    RB[RunBatch<br/>이름표] --> Run[Run<br/>실행]
    Run -.-> Det
    Run -.-> Stack
    Run -.-> VP
    TS[ThresholdSet<br/>판정 문턱] -.-> Det
    ST[Setting<br/>key-value]

    classDef stem fill:#e8f0fe,stroke:#4285f4,stroke-width:2px
    classDef human fill:#fce8e6,stroke:#ea4335,stroke-width:2px
    classDef det fill:#e6f4ea,stroke:#34a853
    classDef side fill:#f8f9fa,stroke:#9aa0a6,color:#5f6368
    class Site,Loc,Smp,Slide,VP,Frame stem
    class OR,VR human
    class Det,Cand,Stack,Img det
    class RB,Run,TS,CD,ST side
```

---

## 시료 계통과 이력

```mermaid
erDiagram
    direction LR
    Site ||--o{ Locality : localities
    Locality ||--o{ Sample : samples
    Sample ||--o{ Slide : slides
    Slide ||--o{ Viewpoint : viewpoints
    Slide ||--o{ Frame : frames
    Slide ||--o{ Run : runs
    RunBatch ||--o{ Run : runs
    Viewpoint ||--o{ Frame : frames
    Viewpoint ||--|| Stack : stack
    Viewpoint ||--o{ Image : images
    Frame ||--|| Image : image
    Stack ||--o{ Image : images
    Viewpoint ||--|| ViewpointReview : review
    Run ||--o{ Stack : stacks
    Run ||--o{ Viewpoint : viewpoints
    Frame ||--o{ Stack : ref_of
```

---

## 검출과 교정

```mermaid
erDiagram
    Image ||--o{ Detection : detections
    Image ||--o{ ObjectReview : object_reviews
    Viewpoint ||--o{ Detection : detections
    Viewpoint ||--o{ ObjectReview : object_reviews
    Run ||--o{ Detection : detections
    ThresholdSet ||--o{ Detection : detections
    Detection ||--o{ Candidate : candidates
    Detection ||--o{ Detection : supersedes
    Candidate ||--o{ ObjectReview : reviews

    Image {
        string path UK "자연 열쇠"
        string kind "stack|frame|depth"
    }
    Detection {
        int image FK "NOT NULL"
        bool is_current "뷰어가 볼 것"
    }
    Candidate {
        string mask_key UK "detection 안에서"
        bool passed "문턱 통과"
        string cls
    }
    ObjectReview {
        string mask_key UK "image 안에서"
        json geom "스스로 든 기하"
        bool removed
        bool accepted
    }
    CD["ClassDef"] {
        string key UK
        bool counted
    }
```

---

## 사람의 교정은 왜 후보에 매이지 않는가

```mermaid
flowchart LR
    subgraph 다시_돌리기_전 [재검출 전]
        C1[Candidate<br/>id=1001<br/>mask_key=1240_880_96_64]
    end
    subgraph 다시_돌리기_후 [재검출 후]
        C2[Candidate<br/>id=7734<br/>mask_key=1240_880_96_64]
    end
    R[ObjectReview<br/>image + mask_key<br/>geom · removed · label]
    C1 -. "FK 였다면 여기서 끊긴다" .-> R
    C2 == "mask_key 로 다시 붙는다<br/>exact → IoU → orphan" ==> R

    classDef gone fill:#f1f3f4,stroke:#9aa0a6,color:#5f6368
    classDef human fill:#fce8e6,stroke:#ea4335,stroke-width:2px
    class C1 gone
    class R human
```

---

## 지금 담긴 것 (2026-08-05)

```mermaid
flowchart LR
    S["Site<br/>5"] --> C["Locality<br/>5"] --> SM["Sample<br/>10"] --> SL["Slide<br/>11"] --> VP["Viewpoint<br/>508"]
    VP --> F["Frame<br/>1,444<br/><small>평균 2.8장/시야</small>"]
    VP --> ST["Stack<br/>355<br/><small>싱글턴 153은 없다</small>"]
    VP --> VR["ViewpointReview<br/>432"]
    VP --> IM["Image<br/>1,952"]
    IM --> OR["ObjectReview<br/>7,472"]
    IM --> D["Detection<br/>2,132"] --> CA["Candidate<br/>97,299<br/><small>평균 46개/검출</small>"]
    RB["RunBatch<br/>2"] --> R["Run<br/>178"]
```
