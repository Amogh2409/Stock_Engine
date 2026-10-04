"""Offline SmartAPI contract tests. No account or network access required."""
import contextlib
import csv
import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import angelone_data as A


class AngelOneDataTests(unittest.TestCase):
    def setUp(self):
        guard = patch.object(A.http.client, "HTTPSConnection", side_effect=AssertionError("network forbidden"))
        guard.start()
        self.addCleanup(guard.stop)
        self.start = A.request_time("2022-01-01 00:00")
        self.end = A.request_time("2022-01-03 23:59")
        self.now = A.request_time("2022-01-04 00:00")
        self.instrument = {"ticker": "TEST", "exchange": "NSE", "tradingsymbol": "TEST-EQ", "symboltoken": "123"}

    def candle(self, timestamp="2022-01-03T09:15:00+05:30"):
        return [timestamp, 100, 110, 90, 105, 200]

    def client(self):
        return A.SmartAPI("synthetic-key", "203.0.113.1", "192.0.2.1", "01:02:03:04:05:06", "synthetic-jwt")

    def test_daily_export_fits_existing_price_importer(self):
        api = Mock()
        api.request.return_value = [self.candle()]
        text, meta = A.collect_candles(api, [self.instrument], "ONE_DAY", self.start, self.end, self.now)
        self.assertEqual(list(csv.DictReader(io.StringIO(text)))[0],
                         dict(Date="2022-01-03", Ticker="TEST", Open="100.0", High="110.0", Low="90.0", Close="105.0", Volume="200.0"))
        self.assertEqual(meta["row_count"], 1)
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))
        import engine
        history, skipped = engine.parse_price_history_csv(text)
        self.assertEqual(skipped, 0)
        self.assertEqual(history["TEST"]["closes"], [105])
        self.assertEqual(history["TEST"]["dates"], ["2022-01-03"])

    def test_intraday_timestamps_are_preserved_and_not_labelled_daily(self):
        api = Mock()
        api.request.return_value = [self.candle(), self.candle("2022-01-03T09:16:00+05:30")]
        text, _ = A.collect_candles(api, [self.instrument], "ONE_MINUTE", self.start, self.end, self.now)
        self.assertTrue(text.startswith("Timestamp,Ticker,"))
        self.assertIn("2022-01-03T09:16:00+05:30", text)

    def test_current_daily_and_incomplete_intraday_bars_are_excluded(self):
        data = [self.candle("2022-01-02T09:15:00+05:30"), self.candle()]
        rows, excluded = A.normalize_candles(data, "TEST", "ONE_DAY", self.start, self.end, A.request_time("2022-01-03 16:00"))
        self.assertEqual((len(rows), excluded), (1, 1))
        rows, excluded = A.normalize_candles([self.candle(), self.candle("2022-01-03T09:16:00+05:30")], "TEST", "ONE_MINUTE",
                                            self.start, self.end, A.request_time("2022-01-03 09:16"))
        self.assertEqual((len(rows), excluded), (1, 1))

    def test_invalid_prices_dates_duplicates_and_ranges_are_refused(self):
        bad = [self.candle("2022-01-03T09:15:00"), self.candle("2022-01-04T09:15:00+05:30")]
        for column, value in ((1, True), (2, 80), (3, -1), (4, float("nan")), (5, -1)):
            row = self.candle(); row[column] = value; bad.append(row)
        for data in [[row] for row in bad] + [[self.candle(), self.candle()]]:
            with self.subTest(data=data), self.assertRaises(A.DataError):
                A.normalize_candles(data, "TEST", "ONE_DAY", self.start, self.end, self.now)
        with self.assertRaises(A.DataError):
            A.normalize_candles([self.candle(), self.candle("2022-01-03T10:00:00+05:30")], "TEST", "ONE_DAY", self.start, self.end, self.now)

    def test_zero_volume_is_preserved_not_filled(self):
        api = Mock(); row = self.candle(); row[5] = 0; api.request.return_value = [row]
        text, meta = A.collect_candles(api, [self.instrument], "ONE_DAY", self.start, self.end, self.now)
        self.assertEqual(meta["zero_volume_rows"], 1)
        self.assertEqual(next(csv.DictReader(io.StringIO(text)))["Volume"], "0.0")

    def test_exact_instrument_mapping_and_partial_quotes_fail_closed(self):
        api = Mock(); match = {k: self.instrument[k] for k in ("exchange", "tradingsymbol", "symboltoken")}
        api.request.return_value = [match]
        self.assertEqual(A.resolve_equities(api, ["TEST"]), [self.instrument])
        for data in ([], [match, match], [{**match, "tradingsymbol": "TEST-BE"}]):
            api.request.return_value = data
            with self.assertRaises(A.DataError):
                A.resolve_equities(api, ["TEST"])
        for data in ({"fetched": [], "unfetched": []}, {"fetched": [{"exchange": "NSE", "symbolToken": "123"}], "unfetched": ["other"]}):
            api.request.return_value = data
            with self.assertRaises(A.DataError):
                A.collect_quotes(api, [self.instrument])

    def test_quote_snapshot_preserves_depth_and_never_infers_trade_delta(self):
        api = Mock(); data = {"fetched": [{"exchange": "NSE", "symbolToken": "123", "depth": {
            "buy": [{"price": 100, "quantity": 500, "orders": 3}], "sell": [{"price": 101, "quantity": 200, "orders": 2}]}}], "unfetched": []}
        api.request.return_value = data
        result = A.collect_quotes(api, [self.instrument])
        self.assertEqual(result["data"], data)
        self.assertNotIn("delta", result)
        self.assertIn("not historical depth", result["basis"])

    def test_greeks_match_contracts_and_do_not_treat_trade_volume_as_oi(self):
        api = Mock(); row = {"name": "TEST", "expiry": "27JAN2022", "optionType": "CE", "strikePrice": "100", "gamma": "0.01", "tradeVolume": "300"}
        api.request.return_value = [row]
        result = A.collect_greeks(api, "TEST", "27JAN2022")
        self.assertNotIn("gex", result)
        self.assertIn("tradeVolume is not open interest", result["basis"])
        for field, value in (("expiry", "24FEB2022"), ("name", "OTHER"), ("gamma", "NaN")):
            api.request.return_value = [{**row, field: value}]
            with self.assertRaises(A.DataError):
                A.collect_greeks(api, "TEST", "27JAN2022")

    def test_api_sends_only_allowlisted_operations_to_the_official_host(self):
        client = self.client()
        with self.assertRaises(A.DataError):
            client.request("placeOrder", {})
        connection = Mock(); response = connection.getresponse.return_value
        response.status = 200; response.read.return_value = b'{"status":true,"data":[]}'
        with patch.object(A.http.client, "HTTPSConnection", return_value=connection) as factory:
            self.assertEqual(client.request("candles", {"interval": "ONE_DAY"}), [])
        factory.assert_called_once_with("apiconnect.angelone.in", timeout=30)
        self.assertEqual(connection.request.call_args.args[:2], ("POST", A.PATHS["candles"]))
        connection.close.assert_called_once()

    def test_errors_do_not_echo_credentials_and_login_does_not_save_tokens(self):
        client = self.client(); connection = Mock(); response = connection.getresponse.return_value
        response.status = 200; response.read.return_value = b'{"status":false,"message":"synthetic-secret"}'
        with patch.object(A.http.client, "HTTPSConnection", return_value=connection), self.assertRaises(A.DataError) as caught:
            client.request("quotes", {})
        self.assertNotIn("synthetic-secret", str(caught.exception))
        client.request = Mock(return_value={"jwtToken": "new-synthetic-session", "refreshToken": "do-not-save"})
        client.login("client", "pin", "otp")
        self.assertEqual(client.headers["Authorization"], "Bearer new-synthetic-session")
        self.assertNotIn("refreshToken", client.__dict__)

    def test_pacing_and_redirects(self):
        client = self.client(); client.last_call = 1
        connection = Mock(); connection.getresponse.return_value.status = 302
        with (patch.object(A.time, "monotonic", return_value=1.5), patch.object(A.time, "sleep") as sleep,
              patch.object(A.http.client, "HTTPSConnection", return_value=connection), self.assertRaises(A.DataError)):
            client.request("quotes", {})
        sleep.assert_called_once_with(0.6000000000000001)
        connection.close.assert_called_once()

    def test_check_and_invalid_inputs_do_not_connect_or_reveal_environment(self):
        out = io.StringIO()
        with patch.dict(A.os.environ, {"ANGEL_API_KEY": "synthetic-secret"}, clear=True), contextlib.redirect_stdout(out):
            self.assertEqual(A.main(["check"]), 0)
        self.assertIn("ANGEL_API_KEY: set", out.getvalue())
        self.assertNotIn("synthetic-secret", out.getvalue())
        for args in (["candles", "--symbols", "TEST", "--from", "2022-01-01 00:00", "--to", "2022-06-01 00:00", "--interval", "ONE_MINUTE"],
                     ["greeks", "--underlying", "TEST", "--expiry", "99JAN2022"]):
            with patch.object(A, "local_client") as client, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(A.main(args), 2)
                client.assert_not_called()

    def test_capture_is_separate_immutable_and_has_no_auth_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = {"kind": "daily", "data": {"row_count": 1}}
            first = A.save_capture(tmp, "daily", payload, "Date,Ticker\n2022-01-03,TEST\n")
            second = A.save_capture(tmp, "daily", payload)
            self.assertNotEqual(first, second)
            self.assertTrue((first / "prices.csv").exists())
            self.assertEqual(json.loads((first / "capture.json").read_text()), payload)
            self.assertNotIn("Authorization", (first / "capture.json").read_text())
            with self.assertRaises(A.DataError):
                A.save_capture(tmp, "quotes", {"bad": float("nan")})
            self.assertEqual(len(list(Path(tmp).iterdir())), 2)


if __name__ == "__main__":
    unittest.main()
