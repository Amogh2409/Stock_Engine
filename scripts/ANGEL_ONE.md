# Angel One data connection

The read-only collector is `scripts/angelone_data.py`. It uses Python's standard
library and has no SDK dependency. It authenticates and reads market data only;
there are no order, portfolio, funds, account-settings or trading methods.
It runs once when invoked. No scheduler, subscription or background service is
started. Live access has not been verified on the owner's account.

## Local setup

1. Create an app/API key in the [SmartAPI portal](https://smartapi.angelone.in/)
   and complete its current account/TOTP requirements. An Angel One trading
   account alone does not supply a configured API key.
2. Set `ANGEL_PUBLIC_IP`, `ANGEL_LOCAL_IP` and `ANGEL_MAC_ADDRESS` in the local
   terminal environment to this machine's actual addresses. The collector does
   not use an external IP lookup or fabricate addresses. Keep any SmartAPI
   network restrictions aligned with your app's settings.
3. Run a collection command in an interactive terminal. It prompts privately
   for the API key, client code, PIN and current authenticator OTP. Input is
   hidden, not written to files, and not echoed. Do not send these in chat.
   Credentials remain in process memory for the run.
4. If you already maintain a local authenticated environment, `ANGEL_API_KEY`
   and `ANGEL_JWT` can be supplied there instead. PIN/OTP are not requested when
   a JWT is supplied. An expired JWT fails without a silent refresh. Local
   `ANGEL_CLIENT_CODE`, `ANGEL_PIN` and `ANGEL_TOTP` variables are also supported,
   but PIN/OTP are best entered at the hidden prompts. A TOTP seed is never
   requested. There are no credential command-line flags or browser storage.

The script reads the process environment, not `.env` files. Check which settings
exist without displaying their values or making a network call:

```bash
python3 scripts/angelone_data.py check
```

## Collect daily prices for the scanner

Example dates below are illustrative pre-holdout dates, not a performed run or
an assertion of provider history coverage. Select a date range supported by the
provider; download access must be checked after login.

```bash
python3 scripts/angelone_data.py candles --symbols TCS,INFY \
  --interval ONE_DAY --from '2022-01-01 00:00' --to '2022-12-30 23:59'
```

Open **Upload prices** in the stock engine and select the produced `prices.csv`.
Keep supplying your fundamentals export separately. The collector resolves exact
NSE `-EQ` symbols, supports up to 50 distinct companies per invocation, and stops
on ambiguous or missing mappings. It does not download historical index
membership or reconstruct delisted instruments from today's search results.
Multiple captures are not merged automatically. Other exchanges and derivatives
are not accepted by this initial equity candle/quote collector.

Daily fields are Date, Ticker, Open, High, Low, Close and Volume. REST prices are
preserved without applying WebSocket scaling. Current-day daily bars are always
excluded, even after market close; use the next day for a completed daily file.
Zero volume is retained and counted, never filled. Missing sessions are not
invented, and a successful response is not proof of complete session coverage.
Corporate-action adjustment is unverified: do not append this provider's rows to
a differently adjusted Yahoo series. Use a consistent file and inspect splits.

## Research captures

```bash
python3 scripts/angelone_data.py candles --symbols TCS \
  --interval ONE_MINUTE --from '2022-12-01 00:00' --to '2022-12-30 23:59'
python3 scripts/angelone_data.py quotes --symbols TCS,INFY
python3 scripts/angelone_data.py greeks --underlying TCS --expiry DDMMMYYYY
```

Replace `DDMMMYYYY` with the exact live expiry. Greek responses must match the
requested underlying and expiry, with no duplicate strike/type pairs. Options
delta is not buyer-minus-seller trade delta. `tradeVolume` is not OI. This adapter
does **not** calculate gamma exposure, infer dealer positions, or join quotes to
an options chain. It has not verified OI/lot-size unit conventions for a GEX join.

Intraday CSV uses **Timestamp**, preserving the offset, and cannot be loaded as
daily history. Bars that have not ended at collection start are excluded. The
file preserves available bars but does not certify session completeness. Session
VWAP, intraday profile/TPO calculations and an intraday UI are not implemented.
Do not relabel intraday rows as daily rows to bypass this separation.

`quotes` records one FULL snapshot, including depth when supplied. It does not
record continuous depth or create a liquidity heatmap. Quote updates are not
guaranteed individual trades. No Time & Sales, footprint or aggressor delta is
inferred. No REST snapshots are treated as historical exchange events.

Only daily `prices.csv` currently feeds selection. All other captures are
research inputs awaiting their own validated processing and UI integration.

## Storage and operational limits

Each successful capture gets a new directory under gitignored
`data-store/angelone/`, with `capture.json`, its SHA-256 digest, and a CSV when
applicable. JSON retains request/instrument provenance, collection start/end
times and source data. It contains no authentication response or headers.
Credentials never reach the frontend or API capture files. Existing captures are
never overwritten, and nothing automatically replaces the current scanner file.

Calls are paced at least 1.1 seconds apart in a single process. Run one collector
per account at a time; other account clients share the provider's limits. HTTP,
rate-limit and authentication errors stop the run without retries or response
body logging. All data is collected and validated before output is created.
A local disk failure can still leave an incomplete directory; only a successful
exit establishes a completed capture.

One request window per instrument is supported, without automatic pagination:
1-minute ≤30 days; 3-minute ≤60; 5/10-minute ≤100; 15/30-minute ≤200; hourly ≤400;
daily ≤2000. API limits and actual history availability are separate constraints.
No backtest, reserved-window analysis, parameter fitting or 50,000-case study is
triggered by these commands. Collecting current Greeks does not create historical
Greeks for an older performance test.

## Verified provider contracts

Reviewed 2026-10-04 against primary documentation; live account access is still
unverified:

- [SmartAPI documentation](https://smartapi.angelone.in/docs): historical OHLCV,
  authentication and request intervals; [market data](https://smartapi.angelone.in/docs/MarketData)
  covers FULL quotes and best-five depth.
- [Official Python client](https://github.com/angel-one/smartapi-python/blob/main/SmartApi/smartConnect.py)
  confirms endpoint paths. This collector does not import the SDK.
- [Depth deprecation notice](https://smartapi.angelone.in/smartapi/forum/topic/5217/deprecation-of-20-market-depth-from-websocket-2-0-effective-april-25-2025):
  20-level depth ended April 25, 2025; best-five remains.
- [Official Greek announcement](https://smartapi.angelone.in/smartapi/forum/topic/4254/announcing-option-greeks-api-for-smartapi-users/1?lang=en-GB)
  describes per-contract Greeks. [Provider clarification](https://smartapi.angelone.in/smartapi/forum/topic/4254/announcing-option-greeks-api-for-smartapi-users/21?lang=en-GB)
  says expired-option Greeks are unavailable.
- [Official streaming parser](https://github.com/angel-one/smartapi-python/blob/main/SmartApi/smartWebSocketV2.py)
  exposes last-trade/quote/depth fields, not explicit trade aggressor flags. Thus
  treating every quote as an aggressor-classified execution would be an unsupported
  inference. A different feed is needed for a true classified tape.

Offline checks run with `.venv/bin/python scripts/test_angelone_data.py` and are
also included in the normal `test_python.py` gate. Synthetic fixtures test schema,
units preservation, dates, duplicates, completeness, instrument matching,
credential-safe failures and compatibility with the daily importer. They cannot
establish live entitlement, feed quality or investment performance.
