// Gateway overhead benchmark.
// For each rate R in RATES, runs two back-to-back scenarios at a constant arrival rate:
//   direct_R : client -> mock upstream                    (baseline)
//   gateway_R: client -> ShieldWall gateway -> mock upstream
// Overhead = gateway latency - direct latency, at the same percentile.
import http from 'k6/http';
import exec from 'k6/execution';
import { Trend, Rate } from 'k6/metrics';

const RATES = (__ENV.RATES || '50,200').split(',').map((r) => parseInt(r, 10));
const DURATION = __ENV.DURATION || '30s';
const GAP_SECONDS = 5;
// API_KEYS = "50:sw_xxx,200:sw_yyy" (one project per rate so the DB cross-check can split them)
const KEYS = Object.fromEntries((__ENV.API_KEYS || '').split(',').filter(Boolean).map((kv) => {
  const i = kv.indexOf(':');
  return [kv.slice(0, i), kv.slice(i + 1)];
}));

const PAYLOAD = JSON.stringify({
  model: 'gpt-4o-mini',
  max_tokens: 64,
  messages: [{
    role: 'user',
    content: 'Hi, I am Riya. Email riya.sharma@example.com, phone +91 98765 43210. Where is my order?',
  }],
});

function seconds(d) {
  const m = /^(\d+)(s|m)$/.exec(d);
  if (!m) throw new Error(`DURATION must look like 30s or 2m, got ${d}`);
  return parseInt(m[1], 10) * (m[2] === 'm' ? 60 : 1);
}

const latency = {};
const errors = {};
const scenarios = {};
let start = 0;
for (const rate of RATES) {
  for (const target of ['direct', 'gateway']) {
    const name = `${target}_${rate}`;
    latency[name] = new Trend(`latency_${name}`, true);
    errors[name] = new Rate(`errors_${name}`);
    scenarios[name] = {
      executor: 'constant-arrival-rate',
      rate,
      timeUnit: '1s',
      duration: DURATION,
      preAllocatedVUs: Math.max(10, rate),
      maxVUs: rate * 4,
      startTime: `${start}s`,
      exec: 'hit',
    };
    start += seconds(DURATION) + GAP_SECONDS;
  }
}

export const options = {
  scenarios,
  summaryTrendStats: ['avg', 'min', 'p(50)', 'p(95)', 'p(99)', 'max'],
  discardResponseBodies: true,
};

export function hit() {
  const name = exec.scenario.name;
  const [target, rate] = name.split('_');
  const headers = { 'Content-Type': 'application/json' };
  let url = __ENV.DIRECT_URL;
  if (target === 'gateway') {
    url = __ENV.GATEWAY_URL;
    headers.Authorization = `Bearer ${KEYS[rate]}`;
  }
  const res = http.post(url, PAYLOAD, { headers, tags: { scenario_name: name } });
  latency[name].add(res.timings.duration);
  errors[name].add(res.status !== 200);
}

function stat(data, metric, key) {
  const m = data.metrics[metric];
  return m ? m.values[key] : null;
}

export function handleSummary(data) {
  const rows = [];
  for (const rate of RATES) {
    const d = `direct_${rate}`;
    const g = `gateway_${rate}`;
    const row = { rate_rps: rate, duration: DURATION };
    for (const p of ['p(50)', 'p(95)', 'p(99)']) {
      const key = p.replace(/[()]/g, '');
      const dv = stat(data, `latency_${d}`, p);
      const gv = stat(data, `latency_${g}`, p);
      row[`direct_${key}_ms`] = dv;
      row[`gateway_${key}_ms`] = gv;
      row[`overhead_${key}_ms`] = dv !== null && gv !== null ? gv - dv : null;
    }
    const count = (n) => (data.metrics[`errors_${n}`] ? data.metrics[`errors_${n}`].values.passes
      + data.metrics[`errors_${n}`].values.fails : 0);
    row.direct_requests = count(d);
    row.gateway_requests = count(g);
    row.direct_error_rate = stat(data, `errors_${d}`, 'rate');
    row.gateway_error_rate = stat(data, `errors_${g}`, 'rate');
    rows.push(row);
  }
  const fmt = (v) => (v === null || v === undefined ? 'n/a' : v.toFixed(2));
  const pct = (v) => (v === null || v === undefined ? 'n/a' : `${(v * 100).toFixed(2)}%`);
  let md = '# Gateway overhead benchmark\n\n';
  md += `Written by bench/run.sh on ${new Date().toISOString()}.\n\n`;
  if (__ENV.HARDWARE) md += `Hardware: ${__ENV.HARDWARE}\n\n`;
  md += 'Mock upstream latency is fixed (MOCK_LATENCY_MS); overhead = gateway - direct at the same percentile.\n\n';
  md += '| Rate (RPS) | Duration | Requests direct / gateway | Direct p50 / p95 / p99 (ms) | Gateway p50 / p95 / p99 (ms) | Overhead p50 / p95 / p99 (ms) | Errors direct / gateway |\n';
  md += '|---|---|---|---|---|---|---|\n';
  for (const r of rows) {
    md += `| ${r.rate_rps} | ${r.duration} | ${r.direct_requests} / ${r.gateway_requests} | ${fmt(r.direct_p50_ms)} / ${fmt(r.direct_p95_ms)} / ${fmt(r.direct_p99_ms)} `
      + `| ${fmt(r.gateway_p50_ms)} / ${fmt(r.gateway_p95_ms)} / ${fmt(r.gateway_p99_ms)} `
      + `| ${fmt(r.overhead_p50_ms)} / ${fmt(r.overhead_p95_ms)} / ${fmt(r.overhead_p99_ms)} `
      + `| ${pct(r.direct_error_rate)} / ${pct(r.gateway_error_rate)} |\n`;
  }
  return {
    stdout: md,
    '/results/k6-summary.json': JSON.stringify({ rows, raw: data.metrics }, null, 2),
    '/results/summary.md': md,
  };
}
