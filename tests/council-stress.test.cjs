const {test} = require('node:test');
const assert = require('node:assert/strict');
const {scenario} = require('../js/council-stress-math.js');
const base = {year: 2025, revenue: 100e6, expenses: 90e6, grant_share: .4};
const zero = {grantCut: 0, wageGrowth: 0, payrollShare: .35, renewalShare: 0, years: 3};
const near = (actual, expected) => assert.ok(Math.abs(actual - expected) < 1e-6, `${actual} != ${expected}`);

test('zero shocks preserve the observed accounting balance at every horizon', () => {
  const result = scenario(base, zero);
  assert.deepEqual(result.path.map(r => r.year), [2026, 2027, 2028]);
  for (const r of result.path) {
    assert.equal(r.balance, 10e6);
    assert.equal(r.fundingPressure, 0);
    assert.equal(r.cumulativePressure, 0);
  }
});
test('grant cut is a permanent level change, not compounded each year', () => {
  const r = scenario(base, {...zero, grantCut: .1});
  assert.deepEqual(r.path.map(p => p.grantLoss), [4e6, 4e6, 4e6]);
  assert.deepEqual(r.path.map(p => p.balance), [6e6, 6e6, 6e6]);
  assert.equal(r.path[2].cumulativePressure, 12e6);
});
test('wages compound on the explicit assumed payroll share', () => {
  const r = scenario(base, {...zero, wageGrowth: .1, payrollShare: .5});
  near(r.path[0].wageCost, 4.5e6);
  near(r.path[1].wageCost, 9.45e6);
  near(r.path[2].wageCost, 14.895e6);
});
test('capital renewal adds funding pressure without expensing the capital outlay', () => {
  const r = scenario(base, {...zero, renewalShare: .05});
  assert.equal(r.path[2].balance, 10e6);
  assert.equal(r.path[2].extraRenewal, 5e6);
  assert.equal(r.path[2].cumulativePressure, 15e6);
});
test('combined final-year drivers reconcile to the funding-pressure total', () => {
  const r = scenario(base, {...zero, grantCut: .2, wageGrowth: .04, renewalShare: .02});
  for (const p of r.path) near(p.fundingPressure, p.baseline - p.balance + p.extraRenewal);
});
test('missing finance is unavailable, never treated as zero', () => {
  for (const key of ['revenue', 'expenses', 'grant_share']) {
    assert.equal(scenario({...base, [key]: null}, zero), null);
    assert.equal(scenario({...base, [key]: NaN}, zero), null);
  }
  assert.equal(scenario({...base, revenue: 0}, zero), null);
});
test('real zero grant exposure is distinct from missing data', () => {
  assert.equal(scenario({...base, grant_share: 0}, {...zero, grantCut: .5}).path[0].grantLoss, 0);
});
test('out-of-range assumptions fail explicitly', () => {
  assert.throws(() => scenario(base, {...zero, years: 4}), RangeError);
  assert.throws(() => scenario(base, {...zero, wageGrowth: -.1}), RangeError);
  assert.throws(() => scenario(base, {...zero, payrollShare: NaN}), RangeError);
});
