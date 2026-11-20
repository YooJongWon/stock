const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const base = path.resolve(__dirname, '..');
function load(relative, dependencies = {}) {
  const module = { exports: {} };
  const code = ts.transpileModule(fs.readFileSync(path.join(base, relative), 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
  }).outputText;
  new Function('require', 'module', 'exports', code)(name => dependencies[name] ?? require(name), module, module.exports);
  return module.exports;
}
const plan = load('lib/swing-plan.ts');
test('old strategy settings adopt 6/10 exits without changing allocations', () => {
  const next = plan.normalizeExitSettings({ total: '20000', stockCount: '5', cashRatio: '17', firstBuyRatio: '60', firstTargetRatio: '8', finalTargetRatio: '12', stopLossRatio: '-7' });
  assert.equal(next.firstTargetRatio, '6'); assert.equal(next.finalTargetRatio, '10'); assert.equal(next.stopLossRatio, '-5');
  assert.equal(next.total, '20000'); assert.equal(next.cashRatio, '17');
  assert.deepEqual(plan.normalizeExitSettings(next), next);
  assert.equal(plan.normalizeExitSettings({ ...next, firstTargetRatio: '7' }).firstTargetRatio, '7');
});
test('legacy exits retain actual sold percentages and migration is idempotent', () => {
  for (const [stage, nextStage, sold] of [[0,0,0],[1,1,40],[2,1,70],[3,2,100]]) {
    const next = plan.normalizeSellProgress({ sellStage: stage, exitStatus: stage === 3 ? 'completed' : 'active' });
    assert.equal(next.sellStage, nextStage); assert.equal(next.legacySoldPct, sold);
    assert.deepEqual(plan.normalizeSellProgress({ ...next, exitStatus: 'active' }), next);
  }
  assert.equal(plan.normalizeSellProgress({ sellStage: 1, exitStatus: 'active', exitPlanVersion: '2' }).legacySoldPct, 0);
});
test('API saves first-buy-only exits, legacy progress and undo history without changing cash', async () => {
  process.env.PORTFOLIO_SESSION_SECRET = 'local-test-session-secret';
  process.env.SUPABASE_URL = 'https://test.invalid';
  process.env.SUPABASE_SECRET_KEY = 'sb_secret_local_test';
  const auth = load('lib/portfolio-auth.ts');
  const route = load('app/api/portfolio/route.ts', { '@/lib/portfolio-auth': auth, '@/lib/swing-plan': plan, '@/lib/portfolio-supabase': load('lib/portfolio-supabase.ts') });
  const { NextRequest } = require('next/server');
  const token = auth.createPortfolioSession().token;
  const originalFetch = global.fetch;
  let saved;
  global.fetch = async (url, init) => { assert.ok(url.startsWith('https://test.invalid/')); saved = JSON.parse(init.body); return new Response(null, { status: 204 }); };
  const snapshot = { firstBuyAmount: 1000, secondBuyAmount: 0, legacyInvestedAmount: 0, buyStage: 1, sellStage: 0, exitStatus: 'active', exitPlanVersion: '2', legacySoldPct: 0 };
  const holding = { ...snapshot, id: 'a', ticker: 'AAPL', note: '', sellStage: 1, undoHistory: [{ action: '1차 매도', createdAt: '', before: snapshot }] };
  async function patch(positions) { return route.PATCH(new NextRequest('http://localhost/api/portfolio', { method: 'PATCH', headers: { cookie: `portfolio_session=${token}` }, body: JSON.stringify({ positions }) })); }
  try {
    assert.equal((await patch([holding])).status, 200);
    assert.equal(saved.positions[0].buyStage, 1); assert.equal(saved.positions[0].sellStage, 1);
    assert.equal(saved.positions[0].undoHistory[0].before.exitPlanVersion, '2'); assert.ok(!('cash_balance' in saved));
    const legacy = { ...holding, buyStage: 2, sellStage: 2, secondBuyAmount: 1000, exitPlanVersion: undefined, undoHistory: [] };
    assert.equal((await patch([legacy])).status, 200);
    assert.equal(saved.positions[0].legacySoldPct, 70); assert.equal(saved.positions[0].sellStage, 1);
    assert.equal((await patch([{ ...holding, sellStage: 3 }])).status, 400);
  } finally { global.fetch = originalFetch; }
});
