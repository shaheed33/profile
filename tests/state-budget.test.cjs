const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {scenario, revenueMix, usable, DEFAULTS, LIMITS} = require('../js/state-budget-math.js');

const data = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'state_budget.json'), 'utf8'));
const near = (a, b, tol = 1e-6) => assert.ok(Math.abs(a - b) <= tol, `${a} != ${b}`);

// A tidy made-up jurisdiction so expected values can be worked out by hand.
const toy = {
  revenue: [100, 100, 100, 100, 100], expenses: [95, 95, 95, 95, 95], nob: [5, 5, 5, 5, 5],
  taxation: [30, 30, 30, 30, 30], grants: [50, 50, 50, 50, 50], gst: [30, 30, 30, 30, 30],
  payroll_tax: [10, 10, 10, 10, 10], transfer_duty: [8, 8, 8, 8, 8], royalties: [5, 5, 5, 5, 5],
  employee: [40, 40, 40, 40, 40], interest: [5, 5, 5, 5, 5], net_debt: [200, 200, 200, 200, 200],
  capex: [null, 10, 10, 10, 10]
};

test('no shocks reproduces every published figure exactly', () => {
  for (const j of data.jurisdictions) {
    const r = scenario(j.series, {});
    assert.ok(r, `${j.short} should be usable`);
    r.years.forEach((y, i) => {
      assert.equal(y.nob, j.series.nob[i + 1]);
      assert.equal(y.netDebt, j.series.net_debt[i + 1]);
      assert.equal(y.interest, j.series.interest[i + 1]);
      assert.equal(y.revenue, j.series.revenue[i + 1]);
    });
  }
});

test('a GST cut is a level change each year and its cost is borrowed', () => {
  const r = scenario(toy, {gst: -0.1, borrowingRate: 0});
  r.years.forEach((y, i) => {
    near(y.revenueChange, -3);
    near(y.balanceChange, -3);
    near(y.extraDebt, 3 * (i + 1));
  });
});

test('extra debt carries interest at the borrowing rate, half a year in the first year', () => {
  const r = scenario(toy, {gst: -0.1, borrowingRate: 0.1});
  near(r.years[0].interestChange, 0.15);          // 10% of half of 3
  near(r.years[0].extraDebt, 3.15);
  near(r.years[1].interestChange, 0.1 * (3.15 + 1.5));
});

test('wage growth compounds on employee and superannuation expenses', () => {
  const r = scenario(toy, {wages: 0.01, borrowingRate: 0});
  near(r.years[0].wageCost, 0.4);
  near(r.years[1].wageCost, 40 * (1.01 ** 2 - 1));
  near(r.years[3].wageCost, 40 * (1.01 ** 4 - 1));
});

test('other spending applies only to expenses that are not wages or interest', () => {
  const r = scenario(toy, {otherSpending: 0.1, borrowingRate: 0});
  near(r.years[0].otherCost, 5);                   // 10% of (95 - 40 - 5)
});

test('extra capital spending raises debt but not the operating balance directly', () => {
  const r = scenario(toy, {capex: 0.5, borrowingRate: 0});
  near(r.years[0].balanceChange, 0);
  near(r.years[3].extraDebt, 20);
});

test('a rate shock reprices published debt gradually', () => {
  const r = scenario(toy, {rateShock: 0.01, repricing: 0.25, borrowingRate: 0});
  near(r.years[0].existingDebtInterest, 0.01 * 0.25 * 200);
  near(r.years[3].existingDebtInterest, 0.01 * 1 * 200);
});

test('a rate shock does not create interest on negative net debt', () => {
  const r = scenario({...toy, net_debt: [-50, -50, -50, -50, -50]}, {rateShock: 0.02, borrowingRate: 0});
  near(r.years[0].existingDebtInterest, 0);
});

test('drivers reconcile to the change in the operating balance', () => {
  for (const j of data.jurisdictions) {
    const r = scenario(j.series, {gst: -0.05, payroll: -0.03, duty: -0.2, royalties: -0.3, wages: 0.01, otherSpending: 0.01, rateShock: 0.01});
    for (const y of r.years) {
      near(y.balanceChange, y.revenueChange - y.wageCost - y.otherCost - y.interestChange, 1e-6);
      near(y.nob, j.series.nob[y.index] + y.balanceChange, 1e-6);
      near(y.netDebt - j.series.net_debt[y.index], y.extraDebt, 1e-6);
    }
  }
});

test('a shock that improves the budget is the mirror image of one that hurts it', () => {
  const up = scenario(toy, {payroll: 0.1, borrowingRate: 0.05});
  const down = scenario(toy, {payroll: -0.1, borrowingRate: 0.05});
  up.years.forEach((y, i) => near(y.balanceChange, -down.years[i].balanceChange));
});

test('missing figures make the scenario unavailable instead of zero', () => {
  assert.equal(scenario({...toy, gst: [30, null, 30, 30, 30]}, {}), null);
  assert.equal(scenario({...toy, capex: [null, 10, 10, NaN, 10]}, {}), null);
  assert.equal(scenario({...toy, net_debt: [null, 200, 200, 200, 200]}, {}), null);
  assert.equal(usable(undefined), false);
});

test('assumptions outside the supported range fail loudly', () => {
  assert.throws(() => scenario(toy, {gst: -0.9}), RangeError);
  assert.throws(() => scenario(toy, {wages: NaN}), RangeError);
  assert.throws(() => scenario(toy, {repricing: 2}), RangeError);
  for (const [k, [lo, hi]] of Object.entries(LIMITS)) {
    assert.ok(scenario(toy, {[k]: lo}));
    assert.ok(scenario(toy, {[k]: hi}));
    assert.ok(DEFAULTS[k] >= lo && DEFAULTS[k] <= hi);
  }
});

test('revenue mix adds up to total revenue for every jurisdiction', () => {
  for (const j of data.jurisdictions) {
    for (let k = 1; k <= 4; k++) {
      const parts = revenueMix(j.series, k);
      near(parts.reduce((t, p) => t + p.value, 0), j.series.revenue[k], 1e-6);
      for (const p of parts) assert.ok(p.value >= -1, `${j.short} ${p.key} negative`);
    }
  }
});

test('published data passes the accounting identity in every year', () => {
  for (const j of data.jurisdictions) {
    j.series.revenue.forEach((rev, i) => {
      const tol = Math.max(3, Math.abs(rev) * 0.0005);
      assert.ok(Math.abs(rev - j.series.expenses[i] - j.series.nob[i]) <= tol, `${j.short} year ${i}`);
    });
  }
});
