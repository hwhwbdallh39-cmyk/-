import os
import yfinance as yf
import pandas as pd
import numpy as np
from flask import Flask, render_template_string, request, jsonify

# ==========================================
#  حقوق الملكية وتفاصيل التطوير (Copyrights)
# ==========================================
APP_AUTHOR = "حقوق الطبع والتطوير محفوظة لـ: عبدالله علي هادي عاتي"
APP_VERSION = "v4.0.0 (Public Web Edition)"
APP_NAME = "نظام التداول والتحليل الذكي | السوق السعودي والأمريكي"

app = Flask(__name__)

# ==========================================
#  محرك تحليل الأسهم وتوليد الإشارات
# ==========================================
def analyze_stock(ticker_symbol, market):
    try:
        symbol = ticker_symbol.strip().upper()
        if market == 'SA' and not symbol.endswith('.SR'):
            symbol = f"{symbol}.SR"

        stock = yf.Ticker(symbol)
        df = stock.history(period="1y")

        if df.empty:
            return {"error": "لم يتم العثور على بيانات للرمز المدخل، تأكد من صحة الرمز والسوق المختار."}

        # 1. المتوسطات المتحركة
        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        df['SMA_50'] = df['Close'].rolling(window=50).mean()

        # 2. مؤشر RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        # 3. مؤشر MACD
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()

        # 4. مستويات الدعم والمقاومة
        support = round(df['Low'].tail(30).min(), 2)
        resistance = round(df['High'].tail(30).max(), 2)

        latest_price = round(df['Close'].iloc[-1], 2)
        latest_rsi = round(df['RSI'].iloc[-1], 2)
        sma_20 = round(df['SMA_20'].iloc[-1], 2)
        sma_50 = round(df['SMA_50'].iloc[-1], 2)
        latest_macd = round(df['MACD'].iloc[-1], 2)
        latest_signal = round(df['Signal_Line'].iloc[-1], 2)

        # خوارزمية تحديد نقاط الشراء والبيع
        signal = "محايد (انتظار)"
        signal_color = "#f39c12"
        reason = "المؤشرات الفنية تظهر توازناً في حركة السعر دون ترجيح مسار مؤكد."

        if latest_rsi < 35 and latest_macd > latest_signal and latest_price <= support * 1.02:
            signal = "شراء قوي جداً (Strong Buy)"
            signal_color = "#2ecc71"
            reason = "السهم يتداول قرب مستوى دعم قوي، مع تشبع بيعي وتدفق سيولة إيجابية عبر مؤشر MACD."
        elif latest_rsi < 45 and latest_price > sma_20 and latest_macd > latest_signal:
            signal = "دخول / شراء (Buy)"
            signal_color = "#27ae60"
            reason = "تقاطع إيجابي لمؤشر MACD مع تداول السعر أعلى من المتوسط المتحرك 20."
        elif latest_rsi > 70 or (latest_price >= resistance * 0.98 and latest_macd < latest_signal):
            signal = "بيع قوي (Strong Sell)"
            signal_color = "#e74c3c"
            reason = "السهم وصل لمناطق مقاومة رئيسية مع تشبع شرائي وبدء تقاطع سلبي لمؤشر MACD."
        elif latest_price < sma_20 and latest_macd < latest_signal:
            signal = "تخفيف الكميات / بيع (Sell)"
            signal_color = "#c0392b"
            reason = "كسر للمتوسط القصير SMA20 وضعف الزخم على مؤشر MACD."

        currency = "SAR" if market == 'SA' else "USD"

        return {
            "symbol": symbol,
            "market": "السوق السعودي (تداول)" if market == 'SA' else "السوق الأمريكي (US)",
            "price": f"{latest_price} {currency}",
            "rsi": latest_rsi,
            "sma_20": f"{sma_20} {currency}",
            "sma_50": f"{sma_50} {currency}",
            "macd": latest_macd,
            "support": f"{support} {currency}",
            "resistance": f"{resistance} {currency}",
            "signal": signal,
            "signal_color": signal_color,
            "reason": reason
        }
    except Exception as e:
        return {"error": f"حدث خطأ أثناء تحليل السهم: {str(e)}"}

# ==========================================
#  الواجهة الأمامية المفتوحة للجميع (HTML/CSS)
# ==========================================
MAIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ app_name }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css" rel="stylesheet">
    <style>
        body { background-color: #0f172a; color: #f8fafc; font-family: system-ui, -apple-system, sans-serif; }
        .card { background-color: #1e293b; border: 1px solid #334155; border-radius: 12px; color: #fff; }
        .btn-primary { background-color: #3b82f6; border: none; }
        .btn-primary:hover { background-color: #2563eb; }
        .badge-signal { font-size: 1.2rem; padding: 10px 20px; border-radius: 8px; }
        .footer { border-top: 1px solid #334155; margin-top: 50px; padding: 20px 0; color: #94a3b8; }
    </style>
</head>
<body>

<div class="container py-5">
    <div class="text-center mb-5">
        <h1 class="fw-bold text-primary">{{ app_name }}</h1>
        <p class="text-muted">منصة التحليل الفني المباشر واستخراج إشارات الأسهم مجاناً للجميع</p>
    </div>

    <div class="row justify-content-center mb-4">
        <div class="col-md-7">
            <div class="card p-4 shadow">
                <form id="searchForm">
                    <div class="mb-3">
                        <label class="form-label">اختر السوق:</label>
                        <select id="marketSelect" class="form-select">
                            <option value="US">السوق الأمريكي (مثل: AAPL, NVDA, TSLA)</option>
                            <option value="SA">السوق السعودي (مثل: 2222 أرامكو, 1120 الراجحي)</option>
                        </select>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">رمز السهم:</label>
                        <div class="input-group">
                            <input type="text" id="tickerInput" class="form-control" placeholder="أدخل رمز السهم..." required>
                            <button type="submit" class="btn btn-primary">تحليل شامل</button>
                        </div>
                    </div>
                </form>
            </div>
        </div>
    </div>

    <div class="row justify-content-center" id="resultContainer" style="display:none;">
        <div class="col-md-8">
            <div class="card p-4 shadow">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <div>
                        <h3 id="stockSymbol" class="m-0"></h3>
                        <small id="stockMarket" class="text-muted"></small>
                    </div>
                    <h4 id="stockPrice" class="text-info m-0"></h4>
                </div>
                <hr style="border-color: #334155;">
                
                <div class="text-center my-3">
                    <h5>إشارة التداول الموصى بها:</h5>
                    <span id="tradeSignal" class="badge badge-signal text-white"></span>
                </div>

                <div class="alert alert-dark mt-3" style="background-color: #0f172a; border-color: #334155;">
                    <strong>التحليل والمبررات: </strong> <span id="signalReason"></span>
                </div>

                <h5 class="mt-4 mb-3">المؤشرات الفنية ومستويات الدعم والمقاومة:</h5>
                <div class="row text-center g-2">
                    <div class="col-6 col-md-4">
                        <div class="p-2 border rounded border-secondary">
                            <small class="text-muted d-block">مستوى الدعم</small>
                            <strong id="supportVal" class="text-success"></strong>
                        </div>
                    </div>
                    <div class="col-6 col-md-4">
                        <div class="p-2 border rounded border-secondary">
                            <small class="text-muted d-block">مستوى المقاومة</small>
                            <strong id="resistanceVal" class="text-danger"></strong>
                        </div>
                    </div>
                    <div class="col-6 col-md-4">
                        <div class="p-2 border rounded border-secondary">
                            <small class="text-muted d-block">مؤشر RSI</small>
                            <strong id="rsiVal"></strong>
                        </div>
                    </div>
                    <div class="col-6 col-md-4">
                        <div class="p-2 border rounded border-secondary">
                            <small class="text-muted d-block">مؤشر MACD</small>
                            <strong id="macdVal"></strong>
                        </div>
                    </div>
                    <div class="col-6 col-md-4">
                        <div class="p-2 border rounded border-secondary">
                            <small class="text-muted d-block">SMA 20</small>
                            <strong id="sma20Val"></strong>
                        </div>
                    </div>
                    <div class="col-6 col-md-4">
                        <div class="p-2 border rounded border-secondary">
                            <small class="text-muted d-block">SMA 50</small>
                            <strong id="sma50Val"></strong>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<footer class="footer text-center">
    <div class="container">
        <p class="m-0">{{ author }} &copy; 2026 - جميع الحقوق محفوظة.</p>
        <small class="text-muted">الإصدار {{ version }}</small>
    </div>
</footer>

<script>
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

    document.getElementById('stockSymbol').innerText = "سهم: " + data.symbol;
    document.getElementById('stockMarket').innerText = data.market;
    document.getElementById('stockPrice').innerText = "السعر الحالي: " + data.price;
    
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

    document.getElementById('resultContainer').style.display = 'block';
});
</script>
</body>
</html>
"""

# ==========================================
#  المسارات العامة (Public Routes)
# ==========================================
@app.route('/')
def home():
    return render_template_string(MAIN_TEMPLATE, app_name=APP_NAME, author=APP_AUTHOR, version=APP_VERSION)

@app.route('/api/analyze', methods=['GET'])
def api_analyze():
    symbol = request.args.get('symbol', '')
    market = request.args.get('market', 'US')
    if not symbol:
        return jsonify({"error": "يرجى تقديم رمز السهم"}), 400
    data = analyze_stock(symbol, market)
    return jsonify(data)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
