// Versioned settings keep old saved defaults from restoring the retired exit plan.
export function normalizeExitSettings<T extends Record<string, unknown>>(settings: T) {
  return settings.exitPlanVersion === "2"
    ? settings
    : { ...settings, stopLossRatio: "-5", firstTargetRatio: "6", finalTargetRatio: "10", exitPlanVersion: "2" };
}

// Preserve the amount already sold under the previous 40/30/30 plan.
// A legacy 1st/2nd sale becomes a partial exit with 60%/30% still remaining.
export function normalizeSellProgress(source: {
  sellStage: number; exitStatus: string; exitPlanVersion?: string; legacySoldPct?: number;
}) {
  if (source.exitPlanVersion === "2") return {
    sellStage: source.sellStage,
    exitPlanVersion: "2",
    legacySoldPct: source.legacySoldPct ?? 0,
  };
  return {
    sellStage: source.sellStage === 3 || source.exitStatus === "completed" ? 2 : source.sellStage > 0 ? 1 : 0,
    exitPlanVersion: "2",
    legacySoldPct: [0, 40, 70, 100][source.sellStage] ?? 0,
  };
}
