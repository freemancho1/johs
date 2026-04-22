"""
VIX & ETF Daily Tracker
- 매일 08:00 KST에 VIX, 에너지·반도체 ETF 가격 수집
- Firestore에 시계열 저장
- 이동평균, 변동성, 상관관계 분석
"""

import os
import json
import logging
import time
import requests as http_requests
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
import numpy as np
from google.cloud import firestore

# ─── 설정 ───────────────────────────────────────────────
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db = firestore.Client(database="vix-etf-db")

# 추적 종목 정의
TICKERS = {
    "^VIX":  {"name": "VIX (공포지수)",       "category": "volatility"},
    "XLE":   {"name": "Energy Select SPDR",   "category": "energy"},
    "VDE":   {"name": "Vanguard Energy",      "category": "energy"},
    "USO":   {"name": "US Oil Fund",          "category": "energy"},
    "SOXX":  {"name": "iShares Semiconductor","category": "semiconductor"},
    "SMH":   {"name": "VanEck Semiconductor", "category": "semiconductor"},
    "XSD":   {"name": "SPDR Semiconductor",   "category": "semiconductor"},
}

COLLECTION_NAME = "market_data"


# ─── Yahoo Finance 직접 호출 ─────────────────────────────
YAHOO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

def fetch_yahoo(ticker, days=5):
    """Yahoo Finance chart API로 직접 가격 데이터 조회"""
    period2 = int(datetime.now().timestamp())
    period1 = int((datetime.now() - timedelta(days=days + 5)).timestamp())  # 여유분 추가

    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?period1={period1}&period2={period2}&interval=1d"
        f"&includePrePost=false&events=div%7Csplit"
    )

    resp = http_requests.get(url, headers=YAHOO_HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    result = data.get("chart", {}).get("result")
    if not result:
        return []

    chart = result[0]
    timestamps = chart.get("timestamp", [])
    quote = chart.get("indicators", {}).get("quote", [{}])[0]

    rows = []
    for i, ts in enumerate(timestamps):
        o = quote.get("open", [None])[i]
        h = quote.get("high", [None])[i]
        l = quote.get("low", [None])[i]
        c = quote.get("close", [None])[i]
        v = quote.get("volume", [0])[i]
        if c is None:
            continue
        rows.append({
            "date": datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d"),
            "open": round(float(o), 4) if o else 0,
            "high": round(float(h), 4) if h else 0,
            "low": round(float(l), 4) if l else 0,
            "close": round(float(c), 4),
            "volume": int(v or 0),
        })

    return rows


# ─── 데이터 수집 ────────────────────────────────────────
def fetch_and_store():
    """Yahoo Finance API로 최신 데이터를 가져와 Firestore에 저장"""
    results = {"success": [], "failed": []}

    for ticker, info in TICKERS.items():
        try:
            rows = fetch_yahoo(ticker, days=5)
            if not rows:
                results["failed"].append({"ticker": ticker, "reason": "no data"})
                continue

            latest = rows[-1]
            trade_date = latest["date"]

            doc_id = f"{ticker}_{trade_date}"
            record = {
                "ticker": ticker,
                "name": info["name"],
                "category": info["category"],
                "date": trade_date,
                "open": latest["open"],
                "high": latest["high"],
                "low": latest["low"],
                "close": latest["close"],
                "volume": latest["volume"],
                "collected_at": datetime.utcnow().isoformat(),
            }

            db.collection(COLLECTION_NAME).document(doc_id).set(record)
            results["success"].append({"ticker": ticker, "date": trade_date, "close": record["close"]})
            logger.info(f"✅ {ticker} ({trade_date}): {record['close']}")
            time.sleep(0.5)  # 요청 간격 조절

        except Exception as e:
            logger.error(f"❌ {ticker}: {e}")
            results["failed"].append({"ticker": ticker, "reason": str(e)})

    return results


# ─── 시계열 분석 ────────────────────────────────────────
def analyze_timeseries():
    """Firestore에 저장된 데이터로 시계열 분석 수행"""
    analysis = {}

    for ticker, info in TICKERS.items():
        # Firestore에서 해당 종목 데이터 조회 (최근 90일)
        docs = (
            db.collection(COLLECTION_NAME)
            .where("ticker", "==", ticker)
            .order_by("date", direction=firestore.Query.DESCENDING)
            .limit(90)
            .stream()
        )

        records = sorted([doc.to_dict() for doc in docs], key=lambda x: x["date"])

        if len(records) < 2:
            analysis[ticker] = {"name": info["name"], "status": "insufficient_data", "count": len(records)}
            continue

        closes = [r["close"] for r in records]
        dates = [r["date"] for r in records]

        # 기본 통계
        current = closes[-1]
        prev = closes[-2]
        daily_change = round(((current - prev) / prev) * 100, 2)

        # 이동평균
        ma5 = round(np.mean(closes[-5:]), 4) if len(closes) >= 5 else None
        ma20 = round(np.mean(closes[-20:]), 4) if len(closes) >= 20 else None
        ma60 = round(np.mean(closes[-60:]), 4) if len(closes) >= 60 else None

        # 일간 수익률 & 변동성
        returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
        volatility = round(np.std(returns) * np.sqrt(252) * 100, 2)  # 연율화 변동성(%)

        # 최고/최저
        high_90d = max(closes)
        low_90d = min(closes)
        drawdown = round(((current - high_90d) / high_90d) * 100, 2)

        # 추세 판단
        if ma5 and ma20:
            if ma5 > ma20:
                trend = "상승 추세 (5일MA > 20일MA)"
            else:
                trend = "하락 추세 (5일MA < 20일MA)"
        else:
            trend = "데이터 부족"

        # 시그널 (VIX 기준)
        signal = None
        if ticker == "^VIX":
            if current > 30:
                signal = "🔴 공포 극심 (VIX > 30)"
            elif current > 20:
                signal = "🟡 경계 (VIX 20~30)"
            else:
                signal = "🟢 안정 (VIX < 20)"

        analysis[ticker] = {
            "name": info["name"],
            "category": info["category"],
            "latest_date": dates[-1],
            "current_price": current,
            "daily_change_pct": daily_change,
            "ma5": ma5,
            "ma20": ma20,
            "ma60": ma60,
            "annualized_volatility_pct": volatility,
            "high_90d": high_90d,
            "low_90d": low_90d,
            "drawdown_from_high_pct": drawdown,
            "trend": trend,
            "signal": signal,
            "data_points": len(records),
        }

    # 카테고리별 상관관계 계산
    correlation = compute_correlation()
    
    return {"tickers": analysis, "correlation": correlation, "analyzed_at": datetime.utcnow().isoformat()}


def compute_correlation():
    """에너지·반도체 ETF 간 상관관계, VIX와의 역상관 분석"""
    all_data = {}

    for ticker in TICKERS:
        docs = (
            db.collection(COLLECTION_NAME)
            .where("ticker", "==", ticker)
            .order_by("date")
            .limit(60)
            .stream()
        )
        records = sorted([doc.to_dict() for doc in docs], key=lambda x: x["date"])
        if len(records) >= 10:
            all_data[ticker] = {r["date"]: r["close"] for r in records}

    if len(all_data) < 2:
        return {"status": "insufficient_data"}

    # 공통 날짜 기준으로 정렬
    common_dates = sorted(set.intersection(*[set(d.keys()) for d in all_data.values()]))
    if len(common_dates) < 10:
        return {"status": "insufficient_common_dates", "count": len(common_dates)}

    # 수익률 기반 상관관계
    returns_map = {}
    for ticker, prices in all_data.items():
        sorted_prices = [prices[d] for d in common_dates]
        rets = [(sorted_prices[i] - sorted_prices[i-1]) / sorted_prices[i-1] 
                for i in range(1, len(sorted_prices))]
        returns_map[ticker] = rets

    tickers_list = list(returns_map.keys())
    corr_results = {}
    for i in range(len(tickers_list)):
        for j in range(i+1, len(tickers_list)):
            t1, t2 = tickers_list[i], tickers_list[j]
            corr = round(float(np.corrcoef(returns_map[t1], returns_map[t2])[0, 1]), 4)
            corr_results[f"{t1} vs {t2}"] = corr

    return {"pairs": corr_results, "common_dates": len(common_dates)}


# ─── API 엔드포인트 ─────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "vix-etf-tracker"})


@app.route("/collect", methods=["POST"])
def collect():
    """데이터 수집 트리거 (Cloud Scheduler가 호출)"""
    logger.info("📊 데이터 수집 시작...")
    results = fetch_and_store()
    logger.info(f"수집 완료: {len(results['success'])}건 성공, {len(results['failed'])}건 실패")
    return jsonify(results), 200


@app.route("/analysis", methods=["GET"])
def analysis():
    """시계열 분석 결과 반환"""
    logger.info("📈 시계열 분석 시작...")
    result = analyze_timeseries()
    return jsonify(result), 200


@app.route("/data/<ticker>", methods=["GET"])
def get_ticker_data(ticker):
    """특정 종목의 시계열 데이터 반환"""
    days = request.args.get("days", 30, type=int)
    
    docs = (
        db.collection(COLLECTION_NAME)
        .where("ticker", "==", ticker)
        .order_by("date", direction=firestore.Query.DESCENDING)
        .limit(days)
        .stream()
    )
    
    records = sorted([doc.to_dict() for doc in docs], key=lambda x: x["date"])
    
    # datetime 직렬화 처리
    for r in records:
        if "collected_at" in r and hasattr(r["collected_at"], "isoformat"):
            r["collected_at"] = r["collected_at"].isoformat()
    
    return jsonify({"ticker": ticker, "count": len(records), "data": records}), 200


@app.route("/backfill", methods=["POST"])
def backfill():
    """과거 데이터 백필 (최초 셋업 시 사용)"""
    days = request.args.get("days", 90, type=int)
    results = {"success": [], "failed": []}

    for ticker, info in TICKERS.items():
        try:
            rows = fetch_yahoo(ticker, days=days)
            if not rows:
                results["failed"].append({"ticker": ticker, "reason": "no data"})
                continue

            batch = db.batch()
            count = 0
            for row in rows:
                doc_id = f"{ticker}_{row['date']}"
                record = {
                    "ticker": ticker,
                    "name": info["name"],
                    "category": info["category"],
                    "date": row["date"],
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": row["volume"],
                    "collected_at": datetime.utcnow().isoformat(),
                }
                batch.set(db.collection(COLLECTION_NAME).document(doc_id), record)
                count += 1

                if count % 400 == 0:
                    batch.commit()
                    batch = db.batch()

            batch.commit()
            results["success"].append({"ticker": ticker, "records": count})
            logger.info(f"✅ {ticker}: {count}건 백필 완료")
            time.sleep(1)  # 종목 간 간격

        except Exception as e:
            logger.error(f"❌ {ticker} 백필 실패: {e}")
            results["failed"].append({"ticker": ticker, "reason": str(e)})

    return jsonify(results), 200


# ─── 서버 실행 ──────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)