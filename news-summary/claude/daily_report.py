""" 
Claude 일일 모니터링 스크립트
- AI 관련 법안/정책, 기술 뉴스, 주식/경제 동향 정보를 매일 자동 수집
- 결과를 Markdown 파일로 저장
"""

import anthropic
import os 
import json
from datetime import datetime, timedelta 
from pathlib import Path


# 설정정보
API_KEY = os.environ.get("ANTHROPIC_API_KEY")
OUTPUT_DIR = Path(".", "daily_report")


def run():
    print(f"API_KEY: {API_KEY}")
    print(f"OUTPUT_DIR: {OUTPUT_DIR}")
    
    
if __name__ == "__main__":
    run()