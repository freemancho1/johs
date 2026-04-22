# PrimeCast 
<small>AI-Powered Korean Stock Market Trading System</small>


<h1>
    PrimeCast
    <br>
    <small style="font-weight: normal; color: #888888; font-size: 15px">
        AI-Powered Korean Stock Market Trading System
    </small>
    <br/>
</h1>

## 프로젝트 개요

한국 주식시장을 대상으로 한 데이터 기반 AI 트레이딩 시스템 구축 프로젝트.  
삼성전자(005930)를 시작점으로, 거시경제 데이터와 기술적 지표를 결합한 ML 파이프라인을 구현한다.

---

## 데이터 파이프라인 (`stock_data_pipeline.py`)

총 7단계로 구성된 완성된 파이프라인. 최종 출력: **(1,376 × 60 × 48) 텐서 + 메타데이터 JSON**

| 단계 | 내용 |
|------|------|
| 1. 데이터 수집 | yfinance / pykrx / FinanceDataReader로 OHLCV 수집 |
| 2. 데이터 정제 | 결측치 처리, 이상치 제거 |
| 3. 피처 엔지니어링 | 7개 그룹, 48개 기술적 지표 생성 |
| 4. 정규화 | Z-score 정규화 (훈련 데이터 기준으로만 fit) |
| 5. 레이블링 | Triple Barrier 레이블링 |
| 6. 시퀀스 생성 | 60일 룩백 윈도우 기반 슬라이딩 윈도우 |
| 7. 데이터 분할 | 시간순 70 / 15 / 15 (Train / Val / Test) |

---

## 핵심 설계 결정

- **단일 대형주 집중**: 삼성전자부터 시작해 복잡도 최소화 후 확장
- **Triple Barrier 레이블링**: 익절 +3%, 손절 -2%, 최대 보유 10일 — 단순 방향성 레이블 대비 실거래 시뮬레이션에 유리
- **Look-ahead Bias 방지**: 정규화 및 레이블링을 훈련 데이터에만 fit — 핵심 원칙으로 전 단계 준수
- **60일 룩백 윈도우**: 시계열 패턴 포착을 위한 시퀀스 길이

---

## 기술 스택

**데이터 수집**  
`yfinance` · `pykrx` · `FinanceDataReader` · ECOS API · World Bank WDI · IMF · FRED · OECD

**ML 라이브러리**  
`pandas` · `numpy` · `scikit-learn` · `matplotlib`

**목표 모델 아키텍처**  
LSTM · Transformer · Reinforcement Learning (조합 앙상블)

---

## 다음 단계

파이프라인 출력 텐서를 기반으로 모델 훈련 단계 진입.  
LSTM → Transformer → RL 순서로 구현 후 앙상블 전략 수립.

---

*Last updated: 2026-04-21*
