import json
from urllib.parse import urlencode

from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def json_dumps(value):
    """
    <script type="application/json"> 안에 넣을 JSON.

    </script> 로 태그를 조기 종료시키는 것을 막아야 하므로 < 를 이스케이프한다.
    """
    text = json.dumps(value, ensure_ascii=False)
    return mark_safe(text.replace("<", "\\u003c").replace("\u2028", "\\u2028"))


@register.simple_tag
def thumb(rel, width=400):
    """축소본 URL. 폴더명에 공백이 있어 경로는 쿼리로 넘긴다."""
    if not rel:
        return ""
    return "/img?" + urlencode({"p": str(rel), "w": int(width)})


@register.simple_tag
def full(rel):
    """원본 URL."""
    if not rel:
        return ""
    return "/img?" + urlencode({"p": str(rel)})


@register.filter
def groups_json(slug):
    """슬러그를 groups_*.json 파일명으로 되돌린다 — 안내 문구용."""
    return f"groups_{slug}.json"
