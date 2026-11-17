"use client";

import { useEffect, useState } from "react";

type Metrics = { trades: number; target_rate: number | null; stop_rate: number | null; win_rate: number | null; mean_return: number | null; profit_factor: number | null; max_drawdown: number | null; expectancy: number | null };
type Candidate = { ticker: string; name?: string; score: number; stage: string; rsi14: number; rvol: number; atr_pct: number; relative_strength: number; return5: number; return10: number; return20: number; reasons: string[]; warnings: string[] };
type Research = { status: string; generated_at?: string; period?: { start: string; end: string; split: string }; universe_count?: number; requested_count?: number; downloaded_count?: number; analyzed_count?: number; observations?: number; cap_known_observations?: number; validation?: { metrics: Metrics }; baselines?: { simple_momentum: { metrics: Metrics }; spy_same_exits: { metrics: Metrics }; spy_buy_hold_return: number }; limitations?: string[]; validation_gates?: Record<string, boolean>; adopted_model?: { score_threshold: number; rules: { feature: string; threshold: number; direction: number; weight: number }[] } | null };
type Snapshot = { status: string; data_date?: string; generated_at?: string; research_generated_at?: string; candidates?: Candidate[]; diagnostics?: { ticker?: string; error: string }[]; universe_count?: number };
const pct = (v: number | null | undefined) => v == null ? "—" : `${(v * 100).toFixed(2)}%`;
const num = (v: number | null | undefined) => v == null ? "—" : v.toLocaleString("ko-KR", { maximumFractionDigits: 2 });
const kst = (v?: string) => v ? new Date(v).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" }) : "—";

export default function Momentum() {
  const [data, setData] = useState<{ research: Research; snapshot: Snapshot } | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    Promise.all(["momentum-research.json", "latest-momentum.json"].map(async (name) => {
      const response = await fetch(`/data/${name}`, { cache: "no-store", signal: controller.signal });
      if (!response.ok) throw new Error("missing");
      return response.json();
    })).then(([research, snapshot]) => setData({ research, snapshot })).catch((e) => { if (e.name !== "AbortError") setError(true); });
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
    {[["현재 급등 초기 후보 TOP 20", early], ["이미 급등한 종목 · 추격 위험", surged]].map(([title, candidates]) => <section className="momentum-section" key={String(title)}><h2>{String(title)}</h2><div className="momentum-cards">{(candidates as Candidate[]).length ? (candidates as Candidate[]).map(c => <article className="momentum-card" key={c.ticker}><header><strong>{c.ticker}</strong><b>{c.score.toFixed(1)}점</b></header><p>{c.name}</p><dl>{[["RSI14", num(c.rsi14)], ["RVOL", `${num(c.rvol)}x`], ["ATR / 주가", pct(c.atr_pct)], ["SPY 대비 RS20", pct(c.relative_strength)], ["5일", pct(c.return5)], ["10일", pct(c.return10)], ["20일", pct(c.return20)]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl><ul>{c.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>{c.warnings.map(w => <p className="momentum-risk" key={w}>{w}</p>)}</article>) : <p className="momentum-muted">{active ? "조건을 충족하는 후보가 없습니다." : "실제 검증을 통과한 조건이 없어 후보를 표시하지 않습니다."}</p>}</div></section>)}
    <section className="momentum-section"><h2>과거 백테스트 · 시간순 분리 검증</h2><p className="momentum-muted">다음 시가 매수, 편도 슬리피지 0.10%·비용 0.05%, 최대 5종목·동일 종목 중복 금지. 일별 평가금액으로 최대 낙폭 계산. 검증 구간으로 조건 재학습 없음.</p><div className="momentum-table-wrap"><table className="momentum-table"><thead><tr><th>검증 성과</th>{metrics.map(m => <th key={m.label}>{m.label}</th>)}</tr></thead><tbody>{([
      ["총 거래 수", (m: Metrics) => num(m.trades)], ["목표 달성률", (m: Metrics) => pct(m.target_rate)], ["손절 비율", (m: Metrics) => pct(m.stop_rate)], ["승률", (m: Metrics) => pct(m.win_rate)], ["평균 손익", (m: Metrics) => pct(m.mean_return)], ["Profit Factor", (m: Metrics) => num(m.profit_factor)], ["최대 낙폭", (m: Metrics) => pct(m.max_drawdown)], ["거래당 기대수익", (m: Metrics) => pct(m.expectancy)],
    ] as [string, (m: Metrics) => string][]).map(([label, format]) => <tr key={label}><th>{label}</th>{metrics.map(m => <td key={m.label}>{m.value ? format(m.value) : "미실행"}</td>)}</tr>)}</tbody></table></div><p className="momentum-muted">SPY 매수 후 보유 수익률: {pct(r.baselines?.spy_buy_hold_return)} · 미실행 성과는 숫자로 대체하지 않습니다. 이 결과는 후보 추천 조건으로 채택되었다는 뜻이 아닙니다.</p></section>
    {r.adopted_model && <section className="momentum-section"><h2>최종 채택 조건</h2><p>점수 {r.adopted_model.score_threshold}점 이상</p><ul>{r.adopted_model.rules.map(rule => <li key={rule.feature}>{rule.feature} {rule.direction > 0 ? "≥" : "≤"} {num(rule.threshold)} · 가중치 {num(rule.weight)}</li>)}</ul></section>}
    <section className="momentum-section"><h2>검증 및 데이터 진단</h2>{r.validation_gates && <ul>{Object.entries(r.validation_gates).map(([name, ok]) => <li key={name}>{name}: {ok ? "충족" : "미충족"}</li>)}</ul>}<ul>{s.diagnostics?.slice(0, 20).map((d, i) => <li key={i}>{d.ticker ? `${d.ticker}: ` : ""}{d.error}</li>)}</ul><details><summary>분석 한계와 주의사항</summary><ul>{r.limitations?.map(l => <li key={l}>{l}</li>)}</ul></details><p><a href="/data/momentum-research.json" download>연구 결과 JSON</a> · <a href="/data/latest-momentum.json" download>현재 스크리닝 JSON</a> · <a href="/data/momentum-feature-statistics.json" download>지표별 성공·실패 통계</a> · <a href="/data/momentum-group-statistics.json" download>섹터·시총 그룹 통계</a> · <a href="/data/momentum-backtest-trades.csv" download>실제 거래 내역</a> · <a href="/data/momentum-backtest-equity.csv" download>일별 평가금액</a></p></section>
  </section>;
}
