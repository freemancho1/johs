_NEWS_SITE = ["한전·발전사·그룹사 관련", "국내", "해외"]

_QUESTION_STR = """
오늘이 {date}이니, 웹 검색 도구를 사용해 어제, 오늘 기준
{site} 최신 AI/에너지 뉴스를 찾아 아래와 같이 정리해줘
1. 뉴스는 정확히 5개를 선정할 것
2. 각 뉴스는 아래 형식으로 작성할 것:
## 📌 N. [제목]
[내용 요약: 반드시 100자 이내로 작성. 초과 금지]
> 📎 출처: [링크]
"""

CATEGORIES = [
    { "name": site, "question": _QUESTION_STR.format(site=site, date="{date}") }
    for site in _NEWS_SITE
]
