"use client";

import { useEffect, useState } from "react";
import MomentumObservations, { type Observation, type UniverseScope } from "./momentum-observations";

type Metrics = { trades: number; target_rate: number | null; stop_rate: number | null; win_rate: number | null; mean_return: number | null; profit_factor: number | null; max_drawdown: number | null; expectancy: number | null };
type Candidate = { ticker: string; name?: string; score: number; stage: string; rsi14: number; rvol: number; atr_pct: number; relative_strength: number; return5: number; return10: number; return20: number; reasons: string[]; warnings: string[] };
type GroupStats = { n: number; mean: number | null; median: number | null; q25: number | null; q75: number | null };
type FeatureStats = { horizon: number; lag: number; feature: string; success: GroupStats; failure: GroupStats; mean_difference: number | null };
type Model = { score_threshold: number; rules: { feature: string; threshold: number; direction: number; weight: number }[] };
type Research = { train_observations?: number; validation_observations?: number; training_metrics?: Metrics; selected_model?: Model; status: string; generated_at?: string; period?: { start: string; end: string; split: string }; universe_count?: number; requested_count?: number; downloaded_count?: number; analyzed_count?: number; observations?: number; cap_known_observations?: number; validation?: { metrics: Metrics }; baselines?: { simple_momentum: { metrics: Metrics }; spy_same_exits: { metrics: Metrics }; spy_buy_hold_return: number }; limitations?: string[]; validation_gates?: Record<string, boolean>; adopted_model?: Model | null };
type Snapshot = { universe_scope?: UniverseScope; observations?: Observation; status: string; data_date?: string; generated_at?: string; research_generated_at?: string; candidates?: Candidate[]; diagnostics?: { ticker?: string; error: string }[]; universe_count?: number };
const pct = (v: number | null | undefined) => v == null ? "—" : `${(v * 100).toFixed(2)}%`;
const num = (v: number | null | undefined) => v == null ? "—" : v.toLocaleString("ko-KR", { maximumFractionDigits: 2 });
const kst = (v?: string) => v ? new Date(v).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" }) : "—";

const featureLabels: Record<string, string> = { rsi14: "RSI14", rvol: "상대 거래량 RVOL", atr_pct: "ATR14 / 주가", return5: "5일 수익률", return10: "10일 수익률", return20: "20일 수익률", ema20_gap: "EMA20 대비 이격", sma50_gap: "SMA50 대비 이격", sma200_gap: "SMA200 대비 이격", high20_gap: "20일 고점 대비 거리", high252_gap: "52주 고점 대비 거리", relative_strength: "SPY 대비 상대강도", volume_growth: "거래량 증가율", body_ratio: "일봉 몸통 비율", upper_wick_ratio: "윗꼬리 비율", ema20: "EMA20 ($)", sma50: "SMA50 ($)", sma200: "SMA200 ($)", market_cap: "시가총액 ($)" };
const gateLabels: Record<string, string> = { sample: "검증 100거래·실제 거래 30종목 이상", positive_expectancy: "비용 차감 기대수익이 양수", profit_factor: "Profit Factor 1 초과", baseline_expectancy: "단순 모멘텀보다 높은 기대수익", full_universe: "전체 유니버스 분석", cap_coverage: "시점별 시가총액 확인" };
const featureValue = (name: string, value: number | null) => ["rsi14", "rvol", "ema20", "sma50", "sma200", "market_cap"].includes(name) ? `${num(value)}${name === "rvol" && value != null ? "x" : ""}` : pct(value);

export default function Momentum() {
  const [data, setData] = useState<{ research: Research; snapshot: Snapshot; statistics: FeatureStats[] } | null>(null);
  const [horizon, setHorizon] = useState(20);
  const [lag, setLag] = useState(1);
  const [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    const reports = Promise.all(["momentum-research.json", "latest-momentum.json"].map(async (name) => {
      const response = await fetch(`/data/${name}`, { cache: "no-store", signal: controller.signal });
      if (!response.ok) throw new Error("missing");
      return response.json();
    }));
    const statistics = fetch("/data/momentum-feature-statistics.json", { cache: "no-store", signal: controller.signal }).then(async response => response.ok ? response.json() : []).catch(() => []);
    Promise.all([reports, statistics]).then(([[research, snapshot], statistics]) => setData({ research, snapshot, statistics })).catch((e) => { if (e.name !== "AbortError") setError(true); });
    return () => controller.abort();
  }, []);
  if (error) return <section className="hero"><h1>급등 모멘텀</h1><p role="alert">분석 파일을 불러오지 못했습니다. 실제 검증 전에는 후보와 성과를 표시하지 않습니다.</p></section>;
  if (!data) return <section className="hero" aria-live="polite"><h1>급등 모멘텀</h1><p>분석 결과를 불러오는 중입니다.</p></section>;
  const { research: r, snapshot: s } = data;
  const active = r.status === "validated_exploratory" && !!r.adopted_model && s.research_generated_at === r.generated_at;
  const stale = !s.generated_at || Date.now() - Date.parse(s.generated_at) > 96 * 3600 * 1000;
  const failed = s.status === "failed";
  const rows = active && !stale && ["success", "degraded"].includes(s.status) ? s.candidates ?? [] : [];
  const early = rows.filter(c => c.stage === "early").slice(0, 20);
  const surged = rows.filter(c => c.stage === "already_surged").slice(0, 20);
  const metrics = [{ label: "MOMENTUM 10+", value: r.validation?.metrics }, { label: "단순 모멘텀", value: r.baselines?.simple_momentum.metrics }, { label: "SPY · 동일 청산", value: r.baselines?.spy_same_exits.metrics }];
  return <section className="momentum-panel">
    <div className="hero"><div className="eyebrow">MOMENTUM 10+ · DATA-DRIVEN RESEARCH</div><h1>급등 모멘텀</h1><p>다음 거래일 시가 진입 · 목표 +10% · 손절 -5% · 최대 20거래일</p></div>
    <div className="run-meta"><div><span>분석 기준 미국장</span><strong>{s.data_date ?? "—"}</strong></div><div><span>데이터 갱신 · 한국 시간</span><strong>{kst(s.generated_at)}</strong></div><div><span>연구 갱신 · 한국 시간</span><strong>{kst(r.generated_at)}</strong></div></div>
    <div className="momentum-notice" role="status">{failed ? "모멘텀 스크리닝 실행 실패 · 진단을 확인하세요." : active ? "탐색적 검증 통과 · 통계적 유의성과 미래 수익을 보장하지 않습니다." : "검증 게이트 미충족 · 최종 채택 조건 없음 · 추천과 모멘텀 점수는 비활성입니다."}{stale && " 데이터가 오래되었거나 갱신 시간이 없습니다."}</div>
    <p className="momentum-muted">연구 {r.period?.start ?? "—"} ~ {r.period?.end ?? "—"} · 검증 시작 {r.period?.split ?? "—"} · 유니버스 {num(r.universe_count)} / 요청 {num(r.requested_count)} / 가격 확보 {num(r.downloaded_count)} / 실제 분석 {num(r.analyzed_count)}종목 · {num(r.observations)}관측 · 시총 확인 {num(r.cap_known_observations)}관측</p>
    <MomentumObservations observation={s.observations} referenceDate={s.data_date} researchGeneratedAt={r.generated_at} generatedAt={s.generated_at} finalCount={rows.length} validationExpectancy={r.validation?.metrics.expectancy} universeScope={s.universe_scope} />
    <section className="momentum-section"><h2>실제 분석 요약</h2><div className="momentum-summary-grid">
      {[["분석 종목", `${num(r.analyzed_count)}종목`], ["학습 관측", num(r.train_observations)], ["검증 관측", num(r.validation_observations)], ["실제 검증 거래", r.validation ? `${num(r.validation.metrics.trades)}건` : "미실행"]].map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}
    </div><p className="momentum-muted">{r.validation ? `학습에서 선택한 조건을 이후 기간에 적용한 결과, 거래당 기대수익은 ${pct(r.validation.metrics.expectancy)}, 목표 달성률은 ${pct(r.validation.metrics.target_rate)}입니다.` : "완료된 검증 결과가 없습니다."} {r.adopted_model ? "채택 조건은 아래에서 확인할 수 있습니다." : "수익성·표본·데이터 확인 기준을 모두 통과하지 못해 추천을 보류합니다."}</p><p className="momentum-risk">시점별 시총 확인 {num(r.cap_known_observations)}관측. 시총 미확인 표본과 현재 상장 종목의 생존자 편향을 포함한 탐색 결과입니다.</p></section>
    <section className="momentum-section"><h2>급등 전 공통 패턴 · 성공과 실패 비교</h2><div className="momentum-controls"><label>목표 관측 기간 <select value={horizon} onChange={e => setHorizon(Number(e.target.value))}>{[5,10,20].map(n => <option value={n} key={n}>{n}거래일 내 +10%</option>)}</select></label><label>지표 시점 <select value={lag} onChange={e => setLag(Number(e.target.value))}>{[1,3,5,10].map(n => <option value={n} key={n}>진입 {n}거래일 전</option>)}</select></label></div>
    <p className="momentum-muted">성공은 +10% 목표가 -5% 손절보다 먼저 발생한 관측입니다. 전체 연구 기간의 설명용 통계이며, 중복 관측을 포함합니다. 지표 차이가 검증된 매수 조건을 뜻하지 않습니다. 표는 좌우로 스크롤할 수 있습니다.</p>
    {data.statistics.length ? <div className="momentum-table-wrap"><table className="momentum-table"><thead><tr><th>지표</th><th>성공 평균</th><th>실패 평균</th><th>성공 중앙값</th><th>실패 중앙값</th><th>성공 25~75분위</th><th>실패 25~75분위</th></tr></thead><tbody>{data.statistics.filter(row => row.horizon === horizon && row.lag === lag).map(row => <tr key={row.feature}><th>{featureLabels[row.feature] ?? row.feature}</th><td>{featureValue(row.feature,row.success.mean)}</td><td>{featureValue(row.feature,row.failure.mean)}</td><td>{featureValue(row.feature,row.success.median)}</td><td>{featureValue(row.feature,row.failure.median)}</td><td>{featureValue(row.feature,row.success.q25)} ~ {featureValue(row.feature,row.success.q75)}</td><td>{featureValue(row.feature,row.failure.q25)} ~ {featureValue(row.feature,row.failure.q75)}</td></tr>)}</tbody></table></div> : <p className="momentum-muted">지표 통계 파일이 없거나 불러오지 못했습니다.</p>}</section>
    {[["현재 급등 초기 후보 TOP 20", early], ["이미 급등한 종목 · 추격 위험", surged]].map(([title, candidates]) => <section className="momentum-section" key={String(title)}><h2>{String(title)}</h2><div className="momentum-cards">{(candidates as Candidate[]).length ? (candidates as Candidate[]).map(c => <article className="momentum-card" key={c.ticker}><header><strong>{c.ticker}</strong><b>{c.score.toFixed(1)}점</b></header><p>{c.name}</p><dl>{[["RSI14", num(c.rsi14)], ["RVOL", `${num(c.rvol)}x`], ["ATR / 주가", pct(c.atr_pct)], ["SPY 대비 RS20", pct(c.relative_strength)], ["5일", pct(c.return5)], ["10일", pct(c.return10)], ["20일", pct(c.return20)]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl><ul>{c.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>{c.warnings.map(w => <p className="momentum-risk" key={w}>{w}</p>)}</article>) : <p className="momentum-muted">{active ? "조건을 충족하는 후보가 없습니다." : "실제 검증을 통과한 조건이 없어 후보를 표시하지 않습니다."}</p>}</div></section>)}
    <section className="momentum-section"><h2>과거 백테스트 · 시간순 분리 검증</h2><p className="momentum-muted">다음 시가 매수, 편도 슬리피지 0.10%·비용 0.05%, 최대 5종목·동일 종목 중복 금지. 일별 평가금액으로 최대 낙폭 계산. 검증 구간으로 조건 재학습 없음.</p><div className="momentum-table-wrap"><table className="momentum-table"><thead><tr><th>검증 성과</th>{metrics.map(m => <th key={m.label}>{m.label}</th>)}</tr></thead><tbody>{([
      ["총 거래 수", (m: Metrics) => num(m.trades)], ["목표 달성률", (m: Metrics) => pct(m.target_rate)], ["손절 비율", (m: Metrics) => pct(m.stop_rate)], ["승률", (m: Metrics) => pct(m.win_rate)], ["평균 손익", (m: Metrics) => pct(m.mean_return)], ["Profit Factor", (m: Metrics) => num(m.profit_factor)], ["최대 낙폭", (m: Metrics) => pct(m.max_drawdown)], ["거래당 기대수익", (m: Metrics) => pct(m.expectancy)],
    ] as [string, (m: Metrics) => string][]).map(([label, format]) => <tr key={label}><th>{label}</th>{metrics.map(m => <td key={m.label}>{m.value ? format(m.value) : "미실행"}</td>)}</tr>)}</tbody></table></div><p className="momentum-muted">SPY 매수 후 보유 수익률: {pct(r.baselines?.spy_buy_hold_return)} · 미실행 성과는 숫자로 대체하지 않습니다. 이 결과는 후보 추천 조건으로 채택되었다는 뜻이 아닙니다.</p></section>
    {r.selected_model && !r.adopted_model && <section className="momentum-section"><h2>학습에서 선택했지만 채택하지 않은 조건</h2><p className="momentum-muted">학습 구간에서만 방향·중앙값·가중치를 도출한 탐색 모델입니다. 아래 조건은 검증에 실패했으며 현재 추천에 사용하지 않습니다. 가중 합산 점수 {r.selected_model.score_threshold} 이상으로 평가했습니다.</p><ul>{r.selected_model.rules.map(rule => <li key={rule.feature}>{featureLabels[rule.feature] ?? rule.feature} {rule.direction > 0 ? "≥" : "≤"} {featureValue(rule.feature,rule.threshold)} · 점수 비중 {pct(rule.weight / r.selected_model!.rules.reduce((sum, r) => sum + r.weight, 0))}</li>)}</ul><p className="momentum-muted">학습 거래당 기대수익 {pct(r.training_metrics?.expectancy)} → 검증 거래당 기대수익 {pct(r.validation?.metrics.expectancy)}. 검증 결과로 다른 조건을 다시 고르지 않았습니다.</p></section>}
    {r.adopted_model && <section className="momentum-section"><h2>최종 채택 조건</h2><p>점수 {r.adopted_model.score_threshold}점 이상</p><ul>{r.adopted_model.rules.map(rule => <li key={rule.feature}>{rule.feature} {rule.direction > 0 ? "≥" : "≤"} {num(rule.threshold)} · 가중치 {num(rule.weight)}</li>)}</ul></section>}
    <section className="momentum-section"><h2>검증 및 데이터 진단</h2>{r.validation_gates && <ul>{Object.entries(r.validation_gates).map(([name, ok]) => <li key={name}>{gateLabels[name] ?? name}: {ok ? "충족" : "미충족"}</li>)}</ul>}<ul>{s.diagnostics?.slice(0, 20).map((d, i) => <li key={i}>{d.ticker ? `${d.ticker}: ` : ""}{d.error}</li>)}</ul><details><summary>분석 한계와 주의사항</summary><ul>{r.limitations?.map(l => <li key={l}>{l}</li>)}</ul></details><p><a href="/data/momentum-research.json" download>연구 결과 JSON</a> · <a href="/data/latest-momentum.json" download>현재 스크리닝 JSON</a> · <a href="/data/momentum-feature-statistics.json" download>지표별 성공·실패 통계</a> · <a href="/data/momentum-group-statistics.json" download>섹터·시총 그룹 통계</a> · <a href="/data/momentum-backtest-trades.csv" download>실제 거래 내역</a> · <a href="/data/momentum-backtest-equity.csv" download>일별 평가금액</a></p></section>
  </section>;
}
