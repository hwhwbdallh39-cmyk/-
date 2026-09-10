import os
import time
import sqlite3
import yfinance as yf
import pandas as pd
import numpy as np
from flask import Flask, render_template_string, request, jsonify

APP_AUTHOR = "حقوق الطبع والتطوير محفوظة لـ: عبدالله علي هادي عاتي"
APP_VERSION = "v8.0.0 (Pro Enterprise Edition)"
APP_NAME = "منصة التحليل والتداول الذكي"

app = Flask(__name__)

DB_PATH = "trading_platform.db"

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
CACHE_TIMEOUT = 15

POPULAR_TICKERS = {
    "GOLD": [
        {"symbol": "GC=F", "name_ar": "عقود الذهب", "name_en": "Gold Futures"},
        {"symbol": "SI=F", "name_ar": "عقود الفضة", "name_en": "Silver Futures"}
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
        elif market == 'GOLD' and symbol not in ['GC=F', 'SI=F', 'XAUUSD=X']:
            symbol = "GC=F"

        asset = yf.Ticker(symbol)
        df = asset.history(period="1y")

        if df.empty:
            return {"error_ar": "لم يتم العثور على بيانات، تأكد من الرمز.", "error_en": "No data found, check symbol."}

        # حساب المؤشرات الفنية المتقدمة
        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        df['SMA_50'] = df['Close'].rolling(window=50).mean()
        df['SMA_200'] = df['Close'].rolling(window=200).mean()

        # Bollinger Bands
        std_20 = df['Close'].rolling(window=20).std()
        df['BB_Upper'] = df['SMA_20'] + (std_20 * 2)
        df['BB_Lower'] = df['SMA_20'] - (std_20 * 2)

        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        # MACD
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
        bb_upper = round(float(df['BB_Upper'].iloc[-1]), 2)
        bb_lower = round(float(df['BB_Lower'].iloc[-1]), 2)

        currency = "SAR" if market == 'SA' else ("USD" if market == 'US' else "USD/Oz")
        stop_loss = round(latest_price * 0.96, 2)
        
        if latest_rsi < 35 and latest_macd > latest_signal:
            signal_ar, signal_en = "مناسب للشراء (تجميع)", "Strong Buy"
            signal_badge = "buy"
            forecast_ar = "توقعات بارتفاع القيمة وانعكاس الاتجاه للأعلى."
            forecast_en = "Bullish reversal expected soon."
        elif latest_rsi > 70 or (latest_price >= resistance * 0.98 and latest_macd < latest_signal):
            signal_ar, signal_en = "مناسب للبيع (جني أرباح)", "Strong Sell"
            signal_badge = "sell"
            forecast_ar = "توقعات بانخفاض مؤقت وتراجع في السعر."
            forecast_en = "Bearish correction expected soon."
        else:
            signal_ar, signal_en = "حالة استقرار (انتظار)", "Hold / Neutral"
            signal_badge = "hold"
            forecast_ar = "تذبذب واستقرار مسار السعر في نطاق عرضي."
            forecast_en = "Price consolidating in a neutral range."

        chart_df = df.tail(40).fillna(0)
        dates = [d.strftime('%Y-%m-%d') for d in chart_df.index]
        prices = [round(p, 2) for p in chart_df['Close'].tolist()]
        sma20 = [round(p, 2) for p in chart_df['SMA_20'].tolist()]
        bb_u = [round(p, 2) for p in chart_df['BB_Upper'].tolist()]
        bb_l = [round(p, 2) for p in chart_df['BB_Lower'].tolist()]

        result = {
            "symbol": symbol,
            "market": market,
            "price": latest_price,
            "currency": currency,
            "rsi": latest_rsi,
            "macd": latest_macd,
            "support": support,
            "resistance": resistance,
            "stop_loss": stop_loss,
            "sma_200": sma_200,
            "bb_upper": bb_upper,
            "bb_lower": bb_lower,
            "signal_ar": signal_ar,
            "signal_en": signal_en,
            "signal_badge": signal_badge,
            "forecast_ar": forecast_ar,
            "forecast_en": forecast_en,
            "chart_dates": dates,
            "chart_prices": prices,
            "chart_sma20": sma20,
            "chart_bb_upper": bb_u,
            "chart_bb_lower": bb_l
        }

        CACHE[cache_key] = {'time': now, 'data': result}
        return result
    except Exception as e:
        return {"error_ar": f"حدث خطأ: {str(e)}", "error_en": f"Error: {str(e)}"}

def get_market_overview():
    tickers = {"S&P 500": "^GSPC", "الذهب": "GC=F", "نفط برنت": "BZ=F", "تاسي": "^TASI"}
    res = []
    for name, sym in tickers.items():
        try:
            t = yf.Ticker(sym)
            h = t.history(period="2d")
            if len(h) >= 2:
                close = h['Close'].iloc[-1]
                prev = h['Close'].iloc[-2]
                change = round(((close - prev) / prev) * 100, 2)
                res.append({"name": name, "price": round(close, 2), "change": change})
        except:
            pass
    return res

MAIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl" id="htmlTag" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ app_name }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://html2canvas.hertzen.com/dist/html2canvas.min.js"></script>
    <style>
        [data-theme="dark"] {
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --border-color: #334155;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent-color: #38bdf8;
            --box-bg: #0f172a;
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
        body { background-color: var(--bg-color); color: var(--text-main); font-family: system-ui, -apple-system, sans-serif; transition: all 0.3s ease; }
        .card-panel { background-color: var(--card-bg); border: 1px solid var(--border-color); border-radius: 12px; }
        .text-accent { color: var(--accent-color); }
        .btn-main { background-color: var(--accent-color); color: #fff; border: none; font-weight: 600; }
        .box-info { background-color: var(--box-bg); border: 1px solid var(--border-color); border-radius: 8px; padding: 12px; }
        .status-badge { font-size: 1.1rem; padding: 6px 16px; border-radius: 20px; display: inline-block; font-weight: bold; }
        .badge-buy { background-color: #10b981; color: #fff; }
        .badge-sell { background-color: #ef4444; color: #fff; }
        .badge-hold { background-color: #f59e0b; color: #fff; }
        .ticker-wrap { overflow: hidden; white-space: nowrap; background: var(--card-bg); border-bottom: 1px solid var(--border-color); }
        .ticker { display: inline-block; animation: ticker 25s linear infinite; }
        @keyframes ticker { 0% { transform: translate3d(0, 0, 0); } 100% { transform: translate3d(-50%, 0, 0); } }
    </style>
</head>
<body>

<!-- شريط أسعار الماركت المتحرك -->
<div class="ticker-wrap py-2 px-3 small">
    <div class="ticker" id="marketTicker">جاري تحصيل بيانات المؤشرات...</div>
</div>

<div class="container py-4" style="max-width: 900px;">
    <!-- خيارات الصفحة -->
    <div class="d-flex justify-content-between align-items-center mb-3">
        <div>
            <button id="langToggleBtn" onclick="toggleLanguage()" class="btn btn-outline-secondary btn-sm">English</button>
            <button onclick="toggleTheme()" class="btn btn-outline-secondary btn-sm ms-1" id="themeBtn">☀️/🌙</button>
        </div>
        <span class="text-secondary small" id="lblAutoRefresh">● تحديث آلي ومباشر</span>
    </div>

    <!-- الهيدر -->
    <div class="text-center mb-4">
        <h2 class="fw-bold text-accent mb-1" id="appTitle">{{ app_name }}</h2>
        <p class="text-secondary small" id="appSubTitle">تحليل فني احترافي، تنبيهات أسعار، وربط دائم بالبيانات</p>
    </div>

    <!-- قائمة المفضلة من السيرفر -->
    <div class="card-panel p-3 mb-3">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="small text-secondary fw-bold" id="lblWatchlist">⭐ المفضلة (SQLite DB):</span>
            <button onclick="addCurrentToWatchlist()" class="btn btn-sm btn-outline-info" id="btnAddFav">+ إضافة للمفضلة</button>
        </div>
        <div id="watchlistContainer" class="d-flex flex-wrap gap-2"></div>
    </div>

    <!-- بطاقة البحث والتحديد -->
    <div class="card-panel p-4 mb-4">
        <form id="searchForm">
            <div class="row g-3">
                <div class="col-md-5">
                    <label class="form-label text-secondary small" id="lblMarket">السوق / الأصل</label>
                    <select id="marketSelect" class="form-select bg-dark text-light border-secondary">
                        <option value="US">السوق الأمريكي</option>
                        <option value="SA">السوق السعودي</option>
                        <option value="GOLD">سوق الذهب والفضة</option>
                    </select>
                </div>
                <div class="col-md-7">
                    <label class="form-label text-secondary small" id="lblSymbol">الرمز</label>
                    <input type="text" id="tickerInput" class="form-control bg-dark text-light border-secondary" placeholder="AAPL, 2222, GC=F" required>
                </div>
            </div>

            <div class="mt-3">
                <div id="quickSelectButtons" class="d-flex flex-wrap gap-2"></div>
            </div>

            <div class="d-flex gap-2 mt-3">
                <button type="submit" class="btn btn-main flex-grow-1 py-2" id="btnAnalyze">تحليل الآن</button>
                <button type="button" onclick="fetchAnalysis()" class="btn btn-outline-secondary py-2">🔄</button>
            </div>
        </form>
    </div>

    <!-- لوحة النتائج التفاعلية -->
    <div id="resultContainer" class="card-panel p-4 mb-4" style="display:none;">
        <div class="d-flex justify-content-between align-items-center pb-3 border-bottom border-secondary">
            <div>
                <h3 id="stockSymbol" class="m-0 text-accent fw-bold"></h3>
            </div>
            <div class="text-end">
                <h3 id="stockPrice" class="m-0 fw-bold"></h3>
                <button onclick="exportReport()" class="btn btn-sm btn-outline-success mt-1">📸 حفظ التقرير كصورة</button>
            </div>
        </div>

        <div class="text-center my-4">
            <div class="small text-secondary mb-1" id="lblSignalHeader">الإشارة الحالية:</div>
            <span id="tradeSignal" class="status-badge"></span>
        </div>

        <!-- التوقعات -->
        <div class="box-info mb-3">
            <div class="text-accent fw-bold mb-1" id="lblForecastHeader">الاتجاه والتوقعات:</div>
            <div id="forecastText" class="small"></div>
        </div>

        <!-- الرسم البياني التفاعلي مع Bollinger Bands -->
        <div class="box-info mb-4">
            <canvas id="priceChart" height="150"></canvas>
        </div>

        <!-- أرقام الدعم والمقاومة والمؤشرات -->
        <div class="row text-center g-2 mb-4">
            <div class="col-6 col-md-3">
                <div class="box-info">
                    <span class="text-secondary d-block small" id="lblSupport">الدعم</span>
                    <strong id="supportVal"></strong>
                </div>
            </div>
            <div class="col-6 col-md-3">
                <div class="box-info">
                    <span class="text-secondary d-block small" id="lblResistance">المقاومة</span>
                    <strong id="resistanceVal"></strong>
                </div>
            </div>
            <div class="col-6 col-md-3">
                <div class="box-info">
                    <span class="text-secondary d-block small">SMA 200</span>
                    <strong id="sma200Val"></strong>
                </div>
            </div>
            <div class="col-6 col-md-3">
                <div class="box-info">
                    <span class="text-secondary d-block small">RSI</span>
                    <strong id="rsiVal"></strong>
                </div>
            </div>
        </div>

        <!-- نظام تنبيهات الأسعار -->
        <div class="box-info mb-3">
            <h6 class="text-accent fw-bold mb-2">🔔 تنبيه سعر مخصص (Price Alert):</h6>
            <div class="row g-2">
                <div class="col-md-5">
                    <input type="number" step="0.01" id="alertPriceInput" class="form-control form-control-sm bg-dark text-light border-secondary" placeholder="ادخل السعر المستهدف">
                </div>
                <div class="col-md-4">
                    <select id="alertCondition" class="form-select form-select-sm bg-dark text-light border-secondary">
                        <option value="ABOVE">إذا ارتفع أعلى من السعر</option>
                        <option value="BELOW">إذا انخفض أقل من السعر</option>
                    </select>
                </div>
                <div class="col-md-3">
                    <button onclick="setPriceAlert()" class="btn btn-sm btn-info w-100">تفعيل التنبيه</button>
                </div>
            </div>
            <div id="activeAlertsList" class="mt-2 small text-secondary"></div>
        </div>

        <!-- حاسبة إدارة المخاطر -->
        <div class="box-info">
            <h6 class="text-accent fw-bold mb-2" id="lblRiskCalc">📊 حاسبة إدارة المخاطر ووقف الخسارة:</h6>
            <div class="row g-2 align-items-center">
                <div class="col-md-6">
                    <label class="form-label text-secondary small m-0" id="lblCapital">رأس المال المخصص للصفقة:</label>
                    <input type="number" id="capitalInput" class="form-control form-control-sm bg-dark text-light border-secondary mt-1" value="10000" oninput="calculateRisk()">
                </div>
                <div class="col-md-6">
                    <div class="small">
                        <div><span id="lblStopLoss">وقف الخسارة المقترح (4%):</span> <strong id="stopLossVal" class="text-danger"></strong></div>
                        <div><span id="lblShares">عدد الأسهم/الوحدات:</span> <strong id="sharesVal" class="text-info"></strong></div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- الفوتر -->
    <div class="text-center mt-4 text-secondary small">
        <p class="m-0">{{ author }}</p>
        <span>{{ version }}</span>
    </div>
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

async function loadMarketOverview() {
    const res = await fetch('/api/market_overview');
    const data = await res.json();
    let text = "";
    data.forEach(item => {
        const color = item.change >= 0 ? '#10b981' : '#ef4444';
        text += `<span class="me-4">${item.name}: <strong>${item.price}</strong> <span style="color:${color}">(${item.change}%)</span></span> `;
    });
    document.getElementById('marketTicker').innerHTML = text + text;
}
loadMarketOverview();
setInterval(loadMarketOverview, 60000);

async function fetchWatchlist() {
    const res = await fetch('/api/watchlist');
    const data = await res.json();
    const container = document.getElementById('watchlistContainer');
    container.innerHTML = '';
    data.forEach(item => {
        const btn = document.createElement('button');
        btn.className = 'btn btn-sm btn-dark text-info border-secondary me-1 mb-1';
        btn.innerText = `${item.symbol} ✖`;
        btn.onclick = (e) => {
            if(e.offsetX > btn.offsetWidth - 20) {
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
    const cond = document.getElementById('alertCondition').value;
    if(!currentData || !price) return;

    await fetch('/api/alerts', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({symbol: currentData.symbol, price: price, condition: cond})
    });
    alert('تم إضافة التنبيه بنجاح');
    checkAlerts();
}

async function checkAlerts() {
    if(!currentData) return;
    const res = await fetch(`/api/alerts?symbol=${currentData.symbol}`);
    const alerts = await res.json();
    alerts.forEach(a => {
        if((a.condition === 'ABOVE' && currentData.price >= a.target_price) || 
           (a.condition === 'BELOW' && currentData.price <= a.target_price)) {
            playAlertSound();
            alert(`🚨 تنبيه سعر! السهم ${a.symbol} وصل إلى السعر المستهدف ${a.target_price}`);
        }
    });
}

function playAlertSound() {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    osc.frequency.setValueAtTime(1000, ctx.currentTime);
    osc.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.5);
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
    checkAlerts();

    if(autoRefreshTimer) clearInterval(autoRefreshTimer);
    autoRefreshTimer = setInterval(fetchAnalysis, 15000);
}

function renderResults(data) {
    document.getElementById('stockSymbol').innerText = data.symbol;
    document.getElementById('stockPrice').innerText = `${data.price} ${data.currency}`;
    
    const signalElem = document.getElementById('tradeSignal');
    signalElem.innerText = currentLang === 'ar' ? data.signal_ar : data.signal_en;
    signalElem.className = "status-badge badge-" + data.signal_badge;

    document.getElementById('forecastText').innerText = currentLang === 'ar' ? data.forecast_ar : data.forecast_en;
    document.getElementById('supportVal').innerText = `${data.support} ${data.currency}`;
    document.getElementById('resistanceVal').innerText = `${data.resistance} ${data.currency}`;
    document.getElementById('sma200Val').innerText = data.sma_200;
    document.getElementById('rsiVal').innerText = data.rsi;

    calculateRisk();
    renderChart(data.chart_dates, data.chart_prices, data.chart_sma20, data.chart_bb_upper, data.chart_bb_lower);

    document.getElementById('resultContainer').style.display = 'block';
}

function renderChart(dates, prices, sma, bbUpper, bbLower) {
    const ctx = document.getElementById('priceChart').getContext('2d');
    if(chartInstance) chartInstance.destroy();

    chartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: dates,
            datasets: [
                { label: 'السعر (Price)', data: prices, borderColor: '#38bdf8', borderWidth: 2, fill: false },
                { label: 'SMA 20', data: sma, borderColor: '#f59e0b', borderWidth: 1, borderDash: [4, 4], fill: false },
                { label: 'BB Upper', data: bbUpper, borderColor: 'rgba(239, 68, 68, 0.4)', borderWidth: 1, fill: false },
                { label: 'BB Lower', data: bbLower, borderColor: 'rgba(16, 185, 129, 0.4)', borderWidth: 1, fill: false }
            ]
        },
        options: {
            responsive: true,
            plugins: { legend: { labels: { color: '#94a3b8' } } },
            scales: {
                x: { ticks: { color: '#94a3b8' }, grid: { color: '#334155' } },
                y: { ticks: { color: '#94a3b8' }, grid: { color: '#334155' } }
            }
        }
    });
}

function calculateRisk() {
    if(!currentData) return;
    const capital = parseFloat(document.getElementById('capitalInput').value) || 0;
    const shares = Math.floor(capital / currentData.price);
    document.getElementById('stopLossVal').innerText = `${currentData.stop_loss} ${currentData.currency}`;
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
        btn.className = 'btn btn-outline-secondary btn-sm text-light';
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
    
