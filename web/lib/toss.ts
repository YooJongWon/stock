const API = "https://openapi.tossinvest.com";
const requestOptions = { cache: "no-store", redirect: "error" } as const;
type Token = { value: string; expiresAt: number };

let cachedToken: Token | undefined;
let pendingToken: Promise<Token> | undefined;

export class TossError extends Error {
  readonly status: number;

  constructor(status: number) {
    super("Toss Securities API request failed");
    this.status = status;
  }
}

async function issueToken(clientId: string, clientSecret: string): Promise<Token> {
  const response = await fetch(`${API}/oauth2/token`, {
    ...requestOptions,
    method: "POST",
    body: new URLSearchParams({
      grant_type: "client_credentials",
      client_id: clientId,
      client_secret: clientSecret,
    }),
    signal: AbortSignal.timeout(8000),
  });
  if (!response.ok) throw new TossError(response.status);

  const data = await response.json();
  if (typeof data?.access_token !== "string" || !data.access_token ||
      !Number.isFinite(data.expires_in) || data.expires_in <= 0) {
    throw new Error("Invalid token response");
  }

  return {
    value: data.access_token,
    expiresAt: Date.now() + Math.max(0, data.expires_in - 30) * 1000,
  };
}

async function getToken(clientId: string, clientSecret: string) {
  if (cachedToken && cachedToken.expiresAt > Date.now()) return cachedToken;

  pendingToken ??= issueToken(clientId, clientSecret)
    .then((token) => (cachedToken = token))
    .finally(() => { pendingToken = undefined; });
  return pendingToken;
}

export type TossHolding = {
  symbol: string;
  name: string;
  currency: string;
  quantity: string;
  lastPrice: string | null;
  value: string | null;
  profitLoss: string | null;
};

const cashCurrencies = ["KRW", "USD"] as const;

export type TossBuyingPower = {
  currency: (typeof cashCurrencies)[number];
  amount: string | null;
};

export type TossSnapshot = {
  accountCount: number;
  checkedAt: string;
  accounts: { holdings: TossHolding[]; buyingPower?: TossBuyingPower[] }[];
};

export async function fetchTossSnapshot(clientId: string, clientSecret: string): Promise<TossSnapshot> {
  const token = await getToken(clientId, clientSecret);
  const accounts = await readResult("/api/v1/accounts", token);
  if (!Array.isArray(accounts)) throw new Error("Invalid accounts response");

  const holdings = await Promise.all(accounts.map(async (account) => {
    if (!Number.isSafeInteger(account?.accountSeq) || account.accountSeq < 1) {
      throw new Error("Invalid account selector");
    }
    const accountSeq = String(account.accountSeq);
    const [result, buyingPower] = await Promise.all([
      readResult("/api/v1/holdings", token, accountSeq),
      Promise.all(cashCurrencies.map((currency) => readBuyingPower(token, accountSeq, currency))),
    ]);
    const items: unknown = result?.items;
    if (!Array.isArray(items)) throw new Error("Invalid holdings response");
    return {
      buyingPower,
      holdings: items.map((item) => ({
        symbol: item.symbol,
        name: item.name,
        currency: item.currency,
        quantity: item.quantity,
        lastPrice: item.lastPrice ?? null,
        value: item.marketValue?.amount ?? null,
        profitLoss: item.profitLoss?.amount ?? null,
      })),
    };
  }));

  return { accountCount: accounts.length, checkedAt: new Date().toISOString(), accounts: holdings };
}

async function readBuyingPower(token: Token, account: string, currency: TossBuyingPower["currency"]): Promise<TossBuyingPower> {
  try {
    const result = await readResult(`/api/v1/buying-power?currency=${currency}`, token, account);
    const amount = result?.cashBuyingPower;
    return {
      currency,
      amount: result?.currency === currency && typeof amount === "string" && /^-?\d+(?:\.\d+)?$/.test(amount)
        ? amount
        : null,
    };
  } catch {
    return { currency, amount: null };
  }
}

async function readResult(path: string, token: Token, account?: string) {
  const headers = new Headers({ Authorization: `Bearer ${token.value}` });
  if (account) headers.set("X-Tossinvest-Account", account);

  const response = await fetch(`${API}${path}`, {
    ...requestOptions,
    headers,
    signal: AbortSignal.timeout(8000),
  });
  if (response.status === 401 && cachedToken === token) cachedToken = undefined;
  if (!response.ok) throw new TossError(response.status);
  return (await response.json())?.result;
}
