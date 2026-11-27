import { readFile } from "node:fs/promises";
import path from "node:path";
import Dashboard, { type MonthlyDashboardResult } from "./ui/dashboard";

async function readData<T>(filename: string, fallback: T): Promise<T> {
  try {
    const file = path.join(process.cwd(), "public", "data", filename);
    return JSON.parse(await readFile(file, "utf8")) as T;
  } catch {
    return fallback;
  }
}

export default async function Home() {
  const [result, status] = await Promise.all([
    readData<MonthlyDashboardResult>("latest-results.json", { data_date: null }),
    readData<{ status: string; reference_date: string | null }>("latest-run-status.json", { status: "not_run", reference_date: null }),
  ]);
  const { data_date, spy_regime, monthly_momentum, sector_reference_date, sector_performance, stock_sectors } = result;
  const hasMarketStatus = ["success", "degraded", "failed", "market_closed"].includes(status.status);
  const marketSession = hasMarketStatus && status.reference_date
    ? { date: status.reference_date, open: status.status !== "market_closed" }
    : null;
  return <Dashboard result={{ data_date, spy_regime, monthly_momentum, sector_reference_date, sector_performance, stock_sectors }}
    marketSession={marketSession} failedSession={status.status === "failed" ? status.reference_date : null} />;
}
