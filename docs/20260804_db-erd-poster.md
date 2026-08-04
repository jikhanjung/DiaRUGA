# diatom DB ERD — 한눈에

**2026-08-04** · A3 가로

도표만 모았다. 칸의 뜻은 [DB 명세](20260804_db-specification.md), 관계 하나하나의
방향·`on_delete`·`related_name` 은 [ERD 문서](20260804_db-erd.md)에 있다.

원본은 `web/viewer/models.py` 이고, 이 그림들은 그 두 문서와 **같은 mermaid 원본**
에서 나온다 — 한쪽만 고쳐져 어긋나는 일이 없다.

---

## 전체 그림

파랑이 줄기(시료 계통), 초록이 검출, 빨강이 사람의 교정, 회색이 설정과 이력이다.
실선은 소유(FK — 지우면 따라 지워진다), 점선은 참조이거나 FK 가 아예 아닌 것이다.

```mermaid
flowchart LR
    Site[Site<br/>지역] --> Core[Core<br/>코어] --> Slide[Slide<br/>슬라이드]
    Slide --> VP[Viewpoint<br/>시야] --> Frame[Frame<br/>사진]
    VP --> Stack[Stack<br/>합성본 1:1]
    VP --> Det[Detection<br/>is_current] --> Cand[Candidate<br/>개체]
    VP --> VR[ViewpointReview<br/>시야 검토 1:1]
    VP --> OR[ObjectReview<br/>개체 교정]
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
    class Site,Core,Slide,VP,Frame stem
    class OR,VR human
    class Det,Cand,Stack det
    class RB,Run,TS,CD,ST side
```

---

## 시료 계통과 이력

```mermaid
erDiagram
    direction LR
    Site ||--o{ Core : cores
    Core ||--o{ Slide : slides
    Slide ||--o{ Viewpoint : viewpoints
    Slide ||--o{ Frame : frames
    Slide ||--o{ Run : runs
    RunBatch ||--o{ Run : runs
    Viewpoint ||--o{ Frame : frames
    Viewpoint ||--|| Stack : stack
    Viewpoint ||--|| ViewpointReview : review
    Run ||--o{ Stack : stacks
    Run ||--o{ Viewpoint : viewpoints
    Frame ||--o{ Stack : ref_of
```

---

## 검출과 교정

```mermaid
erDiagram
    Viewpoint ||--o{ Detection : detections
    Viewpoint ||--o{ ObjectReview : object_reviews
    Frame ||--o{ Detection : detections
    Run ||--o{ Detection : detections
    ThresholdSet ||--o{ Detection : detections
    Detection ||--o{ Candidate : candidates
    Detection ||--o{ Detection : supersedes
    Candidate ||--o{ ObjectReview : reviews

    Detection {
        string target "stack|frame"
        bool is_current "뷰어가 볼 것"
    }
    Candidate {
        string mask_key UK "detection 안에서"
        bool passed "문턱 통과"
        string cls
    }
    ObjectReview {
        string mask_key UK "viewpoint 안에서"
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
    R[ObjectReview<br/>viewpoint + mask_key<br/>geom · removed · label]
    C1 -. "FK 였다면 여기서 끊긴다" .-> R
    C2 == "mask_key 로 다시 붙는다<br/>exact → IoU → orphan" ==> R

    classDef gone fill:#f1f3f4,stroke:#9aa0a6,color:#5f6368
    classDef human fill:#fce8e6,stroke:#ea4335,stroke-width:2px
    class C1 gone
    class R human
```

---

## 지금 담긴 것 (2026-08-04)

```mermaid
flowchart LR
    S["Site<br/>5"] --> C["Core<br/>5"] --> SL["Slide<br/>10"] --> VP["Viewpoint<br/>448"]
    VP --> F["Frame<br/>1,318<br/><small>평균 2.9장/시야</small>"]
    VP --> ST["Stack<br/>317<br/><small>싱글턴 131은 없다</small>"]
    VP --> VR["ViewpointReview<br/>436"]
    VP --> OR["ObjectReview<br/>6,753"]
    VP --> D["Detection<br/>3,705"] --> CA["Candidate<br/>128,583<br/><small>평균 35개/검출</small>"]
    RB["RunBatch<br/>3"] --> R["Run<br/>188"]
```
