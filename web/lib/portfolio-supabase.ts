function supabaseConfig() {
  const url = (process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL || "").replace(/\/$/, "");
  const key = process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY || "";
  if (!url || !key) throw new Error("SUPABASE_URL 및 SUPABASE_SERVICE_ROLE_KEY 환경변수가 필요합니다.");
  return { url, key };
}

export async function supabaseRequest(path: string, init: RequestInit = {}) {
  const { url, key } = supabaseConfig();
  const headers: Record<string, string> = {
    apikey: key,
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  // Current sb_secret_ keys are API keys, not JWTs: send them via apikey only.
  // Legacy service_role keys are JWTs and can also be sent as Authorization Bearer.
  if (!key.startsWith("sb_secret_")) headers.Authorization = `Bearer ${key}`;

  const response = await fetch(`${url}/rest/v1/${path}`, {
    ...init,
    cache: "no-store",
    headers,
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(`Supabase 요청 실패 (${response.status}): ${message.slice(0, 500)}`);
  }
  return response;
}
