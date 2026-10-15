/* Deterministic accounting sensitivities, separate from the statistical model. */
(function (root) {
  'use strict';
  function scenario(base, assumptions) {
    const {grantCut, wageGrowth, payrollShare, renewalShare, years} = assumptions;
    const ranges = [[grantCut, 0, .5], [wageGrowth, 0, .15], [payrollShare, 0, 1], [renewalShare, 0, .2]];
    if (!base || !Number.isFinite(base.revenue) || base.revenue <= 0 ||
        !Number.isFinite(base.expenses) || base.expenses <= 0 ||
        !Number.isFinite(base.grant_share) || base.grant_share < 0 || base.grant_share > 1) return null;
    if (![2, 3].includes(years) || ranges.some(([x, lo, hi]) => !Number.isFinite(x) || x < lo || x > hi)) {
      throw new RangeError('Scenario assumptions are outside the supported range');
    }
    const baseline = base.revenue - base.expenses;
    const grantLoss = base.revenue * base.grant_share * grantCut;
    const extraRenewal = base.revenue * renewalShare;
    let cumulativePressure = 0;
    const path = Array.from({length: years}, (_, i) => {
      const wageCost = base.expenses * payrollShare * (Math.pow(1 + wageGrowth, i + 1) - 1);
      const revenue = base.revenue - grantLoss;
      const expenses = base.expenses + wageCost;
      const balance = revenue - expenses;
      const fundingPressure = grantLoss + wageCost + extraRenewal;
      cumulativePressure += fundingPressure;
      return {year: base.year + i + 1, step: i + 1, baseline, balance,
        revenue, expenses, margin: balance / revenue, grantLoss, wageCost,
        extraRenewal, fundingPressure, cumulativePressure};
    });
    return {path, baseline, assumptions: {...assumptions}};
  }
  const api = {scenario};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.CouncilStressMath = api;
})(typeof window === 'undefined' ? globalThis : window);
