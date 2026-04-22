import os
import json 
import asyncio 
import difflib 

from dataclasses import dataclass, field 
from datetime import datetime 
from pathlib import Path 
from string import Template 
from typing import Any 

try: 
    from google import genai 
    from google.genai import types 
except ImportError as err:
    raise SystemExit(
        "google-genai 패키지 필요\n"
        "> pip install google-genai"
    ) from err
    
    
@dataclass(slots=True)
class NewsItem:
    """ 검색된 뉴스 한 건을 표현하는 데이터 클래스 """
    rank: int
    title: str
    summary: str
    source: str
    url: str
    category: str = "일반"
    
    def format_display(self) -> str:
        """ 터미널 출력용 형식 설정 """
        return (
            f"{self.rank:>2}. [{self.category}] **{self.title}**\n"
            f"    {self.summary}\n"
            f"    └─ 출처: {self.source}  |  {self.url}\n"
        )
        

@dataclass(slots=True)
class SearchConfig:
    """ 검색 설정 값을 한 곳에서 관리. """
    model: str = "gemini-2.5-flash"
    temperature: float = 0.3
    max_results: int = 10
    keywords: list[str] = field(
        default_factory=lambda: ["분산 에너지", "전력 수급", "에너지 신사업 동향"]
    )
    output_dir: Path = field(default_factory=lambda: Path("./news_output"))
    
    
class PromptBuilder:
    _TEMPLATE = Template(
        """ 
오늘자(${today}) 한국의 주요 에너지 관련 최신 뉴스 ${max_results}개를
구글에서 검색해서 요약해 줘.

특히 다음 키워드와 관련된 뉴스를 우선적으로 찾아줘:
${keywords}

다음 JSON 배열 형식으로만 응답해 줘 (다른 텍스트 없이):
[
  {
    "rank": 1,
    "title": "검색된 기사의 정확한 원본 제목 (절대 임의로 축약하지 말 것)",
    "summary": "주요 내용 1~2줄 요약",
    "source": "언론사명",
    "url": "", 
    "category": "분산에너지 또는 전력수급 또는 에너지신사업 또는 일반"
  }
]

주의사항:
- url 필드는 반드시 빈 문자열("")로 남겨둘 것. (가짜 숫자로 주소를 지어내면 절대 안 됨)
- title 필드는 검색 결과에 나온 기사 제목을 훼손하지 말고 그대로 작성할 것.
        """
    )
    
    @classmethod
    def build(cls, config: SearchConfig) -> str:
        keywords_str = "\n".join(f"  - {kw}" for kw in config.keywords)
        return cls._TEMPLATE.substitute(
            today=datetime.now().strftime("%Y년 %m월 %d일"),
            max_results=config.max_results, 
            keywords=keywords_str,
        )
        
        
class EnergyNewsSearcher:
    """ Gemini API를 이용한 에너지 뉴스 비동기 검색기 """
    
    def __init__(self, config: SearchConfig | None = None) -> None:
        self.config = config or SearchConfig()
        self._client = genai.Client()   # 환경변수 GOOGLE_API_KEY 자동참조
        
    async def fetch_news(self) -> list[NewsItem]:
        """ 비동기로 뉴스를 검색하고 NewsItem 리스트로 반환 """
        prompt = PromptBuilder.build(self.config)
        
        # raw_response(JSON 텍스트)와 url_map(실제 검색된 URL 딕셔너리)을 함께 받음
        raw_response, url_map = await asyncio.to_thread(self._call_api, prompt)
        return self._parse_response(raw_response, url_map)
    
    def _call_api(self, prompt: str) -> tuple[str, dict[str, str]]:
        """ (동기) Gemini API 호출 및 메타데이터에서 URL 추출 """
        response = self._client.models.generate_content(
            model=self.config.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[{"google_search": {}}],
                temperature=self.config.temperature,
            ),
        )
        
        text = response.text or ""
                
        print("\n\n\n\n")
        print(text)
        print("\n\n\n\n")
        print(response)
        print("\n\n\n\n")
        
        # [핵심 로직] Grounding Metadata에서 실제 웹페이지의 제목과 URI를 추출
        url_map: dict[str, str] = {}
        if response.candidates:
            candidate = response.candidates[0]
            if candidate.grounding_metadata and candidate.grounding_metadata.grounding_chunks:
                for chunk in candidate.grounding_metadata.grounding_chunks:
                    # 타입 체커 오류를 방지하기 위해 getattr로 안전하게 접근
                    web_data = getattr(chunk, "web", None)
                    if web_data:
                        uri = getattr(web_data, "uri", None)
                        title = getattr(web_data, "title", "")
                        
                        if uri:
                            url_map[title] = uri
                        
        if not text:
            raise ValueError("API 요청에 대한 결과값이 없습니다. (response.text = None)")
            
        return text, url_map
    
    def _parse_response(self, raw: str, url_map: dict[str, str]) -> list[NewsItem]:
        cleaned_response_data = raw.strip().removeprefix("```json").removesuffix("```").strip()
        
        try:
            json_data: Any = json.loads(cleaned_response_data)
        except json.JSONDecodeError as err:
            raise ValueError(f"API 응답을 JSON으로 파싱할 수 없습니다: {err}")
        
        items: list[NewsItem] = []
        for news in json_data:
            match news:
                case {
                    "rank": int(rank),
                    "title": str(title),
                    "summary": str(summary),
                    "source": str(source),
                    **rest, # url 필드는 여기서 무시합니다
                }:
                    real_url = "URL 매칭 실패 (원본 링크 확인 불가)"
                    
                    # 1. 완전 일치 또는 부분 일치 검색
                    for chunk_title, chunk_uri in url_map.items():
                        if title in chunk_title or chunk_title in title:
                            real_url = chunk_uri
                            break
                            
                    # 2. 그래도 못 찾았다면 difflib을 이용한 유사도 검색 (오타/축약 방어)
                    if real_url.startswith("URL 매칭 실패") and url_map:
                        # 일치율이 40% 이상인 가장 비슷한 제목을 찾습니다
                        matches = difflib.get_close_matches(title, url_map.keys(), n=1, cutoff=0.4)
                        if matches:
                            real_url = url_map[matches[0]]
                    
                    items.append(
                        NewsItem(
                            rank=rank, title=title, summary=summary, source=source,
                            url=real_url, 
                            category=rest.get("category", "일반")
                        )
                    )
                case _:
                    pass
                    
        return sorted(items, key=lambda n: n.rank)
    

class ResultRenderer:
    """ 뉴스 결과를 터미널과 파일에 출력 """
    
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir 
        # 폴더 생성: 상위(해당) 폴더가 없으면 만들고, 있으면 무시
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def print_results(self, items: list[NewsItem]) -> None:
        separator = "-" * 75
        print(f"\n{'='*75}")
        print(f"  한국 에너지 최신 뉴스 ({datetime.now():%Y-%m-%d %H:%M})")
        print(f"{'='*75}\n")
        
        if not items:
            print(" 검색 결과가 없습니다.")
            return 
        
        for item in items:
            print(item.format_display())
            print(separator)
            
        print(f"\n총 {len(items)}건 검색 완료")
        
    def save_json(self, items: list[NewsItem]) -> Path:
        """ JSON 파일로 저장 후 경로 반환. """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = self.output_dir / f"energy_news_{timestamp}.json"
        
        payload = [
            {
                "rank": it.rank, 
                "title": it.title, 
                "summary": it.summary,
                "source": it.source,
                "url": it.url,
                "category": it.category
            }
            for it in items
        ]
        
        file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return file_path
    
    
async def main() -> None:
    config = SearchConfig(
        model="gemini-2.5-flash",
        temperature=0.3,
        max_results=10,
        keywords=["분산 에너지", "전력 수급", "에너지 신사업 동향"],
        output_dir=Path("./news_output"),
    )
    
    searcher = EnergyNewsSearcher(config)
    renderer = ResultRenderer(config.output_dir)
    
    print("최신 에너지 뉴스를 검색하는 중입니다. 잠시만 기다려주세요...\n")
    
    try:
        # 비동기 검색 실행
        async with asyncio.timeout(120):
            news_items = await searcher.fetch_news()
            
        renderer.print_results(news_items)
        
        if news_items:
            save_path = renderer.save_json(news_items)
            print(f"\n 뉴스 검색 결과가 저장되었습니다: {save_path.resolve()}")
            
    except* TimeoutError as err:
        print(f" - 검색 시간이 초과되었습니다: {err.exceptions}")
    except* ValueError as err:
        print(f" - 응답 데이터 파싱 과정에서 오류가 발생했습니다: {err.exceptions}")
    except* Exception as err:
        print(f" - 예상치 못한 오류가 발생했습니다: {err.exceptions}")
        raise
    
    
if __name__ == "__main__":
    asyncio.run(main())
        
        