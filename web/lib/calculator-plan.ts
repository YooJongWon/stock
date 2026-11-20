import { normalizeExitSettings } from "./swing-plan";

export type CalculatorInputs = {
  total: string; stockCount: string; cashRatio: string; firstBuyRatio: string;
  stopLossRatio: string; firstTargetRatio: string; finalTargetRatio: string;
  secondEntryRisePct: string; exitPlanVersion: string;
};
type CalculatorPlan = {
  total: number; stockCount: number; perStockAmount: number; firstBuyAmount: number;
  secondBuyAmount: number; stopLossRatio: number; secondEntryRisePct: number;
  sellTargets: { label: string; returnPct: number; sellPct: number }[];
};

export const DEFAULT_CALCULATOR_INPUTS: CalculatorInputs = {
  total: "14000", stockCount: "5", cashRatio: "5", firstBuyRatio: "60",
  stopLossRatio: "-5", firstTargetRatio: "6", finalTargetRatio: "10",
  secondEntryRisePct: "4", exitPlanVersion: "2",
};

export function buildCalculatorPlan(savedInput: Partial<CalculatorInputs> | null | undefined): CalculatorPlan {
  const input = normalizeExitSettings(savedInput ?? {});
  const read = (key: keyof CalculatorInputs, fallback: string) => {
    const raw = input?.[key];
    const value = typeof raw === "string" ? Number(raw) : Number.NaN;
    return Number.isFinite(value) ? value : Number(fallback);
  };
  const total = Math.max(0, read("total", DEFAULT_CALCULATOR_INPUTS.total));
  const stockCount = Math.max(1, Math.min(100, Math.floor(read("stockCount", DEFAULT_CALCULATOR_INPUTS.stockCount))));
  const cashRatio = Math.max(0, Math.min(100, read("cashRatio", DEFAULT_CALCULATOR_INPUTS.cashRatio))) / 100;
  const firstRatio = Math.max(0, Math.min(100, read("firstBuyRatio", DEFAULT_CALCULATOR_INPUTS.firstBuyRatio))) / 100;
  const perStockAmount = total * (1 - cashRatio) / stockCount;
  return {
    total, stockCount, perStockAmount,
    firstBuyAmount: perStockAmount * firstRatio,
    secondBuyAmount: perStockAmount * (1 - firstRatio),
    stopLossRatio: Math.min(0, Math.max(-100, read("stopLossRatio", DEFAULT_CALCULATOR_INPUTS.stopLossRatio))),
    secondEntryRisePct: Math.min(5, Math.max(3, read("secondEntryRisePct", DEFAULT_CALCULATOR_INPUTS.secondEntryRisePct))),
    sellTargets: [
      { label: "1차 매도", returnPct: Math.max(0, read("firstTargetRatio", DEFAULT_CALCULATOR_INPUTS.firstTargetRatio)), sellPct: 50 },
      { label: "2차 매도", returnPct: Math.max(0, read("finalTargetRatio", DEFAULT_CALCULATOR_INPUTS.finalTargetRatio)), sellPct: 50 },
    ],
  };
}
