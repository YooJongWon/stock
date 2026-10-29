import { readFile } from "node:fs/promises";
import path from "node:path";
import Dashboard from "./ui/dashboard";

async function readData<T>(filename: string, fallback: T): Promise<T> {
  try {
    const file = path.join(process.cwd(), "public", "data", filename);
    return JSON.parse(await readFile(file, "utf8")) as T;
  } catch {
    return fallback;
  }
}

async function readText(filename: string, fallback: string): Promise<string> {
  try {
    const file = path.join(process.cwd(), "public", "data", filename);
    return await readFile(file, "utf8");
  } catch {
    return fallback;
  }
}

export default async function Home() {
  const [result, runStatus, markdown] = await Promise.all([
    readData("latest-results.json", {
      status: "missing",
      last_successful_run_at: null,
      data_date: null,
      error: null,
      warnings: [],
      warning_count: 0,
      candidates: [],
      technical_candidates: [],
      waiting_candidates: [],
      buy_count: 0,
      watch_count: 0,
      ready_count: 0,
      waiting_count: 0,
      universe_scanned_count: 0,
      technical_candidate_count: 0,
      candidate_count: 0,
    }),
    readData("latest-run-status.json", { status: "not_run", attempted_at: null, reference_date: null, message: null }),
    readText("latest-candidates.md", "# 미국주식 스윙 스크리너 — 최종 후보\n\n아직 스크리너 결과가 없습니다."),
  ]);
  return <Dashboard result={result} runStatus={runStatus} markdown={markdown} />;
}
