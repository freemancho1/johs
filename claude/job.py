import os
import sys
from datetime import datetime 
from google.cloud import firestore 
import anthropic 


def main():
    print("=" * 50)
    print(f"클로드 일일 질의 시작: {datetime.now()}")
    print("=" * 50)
    
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[ERROR] Anthropic API Key가 없습니다.")
        sys.exit(1)
        
    # question = os.envir