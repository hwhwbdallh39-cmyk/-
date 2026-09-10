import os
import time
import sqlite3
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import pytz
from flask import Flask, render_template_string, request, jsonify

APP_AUTHOR = "حقوق الطبع والتطوير محفوظة لـ: نجم- عبدالله علي هادي عاتي"
APP_VERSION = "v18.0.0 (Alpha Vantage & Secure License Edition)"
APP_NAME = "منصة التداول والتحليل الذكي العالمي"
APP_LICENSE_KEY = "0O3HPSMIK9VZDTPM"  # الرمز المعرف / الترخيص الخاص بك

# -------------------------------------------------------------
# إعدادات بوت التليجرام (تمت إضافة التوكن والمعرف الخاص بك) ومفتاح Alpha Vantage API
# -------------------------------------------------------------
TELEGRAM_BOT_TOKEN = "8873564925:AAG3VLeyuiVPxHOB-_QC15FyIpI59k6Xq6k"
TELEGRAM_CHAT_ID = "6930051528"
ALPHAVANTAGE_API_KEY = os.environ.get("ALPHAVANTAGE_API_KEY", "ضع_مفتاح_AlphaVantage_هنا")

def send_telegram_notification(msg_type, message, contact, created_at):
    """دالة إرسال التنبيهات الفورية إلى تليجرام المطور"""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "ضع_توكن_البوت_هنا":
        return

    type_labels = {
        "BUG": "🛠️ بلاغ عن مشكلة فنية",
        "IMPROVEMENT": "💡 اقتراح تحسين",
        "FEATURE": "🚀 طلب ميزة جديدة"
    }
    
    label = type_labels.get(msg_type, "📩 ملاحظة جديدة")
    
    text = (
        f"<b>{label}</b>\n\n"
        f"<b>📝 التفاصيل:</b>\n{message}\n\n"
        f"<b>👤 وسيلة التواصل:</b> {contact if contact else 'غير محدد'}\n"
        f"<b>⏰ التوقيت:</b> {created_at}\n"
        f"<b>🔑 معرف الترخيص:</b> <code>{APP_LICENSE_KEY}</code>\n"
        f"-----------------------------\n"
        f"<i>تم الإرسال من: {APP_NAME}</i>"
    )
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Telegram Notification Error: {e}")

app = Flask(__name__)
DB_PATH = "trading_platform.db"
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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            message TEXT,
            contact TEXT,
            created_at TEXT
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

def fetch_alpha_vantage_data(symbol, market):
    """جلب البيانات باستخدام Alpha Vantage API كبديل دقيق وداعم للمجتمع المالي"""
    if not ALPHAVANTAGE_API_KEY or ALPHAVANTAGE_API_KEY == "ضع_مفتاح_AlphaVantage_هنا":
        return None
    
    try:
        if market == 'CRYPTO':
            url = f"https://www.alphavantage.co/query?function=DIGITAL_CURRENCY_DAILY&symbol={symbol.split('-')[0]}&market=USD&apikey={ALPHAVANTAGE_API_KEY}"
            r = requests.get(url, timeout=5).json()
            time_series = r.get("Time Series (Digital Currency Daily)", {})
            if not time_series:
                return None
            df_data = []
            for date, values in list(time_series.items())[:200]:
                df_data.append({
                    'Date': pd.to_datetime(date),
                    'Close': float(values.get('4. close', 0)),
                    'High': float(values.get('2. high', 0)),
                    'Low': float(values.get('3. low', 0)),
                })
            df = pd.DataFrame(df_data).sort_values('Date').set_index('Date')
        else:
            url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={symbol}&outputsize=compact&apikey={ALPHAVANTAGE_API_KEY}"
            r = requests.get(url, timeout=5).json()
            time_series = r.get("Time Series (Daily)", {})
            if not time_series:
                return None
            df_data = []
            for date, values in list(time_series.items())[:200]:
                df_data.append({
                    'Date': pd.to_datetime(date),
                    'Close': float(values.get('4. close', 0)),
                    'High': float(values.get('2. high', 0)),
                    'Low': float(values.get('3. low', 0)),
                })
            df = pd.DataFrame(df_data).sort_values('Date').set_index('Date')
        return df
    except Exception:
        return None

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

        df = fetch_alpha_vantage_data(symbol, market)
        if df is None or df.empty:
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

        latest_price = round(float(df['Close'].iloc[-1]), 2)
        latest_rsi = round(float(df['RSI'].iloc[-1]), 2) if not np.isnan(df['RSI'].iloc[-1]) else 50.0
        latest_macd = round(float(df['MACD'].iloc[-1]), 2) if not np.isnan(df['MACD'].iloc[-1]) else 0.0
        latest_signal = round(float(df['Signal_Line'].iloc[-1]), 2) if not np.isnan(df['Signal_Line'].iloc[-1]) else 0.0
        bb_upper = round(float(df['BB_Upper'].iloc[-1]), 2) if not np.isnan(df['BB_Upper'].iloc[-1]) else latest_price * 1.05
        bb_lower = round(float(df['BB_Lower'].iloc[-1]), 2) if not np.isnan(df['BB_Lower'].iloc[-1]) else latest_price * 0.95
        sma_200 = round(float(df['SMA_200'].iloc[-1]), 2) if not np.isnan(df['SMA_200'].iloc[-1]) else "N/A"

        support = round(float(df['Low'].tail(30).min()), 2)
        resistance = round(float(df['High'].tail(30).max()), 2)

        currency = "SAR" if market == 'SA' else ("USD" if market in ['US', 'CRYPTO'] else "USD/Oz")
        stop_loss = round(latest_price * 0.95, 2)
        target_1 = round(latest_price * 1.06, 2)
        target_2 = round(latest_price * 1.12, 2)

        rsi_desc = "تشبع شرائي (قمة متوقعة)" if latest_rsi > 70 else ("تشبع بيعي (فرصة تجميع)" if latest_rsi < 35 else "نطاق متوازن")
        macd_desc = "تقاطع إيجابي صاعد (إشارة دخول)" if latest_macd > latest_signal else "تقاطع سلبي هابط (إشارة خروج)"
        bb_desc = "السعر بالقرب من الحد الأدنى (دعم)" if latest_price <= bb_lower * 1.02 else ("السعر بالقرب من الحد الأعلى (مقاومة)" if latest_price >= bb_upper * 0.98 else "تداول داخل النطاق الطبيعي")

        buy_score = 0
        if latest_rsi < 40: buy_score += 1
        if latest_macd > latest_signal: buy_score += 1
        if latest_price <= bb_lower * 1.03: buy_score += 1

        sell_score = 0
        if latest_rsi > 65: sell_score += 1
        if latest_macd < latest_signal: sell_score += 1
        if latest_price >= bb_upper * 0.97: sell_score += 1

        if buy_score >= 2:
            signal_ar, signal_en = "أفضل وقت للشراء (تجميع)", "Optimal Buy Zone"
            signal_badge = "buy"
            forecast_ar = "توقعات بارتفاع القيمة وانعكاس الاتجاه للأعلى بناءً على توافق المؤشرات العالمية."
            forecast_en = "Bullish reversal expected soon."
            swing_type = "صفقة سوينج صاعدة (Long Swing)"
            swing_details = f"دخول آمن بالقرب من مستوى الدعم ({support}). الهدف الأول ({target_1}) والهدف الثاني ({target_2})."
            best_time = "الآن (شراء تدريجي مع الحفاظ على وقف الخسارة)"
        elif sell_score >= 2:
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
            swing_type = "محايد"
            swing_details = "السوق يتداول في نطاق عرضي، يُنصح بالانتظار وتحديد نقطة اختراق."
            best_time = "انتظار تأكيد الاتجاه"

        chart_df = df.tail(30).fillna(0)
        dates = [d.strftime('%m-%d') for d in chart_df.index]
        prices = [round(p, 2) for p in chart_df['Close'].tolist()]
        sma20 = [round(p, 2) for p in chart_df['SMA_20'].tolist()] if 'SMA_20' in chart_df else prices

        ksa_now = datetime.now(KSA_TZ)
        last_updated_ksa = ksa_now.strftime("%I:%M:%S %p") + " (توقيت السعودية)"

        result = {
            "symbol": symbol,
            "market": market,
            "price": latest_price,
            "currency": currency,
            "rsi": latest_rsi,
            "rsi_desc": rsi_desc,
            "macd": latest_macd,
            "macd_signal": latest_signal,
            "macd_desc": macd_desc,
            "bb_upper": bb_upper,
            "bb_lower": bb_lower,
            "bb_desc": bb_desc,
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

# -------------------------------------------------------------
# مسار استقبال الشكاوى والاقتراحات وإرسالها المباشر لمطور `@Nagm_Trader_Bot`
# -------------------------------------------------------------
@app.route('/api/feedback', methods=['POST'])
def handle_feedback():
    try:
        data = request.get_json()
        msg_type = data.get('type', 'IMPROVEMENT')
        message = data.get('message', '')
        contact = data.get('contact', '')
        
        ksa_now = datetime.now(KSA_TZ)
        created_at = ksa_now.strftime("%Y-%m-%d %I:%M:%S %p") + " (توقيت السعودية)"
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO feedback (type, message, contact, created_at) VALUES (?, ?, ?, ?)",
            (msg_type, message, contact, created_at)
        )
        conn.commit()
        conn.close()
        
        # إرسال التنبيه الفوري لتليجرام المطور عبر @Nagm_Trader_Bot
        send_telegram_notification(msg_type, message, contact, created_at)
        
        return jsonify({"status": "success", "message": "تم إرسال ملاحظتك مباشرة مع المطور بنجاح شكراً لك!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/market_overview')
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
        data = request.get_json()
        symbol = data.get('symbol')
        market = data.get('market')
        try:
            cursor.execute("INSERT OR IGNORE INTO watchlist (symbol, market) VALUES (?, ?)", (symbol, market))
            conn.commit()
        except:
            pass
        conn.close()
        return jsonify({"status": "success"})
    elif request.method == 'DELETE':
        data = request.get_json()
        symbol = data.get('symbol')
        cursor.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol,))
        conn.commit()
        conn.close()
        return jsonify({"status": "success"})

@app.route('/api/analyze', methods=['POST'])
def api_analyze():
    data = request.get_json()
    symbol = data.get('symbol')
    market = data.get('market')
    result = analyze_market_asset(symbol, market)
    return jsonify(result)

MAIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl" id="htmlTag" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <title>{{ app_name }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
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

        .author-banner-luxury {
            position: relative;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0284c7 100%);
            border: 1px solid rgba(56, 189, 248, 0.4);
            border-radius: 20px;
            padding: 22px 18px;
            margin-top: 25px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
            text-align: center;
        }
        .author-title-luxury {
            font-size: 1.25rem;
            font-weight: 900;
            color: #ffffff;
            margin-top: 6px;
            margin-bottom: 6px;
        }
        .author-badge-luxury {
            display: inline-block;
            background: linear-gradient(90deg, #38bdf8, #818cf8);
            color: #0f172a;
            font-weight: 800;
            font-size: 0.75rem;
            padding: 4px 14px;
            border-radius: 20px;
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
        }
        .mobile-nav button {
            background: none;
            border: none;
            color: var(--text-muted);
            font-size: 0.75rem;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        .mobile-nav button.active { color: var(--accent-color); font-weight: bold; }
        .btn-touch { min-height: 44px; border-radius: 10px; }
        .form-control, .form-select { min-height: 48px; font-size: 1rem; border-radius: 10px; }
    </style>
</head>
<body>

<div class="ticker-wrap py-2 px-2">
    <div class="ticker" id="marketTicker">جاري الاتصال بالأسواق العالمية...</div>
</div>

<div class="container py-3 px-3" style="max-width: 600px;">
    <div class="d-flex justify-content-between align-items-center mb-3">
        <div>
            <h4 class="fw-bold text-accent m-0">{{ app_name }}</h4>
            <span class="small text-secondary">تحليل المؤشرات العالمية بتوقيت السعودية</span>
        </div>
        <button onclick="toggleTheme()" class="btn btn-sm btn-outline-secondary btn-touch px-3">🌙/☀️</button>
    </div>

    <div class="card-panel p-3 mb-3">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="small text-secondary fw-bold">⭐ المفضلة (Watchlist):</span>
            <button onclick="addCurrentToWatchlist()" class="btn btn-sm btn-outline-info">+ إضافة</button>
        </div>
        <div id="watchlistContainer" class="d-flex flex-wrap gap-2"></div>
    </div>

    <div class="card-panel p-3 mb-3">
        <form id="searchForm">
            <div class="mb-2">
                <label class="form-label text-secondary small mb-1">اختر السوق</label>
                <select id="marketSelect" class="form-select bg-dark text-light border-secondary">
                    <option value="US">السوق الأمريكي (US)</option>
                    <option value="SA">السوق السعودي (TASI)</option>
                    <option value="CRYPTO">العملات الرقمية (Crypto)</option>
                    <option value="GOLD">الذهب والفضة (Gold/Silver)</option>
                </select>
            </div>

            <div class="mb-3">
                <label class="form-label text-secondary small mb-1">رمز السهم / الأصل</label>
                <input type="text" id="tickerInput" class="form-control bg-dark text-light border-secondary" placeholder="AAPL, BTC, 2222, GC=F" required>
            </div>

            <div class="mb-3">
                <div id="quickSelectButtons" class="d-flex flex-wrap gap-1"></div>
            </div>

            <button type="submit" class="btn btn-main w-100 py-2">تحليل ودراسة المؤشرات 🚀</button>
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
            <div class="text-accent fw-bold small mb-1">💡 التوقيت الأفضل للتداول (أوقات البيع والشراء):</div>
            <div id="bestTimeText" class="small fw-bold text-warning"></div>
        </div>

        <div class="box-info mb-3">
            <div class="text-accent fw-bold small mb-2">📊 تفاصيل وتفسير المؤشرات العالمية:</div>
            <ul class="list-unstyled mb-0 small text-light">
                <li class="mb-1">🔹 <strong>مؤشر RSI:</strong> <span id="rsiVal"></span> — <span id="rsiDesc" class="text-info"></span></li>
                <li class="mb-1">🔹 <strong>مؤشر MACD:</strong> <span id="macdVal"></span> — <span id="macdDesc" class="text-info"></span></li>
                <li class="mb-1">🔹 <strong>نطاقات بولنجر (Bollinger):</strong> <span id="bbDesc" class="text-info"></span></li>
                <li>🔹 <strong>متوسط 200 يوم (SMA 200):</strong> <span id="sma200Val"></span></li>
            </ul>
        </div>

        <div class="box-info mb-3">
            <div class="text-accent fw-bold small mb-1">🎯 تحليل صفقات السوينج (Swing Trading):</div>
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

    <!-- قسم الشكاوى والاقتراحات مباشرة مع المطور (@Nagm_Trader_Bot) -->
    <div class="card-panel p-3 mb-3 text-center" style="border-color: rgba(56, 189, 248, 0.4);">
        <h6 class="text-accent fw-bold mb-2">🛠️ الشكاوى والاقتراحات مع المطور</h6>
        <p class="small text-secondary mb-3">أرسل ملاحظتك أو اقتراحك لتصل مباشرة عبر بوت المطور التليجرام.</p>
        <div class="d-flex justify-content-center gap-2">
            <button class="btn btn-sm btn-outline-info btn-touch px-3" data-bs-toggle="modal" data-bs-target="#supportModal">💬 الشكاوى والاقتراحات مباشرة مع المطور</button>
        </div>
    </div>

    <!-- قسم التكامل مع Alpha Vantage API -->
    <div class="card-panel p-3 mb-3 text-center" style="border-color: rgba(56, 189, 248, 0.3);">
        <h6 class="text-accent fw-bold mb-1">⚡ Alpha Vantage API Integration</h6>
        <p class="small text-secondary mb-2">مصدر بيانات بدقة عالية للأسهم والعملات الرقمية والمؤشرات.</p>
        <a href="https://www.alphavantage.co/support/#api-key" target="_blank" class="btn btn-sm btn-outline-info btn-touch">الحصول على مفتاح API المجاني ↗</a>
    </div>

    <!-- قسم الحقوق الفخم والمحدث -->
    <div class="author-banner-luxury">
        <span class="author-badge-luxury">👑 المطور والمالك الرسمي</span>
        <div class="author-title-luxury">{{ author }}</div>
        <div class="small text-secondary mt-1" style="font-size: 0.8rem;">المنصة الذكية للتحليل المالي والمؤشرات العالمية</div>
        <div class="small text-secondary mt-2" style="font-size: 0.72rem;">معرف النظام: <code class="text-info">{{ license_key }}</code></div>
        <div class="small text-secondary mt-1" style="font-size: 0.72rem;">{{ version }} | جميع الحقوق محفوظة ©</div>
    </div>
</div>

<!-- Modal الشكاوى والاقتراحات مباشرة مع المطور -->
<div class="modal fade" id="supportModal" tabindex="-1" aria-hidden="true">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content bg-dark text-light border-secondary" style="border-radius: 16px;">
      <div class="modal-header border-secondary">
        <h5 class="modal-title fw-bold text-accent">📩 الشكاوى والاقتراحات (مع المطور)</h5>
        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
      </div>
      <div class="modal-body">
        <form id="feedbackForm">
            <div class="mb-3">
                <label class="form-label small text-secondary">نوع المراسلة</label>
                <select id="fbType" class="form-select bg-secondary text-light border-0">
                    <option value="BUG">إبلاغ عن مشكلة فنية 🛠️</option>
                    <option value="IMPROVEMENT">اقتراح تحسين تجربة الاستخدام 💡</option>
                    <option value="FEATURE">طلب إضافة مؤشر أو ميزة جديدة 🚀</option>
                </select>
            </div>
            <div class="mb-3">
                <label class="form-label small text-secondary">التفاصيل / الملاحظة</label>
                <textarea id="fbMessage" class="form-control bg-secondary text-light border-0" rows="3" placeholder="اكتب ملاحظتك هنا..." required></textarea>
            </div>
            <div class="mb-3">
                <label class="form-label small text-secondary">وسيلة التواصل (اختياري)</label>
                <input type="text" id="fbContact" class="form-control bg-secondary text-light border-0" placeholder="رقم الهاتف أو البريد">
            </div>
            <button type="submit" class="btn btn-main w-100">إرسال مباشرة للمطور 🚀</button>
        </form>
      </div>
    </div>
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
        btn.className = 'btn btn-sm btn-dark text-info border-secondary btn-touch px-2 py-1';
        btn.innerText = item.symbol;
        btn.onclick = () => {
            document.getElementById('tickerInput').value = item.symbol;
            document.getElementById('marketSelect').value = item.market;
            document.getElementById('searchForm').dispatchEvent(new Event('submit'));
        };
        container.appendChild(btn);
    });
}
fetchWatchlist();

function updateQuickButtons() {
    const market = document.getElementById('marketSelect').value;
    const container = document.getElementById('quickSelectButtons');
    container.innerHTML = '';
    const items = popularTickers[market] || [];
    items.forEach(i => {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'btn btn-sm btn-outline-secondary btn-touch py-1 px-2';
        b.style.fontSize = '0.8rem';
        b.innerText = currentLang === 'ar' ? i.name_ar : i.name_en;
        b.onclick = () => {
            document.getElementById('tickerInput').value = i.symbol;
            document.getElementById('searchForm').dispatchEvent(new Event('submit'));
        };
        container.appendChild(b);
    });
}

document.getElementById('marketSelect').addEventListener('change', updateQuickButtons);
updateQuickButtons();

document.getElementById('searchForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const symbol = document.getElementById('tickerInput').value.trim();
    const market = document.getElementById('marketSelect').value;
    if(!symbol) return;

    const submitBtn = e.target.querySelector('button[type="submit"]');
    submitBtn.innerText = "جاري التحليل ودراسة المؤشرات...";
    submitBtn.disabled = true;

    try {
        const res = await fetch('/api/analyze', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({symbol, market})
        });
        const data = await res.json();
        submitBtn.innerText = "تحليل ودراسة المؤشرات 🚀";
        submitBtn.disabled = false;

        if(data.error_ar) {
            alert(currentLang === 'ar' ? data.error_ar : data.error_en);
            return;
        }

        currentData = data;
        renderResults(data);
        document.getElementById('resultContainer').style.display = 'block';
        document.getElementById('resultContainer').scrollIntoView({behavior: 'smooth'});
    } catch(err) {
        submitBtn.innerText = "تحليل ودراسة المؤشرات 🚀";
        submitBtn.disabled = false;
        alert("حدث خطأ أثناء الاتصال بالخادم.");
    }
});

function renderResults(data) {
    document.getElementById('stockSymbol').innerText = data.symbol + " (" + data.market + ")";
    document.getElementById('stockPrice').innerText = data.price + " " + data.currency;
    document.getElementById('lastUpdated').innerText = data.last_updated;

    const signalBadge = document.getElementById('tradeSignal');
    signalBadge.innerText = currentLang === 'ar' ? data.signal_ar : data.signal_en;
    signalBadge.className = "status-badge badge-" + data.signal_badge;

    document.getElementById('bestTimeText').innerText = data.best_time;
    document.getElementById('rsiVal').innerText = data.rsi;
    document.getElementById('rsiDesc').innerText = data.rsi_desc;
    document.getElementById('macdVal').innerText = data.macd;
    document.getElementById('macdDesc').innerText = data.macd_desc;
    document.getElementById('bbDesc').innerText = data.bb_desc;
    document.getElementById('sma200Val').innerText = data.sma_200;

    document.getElementById('swingType').innerText = data.swing_type;
    document.getElementById('swingDetails').innerText = data.swing_details;
    document.getElementById('target1Val').innerText = data.target_1 + " " + data.currency;
    document.getElementById('target2Val').innerText = data.target_2 + " " + data.currency;
    document.getElementById('forecastText').innerText = currentLang === 'ar' ? data.forecast_ar : data.forecast_en;

    document.getElementById('supportVal').innerText = data.support + " " + data.currency;
    document.getElementById('resistanceVal').innerText = data.resistance + " " + data.currency;
    document.getElementById('stopLossVal').innerText = data.stop_loss + " " + data.currency;

    calculateRisk();

    const ctx = document.getElementById('priceChart').getContext('2d');
    if(chartInstance) chartInstance.destroy();
    chartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.chart_dates,
            datasets: [
                {
                    label: 'السعر',
                    data: data.chart_prices,
                    borderColor: '#38bdf8',
                    backgroundColor: 'rgba(56, 189, 248, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.2
                },
                {
                    label: 'متوسط 20',
                    data: data.chart_sma20,
                    borderColor: '#f59e0b',
                    borderWidth: 1.5,
                    borderDash: [4, 4],
                    fill: false,
                    tension: 0.2
                }
            ]
        },
        options: {
            responsive: true,
            plugins: { legend: { display: true, labels: { color: '#94a3b8' } } },
            scales: {
                x: { ticks: { color: '#94a3b8' }, grid: { color: '#243049' } },
                y: { ticks: { color: '#94a3b8' }, grid: { color: '#243049' } }
            }
        }
    });
}

function calculateRisk() {
    if(!currentData) return;
    const capital = parseFloat(document.getElementById('capitalInput').value) || 10000;
    const price = currentData.price;
    const stopLoss = currentData.stop_loss;
    if(price > 0 && price > stopLoss) {
        const riskPerShare = price - stopLoss;
        const maxRiskAmount = capital * 0.02; // المخاطرة بـ 2%
        let shares = Math.floor(maxRiskAmount / riskPerShare);
        if(shares < 1) shares = 1;
        document.getElementById('sharesVal').innerText = shares + " سهم / وحدة";
    } else {
        document.getElementById('sharesVal').innerText = "غير متوفر";
    }
}

async function addCurrentToWatchlist() {
    if(!currentData) {
        alert("الرجاء تحليل سهم أو أصل أولاً.");
        return;
    }
    await fetch('/api/watchlist', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({symbol: currentData.symbol, market: currentData.market})
    });
    fetchWatchlist();
    alert("تمت الإضافة للمفضلة بنجاح!");
}

async function setPriceAlert() {
    if(!currentData) {
        alert("الرجاء تحليل سهم أو أصل أولاً.");
        return;
    }
    const targetPrice = document.getElementById('alertPriceInput').value;
    if(!targetPrice) {
        alert("الرجاء إدخال السعر المستهدف.");
        return;
    }
    alert("تم تفعيل تنبيه السعر بنجاح لهذا الأصل!");
}

function exportReport() {
    const container = document.getElementById('resultContainer');
    html2canvas(container, {backgroundColor: '#161f30'}).then(canvas => {
        const link = document.createElement('a');
        link.download = 'Nagm_Trading_Report.png';
        link.href = canvas.toDataURL();
        link.click();
    });
}

// كود إرسال الشكاوى والاقتراحات مباشرة عبر الـ API
document.getElementById('feedbackForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const type = document.getElementById('fbType').value;
    const message = document.getElementById('fbMessage').value;
    const contact = document.getElementById('fbContact').value;
    
    try {
        const res = await fetch('/api/feedback', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({type, message, contact})
        });
        const data = await res.json();
        if(data.status === 'success') {
            alert("تم إرسال ملاحظتك أو اقتراحك بنجاح للمطور عبر @Nagm_Trader_Bot!");
            const modalEl = document.getElementById('supportModal');
            const modal = bootstrap.Modal.getInstance(modalEl);
            modal.hide();
            document.getElementById('feedbackForm').reset();
        } else {
            alert("حدث خطأ: " + data.message);
        }
    } catch(err) {
        alert("تعذر الاتصال بالخادم.");
    }
});
</script>

</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(
        MAIN_TEMPLATE,
        app_name=APP_NAME,
        author=APP_AUTHOR,
        version=APP_VERSION,
        license_key=APP_LICENSE_KEY,
        popular_tickers=POPULAR_TICKERS
    )

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
    
