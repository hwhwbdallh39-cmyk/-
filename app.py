import os
import time
import sqlite3
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import pytz  # لضبط توقيت المملكة العربية السعودية
from flask import Flask, render_template_string, request, jsonify

APP_AUTHOR = "حقوق الطبع والتطوير محفوظة لـ: نجم- عبدالله علي هادي عاتي"
APP_VERSION = "v12.2.0 (KSA Timezone & Prominent Rights Edition)"
APP_NAME = "منصة التداول والتحليل الذكي العالمي"

app = Flask(__name__)
DB_PATH = "trading_platform.db"

# تحديد التوقيت المحلي لـ المملكة العربية السعودية
KSA_TZ = pytz.timezone('Asia/Riyadh')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT UNIQUE,
            market TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            target_price REAL,
            condition TEXT,
            is_active INTEGER DEFAULT 1
        )
    ''')
    conn.commit()
    conn.close()

init_db()

CACHE = {}
CACHE_TIMEOUT = 10

GLOBAL_MARKETS = [
    {"symbol": "^GSPC", "name_ar": "أس آند بي 500", "name_en": "S&P 500"},
    {"symbol": "^DJI", "name_ar": "داو جونز", "name_en": "Dow Jones"},
    {"symbol": "^IXIC", "name_ar": "ناسداك", "name_en": "Nasdaq"},
    {"symbol": "^TASI.SR", "name_ar": "تاسي السعودي", "name_en": "TASI"},
    {"symbol": "GC=F", "name_ar": "الذهب", "name_en": "Gold"},
    {"symbol": "SI=F", "name_ar": "الفضة", "name_en": "Silver"},
    {"symbol": "BZ=F", "name_ar": "نفط برنت", "name_en": "Brent Crude"},
    {"symbol": "BTC-USD", "name_ar": "بيتكوين", "name_en": "Bitcoin"}
]

POPULAR_TICKERS = {
    "GOLD": [
        {"symbol": "GC=F", "name_ar": "عقود الذهب", "name_en": "Gold Futures"},
        {"symbol": "SI=F", "name_ar": "عقود الفضة", "name_en": "Silver Futures"}
    ],
    "CRYPTO": [
        {"symbol": "BTC-USD", "name_ar": "بيتكوين", "name_en": "Bitcoin"},
        {"symbol": "ETH-USD", "name_ar": "إيثريوم", "name_en": "Ethereum"},
        {"symbol": "SOL-USD", "name_ar": "سولانا", "name_en": "Solana"},
        {"symbol": "BNB-USD", "name_ar": "بينانس كوين", "name_en": "BNB"},
        {"symbol": "XRP-USD", "name_ar": "ريبل", "name_en": "XRP"}
    ],
    "SA": [
        {"symbol": "2222.SR", "name_ar": "أرامكو", "name_en": "Aramco"},
        {"symbol": "1120.SR", "name_ar": "الراجحي", "name_en": "Al Rajhi"},
        {"symbol": "1180.SR", "name_ar": "الأهلي", "name_en": "SNB"},
        {"symbol": "2010.SR", "name_ar": "سابك", "name_en": "SABIC"},
        {"symbol": "7010.SR", "name_ar": "stc", "name_en": "stc"},
        {"symbol": "1211.SR", "name_ar": "معادن", "name_en": "Ma'aden"}
    ],
    "US": [
        {"symbol": "AAPL", "name_ar": "أبل", "name_en": "Apple"},
        {"symbol": "NVDA", "name_ar": "إنفيديا", "name_en": "Nvidia"},
        {"symbol": "MSFT", "name_ar": "مايكروسوفت", "name_en": "Microsoft"},
        {"symbol": "AMZN", "name_ar": "أمازون", "name_en": "Amazon"},
        {"symbol": "TSLA", "name_ar": "تيسلا", "name_en": "Tesla"}
    ]
}

def analyze_market_asset(ticker_symbol, market):
    cache_key = f"{ticker_symbol}_{market}"
    now = time.time()
    if cache_key in CACHE and (now - CACHE[cache_key]['time']) < CACHE_TIMEOUT:
        return CACHE[cache_key]['data']

    try:
        symbol = ticker_symbol.strip().upper()
        if market == 'SA' and not symbol.endswith('.SR'):
            symbol = f"{symbol}.SR"
        elif market == 'CRYPTO' and not symbol.endswith('-USD'):
            symbol = f"{symbol}-USD"
        elif market == 'GOLD' and symbol not in ['GC=F', 'SI=F', 'XAUUSD=X']:
            symbol = "GC=F"

        asset = yf.Ticker(symbol)
        df = asset.history(period="1y")

        if df.empty:
            return {"error_ar": "لم يتم العثور على بيانات، تأكد من الرمز.", "error_en": "No data found, check symbol."}

        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        df['SMA_50'] = df['Close'].rolling(window=50).mean()
        df['SMA_200'] = df['Close'].rolling(window=200).mean()

        std_20 = df['Close'].rolling(window=20).std()
        df['BB_Upper'] = df['SMA_20'] + (std_20 * 2)
        df['BB_Lower'] = df['SMA_20'] - (std_20 * 2)

        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()

        support = round(float(df['Low'].tail(30).min()), 2)
        resistance = round(float(df['High'].tail(30).max()), 2)
        latest_price = round(float(df['Close'].iloc[-1]), 2)
        latest_rsi = round(float(df['RSI'].iloc[-1]), 2)
        latest_macd = round(float(df['MACD'].iloc[-1]), 2)
        latest_signal = round(float(df['Signal_Line'].iloc[-1]), 2)
        sma_200 = round(float(df['SMA_200'].iloc[-1]), 2) if not np.isnan(df['SMA_200'].iloc[-1]) else "N/A"

        currency = "SAR" if market == 'SA' else ("USD" if market in ['US', 'CRYPTO'] else "USD/Oz")
        stop_loss = round(latest_price * 0.95, 2)
        target_1 = round(latest_price * 1.06, 2)
        target_2 = round(latest_price * 1.12, 2)

        swing_type = "محايد"
        swing_details = "السوق يتداول في نطاق عرضي، يُنصح بالانتظار وتحديد نقطة اختراق."
        best_time = "انتظار تأكيد الاتجاه"

        if latest_rsi < 35 and latest_macd > latest_signal:
            signal_ar, signal_en = "أفضل وقت للشراء (تجميع)", "Optimal Buy Zone"
            signal_badge = "buy"
            forecast_ar = "توقعات بارتفاع القيمة وانعكاس الاتجاه للأعلى بناءً على المؤشرات الفنية."
            forecast_en = "Bullish reversal expected soon."
            swing_type = "صفقة سوينج صاعدة (Long Swing)"
            swing_details = f"دخول آمن بالقرب من مستوى الدعم ({support}). الهدف الأول ({target_1}) والهدف الثاني ({target_2})."
            best_time = "الآن (شراء تدريجي مع الحفاظ على وقف الخسارة)"
        elif latest_rsi > 70 or (latest_price >= resistance * 0.98 and latest_macd < latest_signal):
            signal_ar, signal_en = "أفضل وقت للبيع (جني أرباح)", "Optimal Sell Zone"
            signal_badge = "sell"
            forecast_ar = "توقعات بانخفاض مؤقت وتراجع في السعر بسبب وصول السهم لمناطق تشبع شرائي."
            forecast_en = "Bearish correction expected soon."
            swing_type = "صفقة سوينج هابطة / جني أرباح"
            swing_details = f"الوصول لمناطق المقاومة ({resistance}). يُفضل تخفيف الكميات أو البيع وإعادة الشراء من مناطق أدنى."
            best_time = "الآن (تخفيف الكميات وجني الأرباح)"
        else:
            signal_ar, signal_en = "حالة استقرار (مراقبة)", "Hold / Neutral"
            signal_badge = "hold"
            forecast_ar = "تذبذب واستقرار مسار السعر في نطاق عرضي."
            forecast_en = "Price consolidating in a neutral range."

        chart_df = df.tail(30).fillna(0)
        dates = [d.strftime('%m-%d') for d in chart_df.index]
        prices = [round(p, 2) for p in chart_df['Close'].tolist()]
        sma20 = [round(p, 2) for p in chart_df['SMA_20'].tolist()]

        # الحصول على الوقت الحالي بتوقيت مكة المكرمة / السعودية
        ksa_now = datetime.now(KSA_TZ)
        last_updated_ksa = ksa_now.strftime("%I:%M:%S %p") + " (بتوقيت السعودية)"

        result = {
            "symbol": symbol,
            "market": market,
            "price": latest_price,
            "currency": currency,
            "rsi": latest_rsi,
            "support": support,
            "resistance": resistance,
            "stop_loss": stop_loss,
            "target_1": target_1,
            "target_2": target_2,
            "sma_200": sma_200,
            "signal_ar": signal_ar,
            "signal_en": signal_en,
            "signal_badge": signal_badge,
            "forecast_ar": forecast_ar,
            "forecast_en": forecast_en,
            "swing_type": swing_type,
            "swing_details": swing_details,
            "best_time": best_time,
            "chart_dates": dates,
            "chart_prices": prices,
            "chart_sma20": sma20,
            "last_updated": last_updated_ksa
        }

        CACHE[cache_key] = {'time': now, 'data': result}
        return result
    except Exception as e:
        return {"error_ar": f"حدث خطأ: {str(e)}", "error_en": f"Error: {str(e)}"}

def get_market_overview():
    res = []
    for m in GLOBAL_MARKETS:
        try:
            t = yf.Ticker(m["symbol"])
            h = t.history(period="2d")
            if len(h) >= 2:
                close = h['Close'].iloc[-1]
                prev = h['Close'].iloc[-2]
                change = round(((close - prev) / prev) * 100, 2)
                res.append({
                    "symbol": m["symbol"],
                    "name_ar": m["name_ar"],
                    "name_en": m["name_en"],
                    "price": round(close, 2),
                    "change": change
                })
        except:
            pass
    return res

MAIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl" id="htmlTag" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <title>{{ app_name }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://html2canvas.hertzen.com/dist/html2canvas.min.js"></script>
    <style>
        :root {
            --sat: env(safe-area-inset-top);
            --sab: env(safe-area-inset-bottom);
        }
        [data-theme="dark"] {
            --bg-color: #090d16;
            --card-bg: #161f30;
            --border-color: #243049;
            --text-main: #f1f5f9;
            --text-muted: #94a3b8;
            --accent-color: #38bdf8;
            --box-bg: #0d1424;
        }
        [data-theme="light"] {
            --bg-color: #f8fafc;
            --card-bg: #ffffff;
            --border-color: #e2e8f0;
            --text-main: #0f172a;
            --text-muted: #64748b;
            --accent-color: #0284c7;
            --box-bg: #f1f5f9;
        }
        * { -webkit-tap-highlight-color: transparent; user-select: none; }
        input, select, textarea { user-select: text !important; }
        body { 
            background-color: var(--bg-color); 
            color: var(--text-main); 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; 
            padding-top: var(--sat);
            padding-bottom: calc(90px + var(--sab)); 
            touch-action: manipulation;
        }
        .card-panel { background-color: var(--card-bg); border: 1px solid var(--border-color); border-radius: 16px; }
        .text-accent { color: var(--accent-color); }
        .btn-main { background-color: var(--accent-color); color: #fff; border: none; font-weight: 600; min-height: 50px; font-size: 1.05rem; border-radius: 12px; }
        .box-info { background-color: var(--box-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 12px; }
        .status-badge { font-size: 1.05rem; padding: 8px 22px; border-radius: 30px; display: inline-block; font-weight: bold; }
        .badge-buy { background-color: #10b981; color: #fff; }
        .badge-sell { background-color: #ef4444; color: #fff; }
        .badge-hold { background-color: #f59e0b; color: #fff; }
        
        .ticker-wrap { overflow: hidden; white-space: nowrap; background: var(--card-bg); border-bottom: 1px solid var(--border-color); font-size: 0.85rem; }
        .ticker { display: inline-block; animation: ticker 30s linear infinite; }
        @keyframes ticker { 0% { transform: translate3d(0, 0, 0); } 100% { transform: translate3d(-50%, 0, 0); } }

        /* تصميم كرت حقوق الطبع الفخم والبارز */
        .author-banner {
            background: linear-gradient(135deg, rgba(56, 189, 248, 0.2), rgba(16, 185, 129, 0.2));
            border: 2px solid var(--accent-color);
            border-radius: 20px;
            padding: 20px 15px;
            margin-top: 25px;
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.4);
            position: relative;
            overflow: hidden;
        }
        .author-banner::before {
            content: '';
            position: absolute;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 60%);
            pointer-events: none;
        }
        .author-title {
            font-size: 1.35rem;
            font-weight: 900;
            color: #ffffff;
            text-shadow: 0 2px 4px rgba(0,0,0,0.5);
            letter-spacing: 0.5px;
        }
        .author-badge {
            display: inline-block;
            background-color: var(--accent-color);
            color: #000;
            font-weight: bold;
            font-size: 0.8rem;
            padding: 3px 12px;
            border-radius: 12px;
            margin-bottom: 8px;
        }

        .mobile-nav {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background-color: var(--card-bg);
            border-top: 1px solid var(--border-color);
            display: flex;
            justify-content: space-around;
            padding-top: 8px;
            padding-bottom: calc(8px + var(--sab));
            z-index: 1000;
            backdrop-filter: blur(10px);
        }
        .mobile-nav button {
            background: none;
            border: none;
            color: var(--text-muted);
            font-size: 0.75rem;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 2px;
        }
        .mobile-nav button.active { color: var(--accent-color); font-weight: bold; }
        .btn-touch { min-height: 44px; border-radius: 10px; }
        .form-control, .form-select { min-height: 48px; font-size: 1rem; border-radius: 10px; }
        
        .pulse-dot {
            height: 8px;
            width: 8px;
            background-color: #10b981;
            border-radius: 50%;
            display: inline-block;
            box-shadow: 0 0 0 rgba(16, 185, 129, 0.4);
            animation: pulse 1.5s infinite;
        }
        @keyframes pulse {
            0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
            70% { box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
            100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
        }
    </style>
</head>
<body>

<div class="ticker-wrap py-2 px-2">
    <div class="ticker" id="marketTicker">جاري الاتصال بالأسواق العالمية...</div>
</div>

<div class="container py-3 px-3" style="max-width: 600px;">
    <div class="d-flex justify-content-between align-items-center mb-3">
        <div>
            <h4 class="fw-bold text-accent m-0" id="appTitle">{{ app_name }}</h4>
            <span class="small text-secondary"><span class="pulse-dot me-1"></span> تحديث آلي مباشر بتوقيت السعودية</span>
        </div>
        <button onclick="toggleTheme()" class="btn btn-sm btn-outline-secondary btn-touch px-3" id="themeBtn">🌙/☀️</button>
    </div>

    <div class="card-panel p-3 mb-3">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="small text-secondary fw-bold">⭐ المفضلة (Watchlist):</span>
            <button onclick="addCurrentToWatchlist()" class="btn btn-sm btn-outline-info" id="btnAddFav">+ إضافة</button>
        </div>
        <div id="watchlistContainer" class="d-flex flex-wrap gap-2"></div>
    </div>

    <div class="card-panel p-3 mb-3">
        <form id="searchForm">
            <div class="mb-2">
                <label class="form-label text-secondary small mb-1" id="lblMarket">اختر السوق</label>
                <select id="marketSelect" class="form-select bg-dark text-light border-secondary">
                    <option value="US">السوق الأمريكي (US)</option>
                    <option value="SA">السوق السعودي (TASI)</option>
                    <option value="CRYPTO">العملات الرقمية (Crypto)</option>
                    <option value="GOLD">الذهب والفضة (Gold/Silver)</option>
                </select>
            </div>

            <div class="mb-3">
                <label class="form-label text-secondary small mb-1" id="lblSymbol">رمز السهم / الأصل</label>
                <input type="text" id="tickerInput" class="form-control bg-dark text-light border-secondary" placeholder="AAPL, BTC, 2222, GC=F" required>
            </div>

            <div class="mb-3">
                <div id="quickSelectButtons" class="d-flex flex-wrap gap-1"></div>
            </div>

            <button type="submit" class="btn btn-main w-100 py-2" id="btnAnalyze">تحليل ودراسة الحالة 🚀</button>
        </form>
    </div>

    <div id="resultContainer" class="card-panel p-3 mb-4" style="display:none;">
        <div class="d-flex justify-content-between align-items-center pb-2 border-bottom border-secondary">
            <div>
                <h4 id="stockSymbol" class="m-0 text-accent fw-bold"></h4>
                <span class="text-secondary small">● آخر تحديث: <span id="lastUpdated" class="text-info fw-bold">--</span></span>
            </div>
            <div class="text-end">
                <h4 id="stockPrice" class="m-0 fw-bold"></h4>
                <button onclick="exportReport()" class="btn btn-sm btn-outline-success mt-1 py-0" style="font-size: 0.75rem;">📸 حفظ كصورة</button>
            </div>
        </div>

        <div class="text-center my-3">
            <span id="tradeSignal" class="status-badge"></span>
        </div>

        <div class="box-info mb-3">
            <div class="text-accent fw-bold small mb-1">💡 التوقيت الأفضل للتداول:</div>
            <div id="bestTimeText" class="small fw-bold text-warning"></div>
        </div>

        <div class="box-info mb-3">
            <div class="text-accent fw-bold small mb-1">🎯 تحليل صفقات السوينج المتوقعة (Swing Trading):</div>
            <div id="swingType" class="fw-bold text-light mb-1"></div>
            <div id="swingDetails" class="small text-secondary mb-2"></div>
            <div class="row g-2 text-center small">
                <div class="col-6"><span class="text-secondary">الهدف الأول:</span> <strong id="target1Val" class="text-success"></strong></div>
                <div class="col-6"><span class="text-secondary">الهدف الثاني:</span> <strong id="target2Val" class="text-success"></strong></div>
            </div>
        </div>

        <div class="box-info mb-3">
            <div class="text-accent fw-bold small mb-1">الاتجاه المتوقع ودراسة الحركة:</div>
            <div id="forecastText" class="small"></div>
        </div>

        <div class="box-info mb-3">
            <canvas id="priceChart" height="200"></canvas>
        </div>

        <div class="row text-center g-2 mb-3">
            <div class="col-6">
                <div class="box-info">
                    <span class="text-secondary d-block small">مستوى الدعم</span>
                    <strong id="supportVal" class="text-light"></strong>
                </div>
            </div>
            <div class="col-6">
                <div class="box-info">
                    <span class="text-secondary d-block small">مستوى المقاومة</span>
                    <strong id="resistanceVal" class="text-light"></strong>
                </div>
            </div>
            <div class="col-6">
                <div class="box-info">
                    <span class="text-secondary d-block small">SMA 200</span>
                    <strong id="sma200Val" class="text-light"></strong>
                </div>
            </div>
            <div class="col-6">
                <div class="box-info">
                    <span class="text-secondary d-block small">RSI</span>
                    <strong id="rsiVal" class="text-light"></strong>
                </div>
            </div>
        </div>

        <div class="box-info mb-3">
            <h6 class="text-accent fw-bold small mb-2">🔔 ضبط تنبيه سعر:</h6>
            <div class="row g-2">
                <div class="col-7">
                    <input type="number" step="0.01" id="alertPriceInput" class="form-control form-control-sm bg-dark text-light border-secondary" placeholder="السعر">
                </div>
                <div class="col-5">
                    <button onclick="setPriceAlert()" class="btn btn-sm btn-info w-100 btn-touch">تفعيل</button>
                </div>
            </div>
        </div>

        <div class="box-info">
            <h6 class="text-accent fw-bold small mb-2">📊 وقف الخسارة وإدارة السيولة:</h6>
            <div class="row g-2 align-items-center">
                <div class="col-12 mb-1">
                    <input type="number" id="capitalInput" class="form-control form-control-sm bg-dark text-light border-secondary" value="10000" oninput="calculateRisk()" placeholder="رأس المال">
                </div>
                <div class="col-6 small">
                    وقف الخسارة: <strong id="stopLossVal" class="text-danger"></strong>
                </div>
                <div class="col-6 small text-end">
                    الكمية: <strong id="sharesVal" class="text-info"></strong>
                </div>
            </div>
        </div>
    </div>

    <!-- التذييل البارز والواضح للحقوق -->
    <div class="author-banner text-center">
        <span class="author-badge">الملكية والبرمجة</span>
        <div class="author-title">{{ author }}</div>
        <div class="small text-secondary mt-1">{{ version }} | جميع الحقوق محفوظة</div>
    </div>
</div>

<div class="mobile-nav">
    <button onclick="window.scrollTo({top: 0, behavior: 'smooth'});" class="active">
        <span>🔍</span>
        <span>بحث</span>
    </button>
    <button onclick="document.getElementById('resultContainer').scrollIntoView({behavior: 'smooth'});">
        <span>📈</span>
        <span>التحليل</span>
    </button>
    <button onclick="fetchWatchlist();">
        <span>⭐</span>
        <span>المفضلة</span>
    </button>
    <button onclick="toggleLanguage();">
        <span>🌐</span>
        <span id="navLang">EN</span>
    </button>
</div>

<script>
const popularTickers = {{ popular_tickers|tojson }};
let currentLang = 'ar';
let autoRefreshTimer = null;
let chartInstance = null;
let currentData = null;

function toggleTheme() {
    const html = document.getElementById('htmlTag');
    const theme = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', theme);
}

function toggleLanguage() {
    currentLang = currentLang === 'ar' ? 'en' : 'ar';
    document.getElementById('htmlTag').dir = currentLang === 'ar' ? 'rtl' : 'ltr';
    document.getElementById('navLang').innerText = currentLang === 'ar' ? 'EN' : 'عربي';
    updateQuickButtons();
    loadMarketOverview();
    if(currentData) renderResults(currentData);
}

async function loadMarketOverview() {
    try {
        const res = await fetch('/api/market_overview');
        const data = await res.json();
        let text = "";
        data.forEach(item => {
            const name = currentLang === 'ar' ? item.name_ar : item.name_en;
            const color = item.change >= 0 ? '#10b981' : '#ef4444';
            const sign = item.change >= 0 ? '+' : '';
            text += `<span class="me-4">${name}: <strong>${item.price}</strong> <span style="color:${color}">(${sign}${item.change}%)</span></span> `;
        });
        document.getElementById('marketTicker').innerHTML = text + text;
    } catch(e){}
}

loadMarketOverview();
setInterval(loadMarketOverview, 10000);

async function fetchWatchlist() {
    const res = await fetch('/api/watchlist');
    const data = await res.json();
    const container = document.getElementById('watchlistContainer');
    container.innerHTML = '';
    data.forEach(item => {
        const btn = document.createElement('button');
        btn.className = 'btn btn-sm btn-dark text-info border-secondary me-1 mb-1 btn-touch';
        btn.innerText = `${item.symbol} ✖`;
        btn.onclick = (e) => {
            if(e.offsetX > btn.offsetWidth - 25) {
                removeFromWatchlist(item.symbol);
            } else {
                document.getElementById('marketSelect').value = item.market;
                document.getElementById('tickerInput').value = item.symbol;
                fetchAnalysis();
            }
        };
        container.appendChild(btn);
    });
}

async function addCurrentToWatchlist() {
    if(!currentData) return;
    await fetch('/api/watchlist', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({symbol: currentData.symbol, market: currentData.market})
    });
    fetchWatchlist();
}

async function removeFromWatchlist(symbol) {
    await fetch(`/api/watchlist?symbol=${symbol}`, { method: 'DELETE' });
    fetchWatchlist();
}

async function setPriceAlert() {
    const price = parseFloat(document.getElementById('alertPriceInput').value);
    if(!currentData || !price) return;
    await fetch('/api/alerts', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({symbol: currentData.symbol, price: price, condition: 'ABOVE'})
    });
    alert('تم تفعيل التنبيه');
}

async function fetchAnalysis() {
    const symbol = document.getElementById('tickerInput').value;
    const market = document.getElementById('marketSelect').value;
    if(!symbol) return;

    const response = await fetch(`/api/analyze?symbol=${symbol}&market=${market}`);
    const data = await response.json();

    if(data.error_ar) {
        alert(data.error_ar);
        return;
    }

    currentData = data;
    renderResults(data);

    if(autoRefreshTimer) clearInterval(autoRefreshTimer);
    autoRefreshTimer = setInterval(fetchAnalysis, 10000);
}

function renderResults(data) {
    document.getElementById('stockSymbol').innerText = data.symbol;
    document.getElementById('stockPrice').innerText = `${data.price} ${data.currency}`;
    document.getElementById('lastUpdated').innerText = data.last_updated;
    
    const signalElem = document.getElementById('tradeSignal');
    signalElem.innerText = currentLang === 'ar' ? data.signal_ar : data.signal_en;
    signalElem.className = "status-badge badge-" + data.signal_badge;

    document.getElementById('bestTimeText').innerText = data.best_time;
    document.getElementById('swingType').innerText = data.swing_type;
    document.getElementById('swingDetails').innerText = data.swing_details;
    document.getElementById('target1Val').innerText = `${data.target_1} ${data.currency}`;
    document.getElementById('target2Val').innerText = `${data.target_2} ${data.currency}`;

    document.getElementById('forecastText').innerText = currentLang === 'ar' ? data.forecast_ar : data.forecast_en;
    document.getElementById('supportVal').innerText = `${data.support}`;
    document.getElementById('resistanceVal').innerText = `${data.resistance}`;
    document.getElementById('sma200Val').innerText = data.sma_200;
    document.getElementById('rsiVal').innerText = data.rsi;

    calculateRisk();
    renderChart(data.chart_dates, data.chart_prices, data.chart_sma20);

    document.getElementById('resultContainer').style.display = 'block';
}

function renderChart(dates, prices, sma) {
    const ctx = document.getElementById('priceChart').getContext('2d');
    if(chartInstance) chartInstance.destroy();

    chartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: dates,
            datasets: [
                { label: 'السعر', data: prices, borderColor: '#38bdf8', borderWidth: 2, pointRadius: 1 },
                { label: 'SMA 20', data: sma, borderColor: '#f59e0b', borderWidth: 1, borderDash: [3, 3], pointRadius: 0 }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { ticks: { color: '#94a3b8', font: { size: 9 } }, grid: { display: false } },
                y: { ticks: { color: '#94a3b8', font: { size: 9 } }, grid: { color: '#243049' } }
            }
        }
    });
}

function calculateRisk() {
    if(!currentData) return;
    const capital = parseFloat(document.getElementById('capitalInput').value) || 0;
    const shares = Math.floor(capital / currentData.price);
    document.getElementById('stopLossVal').innerText = `${currentData.stop_loss}`;
    document.getElementById('sharesVal').innerText = shares > 0 ? shares : 0;
}

function exportReport() {
    html2canvas(document.getElementById('resultContainer')).then(canvas => {
        const link = document.createElement('a');
        link.download = `Analysis_${currentData.symbol}.png`;
        link.href = canvas.toDataURL();
        link.click();
    });
}

function updateQuickButtons() {
    const market = document.getElementById('marketSelect').value;
    const container = document.getElementById('quickSelectButtons');
    container.innerHTML = '';
    
    popularTickers[market].forEach(item => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn btn-outline-secondary btn-sm text-light me-1 mb-1 btn-touch';
        btn.innerText = item.name_ar;
        btn.onclick = () => {
            document.getElementById('tickerInput').value = item.symbol;
            fetchAnalysis();
        };
        container.appendChild(btn);
    });
}

document.getElementById('marketSelect').addEventListener('change', updateQuickButtons);
updateQuickButtons();
fetchWatchlist();

document.getElementById('searchForm').addEventListener('submit', function(e) {
    e.preventDefault();
    fetchAnalysis();
});
</script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(MAIN_TEMPLATE, app_name=APP_NAME, author=APP_AUTHOR, version=APP_VERSION, popular_tickers=POPULAR_TICKERS)

@app.route('/api/analyze', methods=['GET'])
def api_analyze():
    symbol = request.args.get('symbol', '')
    market = request.args.get('market', 'US')
    if not symbol:
        return jsonify({"error_ar": "يرجى كتابة الرمز", "error_en": "Please enter symbol"}), 400
    data = analyze_market_asset(symbol, market)
    return jsonify(data)

@app.route('/api/market_overview', methods=['GET'])
def api_market_overview():
    return jsonify(get_market_overview())

@app.route('/api/watchlist', methods=['GET', 'POST', 'DELETE'])
def api_watchlist():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if request.method == 'GET':
        cursor.execute("SELECT symbol, market FROM watchlist")
        rows = cursor.fetchall()
        conn.close()
        return jsonify([{"symbol": r[0], "market": r[1]} for r in rows])
    elif request.method == 'POST':
        data = request.json
        try:
            cursor.execute("INSERT INTO watchlist (symbol, market) VALUES (?, ?)", (data['symbol'], data['market']))
            conn.commit()
        except:
            pass
        conn.close()
        return jsonify({"success": True})
    elif request.method == 'DELETE':
        symbol = request.args.get('symbol')
        cursor.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})

@app.route('/api/alerts', methods=['GET', 'POST'])
def api_alerts():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if request.method == 'POST':
        data = request.json
        cursor.execute("INSERT INTO alerts (symbol, target_price, condition) VALUES (?, ?, ?)", 
                       (data['symbol'], data['price'], data['condition']))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    else:
        symbol = request.args.get('symbol')
        cursor.execute("SELECT id, symbol, target_price, condition FROM alerts WHERE symbol = ? AND is_active = 1", (symbol,))
        rows = cursor.fetchall()
        conn.close()
        return jsonify([{"id": r[0], "symbol": r[1], "target_price": r[2], "condition": r[3]} for r in rows])

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
