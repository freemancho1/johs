# VIX & ETF Daily Tracker on GCP

## 아키텍처
```
Cloud Scheduler (매일 08:00 KST)
    → Cloud Run (Python 서비스)
        → yfinance로 데이터 수집
        → Firestore에 저장
        → 시계열 분석 수행
```

## 추적 종목
| 카테고리 | 티커 | 설명 |
|---------|------|------|
| 공포지수 | ^VIX | CBOE Volatility Index |
| 에너지 ETF | XLE | Energy Select Sector SPDR |
| 에너지 ETF | VDE | Vanguard Energy ETF |
| 에너지 ETF | USO | United States Oil Fund |
| 반도체 ETF | SOXX | iShares Semiconductor ETF |
| 반도체 ETF | SMH | VanEck Semiconductor ETF |
| 반도체 ETF | XSD | SPDR S&P Semiconductor ETF |

## 배포 방법

### 1. 환경 변수 설정
```bash
export PROJECT_ID=your-project-id
export REGION=asia-northeast3  # 서울 리전
gcloud config set project $PROJECT_ID
```

### 2. API 활성화 (이미 완료)
```bash
gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  cloudscheduler.googleapis.com \
  cloudbuild.googleapis.com
```

### 3. Firestore 데이터베이스 생성
```bash
gcloud firestore databases create --location=asia-northeast1
```

### 4. Cloud Run 배포
```bash
cd vix-etf-tracker
gcloud run deploy vix-etf-tracker \
  --source . \
  --region $REGION \
  --no-allow-unauthenticated \
  --memory 512Mi \
  --timeout 300
```

### 5. Cloud Scheduler 설정 (매일 08:00 KST)
```bash
# 서비스 계정 생성
gcloud iam service-accounts create scheduler-invoker \
  --display-name "Cloud Scheduler Invoker"

# Cloud Run 호출 권한 부여
gcloud run services add-iam-policy-binding vix-etf-tracker \
  --region $REGION \
  --member "serviceAccount:scheduler-invoker@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role "roles/run.invoker"

# 스케줄러 생성
SERVICE_URL=$(gcloud run services describe vix-etf-tracker --region $REGION --format 'value(status.url)')

gcloud scheduler jobs create http vix-etf-daily-collect \
  --location $REGION \
  --schedule "0 8 * * 1-5" \
  --time-zone "Asia/Seoul" \
  --uri "${SERVICE_URL}/collect" \
  --http-method POST \
  --oidc-service-account-email "scheduler-invoker@${PROJECT_ID}.iam.gserviceaccount.com"
```

### 6. 수동 테스트
```bash
# 수동 수집 트리거
gcloud scheduler jobs run vix-etf-daily-collect --location $REGION

# 또는 직접 호출
curl -X POST ${SERVICE_URL}/collect \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)"
```

## API 엔드포인트

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/collect` | POST | 오늘 데이터 수집 |
| `/analysis` | GET | 전체 시계열 분석 결과 |
| `/data/{ticker}` | GET | 특정 종목 시계열 데이터 |
| `/health` | GET | 헬스체크 |
