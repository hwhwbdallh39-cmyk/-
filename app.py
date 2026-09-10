import os
import yfinance as yf
import pandas as pd
import numpy as np
from flask import Flask, render_template_string, request, jsonify

APP_AUTHOR = "حقوق الطبع والتطوير محفوظة لـ: عبدالله علي هادي عاتي"
APP_VERSION = "v5.0.0 (Gold & Global Markets Edition)"
APP_NAME = "نظام التحليل الذكي | أسهم وهب"

app = Flask(__name__)

# قائمة شاملة بالأسهم الشائعة في السوقين ومعدن الذهب
POPULAR_TICKERS = {
    "GOLD": [
        {"symbol": "GC=F", "name": "عقود الذهب الآجلة (Gold Futures)"},
        {"symbol": "XAUUSD=X", "name": "الذهب مقابل الدولار (Spot Gold)"}
    ],
    "SA": [
        {"symbol": "2222.SR", "name": "أرامكو السعودية"},
        {"symbol": "1120.SR", "name": "مصرف الراجحي"},
        {"symbol": "1180.SR", "name": "البنك الأهلي السعودي"},
        {"symbol": "2010.SR", "name": "سابك"},
        {"symbol": "7010.SR", "name": "stc (الأس تي سي)"},
        {"symbol": "2350.SR", "name": "كيان السعودية"},
        {"symbol": "1211.SR", "name": "معادن"},
        {"symbol": "4190.SR", "name": "جرير"},
        {"symbol": "2082.SR", "name": "أكوا باور"}
    ],
    "US": [
        {"symbol": "AAPL", "name": "أبل (Apple)"},
        {"symbol": "NVDA", "name": "إنفيديا (Nvidia)"},
        {"symbol": "MSFT", "name": "مايكروسوفت (Microsoft)"},
        {"symbol": "AMZN", "name": "أمازون (Amazon)"},
        {"symbol": "TSLA", "name": "تيسلا (Tesla)"},
        {"symbol": "GOOGL", "name": "جوجل (Alphabet)"},
        {"symbol": "META", "name": "ميتا (Meta)"}
    ]
}

def analyze_market_asset(ticker_symbol, market):
    try:
        symbol = ticker_symbol.strip().upper()

        if market == 'SA' and not symbol.endswith('.SR'):
            symbol = f"{symbol}.SR"
        elif market == 'GOLD' and symbol not in ['GC=F', 'XAUUSD=X']:
            symbol = "GC=F"

        asset = yf.Ticker(symbol)
        df = asset.history(period="1y")

        if df.empty:
            return {"error": "لم يتم العثور على بيانات للرمز المدخل، يرجى التأكد من كتابة الرمز بشكل صحيح."}

        # مؤشرات فنية
        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        df['SMA_50'] = df['Close'].rolling(window=50).mean()

        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()

        support = round(df['Low'].tail(30).min(), 2)
        resistance = round(df['High'].tail(30).max(), 2)

        latest_price = round(df['Close'].iloc[-1], 2)
        latest_rsi = round(df['RSI'].iloc[-1], 2)
        sma_20 = round(df['SMA_20'].iloc[-1], 2)
        sma_50 = round(df['SMA_50'].iloc[-1], 2)
        latest_macd = round(df['MACD'].iloc[-1], 2)
        latest_signal = round(df['Signal_Line'].iloc[-1], 2)

        # تحليلات الذهب والتوقعات
        gold_forecast = ""
        best_time_to_sell = ""

        if market == 'GOLD':
            currency = "USD / Ounce"
            if latest_rsi > 70:
                gold_forecast = "توقعات بانخفاض قادم تصحيحي (الهبوط مؤقت نتيجة تشبع شرائي مرتفع)."
                best_time_to_sell = "الآن يعد وقتاً مناسباً للبيع كجني أرباح جزئي بالقرب من قمم المقاومة."
            elif latest_rsi < 35:
                gold_forecast = "توقعات بارتفاع وقيعان تجميعية (تجهيز لموجة صعود جديدة)."
                best_time_to_sell = "يفضل الانتظار وعدم البيع الآن، والتريث لحين وصول مؤشر RSI لمناطق 65-70."
            else:
                gold_forecast = "استقرار وتذبذب عرضي، اتجاه الذهب مرتبط بالسياسة النقدية ومستويات الفائدة والسيولة."
                best_time_to_sell = f"أفضل منطقة بيع مستهدفة هي عند اقتراب السعر من حاجز المقاومة الحالي عند {resistance} USD."
        else:
            currency = "SAR" if market == 'SA' else "USD"

        # الإشارات الفنية
        if latest_rsi < 35 and latest_macd > latest_signal and latest_price <= support * 1.02:
            signal = "شراء قوي (Strong Buy)"
            signal_color = "#10b981" # أخضر فاقع واضح
            reason = "دعم قوي وتراجع الحجم مع وصول RSI لمناطق تشبع بيعي."
        elif latest_rsi < 45 and latest_price > sma_20:
            signal = "دخول / شراء (Buy)"
            signal_color = "#34d399"
            reason = "تداول إيجابي فوق المتوسط 20 وزخم تصاعدي."
        elif latest_rsi > 70 or (latest_price >= resistance * 0.98 and latest_macd < latest_signal):
            signal = "جني أرباح / بيع (Sell)"
            signal_color = "#ef4444" # أحمر واضح
            reason = "وصول السهم/الأصل لمستويات مقاومة تاريخية مع تشبع الشرائي."
        else:
            signal = "محايد (Hold / Wait)"
            signal_color = "#f59e0b" # أصفر واضح
            reason = "توازن في القوى الشرائية والبيعية دون اتجاه واضح."

        return {
            "symbol": symbol,
            "market": market,
            "price": f"{latest_price} {currency}",
            "rsi": latest_rsi,
            "sma_20": f"{sma_20} {currency}",
            "sma_50": f"{sma_50} {currency}",
            "macd": latest_macd,
            "support": f"{support} {currency}",
            "resistance": f"{resistance} {currency}",
            "signal": signal,
            "signal_color": signal_color,
            "reason": reason,
            "gold_forecast": gold_forecast,
            "best_time_to_sell": best_time_to_sell
        }
    except Exception as e:
        return {"error": f"خطأ في التحليل: {str(e)}"}

# التنسيق البصري المتطور وألوان عالية التباين
MAIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ app_name }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css" rel="stylesheet">
    <style>
        body { background-color: #0b0f19; color: #f1f5f9; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        .card-custom { background-color: #1e293b; border: 1px solid #334155; border-radius: 16px; color: #ffffff; }
        .text-gold { color: #fbbf24; }
        .btn-gold { background-color: #d97706; color: #ffffff; border: none; font-weight: bold; }
        .btn-gold:hover { background-color: #b45309; color: #ffffff; }
        .stat-box { background-color: #0f172a; border: 1px solid #475569; border-radius: 10px; padding: 12px; }
        .badge-signal { font-size: 1.25rem; font-weight: bold; padding: 10px 24px; border-radius: 50px; }
        .footer { border-top: 1px solid #334155; margin-top: 60px; padding: 25px 0; color: #94a3b8; }
    </style>
</head>
<body>

<div class="container py-5">
    <div class="text-center mb-5">
        <h1 class="fw-bold text-gold display-5">{{ app_name }}</h1>
        <p class="text-light lead">تحليل مباشر للأسهم السعودية والأمريكية وسوق الذهب العالمي</p>
    </div>

    <div class="row justify-content-center mb-4">
        <div class="col-md-8">
            <div class="card card-custom p-4 shadow-lg">
                <form id="searchForm">
                    <div class="row g-3">
                        <div class="col-md-5">
                            <label class="form-label text-warning fw-bold">اختر السوق / الأصل:</label>
                            <select id="marketSelect" class="form-select bg-dark text-white border-secondary">
                                <option value="US">السوق الأمريكي (US Stocks)</option>
                                <option value="SA">السوق السعودي (تداول)</option>
                                <option value="GOLD">بورصة الذهب العالمي (Gold XAU)</option>
                            </select>
                        </div>
                        <div class="col-md-7">
                            <label class="form-label text-warning fw-bold">الرمز أو اختر من القائمة:</label>
                            <input type="text" id="tickerInput" class="form-control bg-dark text-white border-secondary mb-2" placeholder="مثال: 2222 أو AAPL أو GC=F" required>
                        </div>
                    </div>

                    <div class="mb-3 mt-2">
                        <small class="text-muted d-block mb-1">اختيارات سريعة:</small>
                        <div id="quickSelectButtons" class="d-flex flex-wrap gap-2"></div>
                    </div>

                    <button type="submit" class="btn btn-gold w-100 py-2 fs-5 mt-2">بدء التحليل الفني والتوقعات</button>
                </form>
            </div>
        </div>
    </div>

    <!-- نتائج التحليل -->
    <div class="row justify-content-center" id="resultContainer" style="display:none;">
        <div class="col-md-8">
            <div class="card card-custom p-4 shadow-lg">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <div>
                        <h2 id="stockSymbol" class="m-0 text-gold fw-bold"></h2>
                    </div>
                    <h3 id="stockPrice" class="text-info m-0 fw-bold"></h3>
                </div>
                <hr style="border-color: #475569;">
                
                <div class="text-center my-4">
                    <h5 class="text-light mb-2">إشارة التداول الرئيسية:</h5>
                    <span id="tradeSignal" class="badge badge-signal text-white shadow"></span>
                </div>

                <div class="alert bg-dark text-white border-secondary p-3 rounded-3 mb-4">
                    <h6 class="text-warning fw-bold">سبب الإشارة والتحليل:</h6>
                    <p id="signalReason" class="m-0 text-light"></p>
                </div>

                <!-- قسم توقعات الذهب (يظهر فقط عند اختيار الذهب) -->
                <div id="goldSection" class="alert alert-warning bg-dark text-warning border-warning p-3 rounded-3 mb-4" style="display:none;">
                    <h5 class="fw-bold border-bottom border-warning pb-2">توقعات بورصة الذهب واستراتيجية البيع:</h5>
                    <p class="mb-2"><strong>حالة السوق والتوقعات:</strong> <span id="goldForecastText" class="text-white"></span></p>
                    <p class="m-0"><strong>أفضل وقت للبيع:</strong> <span id="goldSellTimeText" class="text-white"></span></p>
                </div>

                <h5 class="mt-4 mb-3 text-gold">المؤشرات الفنية والدعم والمقاومة:</h5>
                <div class="row text-center g-3">
                    <div class="col-6 col-md-4">
                        <div class="stat-box">
                            <small class="text-muted d-block">مستوى الدعم</small>
                            <strong id="supportVal" class="text-success fs-5"></strong>
                        </div>
                    </div>
                    <div class="col-6 col-md-4">
                        <div class="stat-box">
                            <small class="text-muted d-block">مستوى المقاومة</small>
                            <strong id="resistanceVal" class="text-danger fs-5"></strong>
                        </div>
                    </div>
                    <div class="col-6 col-md-4">
                        <div class="stat-box">
                            <small class="text-muted d-block">مؤشر RSI</small>
                            <strong id="rsiVal" class="text-warning fs-5"></strong>
                        </div>
                    </div>
                    <div class="col-6 col-md-4">
                        <div class="stat-box">
                            <small class="text-muted d-block">مؤشر MACD</small>
                            <strong id="macdVal" class="text-info fs-5"></strong>
                        </div>
                    </div>
                    <div class="col-6 col-md-4">
                        <div class="stat-box">
                            <small class="text-muted d-block">متوسط 20 يوم</small>
                            <strong id="sma20Val" class="text-light fs-5"></strong>
                        </div>
                    </div>
                    <div class="col-6 col-md-4">
                        <div class="stat-box">
                            <small class="text-muted d-block">متوسط 50 يوم</small>
                            <strong id="sma50Val" class="text-light fs-5"></strong>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<footer class="footer text-center">
    <div class="container">
        <p class="m-0 text-light">{{ author }} &copy; 2026 - جميع الحقوق محفوظة.</p>
        <small class="text-muted">{{ version }}</small>
    </div>
</footer>

<script>
const popularTickers = {{ popular_tickers|tojson }};

function updateQuickButtons() {
    const market = document.getElementById('marketSelect').value;
    const container = document.getElementById('quickSelectButtons');
    container.innerHTML = '';
    
    popularTickers[market].forEach(item => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn btn-outline-light btn-sm';
        btn.innerText = item.name;
        btn.onclick = () => {
            document.getElementById('tickerInput').value = item.symbol;
        };
        container.appendChild(btn);
    });
}

document.getElementById('marketSelect').addEventListener('change', updateQuickButtons);
updateQuickButtons();

document.getElementById('searchForm').addEventListener('submit', async function(e) {
    e.preventDefault();
    const symbol = document.getElementById('tickerInput').value;
    const market = document.getElementById('marketSelect').value;
    
    const response = await fetch(`/api/analyze?symbol=${symbol}&market=${market}`);
    const data = await response.json();

    if(data.error) {
        alert(data.error);
        return;
    }

    document.getElementById('stockSymbol').innerText = data.symbol;
    document.getElementById('stockPrice').innerText = data.price;
    
    const signalElem = document.getElementById('tradeSignal');
    signalElem.innerText = data.signal;
    signalElem.style.backgroundColor = data.signal_color;

    document.getElementById('signalReason').innerText = data.reason;
    document.getElementById('supportVal').innerText = data.support;
    document.getElementById('resistanceVal').innerText = data.resistance;
    document.getElementById('rsiVal').innerText = data.rsi;
    document.getElementById('macdVal').innerText = data.macd;
    document.getElementById('sma20Val').innerText = data.sma_20;
    document.getElementById('sma50Val').innerText = data.sma_50;

    const goldSec = document.getElementById('goldSection');
    if(market === 'GOLD') {
        document.getElementById('goldForecastText').innerText = data.gold_forecast;
        document.getElementById('goldSellTimeText').innerText = data.best_time_to_sell;
        goldSec.style.display = 'block';
    } else {
        goldSec.style.display = 'none';
    }

    document.getElementById('resultContainer').style.display = 'block';
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
        return jsonify({"error": "يرجى تقديم الرمز"}), 400
    data = analyze_market_asset(symbol, market)
    return jsonify(data)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
