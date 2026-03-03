const stockListEl = document.getElementById('stockList');
const stockCountEl = document.getElementById('stockCount');
const searchInput = document.getElementById('searchInput');
const emptyState = document.getElementById('emptyState');
const stockDetails = document.getElementById('stockDetails');
const stockNameEl = document.getElementById('stockName');
const stockSymbolEl = document.getElementById('stockSymbol');
const latestPriceEl = document.getElementById('latestPrice');
const priceChangeEl = document.getElementById('priceChange');
const rsiEl = document.getElementById('rsi');
const statsGrid = document.getElementById('statsGrid');
const timelineBody = document.getElementById('timelineBody');

let allStocks = [];
let selectedSymbol = null;
let poller = null;

const formatNum = (value, digits = 2) => {
  if (value === null || Number.isNaN(value)) return '—';
  return Number(value).toLocaleString('en-IN', {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
};

const formatCompact = (value) => {
  if (value === null || Number.isNaN(value)) return '—';
  return new Intl.NumberFormat('en-IN', {
    notation: 'compact',
    maximumFractionDigits: 2,
  }).format(value);
};

const statCard = (label, value) => `
  <article class="stat">
    <span>${label}</span>
    <strong>${value}</strong>
  </article>
`;

const renderStockList = (stocks) => {
  stockListEl.innerHTML = '';

  stocks.slice(0, 600).forEach((stock) => {
    const li = document.createElement('li');
    const button = document.createElement('button');
    button.className = 'stock-item';
    button.innerHTML = `<strong>${stock.name}</strong><small>${stock.symbol}</small>`;
    button.addEventListener('click', () => {
      selectedSymbol = stock.symbol;
      loadQuote(stock.symbol);
      if (poller) clearInterval(poller);
      poller = setInterval(() => loadQuote(stock.symbol, true), 60 * 1000);
    });
    li.appendChild(button);
    stockListEl.appendChild(li);
  });
};

const renderQuote = (data) => {
  emptyState.classList.add('hidden');
  stockDetails.classList.remove('hidden');

  const { stats } = data;
  const changeClass = stats.priceChange >= 0 ? 'positive' : 'negative';

  stockNameEl.textContent = data.name;
  stockSymbolEl.textContent = `${data.symbol} · ${data.currency}`;
  latestPriceEl.textContent = `₹${formatNum(stats.latestPrice)}`;

  priceChangeEl.className = changeClass;
  priceChangeEl.textContent = `${stats.priceChange >= 0 ? '+' : ''}${formatNum(stats.priceChange)} (${formatNum(stats.priceChangePct)}%)`;

  rsiEl.textContent = formatNum(stats.rsi14);

  statsGrid.innerHTML = [
    statCard('SMA 20', `₹${formatNum(stats.sma20)}`),
    statCard('EMA 20', `₹${formatNum(stats.ema20)}`),
    statCard('Day High', `₹${formatNum(stats.dayHigh)}`),
    statCard('Day Low', `₹${formatNum(stats.dayLow)}`),
    statCard('Avg Volume', formatCompact(stats.avgVolume)),
    statCard('Volatility', `${formatNum(stats.volatility)}%`),
  ].join('');

  const recentRows = data.timeline.slice(-20).reverse();
  timelineBody.innerHTML = recentRows
    .map(
      (row) => `
      <tr>
        <td>${new Date(row.timestamp).toLocaleString('en-IN', { hour12: false })}</td>
        <td>${formatNum(row.open)}</td>
        <td>${formatNum(row.high)}</td>
        <td>${formatNum(row.low)}</td>
        <td>${formatNum(row.close)}</td>
        <td>${formatCompact(row.volume)}</td>
      </tr>
    `,
    )
    .join('');
};

const loadQuote = async (symbol, silent = false) => {
  try {
    const res = await fetch(`/api/quote/${encodeURIComponent(symbol)}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to load quote');
    renderQuote(data);
  } catch (error) {
    if (!silent) {
      emptyState.classList.remove('hidden');
      emptyState.textContent = error.message;
      stockDetails.classList.add('hidden');
    }
  }
};

const loadStocks = async () => {
  stockCountEl.textContent = 'Loading stock universe...';

  try {
    const res = await fetch('/api/stocks');
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Unable to load stocks');

    allStocks = data.stocks;
    stockCountEl.textContent = `${data.count.toLocaleString('en-IN')} Indian stocks available`;
    renderStockList(allStocks);
  } catch (error) {
    stockCountEl.textContent = error.message;
  }
};

searchInput.addEventListener('input', (event) => {
  const q = event.target.value.trim().toLowerCase();
  if (!q) {
    renderStockList(allStocks);
    return;
  }

  const filtered = allStocks.filter(
    (item) => item.name.toLowerCase().includes(q) || item.symbol.toLowerCase().includes(q),
  );

  stockCountEl.textContent = `${filtered.length.toLocaleString('en-IN')} matches`;
  renderStockList(filtered);
});

loadStocks();
