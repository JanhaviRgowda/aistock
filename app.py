import csv
import json
import math
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get('PORT', '3000'))
PUBLIC_DIR = os.path.join(os.path.dirname(__file__), 'public')
NSE_EQUITY_CSV = 'https://archives.nseindia.com/content/equities/EQUITY_L.csv'

FALLBACK_STOCKS = [
    {'symbol': 'RELIANCE.NS', 'name': 'Reliance Industries Limited'},
    {'symbol': 'TCS.NS', 'name': 'Tata Consultancy Services Limited'},
    {'symbol': 'INFY.NS', 'name': 'Infosys Limited'},
    {'symbol': 'HDFCBANK.NS', 'name': 'HDFC Bank Limited'},
    {'symbol': 'ICICIBANK.NS', 'name': 'ICICI Bank Limited'},
    {'symbol': 'HINDUNILVR.NS', 'name': 'Hindustan Unilever Limited'},
    {'symbol': 'SBIN.NS', 'name': 'State Bank of India'},
    {'symbol': 'ITC.NS', 'name': 'ITC Limited'},
    {'symbol': 'BHARTIARTL.NS', 'name': 'Bharti Airtel Limited'},
    {'symbol': 'LT.NS', 'name': 'Larsen & Toubro Limited'},
]

stock_cache = {'updated_at': 0, 'data': []}
STOCK_CACHE_TTL = 6 * 60 * 60


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def sma(values, period):
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def ema(values, period):
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    current = sum(values[:period]) / period
    for value in values[period:]:
        current = value * k + current * (1 - k)
    return current


def rsi(values, period=14):
    if len(values) <= period:
        return None
    gains = 0
    losses = 0
    for idx in range(1, period + 1):
        change = values[idx] - values[idx - 1]
        if change >= 0:
            gains += change
        else:
            losses -= change

    avg_gain = gains / period
    avg_loss = losses / period

    for idx in range(period + 1, len(values)):
        change = values[idx] - values[idx - 1]
        gain = max(change, 0)
        loss = max(-change, 0)
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period

    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def volatility(values):
    if len(values) < 2:
        return None
    returns = []
    for i in range(1, len(values)):
        prev = values[i - 1]
        if prev == 0:
            continue
        returns.append((values[i] - prev) / prev)
    if not returns:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / len(returns)
    return math.sqrt(variance) * 100


def fetch_json(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode('utf-8'))


def fetch_stocks():
    now = time.time()
    if stock_cache['data'] and (now - stock_cache['updated_at']) < STOCK_CACHE_TTL:
        return stock_cache['data']

    request = urllib.request.Request(NSE_EQUITY_CSV, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(request, timeout=20) as response:
        text = response.read().decode('utf-8', errors='ignore')

    rows = csv.DictReader(text.splitlines())
    stocks = []
    for row in rows:
        symbol = (row.get('SYMBOL') or '').strip()
        name = (row.get('NAME OF COMPANY') or '').strip()
        series = (row.get(' SERIES') or row.get('SERIES') or '').strip()
        if symbol and name and series == 'EQ':
            stocks.append({'symbol': f'{symbol}.NS', 'name': name})

    stocks.sort(key=lambda item: item['name'])
    stock_cache['data'] = stocks
    stock_cache['updated_at'] = now
    return stocks


def build_quote_from_timeline(symbol, name, timeline):
    close_values = [point['close'] for point in timeline if point['close'] is not None]
    high_values = [point['high'] for point in timeline if point['high'] is not None]
    low_values = [point['low'] for point in timeline if point['low'] is not None]
    volume_values = [point['volume'] for point in timeline if point['volume'] is not None]

    latest_price = close_values[-1]
    start_price = close_values[0]
    change = latest_price - start_price
    change_pct = (change / start_price * 100) if start_price else None

    return {
        'symbol': symbol,
        'name': name,
        'currency': 'INR',
        'interval': '5m',
        'stats': {
            'latestPrice': latest_price,
            'priceChange': change,
            'priceChangePct': change_pct,
            'rsi14': rsi(close_values, 14),
            'sma20': sma(close_values, 20),
            'ema20': ema(close_values, 20),
            'dayHigh': max(high_values) if high_values else None,
            'dayLow': min(low_values) if low_values else None,
            'avgVolume': (sum(volume_values) / len(volume_values)) if volume_values else None,
            'volatility': volatility(close_values),
        },
        'timeline': timeline,
    }


def fallback_quote(symbol):
    base = 2000 + (sum(ord(ch) for ch in symbol) % 900)
    timeline = []
    for i in range(100):
        drift = math.sin(i / 8) * 8
        price = base + drift + (i * 0.6)
        timeline.append(
            {
                'timestamp': datetime.fromtimestamp(time.time() - (99 - i) * 300, timezone.utc).isoformat(),
                'open': price - 2,
                'high': price + 4,
                'low': price - 5,
                'close': price,
                'volume': 30000 + i * 100,
            }
        )
    display_name = next((item['name'] for item in FALLBACK_STOCKS if item['symbol'] == symbol), symbol)
    return build_quote_from_timeline(symbol, display_name, timeline)


def fetch_quote(symbol):
    query = urllib.parse.urlencode({'interval': '5m', 'range': '5d'})
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?{query}'
    payload = fetch_json(url)

    result = (((payload.get('chart') or {}).get('result') or [None])[0])
    if not result:
        error = ((payload.get('chart') or {}).get('error') or {}).get('description') or 'No data'
        raise ValueError(error)

    timestamps = result.get('timestamp') or []
    quote = ((result.get('indicators') or {}).get('quote') or [{}])[0]
    opens = quote.get('open') or []
    highs = quote.get('high') or []
    lows = quote.get('low') or []
    closes = quote.get('close') or []
    volumes = quote.get('volume') or []

    timeline = []
    for i, ts in enumerate(timestamps):
        close = to_float(closes[i] if i < len(closes) else None)
        if close is None:
            continue
        timeline.append(
            {
                'timestamp': datetime.fromtimestamp(ts, timezone.utc).isoformat(),
                'open': to_float(opens[i] if i < len(opens) else None),
                'high': to_float(highs[i] if i < len(highs) else None),
                'low': to_float(lows[i] if i < len(lows) else None),
                'close': close,
                'volume': to_float(volumes[i] if i < len(volumes) else None),
            }
        )

    if not timeline:
        raise ValueError(f'No data available for {symbol}')

    meta = result.get('meta') or {}
    return build_quote_from_timeline(symbol, meta.get('longName') or meta.get('shortName') or symbol, timeline)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PUBLIC_DIR, **kwargs)

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/api/stocks':
            try:
                stocks = fetch_stocks()
            except Exception:
                stocks = FALLBACK_STOCKS
            self._send_json(200, {'count': len(stocks), 'stocks': stocks})
            return

        if self.path.startswith('/api/quote/'):
            raw_symbol = self.path.split('/api/quote/', 1)[1]
            symbol = urllib.parse.unquote(raw_symbol).strip().upper()
            if not symbol:
                self._send_json(400, {'error': 'Symbol is required'})
                return
            if not (symbol.endswith('.NS') or symbol.endswith('.BO')):
                symbol = f'{symbol}.NS'
            try:
                quote = fetch_quote(symbol)
            except Exception:
                quote = fallback_quote(symbol)
            self._send_json(200, quote)
            return

        return super().do_GET()


if __name__ == '__main__':
    server = ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    print(f'Server running at http://localhost:{PORT}')
    server.serve_forever()
