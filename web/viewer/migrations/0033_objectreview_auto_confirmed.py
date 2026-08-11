"""검토 완료로 확인한 통과분에 표시를 단다 (`ObjectReview.auto_confirmed`).

**칸을 더하기만 한다** — 자료를 옮기지 않고 걷는 것도 없다. 그래서 옛
파이프라인 이미지가 서지 않고(0032 와 다른 자리다), 뷰어만 올려도 된다.

**`db_default` 를 함께 준다.** Django 의 `default` 는 파이썬 쪽이라 판이 다른
옛 이미지의 INSERT 에는 칼럼이 아예 안 들어간다 — 뷰어와 파이프라인은 굽는
주기가 달라 판이 같아질 일이 없다 (HANDOFF 3.7).

**이미 있는 행은 `False` 다.** 지난 검토가 남긴 통과분은 소급해서 확인 표시를
받지 않는다 — 그때 사람이 무엇을 보고 완료를 눌렀는지 우리가 알 수 없고,
**사람이 안 한 서명을 대신 적으면 안 된다.** 다시 완료를 누르면 그때 선다.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("viewer", "0032_diatom_object")]

    operations = [
        migrations.AddField(
            model_name="objectreview",
            name="auto_confirmed",
            field=models.BooleanField(db_default=False, default=False)),
    ]
