---
name: screener-data-reliability
description: Diagnose and repair stale Yahoo daily closes, SEC EDGAR retrieval failures, and missing US stock screener data while preserving the screening strategy.
---

Use the screener run's reference date and published diagnostics to reproduce failures. Group price failures by exchange, returned session and provider error before inferring a common cause. Compare the run time against the exchange calendar and check whether the listing traded on the target session.

- Require a confirmed regular-session bar on the reference date. Retry only incomplete requests within existing rate limits. For Yahoo, compare the period request with the explicit date-range request. Keep adjustment rules consistent and use a complete history from one request. If the reference bar is still missing, retain the stale-close diagnostic and exclude the ticker from that session's results.
- For `companyfacts` 404s, confirm ticker and CIK using SEC submissions and look for original reports. Use filing dates and reporting periods available by the reference date. Validate XBRL unit, tag, and reporting context. Do not infer data where the filing lacks usable facts.
- Preserve validated SEC fields even if earnings periods are incomplete. Apply the existing Yahoo point-in-time guard. Report unresolved values by field and keep them missing. A five-year growth recovery requires annual revenue with a comparable tag and currency over a 4–6 year span.
- Reproduce with saved responses for stale and recovered bars, missing earnings periods, and SEC 404s with and without usable filings. Compare classifications and scores on unchanged inputs. New validated inputs may change candidate membership and relative rank.
- Run `python -m pytest -q`. If dashboard labels or controls change, also verify the dashboard with the existing web build and browser tests where available.
