import { readFile } from "node:fs/promises";
import path from "node:path";
import Dashboard, { type MarketSession, type MonthlyDashboardResult } from "./ui/dashboard";

type DataRead<T> =
  | { state: "ready"; value: T }
  | { state: "missing" | "error"; value: null };

async function readData<T>(filename: string, requiredKey: keyof T): Promise<DataRead<T>> {
  try {
    const file = path.join(process.cwd(), "public", "data", filename);
    const value: unknown = JSON.parse(await readFile(file, "utf8"));
    if (!value || typeof value !== "object" || Array.isArray(value) || !(requiredKey in value)) {
      return { state: "error", value: null };
    }
    return { state: "ready", value: value as T };
  } catch (error) {
    const missing = error instanceof Error && "code" in error && error.code === "ENOENT";
    return { state: missing ? "missing" : "error", value: null };
  }
}

export default async function Home() {
  const [result, status] = await Promise.all([
    readData<MonthlyDashboardResult>("latest-results.json", "data_date"),
    readData<{ status: string; reference_date: string | null; market_session?: MarketSession }>(
      "latest-run-status.json", "status"),
  ]);
  const { data_date, spy_regime, monthly_momentum, monthly_ranking_quality, sector_reference_date, sector_performance, stock_sectors } =
    result.value ?? { data_date: null };
  const run = status.value;
  return <Dashboard result={{ data_date, spy_regime, monthly_momentum, monthly_ranking_quality, sector_reference_date, sector_performance, stock_sectors }}
    marketSession={run?.market_session ?? null} batchReferenceDate={run?.reference_date ?? null}
    failedSession={run?.status === "failed" ? run.reference_date : null}
    dataLoadError={result.state === "error" ? "results" : status.state === "error" ? "status" : undefined} />;
}
