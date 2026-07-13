// 세무조정 계산 엔진 — 4개 항목의 한도초과액을 계산하는 순수 함수 모음.
// 금액 단위는 전부 "원"으로 통일한다 (호출부에서 만원/억원 단위를 원 단위로 환산해 전달할 것).
// 각 함수는 { limit, excess, basis, lawRef } 형태를 반환한다.
//   limit  : 세법상 손금 한도액
//   excess : 한도초과액(손금불산입액). 0 이상.
//   basis  : 계산 과정을 보여주는 { label, value } 배열
//   lawRef : { name, url } 근거 법령과 law.go.kr 링크

// law/jo는 /api/lawtext (법제처 국가법령정보센터 Open API 프록시)에서 원문을 가져올 때 쓰는 키.
// 4개 항목 모두 시행령이 아니라 법인세법 본조에 한도 산식이 직접 규정되어 있음 (law.go.kr Open API로 확인).
const LAW_LINKS = {
  entertainment: { name: "법인세법 제25조 (기업업무추진비의 손금불산입)", url: "https://www.law.go.kr/법령/법인세법/제25조", law: "법인세법", jo: 25 },
  depreciation:  { name: "법인세법 제23조 (감가상각비의 손금불산입)", url: "https://www.law.go.kr/법령/법인세법/제23조", law: "법인세법", jo: 23 },
  badDebt:       { name: "법인세법 제34조 (대손충당금의 손금산입)", url: "https://www.law.go.kr/법령/법인세법/제34조", law: "법인세법", jo: 34 },
  donation:      { name: "법인세법 제24조 (기부금의 손금불산입)", url: "https://www.law.go.kr/법령/법인세법/제24조", law: "법인세법", jo: 24 },
};

function clamp0(n) { return n > 0 ? n : 0; }

/**
 * 기업업무추진비(접대비) 한도초과액.
 * @param {object} p
 * @param {number} p.revenue      해당 사업연도 수입금액(매출액, 원)
 * @param {boolean} p.isSmallBiz  중소기업 여부 (기본한도 3,600만 vs 1,200만)
 * @param {number} p.spent        실제 지출한 기업업무추진비(원)
 * @param {number} [p.months]     사업연도 월수(월할 계산용, 기본 12)
 */
function entertainmentLimit({ revenue, isSmallBiz, spent, months = 12 }) {
  const baseLimit = Math.round((isSmallBiz ? 36_000_000 : 12_000_000) * (months / 12));

  const TIERS = [
    { upTo: 10_000_000_000, rate: 0.003 },   // 100억원 이하분: 0.3%
    { upTo: 50_000_000_000, rate: 0.002 },   // 100억~500억원분: 0.2%
    { upTo: Infinity, rate: 0.0003 },        // 500억원 초과분: 0.03%
  ];
  let remaining = clamp0(revenue);
  let prevCap = 0;
  let revenueLimit = 0;
  for (const tier of TIERS) {
    if (remaining <= 0) break;
    const bracketSize = tier.upTo - prevCap;
    const taxedInBracket = Math.min(remaining, bracketSize);
    revenueLimit += taxedInBracket * tier.rate;
    remaining -= taxedInBracket;
    prevCap = tier.upTo;
  }

  const limit = baseLimit + revenueLimit;
  const excess = clamp0(spent - limit);

  return {
    limit,
    excess,
    basis: [
      { label: "기본한도", value: baseLimit },
      { label: "수입금액 한도 (체감률 적용)", value: Math.round(revenueLimit) },
      { label: "한도 합계", value: Math.round(limit) },
      { label: "실제 지출액", value: spent },
    ],
    lawRef: LAW_LINKS.entertainment,
  };
}

/**
 * 감가상각비 시부인 계산 (정액법 단순 가정).
 * @param {object} p
 * @param {number} p.acquisitionCost 세무상 취득가액(원)
 * @param {number} p.rate            세법상 상각률 (예: 내용연수 5년 → 0.2)
 * @param {number} p.bookDepreciation 회사가 계상한 감가상각비(원)
 */
function depreciationDisqualified({ acquisitionCost, rate, bookDepreciation }) {
  const limit = acquisitionCost * rate;
  const excess = clamp0(bookDepreciation - limit);
  const shortfall = clamp0(limit - bookDepreciation);

  return {
    limit,
    excess,
    basis: [
      { label: "세법상 상각범위액 (취득가액 × 상각률)", value: Math.round(limit) },
      { label: "회사 계상 감가상각비", value: bookDepreciation },
      { label: "시인부족액 (참고, 손금추인 불가)", value: Math.round(shortfall) },
    ],
    lawRef: LAW_LINKS.depreciation,
  };
}

/**
 * 대손충당금 한도초과액.
 * @param {object} p
 * @param {number} p.receivables 세무상 채권잔액(원)
 * @param {number} p.bookReserve 회사가 설정한 대손충당금(원)
 * @param {number} p.actualRate  대손실적률 (예: 0.015 = 1.5%)
 */
function badDebtReserveLimit({ receivables, bookReserve, actualRate }) {
  const appliedRate = Math.max(0.01, actualRate || 0);
  const limit = receivables * appliedRate;
  const excess = clamp0(bookReserve - limit);

  return {
    limit,
    excess,
    basis: [
      { label: "적용률 (MAX(1%, 대손실적률))", value: appliedRate, isRate: true },
      { label: "한도액 (채권잔액 × 적용률)", value: Math.round(limit) },
      { label: "회사 설정액", value: bookReserve },
    ],
    lawRef: LAW_LINKS.badDebt,
  };
}

/**
 * 기부금 한도초과액 (특례기부금 50% → 일반기부금 10% 순서로 계산).
 * @param {object} p
 * @param {number} p.adjustedIncome  기준소득금액 (차가감소득금액 + 기부금 지출액)
 * @param {number} p.specialDonation 특례기부금 지출액
 * @param {number} p.generalDonation 일반기부금 지출액
 */
function donationLimit({ adjustedIncome, specialDonation, generalDonation }) {
  const specialCap = adjustedIncome * 0.5;
  const specialRecognized = Math.min(specialDonation, specialCap);
  const specialExcess = clamp0(specialDonation - specialCap);

  const generalBase = adjustedIncome - specialRecognized;
  const generalCap = generalBase * 0.1;
  const generalRecognized = Math.min(generalDonation, generalCap);
  const generalExcess = clamp0(generalDonation - generalCap);

  const limit = specialCap + generalCap;
  const excess = specialExcess + generalExcess;

  return {
    limit,
    excess,
    basis: [
      { label: "특례기부금 한도 (기준소득금액 × 50%)", value: Math.round(specialCap) },
      { label: "특례기부금 한도초과액", value: Math.round(specialExcess) },
      { label: "일반기부금 한도 (잔여기준소득 × 10%)", value: Math.round(generalCap) },
      { label: "일반기부금 한도초과액", value: Math.round(generalExcess) },
    ],
    lawRef: LAW_LINKS.donation,
  };
}
