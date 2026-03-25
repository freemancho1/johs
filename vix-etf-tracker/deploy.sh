#!/bin/bash
set -e

# ─── 설정 ───────────────────────────────────────────────
# bashrc에 등록된 GCP_PROJECT_ID, GCP_REGION 환경변수를 사용합니다
PROJECT_ID="${GCP_PROJECT_ID:?'GCP_PROJECT_ID 환경변수가 설정되지 않았습니다. bashrc를 확인하세요.'}"
REGION="${GCP_REGION:?'GCP_REGION 환경변수가 설정되지 않았습니다. bashrc를 확인하세요.'}"
SCHEDULER_LOCATION="${REGION}"
SERVICE_NAME="vix-etf-tracker"
DB_NAME="vix-etf-db"
SA_NAME="scheduler-invoker"

echo "🚀 VIX & ETF Tracker 배포 시작"
echo "   프로젝트: ${PROJECT_ID}"
echo "   리전: ${REGION}"
echo ""

# ─── 1. 프로젝트 설정 ───────────────────────────────────
gcloud config set project ${PROJECT_ID}

# ─── 2. Firestore 생성 (이미 있으면 스킵) ────────────────
echo "📦 Firestore 설정 (DB: ${DB_NAME})..."
gcloud firestore databases create \
  --database=${DB_NAME} \
  --location=${REGION} \
  --type=firestore-native 2>/dev/null || \
  echo "  (Firestore ${DB_NAME}이 이미 존재합니다)"

# ─── 3. Firestore 인덱스 배포 ───────────────────────────
echo "📇 Firestore 인덱스 배포..."
gcloud firestore indexes composite create \
  --database=${DB_NAME} \
  --collection-group=market_data \
  --field-config field-path=ticker,order=ascending \
  --field-config field-path=date,order=ascending 2>/dev/null || true

gcloud firestore indexes composite create \
  --database=${DB_NAME} \
  --collection-group=market_data \
  --field-config field-path=ticker,order=ascending \
  --field-config field-path=date,order=descending 2>/dev/null || true

# ─── 4. Cloud Run 배포 ──────────────────────────────────
echo "🐳 Cloud Run 배포..."
gcloud run deploy ${SERVICE_NAME} \
  --source . \
  --region ${REGION} \
  --no-allow-unauthenticated \
  --memory 512Mi \
  --timeout 300 \
  --min-instances 0 \
  --max-instances 1

SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} \
  --region ${REGION} --format 'value(status.url)')
echo "  서비스 URL: ${SERVICE_URL}"

# ─── 5. 서비스 계정 & 스케줄러 ──────────────────────────
echo "⏰ Cloud Scheduler 설정..."

# 서비스 계정 생성
gcloud iam service-accounts create ${SA_NAME} \
  --display-name "Cloud Scheduler Invoker" 2>/dev/null || \
  echo "  (서비스 계정이 이미 존재합니다)"

SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# 권한 부여
gcloud run services add-iam-policy-binding ${SERVICE_NAME} \
  --region ${REGION} \
  --member "serviceAccount:${SA_EMAIL}" \
  --role "roles/run.invoker" \
  --quiet

# 스케줄러 생성 (평일 08:00 KST)
gcloud scheduler jobs delete vix-etf-daily-collect \
  --location ${SCHEDULER_LOCATION} --quiet 2>/dev/null || true

gcloud scheduler jobs create http vix-etf-daily-collect \
  --location ${SCHEDULER_LOCATION} \
  --schedule "0 8 * * 1-5" \
  --time-zone "Asia/Seoul" \
  --uri "${SERVICE_URL}/collect" \
  --http-method POST \
  --oidc-service-account-email "${SA_EMAIL}"

# ─── 6. 백필 (최초 90일치 수집) ─────────────────────────
echo "📊 과거 90일 데이터 백필 중..."
curl -s -X POST "${SERVICE_URL}/backfill?days=90" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" | python3 -m json.tool

echo ""
echo "✅ 배포 완료!"
echo "   수집: POST ${SERVICE_URL}/collect"
echo "   분석: GET  ${SERVICE_URL}/analysis"
echo "   데이터: GET  ${SERVICE_URL}/data/{ticker}?days=30"
echo "   스케줄: 평일 08:00 KST 자동 실행"