import os
import sys
import time
from datetime import datetime 
from google.cloud import firestore 
import anthropic 
from anthropic.types import TextBlock 

from questions import CATEGORIES


MODEL           = "claude-sonnet-4-6"
MAX_TOKENS      = 4096
MAX_SEARCH_USES = 3         # 카테고리당 최대 웹 검색 횟 수
RETRY_COUNT     = 3         # Rate limit 에러 발생 시 최대 재시도 횟 수
CATEGORY_DELAY  = 15        # 카테고리 간 대기 시간 (초)


# ============================================================
# Claude API 호출 (Rate limit 재시도 포함)
# ============================================================
def call_claude_with_retry(client, question: str) -> str:
    for attempt in range(RETRY_COUNT):
        try:
            message = client.messages.create(
                model = MODEL,
                max_tokens=MAX_TOKENS,
                tools=[{
                    "type": "web_search_20260209",
                    "name": "web_search",
                    "max_uses": MAX_SEARCH_USES
                }],
                messages=[{"role": "user", "content": question}]
            )
            
            # 웹 검색 횟 수 로그
            if hasattr(message, "usage") and hasattr(message.usage, "server_tool_use"):
                search_count = message.usage.server_tool_use.web_search_requests
                print(f"  - 웹 검색 실행 횟 수: {search_count}회")
                
            # 카테고리별 결과 합치기
            answer = "\n".join(
                block.text for block in message.content 
                if isinstance(block, TextBlock)
            )
            
            return answer
        except Exception as err:
            if "rate_limit_error" in str(err):
                wait = 60 * (attempt + 1)
                print(f"  - Rate limit 초과. {wait}초 후 재시도... ({attempt+1}/{RETRY_COUNT})")
                time.sleep(wait)
            else:
                raise err
            
    raise Exception(f"최대 재시도 횟 수({RETRY_COUNT}회) 초과 오류")


# ============================================================
# 100자 초과 요약 후처리
# ============================================================
def trim_summaries(text: str, max_chars: int = 100) -> str:
    lines = text.split("\n")
    result = []
    
    for line in lines:
        if (line.startswith("#") or
                line.startswith(">") or
                line.startswith("---") or
                line.strip() == ""):
            result.append(line)
        elif len(line) > max_chars:
            result.append(line[:max_chars] + "...")
        else:
            result.append(line)
            
    return "\n".join(result)


def main():
    print("=" * 50)
    print(f"클로드 일일 질의 시작: {datetime.now()}")
    print("=" * 50)
    
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[ERROR] Anthropic API Key가 없습니다.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    today = datetime.now().strftime("%Y년 %m월 %d일")
    
    all_answers = []
    for idx, category in enumerate(CATEGORIES):
        print(f"\n[{idx+1}/{len(CATEGORIES)}] 카테고리: {category['name']} 질의 중...")
        
        category_name = f"# {category['name']}\n\n"
        question = category["question"].format(date=today)
        
        try:
            answer = call_claude_with_retry(client, question)
            answer = trim_summaries(answer)
            all_answers.append(f"{category_name}{answer}")
            print(f"  - 완료 ({len(answer)}자)")
        except Exception as err:
            print(f"  - 오류: {err}")
            all_answers.append(f"{category_name}  - 조회 실패: {err}")
            
        # 마지막 카테고리가 아니면 대기
        if idx < len(CATEGORIES) - 1:
            print(f"  -- 다음 카테고리 검색을 위해 {CATEGORY_DELAY}초 대기중...")
            time.sleep(CATEGORY_DELAY)
            
    # 최종 결과 합치기
    final_answer = f"\n\n{'-'*30}\n\n".join(all_answers)
    print(final_answer)
        

if __name__ == "__main__":
    main()