// Charge à débit constant sur /order et /catalog, avec journal de chaque requête.
import http from 'k6/http';
import { Trend, Rate } from 'k6/metrics';

const RATE = Number(__ENV.RATE || 100);              // requêtes par seconde au total
const DURATION = __ENV.DURATION || '180s';           // durée de l'exécution
const ORDER_SHARE = Number(__ENV.ORDER_SHARE || 0.5); // part de la charge vers /order
const BASE = __ENV.BASE_URL || 'http://order:8080';
const CLIENT_TIMEOUT = __ENV.CLIENT_TIMEOUT || '10s'; // le client abandonne après ce délai
const OUT_DIR = __ENV.OUT_DIR || '/results';

const orderRate = Math.max(1, Math.round(RATE * ORDER_SHARE));
const catalogRate = Math.max(1, RATE - orderRate);

export const options = {
  scenarios: {
    orders:  { executor: 'constant-arrival-rate', rate: orderRate,   timeUnit: '1s',
               duration: DURATION, preAllocatedVUs: 50, maxVUs: 600, exec: 'order' },
    catalog: { executor: 'constant-arrival-rate', rate: catalogRate, timeUnit: '1s',
               duration: DURATION, preAllocatedVUs: 50, maxVUs: 600, exec: 'catalog' },
  },
  summaryTrendStats: ['count', 'avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

const orderDuration = new Trend('order_duration', true);
const catalogDuration = new Trend('catalog_duration', true);
const orderSuccess = new Rate('order_success');
const catalogSuccess = new Rate('catalog_success');

// Envoie une requête, mesure sa durée réelle et l'écrit dans le journal
function call(ep, url, params, trend, rate) {
  const start = Date.now();
  const res = http.get(url, params);
  const elapsed = Date.now() - start;
  const ok = res.status === 200;
  trend.add(elapsed);
  rate.add(ok);

  let reason = 'OK';
  if (!ok) {
    if (res.status === 0) {
      reason = res.error_code === 1050 ? 'CLIENT_TIMEOUT' : 'CLIENT_ERROR';
    } else if (ep === 'order' && res.status === 503) {
      reason = 'HTTP_503';
      try { reason = res.json('reason') || reason; } catch (e) {}
    } else {
      reason = 'HTTP_' + res.status;
    }
  }
  console.log(JSON.stringify({ t: start, ep: ep, s: res.status, d: elapsed, r: reason }));
}

export function order() {
  call('order', `${BASE}/order`, { timeout: CLIENT_TIMEOUT }, orderDuration, orderSuccess);
}

export function catalog() {
  call('catalog', `${BASE}/catalog`, { timeout: CLIENT_TIMEOUT, responseType: 'none' },
       catalogDuration, catalogSuccess);
}

// Résumé de fin d'exécution : affiché à l'écran et sauvegardé en JSON
export function handleSummary(data) {
  const v = (name) => (data.metrics[name] ? data.metrics[name].values : {});
  const ep = (d, s) => ({
    requests: d.count || 0,
    success_rate: s.rate !== undefined ? s.rate : null,
    avg_ms: d.avg, p50_ms: d.med, p90_ms: d['p(90)'], p95_ms: d['p(95)'], p99_ms: d['p(99)'], max_ms: d.max,
  });
  const summary = {
    rate: RATE, duration: DURATION, order_share: ORDER_SHARE,
    order: ep(v('order_duration'), v('order_success')),
    catalog: ep(v('catalog_duration'), v('catalog_success')),
    dropped_iterations: v('dropped_iterations').count || 0,
  };
  const f = (x) => (x === undefined || x === null ? '-' : Number(x).toFixed(1));
  const pct = (x) => (x === null ? '-' : (x * 100).toFixed(1) + '%');
  const line = (name, e) =>
    `${name.padEnd(9)} n=${e.requests}  succès=${pct(e.success_rate)}  ` +
    `p50=${f(e.p50_ms)}  p95=${f(e.p95_ms)}  p99=${f(e.p99_ms)}  max=${f(e.max_ms)} ms\n`;
  const text = '\n=== Résumé ===\n' + line('/order', summary.order) + line('/catalog', summary.catalog) +
    `Requêtes non envoyées (k6 saturé) : ${summary.dropped_iterations}\n`;
  return { [`${OUT_DIR}/summary.json`]: JSON.stringify(summary, null, 2), stdout: text };
}
