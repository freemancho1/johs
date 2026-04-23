# MPP: Muse Pulse Project

우리나라 주식시장에서 AI를 이용해 특정 주식의 미래 가격을 예측하고, 실시간으로 매도·매수 시기를 자동으로 판단하여 매매를 자동화하는 시스템을 개발하는 프로젝트로
> MP는 시장 참여자의 `뮤즈(Muse, 아이디어·심리·의도)`에서 살아있는 `펄스(Pulse, 맥박·맥락)`을 짚어낸다는 뜻으로, `참여자의 심리를 바로 찾아 거래를 주도한다`는 의미임

<br/>

## 프로젝트 개요 (Overview)

과거 다양한 데이터(`STEP-1. 데이터 수집` 참조)와 인공지능을 이용해 단일 종목을 대상으로 `예측 모델`, `타이밍 모델` 및 `집행 모델`을 학습해 실시간 매매를 통해 수익창출을 목적으로 하는 시스템을 개발하는 프로젝트로, 주요 기능은 다음과 같다.

### STEP-1. 데이터 수집

아래 표시된 데이터는 인터넷 상에서 무료로 접근 가능한 데이터를 기반으로 정리함

#### 1-1. 모델 학습용 데이터 (과거 데이터)

| 구분 | 데이터 | 출처 |
|:---|:---|:---|
|1-1-1.<br>가격·거래 데이터 | · 일봉 OHLCV <br> · 분봉 OHLCV (1/5/15/30/60분) <br> · 수정 주가 <br> · 상장·상폐 이력 <br> · 거래정지 이력 <br> · 공매도 잔고·대차잔고 | ⇒ pykrx, FinanceDataReader, yfinance <br> ⇒ pykrx (최근분), 네이버 금융 크롤링 <br> ⇒ FinanceDataReader, yfinance <br> ⇒ pykrx, krx 정보데이터시스템 <br> ⇒ KRX 정보데이터시스템 크롤링 <br> ⇒ KRX 정보데이터시스템 |
|1-1-2.<br>수급 데이터 | · 투자자별 일별 순매수 <br> · 프로그램 매매 (차익·비차익) <br> · 외국인 지분율 추이 <br> | ⇒ pykrx <br> ⇒ pykrx, KRX <br> ⇒ pykrx <br> | 
|1-1-3.<br>재무·펀드멘털| · 분기·연간 재무제표 <br> · 주요 재무비율 (PER/PBR/ROE) <br> · 배당 이력 <br> · 유·무상 증자 이력 <br> | ⇒ DART Open API <br> ⇒ FinanceDataReader, DART <br> ⇒ DART, pykrx <br> ⇒ DART <br> | 
|1-1-4.<br>공시·이벤트| · 전체 공시 이력 <br> · 주요 사항 보고서 (합병·분할·증자) <br> · 내부자 거래 (임원·주요주주) <br> · 실적 공시 <br> | ⇒ DART Open API <br> ⇒ DART <br> ⇒ DART <br> ⇒ DART <br> | 
|1-1-5.<br>뉴스·텍스트·<br>사전학습 모델| · 네이버 금융 뉴스 <br> · 연합뉴스 경제 섹션 <br> · 이데일리·뉴시스 경제 <br> · 한경컨센서스 리포트 <br> · KR-FinBert 모델 <br> | ⇒ 네이버 크롤링 <br> ⇒ RSS + 크롤링 <br> ⇒ RSS <br> ⇒ 크롤링 <br> ⇒ Hugging Face Download <br> | 
|1-1-6.<br>거시경제 지표|· 한국 금리·물가·환율·고용<br>· 미국 금리·CPI·고용·PCE<br>· OECD 경기 선행지수<br>· 국제 거시지표<br>· 원자재 가격 (WTI, 구리, 금)<br>· 달러 인덱스 (DXY)<br>|⇒ ECOS (한국은행) API<br>⇒ FRED API<br>⇒ OECD data API<br>⇒ World Bank (wbgapi)<br>⇒ yfinance (선물 티커), FRED<br>⇒ yfinance<br>| 
|1-1-7.<br>시장·섹터 데이터|· KOSPI·KOSPI200·KOSDAQ<br>· 업종·섹터 지수<br>· 섹터 ETF 시계열<br>· 해외 지수 (S&P500, Nasdaq..)<br>· VIX<br>· V-KOSPI<br>|⇒ pykrx, FinanceDataReader<br>⇒ pykrx<br>⇒ pykrx, FinanceDataReader<br>⇒ yfinance<br>⇒ yfinance<br>⇒ KRX 정보데이터시스템<br>| 
|1-1-8.<br>파생상품 데이터|· KOSPI200 선물 일봉<br>· Put/Call Ratio<br>|⇒ pykrx, FinanceDataReader<br>⇒ KRX 정보데이터시스템<br>| 
|1-1-9.<br>대안 데이터|· Google Trends<br>· 네이버 데이터랩 검색 드렌드<br>|⇒ pytrends 라이브러리<br>⇒ 네이버 개발자 API<br>|

#### 1-2. 실시간 데이터
실시간 영역의 데이터는 모델 학습용으로 수집한 과거 데이터보다 제약조건이 많아 종류나 양 측면에서 현저히 적음

| 구분 | 데이터 | 출처 |
|:---|:---|:---|
|1-2-1.<br>실시간 시세 |· 체결가·체결량·호가 스트림<br>· 호가 (1~10호가)<br>· 일중 VWAP·체결 강도<br>|⇒ KIS Open API<br>⇒ KIS Websocket<br>⇒ 직접 계산<br>|
|1-2-2.<br>실시간 시장 전체 |· KOSPI·KOSPI200 실시간 지수<br>· KOSPI200 선물 실시간<br>· 투자자별 실시간 추정 순매수<br>· 원/달러 실시간 환율<br>|⇒ KIS Websocket<br>⇒ KIS Websocket<br>⇒ KIS Websocket, 네이버 금융<br>⇒ KIS Websocket, 네이버 금융<br>|
|1-2-3.<br>실시간 해외 마켓 |· S&P500·Nasdaq 선물<br>· SOX 지수<br>· 삼성전자 ADR (야간)<br>· 원자재 실시간<br>|⇒ yfinance (15분 지연, 실시간은 유료)<br>⇒ yfinance (지연)<br>⇒ yfinance (지연)<br>⇒ yfinance (지연)<br>|
|1-2-4.<br> 실시간 공시·시장 조치 |· **DART 공시 실시간**<br>· KRX 시장 조치<br>· 거래 정지<br>|⇒ DART Open API 폴링(무료, 분 단위)<br>⇒ KRX 정보데이터 크롤링<br>⇒ KRX, 증권사 API<br>|
|1-2-5.<br>실시간 뉴스·속보 |· 연합뉴스 RSS<br>· 이데일리·뉴시스<br>· 네이버 금융 뉴스<br>· 경제지표 캘린더<br>|⇒ RSS 폴링<br>⇒ RSS 폴링<br>⇒ 크롤링<br>⇒ Investing.com 크롤링<br>|
|1-2-6.<br> 실시간 계좌·주문 상태 |· 체결 통보<br>· 미체결 주문·잔고·증거금<br>· 실시간 PnL<br>|⇒ KIS Websocket<br>⇒ KIS REST API<br>⇒ 직접 계산<br>| 
|1-2-7.<br> 실시간 파생 피처|· KIS 호가, VWAP 등<br>|⇒ 원천 데이터를 이용 직접 계산<br>|
|1-2-8.<br> 대안 실시간 데이터|· Google Trends (일단위)<br>· 네이버 종목 토론실<br>· X(Twitter) API<br>|⇒ pytrends (진짜 실시간은 아님)<br>⇒ 크롤링 (5~15분 단위)<br>⇒ 사실상 유료<br>| 

* KIS Open API가 국내 무료 실시간 시세의 사실상 표준으로, 계좌만 있으면 모의투자·실전 모두 무료이지만 **초당 호출 제한이 있어 구독 종목 수가 제한됨(보통 40종목 수준)**
* 해외 실시간 데이터는 장이 열리는 시간이 미국과 한국이 다르기 때문에 15분 지연은 문제가 되지 않지만, **미국 선물이나 야간 거래에 대한 자료는 15분 지연값이라도 필요**하니 가져올 필요가 있음

#### 1-3. 보조 데이터

| 구분 | 데이터 | 출처 |
|:---|:---|:---|
|1-3-1.<br>보조 데이터 |· 거래일·휴장일 캘린더<br>· 종목 마스터 (코드·명·업종)<br>· 시가총액·상장 주식수<br>· 지수 편입 종목 리스트<br>|⇒ pykrx, exchange_calendars<br>⇒ pykrx, FinanceDataReader, KRX<br>⇒ pykrx<br>⇒ pykrx (KOSPI200 등)<br>|

### STEP-2. 데이터 전처리




<br>

---
*Last updated⇒ 2026-04-23 18:00 freeman.cho@gmail.com*
