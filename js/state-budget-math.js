/* State Budget Resilience Monitor: the scenario arithmetic.
 *
 * Deterministic and transparent. It starts from each government's published
 * general government budget (2026-27 to 2029-30) and adds the effect of the
 * shocks the reader chooses. Everything else stays exactly as published.
 *
 * Index 0 of every series is 2025-26 (the latest estimate of the year just
 * finished); indexes 1 to 4 are the budget year and three forward years.
 * All amounts are $ million.
 */
(function (root) {
  'use strict';

  var LIMITS = {
    gst: [-0.5, 0.5], otherGrants: [-0.5, 0.5], payroll: [-0.5, 0.5], duty: [-0.6, 0.6], royalties: [-0.8, 0.8],
    wages: [-0.02, 0.05], otherSpending: [-0.1, 0.2], capex: [-0.5, 0.5],
    rateShock: [-0.02, 0.04], repricing: [0, 1], borrowingRate: [0, 0.12]
  };

  var DEFAULTS = {
    gst: 0, otherGrants: 0, payroll: 0, duty: 0, royalties: 0,
    wages: 0, otherSpending: 0, capex: 0,
    rateShock: 0, repricing: 0.2, borrowingRate: 0.05
  };

  var REQUIRED = ['revenue', 'expenses', 'nob', 'grants', 'gst', 'payroll_tax', 'transfer_duty', 'royalties',
    'employee', 'interest', 'net_debt', 'capex'];

  function finite(x) { return typeof x === 'number' && isFinite(x); }

  function validate(a) {
    var out = {};
    Object.keys(DEFAULTS).forEach(function (k) {
      var v = a && a[k] !== undefined ? a[k] : DEFAULTS[k];
      if (!finite(v) || v < LIMITS[k][0] - 1e-12 || v > LIMITS[k][1] + 1e-12) {
        throw new RangeError('Assumption "' + k + '" must be between ' + LIMITS[k][0] + ' and ' + LIMITS[k][1]);
      }
      out[k] = v;
    });
    return out;
  }

  /* Returns null when the jurisdiction lacks a figure the scenario needs.
   * Missing data is never treated as zero. */
  function usable(series) {
    if (!series) return false;
    return REQUIRED.every(function (k) {
      var s = series[k];
      if (!s || s.length < 5) return false;
      for (var i = 1; i < 5; i++) if (!finite(s[i])) return false;
      return k !== 'net_debt' || finite(s[0]);
    });
  }

  function scenario(series, assumptions) {
    var a = validate(assumptions);
    if (!usable(series)) return null;
    var s = series;
    var years = [];
    var extraDebt = 0;          // cumulative change in net debt caused by the scenario
    var cumulative = 0;         // cumulative change in the operating balance
    for (var k = 1; k <= 4; k++) {
      var otherGrants = s.grants[k] - s.gst[k];
      var otherExpenses = s.expenses[k] - s.employee[k] - s.interest[k];
      var parts = {
        gst: s.gst[k] * a.gst,
        otherGrants: otherGrants * a.otherGrants,
        payroll: s.payroll_tax[k] * a.payroll,
        duty: s.transfer_duty[k] * a.duty,
        royalties: s.royalties[k] * a.royalties
      };
      var revenueChange = parts.gst + parts.otherGrants + parts.payroll + parts.duty + parts.royalties;
      var wageCost = s.employee[k] * (Math.pow(1 + a.wages, k) - 1);
      var otherCost = otherExpenses * a.otherSpending;
      var capexChange = s.capex[k] * a.capex;
      // Cash needed before interest: a weaker operating result plus any extra capital spending.
      var needBeforeInterest = -(revenueChange - wageCost - otherCost) + capexChange;
      // Extra debt is assumed to be raised evenly through the year, so it costs half a year's interest.
      var newDebtInterest = (a.borrowingRate + a.rateShock) * (extraDebt + needBeforeInterest / 2);
      // A rate shock also reaches published debt as it is refinanced: a share each year, building up.
      var repriced = Math.min(1, a.repricing * k);
      var openingDebt = Math.max(0, s.net_debt[k - 1]);
      var existingDebtInterest = a.rateShock * repriced * openingDebt;
      var interestChange = newDebtInterest + existingDebtInterest;
      var balanceChange = revenueChange - wageCost - otherCost - interestChange;
      extraDebt += needBeforeInterest + interestChange;
      cumulative += balanceChange;
      var revenue = s.revenue[k] + revenueChange;
      var interest = s.interest[k] + interestChange;
      var netDebt = s.net_debt[k] + extraDebt;
      years.push({
        index: k,
        published: {
          revenue: s.revenue[k], expenses: s.expenses[k], nob: s.nob[k], interest: s.interest[k],
          netDebt: s.net_debt[k], capex: s.capex[k],
          debtToRevenue: s.net_debt[k] / s.revenue[k], interestToRevenue: s.interest[k] / s.revenue[k]
        },
        revenueParts: parts,
        revenueChange: revenueChange,
        wageCost: wageCost,
        otherCost: otherCost,
        interestChange: interestChange,
        newDebtInterest: newDebtInterest,
        existingDebtInterest: existingDebtInterest,
        capexChange: capexChange,
        balanceChange: balanceChange,
        cumulativeBalanceChange: cumulative,
        extraDebt: extraDebt,
        revenue: revenue,
        expenses: s.expenses[k] + wageCost + otherCost + interestChange,
        nob: s.nob[k] + balanceChange,
        interest: interest,
        netDebt: netDebt,
        debtToRevenue: netDebt / revenue,
        interestToRevenue: interest / revenue
      });
    }
    return { years: years, assumptions: a };
  }

  /* Revenue mix in the budget year, for the exposure chart. Parts add up to total revenue. */
  function revenueMix(series, k) {
    k = k === undefined ? 1 : k;
    var s = series;
    var otherTax = s.taxation[k] - s.payroll_tax[k] - s.transfer_duty[k];
    var otherGrants = s.grants[k] - s.gst[k];
    var other = s.revenue[k] - s.taxation[k] - s.grants[k] - s.royalties[k];
    return [
      { key: 'gst', value: s.gst[k] },
      { key: 'otherGrants', value: otherGrants },
      { key: 'payroll', value: s.payroll_tax[k] },
      { key: 'duty', value: s.transfer_duty[k] },
      { key: 'otherTax', value: otherTax },
      { key: 'royalties', value: s.royalties[k] },
      { key: 'other', value: other }
    ];
  }

  var api = { scenario: scenario, revenueMix: revenueMix, usable: usable, LIMITS: LIMITS, DEFAULTS: DEFAULTS };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.StateBudgetMath = api;
})(typeof window === 'undefined' ? globalThis : window);
