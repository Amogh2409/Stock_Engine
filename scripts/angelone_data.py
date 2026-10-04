#!/usr/bin/env python3
"""Read-only Angel One SmartAPI collection. No orders, no background work.

Uses only the standard library. Credentials are read locally, never exported.
Daily candles fit the existing Upload prices flow; intraday/quotes/Greeks stay
separate research artifacts. See scripts/ANGEL_ONE.md for setup and limitations.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import getpass
import hashlib
import http.client
import io
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import uuid


IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
HOST = "apiconnect.angelone.in"
PATHS = {
    "login": "/rest/auth/angelbroking/user/v1/loginByPassword",
    "search": "/rest/secure/angelbroking/order/v1/searchScrip",
    "candles": "/rest/secure/angelbroking/historical/v1/getCandleData",
    "quotes": "/rest/secure/angelbroking/market/v1/quote",
    "greeks": "/rest/secure/angelbroking/marketData/v1/optionGreek",
}
MAX_DAYS = {"ONE_MINUTE": 30, "THREE_MINUTE": 60, "FIVE_MINUTE": 100,
            "TEN_MINUTE": 100, "FIFTEEN_MINUTE": 200, "THIRTY_MINUTE": 200,
            "ONE_HOUR": 400, "ONE_DAY": 2000}


class DataError(ValueError):
    """Safe user-facing errors; never include headers, credentials or response bodies."""


def text_header(value):
    if not isinstance(value, str) or not value or not value.isascii() or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise DataError("Missing or invalid local authentication/header setting.")
    return value


class SmartAPI:
    def __init__(self, api_key, public_ip, local_ip, mac, jwt=None):
        try:
            ipaddress.ip_address(public_ip)
            ipaddress.ip_address(local_ip)
        except ValueError:
            raise DataError("Configure valid ANGEL_PUBLIC_IP and ANGEL_LOCAL_IP addresses.") from None
        if not re.fullmatch(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", mac):
            raise DataError("Configure ANGEL_MAC_ADDRESS as six colon-separated hexadecimal bytes.")
        self.headers = {"Content-Type": "application/json", "Accept": "application/json",
                        "X-UserType": "USER", "X-SourceID": "WEB",
                        "X-ClientPublicIP": public_ip, "X-ClientLocalIP": local_ip,
                        "X-MACAddress": mac, "X-PrivateKey": text_header(api_key)}
        if jwt:
            self.headers["Authorization"] = "Bearer " + text_header(jwt)
        self.last_call = None

    def request(self, operation, payload):
        if operation not in PATHS:
            raise DataError("Unsupported operation: this collector only authenticates and reads market data.")
        if operation != "login" and "Authorization" not in self.headers:
            raise DataError("Authenticate locally before collecting data.")
        # Conservative shared pacing, including search and options endpoints.
        if self.last_call is not None:
            time.sleep(max(0, 1.1 - (time.monotonic() - self.last_call)))
        self.last_call = time.monotonic()
        conn = http.client.HTTPSConnection(HOST, timeout=30)
        try:
            conn.request("POST", PATHS[operation], json.dumps(payload, allow_nan=False), self.headers)
            response = conn.getresponse()
            if response.status != 200:
                raise DataError("SmartAPI HTTP %d. Check local authentication, permissions or rate limits; no automatic retry." % response.status)
            raw = response.read(16 * 1024 * 1024 + 1)
            if len(raw) > 16 * 1024 * 1024:
                raise DataError("SmartAPI response exceeded the collection size limit.")
            body = json.loads(raw)
        except (OSError, http.client.HTTPException, UnicodeError, json.JSONDecodeError):
            raise DataError("SmartAPI connection or JSON response failed; credentials and response details were not logged.") from None
        finally:
            conn.close()
        if not isinstance(body, dict) or body.get("status") is not True:
            # Provider messages can contain echoed input; do not print them.
            raise DataError("SmartAPI rejected the request or returned no data. Check login, instrument and date range locally.")
        return body.get("data")

    def login(self, client_code, pin, otp):
        data = self.request("login", {"clientcode": text_header(client_code),
                                     "password": text_header(pin), "totp": text_header(otp)})
        if not isinstance(data, dict) or not data.get("jwtToken"):
            raise DataError("SmartAPI login returned no session token.")
        self.headers["Authorization"] = "Bearer " + text_header(data["jwtToken"])
        # Refresh/feed tokens are neither persisted nor printed.


def symbols_arg(value):
    symbols = value.upper().split(",")
    if not 1 <= len(symbols) <= 50 or len(set(symbols)) != len(symbols):
        raise DataError("Choose 1–50 distinct NSE equity symbols per run.")
    if any(not re.fullmatch(r"[A-Z0-9][A-Z0-9&_.-]{0,39}", s) for s in symbols):
        raise DataError("Use comma-separated NSE symbols without spaces or exchange suffixes.")
    return symbols


def resolve_equities(api, symbols):
    instruments = []
    for symbol in symbols:
        data = api.request("search", {"exchange": "NSE", "searchscrip": symbol + "-EQ"})
        if not isinstance(data, list):
            raise DataError("SmartAPI instrument search returned an invalid response.")
        matches = [x for x in data if isinstance(x, dict) and x.get("exchange") == "NSE"
                   and x.get("tradingsymbol") == symbol + "-EQ"]
        if len(matches) != 1 or not re.fullmatch(r"[0-9]+", str(matches[0].get("symboltoken", ""))):
            raise DataError("An exact NSE equity match was missing or ambiguous; collection stopped.")
        instruments.append({"ticker": symbol, "exchange": "NSE", "symboltoken": str(matches[0]["symboltoken"]),
                            "tradingsymbol": matches[0]["tradingsymbol"]})
    if len({x["symboltoken"] for x in instruments}) != len(instruments):
        raise DataError("Instrument search returned duplicate tokens for different symbols.")
    return instruments


def request_time(value):
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=IST)
        if parsed.strftime("%Y-%m-%d %H:%M") != value:
            raise ValueError()
        return parsed
    except (TypeError, ValueError):
        raise DataError("Dates must use YYYY-MM-DD HH:MM in Asia/Kolkata.") from None


def number(value):
    if isinstance(value, bool):
        raise DataError("Boolean values are not market prices or quantities.")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise DataError("Missing or invalid market number.") from None
    if not math.isfinite(result):
        raise DataError("Non-finite market number.")
    return result


def normalize_candles(data, ticker, interval, start, end, now):
    if not isinstance(data, list) or not data:
        raise DataError("No candles returned; no file was created.")
    rows, previous, excluded = [], None, 0
    for candle in data:
        if not isinstance(candle, list) or len(candle) != 6:
            raise DataError("Unexpected candle schema; expected timestamp and OHLCV.")
        try:
            timestamp = dt.datetime.fromisoformat(candle[0])
            if timestamp.tzinfo is None:
                raise ValueError()
            timestamp = timestamp.astimezone(IST)
        except (TypeError, ValueError):
            raise DataError("Candle timestamps must include a timezone.") from None
        if timestamp < start or timestamp > end or (previous is not None and timestamp <= previous):
            raise DataError("Candles are out of range, duplicated or not ordered.")
        if interval == "ONE_DAY" and previous and previous.date() == timestamp.date():
            raise DataError("Multiple daily candles for one date.")
        previous = timestamp
        opening, high, low, close, volume = map(number, candle[1:])
        if min(opening, high, low, close) <= 0 or not low <= min(opening, close) <= max(opening, close) <= high or volume < 0:
            raise DataError("Candle has inconsistent OHLC or negative volume.")
        # Conservatively omit today's daily bar. Intraday bars must have ended.
        minutes = {"ONE_MINUTE": 1, "THREE_MINUTE": 3, "FIVE_MINUTE": 5, "TEN_MINUTE": 10,
                   "FIFTEEN_MINUTE": 15, "THIRTY_MINUTE": 30, "ONE_HOUR": 60}
        if ((interval == "ONE_DAY" and timestamp.date() >= now.astimezone(IST).date()) or
                (interval != "ONE_DAY" and timestamp + dt.timedelta(minutes=minutes[interval]) > now)):
            excluded += 1
            continue
        date = timestamp.date().isoformat() if interval == "ONE_DAY" else timestamp.isoformat()
        rows.append([date, ticker, opening, high, low, close, volume])
    if not rows:
        raise DataError("No completed candles remain after excluding current/future bars.")
    return rows, excluded


def collect_candles(api, instruments, interval, start, end, now):
    if start > end or (end - start) > dt.timedelta(days=MAX_DAYS[interval]):
        raise DataError("Invalid range or range exceeds the provider's per-request interval limit.")
    rows, excluded, raw = [], 0, []
    for item in instruments:
        request = {"exchange": "NSE", "symboltoken": item["symboltoken"], "interval": interval,
                   "fromdate": start.strftime("%Y-%m-%d %H:%M"), "todate": end.strftime("%Y-%m-%d %H:%M")}
        data = api.request("candles", request)
        normalized, skipped = normalize_candles(data, item["ticker"], interval, start, end, now)
        rows.extend(normalized)
        excluded += skipped
        raw.append({"instrument": item, "request": request, "data": data})
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["Date" if interval == "ONE_DAY" else "Timestamp", "Ticker", "Open", "High", "Low", "Close", "Volume"])
    writer.writerows(sorted(rows, key=lambda row: (row[0], row[1])))
    return buffer.getvalue(), {"records": raw, "row_count": len(rows), "excluded_incomplete": excluded,
                              "zero_volume_rows": sum(row[-1] == 0 for row in rows)}


def collect_quotes(api, instruments):
    tokens = [x["symboltoken"] for x in instruments]
    data = api.request("quotes", {"mode": "FULL", "exchangeTokens": {"NSE": tokens}})
    if not isinstance(data, dict) or data.get("unfetched") or not isinstance(data.get("fetched"), list):
        raise DataError("Quote snapshot is incomplete or invalid.")
    fetched = data["fetched"]
    if (len(fetched) != len(tokens) or any(not isinstance(x, dict) or x.get("exchange") != "NSE" for x in fetched)
            or {str(x.get("symbolToken")) for x in fetched} != set(tokens)):
        raise DataError("Quote tokens do not match the requested instruments.")
    # Preserve provider field units/timestamps; snapshots are not a trade tape.
    return {"instruments": instruments, "data": data,
            "basis": "One FULL quote snapshot. Best-five depth only; not historical depth, trade delta or Time & Sales."}


def collect_greeks(api, name, expiry):
    names = symbols_arg(name)
    if len(names) != 1:
        raise DataError("Choose exactly one underlying for option Greeks.")
    name = names[0]
    try:
        dt.datetime.strptime(expiry, "%d%b%Y")
    except ValueError:
        raise DataError("Expiry must use DDMMMYYYY, for example 25JAN2024; choose a live contract for collection.") from None
    data = api.request("greeks", {"name": name, "expirydate": expiry})
    if not isinstance(data, list) or not data:
        raise DataError("No option Greeks returned for this underlying and expiry.")
    seen = set()
    for row in data:
        if not isinstance(row, dict) or row.get("name") != name or row.get("expiry") != expiry or row.get("optionType") not in ("CE", "PE"):
            raise DataError("Option Greek contract does not match the requested underlying/expiry.")
        strike, gamma = number(row.get("strikePrice")), number(row.get("gamma"))
        key = (strike, row["optionType"])
        if strike <= 0 or gamma < 0 or key in seen:
            raise DataError("Invalid or duplicate option Greek contract.")
        seen.add(key)
    return {"request": {"name": name, "expirydate": expiry}, "data": data,
            "basis": "Provider option Greeks. Options delta is not trade delta. tradeVolume is not open interest; no GEX or dealer positioning inferred."}


def save_capture(root, kind, payload, csv_text=None):
    # Complete collection/validation before writing; never overwrite a prior run.
    try:
        encoded = json.dumps(payload, indent=2, allow_nan=False) + "\n"
    except (ValueError, TypeError):
        raise DataError("Provider data cannot be archived as finite JSON; no output was written.") from None
    directory = Path(root) / (dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ_") + uuid.uuid4().hex[:8])
    directory.mkdir(parents=True, mode=0o700)
    (directory / "capture.json").write_text(encoded, encoding="utf-8")
    if csv_text is not None:
        (directory / ("prices.csv" if kind == "daily" else "intraday.csv")).write_text(csv_text, encoding="utf-8")
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    (directory / "capture.sha256").write_text(digest + "  capture.json\n", encoding="utf-8")
    return directory


def local_client():
    public_ip, local_ip, mac = (os.environ.get(k, "") for k in ("ANGEL_PUBLIC_IP", "ANGEL_LOCAL_IP", "ANGEL_MAC_ADDRESS"))
    if not all((public_ip, local_ip, mac)):
        raise DataError("Set ANGEL_PUBLIC_IP, ANGEL_LOCAL_IP and ANGEL_MAC_ADDRESS locally. See scripts/ANGEL_ONE.md.")
    def secret(env, prompt):
        if os.environ.get(env):
            return os.environ[env]
        if not sys.stdin.isatty():
            raise DataError("Run interactively for hidden local credential entry, or configure the local environment.")
        return getpass.getpass(prompt)
    api = SmartAPI(secret("ANGEL_API_KEY", "SmartAPI key (hidden): "), public_ip, local_ip, mac, os.environ.get("ANGEL_JWT"))
    if "Authorization" not in api.headers:
        api.login(secret("ANGEL_CLIENT_CODE", "Client code (hidden): "),
                  secret("ANGEL_PIN", "Angel PIN (hidden, not saved): "),
                  secret("ANGEL_TOTP", "Current authenticator OTP (hidden, not saved): "))
    return api


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="Check local setup without network access or displaying values")
    for command in ("candles", "quotes", "greeks"):
        p = sub.add_parser(command)
        p.add_argument("--out", type=Path, default=Path(__file__).resolve().parent.parent / "data-store" / "angelone")
        if command in ("candles", "quotes"):
            p.add_argument("--symbols", required=True, help="NSE cash equity tickers, comma separated")
        if command == "candles":
            p.add_argument("--interval", choices=MAX_DAYS, default="ONE_DAY")
            p.add_argument("--from", dest="start", required=True)
            p.add_argument("--to", dest="end", required=True)
        if command == "greeks":
            p.add_argument("--underlying", required=True)
            p.add_argument("--expiry", required=True)
    args = parser.parse_args(argv)
    if args.command == "check":
        for name in ("ANGEL_API_KEY", "ANGEL_CLIENT_CODE", "ANGEL_JWT", "ANGEL_PUBLIC_IP", "ANGEL_LOCAL_IP", "ANGEL_MAC_ADDRESS"):
            print(name + ": " + ("set" if os.environ.get(name) else "not set"))
        print("Offline setup check only. It does not validate credentials or connect to Angel One.")
        return 0
    try:
        # Validate user inputs before authentication or any API operation.
        symbols = symbols_arg(args.symbols) if args.command != "greeks" else None
        if args.command == "candles":
            start, end = request_time(args.start), request_time(args.end)
            if start > end or end - start > dt.timedelta(days=MAX_DAYS[args.interval]):
                raise DataError("Invalid date range; see the interval limits in scripts/ANGEL_ONE.md.")
        if args.command == "greeks":
            if len(symbols_arg(args.underlying)) != 1 or not re.fullmatch(r"[0-9]{2}[A-Z]{3}[0-9]{4}", args.expiry):
                raise DataError("Choose one underlying and a DDMMMYYYY expiry.")
            try:
                dt.datetime.strptime(args.expiry, "%d%b%Y")
            except ValueError:
                raise DataError("Invalid option expiry date.") from None
        api = local_client()
        started = dt.datetime.now(dt.timezone.utc)
        instruments = resolve_equities(api, symbols) if symbols else None
        csv_text = None
        if args.command == "candles":
            csv_text, data = collect_candles(api, instruments, args.interval, start, end, started)
            kind = "daily" if args.interval == "ONE_DAY" else "intraday"
        elif args.command == "quotes":
            kind, data = "quotes", collect_quotes(api, instruments)
        else:
            kind, data = "greeks", collect_greeks(api, args.underlying, args.expiry)
        payload = {"schema": "angelone-capture/1", "source": "Angel One SmartAPI REST", "kind": kind,
                   "started_at_utc": started.isoformat(), "received_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                   "adjustment_basis": "Provider supplied; corporate-action adjustment not independently verified. Do not mix with other providers.",
                   "data": data}
        directory = save_capture(args.out, kind, payload, csv_text)
        print("Saved market data to " + str(directory))
        print("Upload prices.csv into the scanner." if kind == "daily" else "Research capture only; not consumed by stock scoring or review filters.")
        return 0
    except DataError as error:
        print(str(error), file=sys.stderr)
        return 2
    except OSError:
        # Never print arbitrary I/O/provider exception content in a credentialed run.
        print("Local collection or output failed. Check paths, permissions and network setup.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
