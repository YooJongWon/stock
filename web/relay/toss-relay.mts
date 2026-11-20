import { createHash, timingSafeEqual } from "node:crypto";
import { createServer } from "node:http";
import { fetchTossSnapshot, TossError, type TossSnapshot } from "../lib/toss.ts";

const { TOSS_CLIENT_ID: clientId, TOSS_CLIENT_SECRET: clientSecret, TOSS_RELAY_SECRET: secret } = process.env;
if (!clientId || !clientSecret || !secret || secret.length < 32) {
  throw new Error("Set TOSS_CLIENT_ID, TOSS_CLIENT_SECRET and TOSS_RELAY_SECRET (at least 32 characters).");
}

const digest = (value: string) => createHash("sha256").update(value).digest();
const expected = digest(`Bearer ${secret}`);
let pending: Promise<TossSnapshot> | undefined;

createServer(async (request, response) => {
  const reply = (status: number, body: object) => {
    response.writeHead(status, { "Content-Type": "application/json", "Cache-Control": "private, no-store" });
    response.end(JSON.stringify(body));
  };
  if (request.method !== "GET" || request.url !== "/snapshot") return reply(404, {});
  if (!timingSafeEqual(expected, digest(request.headers.authorization ?? ""))) return reply(401, {});

  try {
    pending ??= fetchTossSnapshot(clientId, clientSecret).finally(() => { pending = undefined; });
    reply(200, await pending);
  } catch (error) {
    reply(502, { upstreamStatus: error instanceof TossError ? error.status : null });
  }
}).listen(8787, "127.0.0.1");
