# The Yahoo data contract

What each Yahoo field actually **means**, verified by rebuilding it from the
statements it came from. A field name is not a contract. Yahoo ships more than
one unit convention in a single payload: for TCS on 2026-09-16, `dividendYield`
is `2.95` and its neighbour `trailingAnnualDividendYield` is `0.0289` — the same
quantity, the same stock, the same response, two conventions.

The executable form of this table lives in `FIELD_CONTRACTS` in
[yahoo_fundamentals.py](scripts/yahoo_fundamentals.py), and the invariants are
enforced by `scripts/yahoo_fundamentals.py --self-test`. This file is the
reasoning; that code is the thing that runs.

## How it was verified

Three layers, the third being the one that counts:

1. **Semantic** — what the field is supposed to mean.
2. **Scaling** — fraction, percent, or raw currency.
3. **Reconstruction** — rebuild it independently from the underlying statements
   and compare. This is what catches a field whose *name* is right and whose
   *content* is not.

`scripts/yahoo_contract_audit.py` runs all three across ten companies chosen
for edge cases rather than convenience:

| ticker | the case it covers |
|---|---|
| HDFCBANK | bank; balance sheet reshaped by the 2023 HDFC Ltd merger |
| BAJFINANCE | NBFC |
| TCS | IT; net cash; the ticker the original conventions were fitted to |
| INFY | IT; net cash; independent control on TCS |
| ADANIGREEN | heavily leveraged power |
| VEDL | leveraged metals; unusually high dividend yield |
| COALINDIA | high dividend yield; large net cash |
| ETERNAL | loss-making / recently turned |
| TATASTEEL | cyclical, has posted losses |
| JIOFIN | balance sheet created by the 2023 Reliance demerger |

## The contract

| Field | Raw Yahoo key | Raw unit | Internal unit | Transformation | Independent check | Status |
|---|---|---|---|---|---|---|
| D/E | `debtToEquity` | **percent of equity** | ratio | `÷100` | Total Debt ÷ Stockholders Equity ×100 | **verified** 8/8 available |
| ROE | `returnOnEquity` | **fraction** | percent | `×100` | FY Net Income ÷ FY equity | **verified** 3/3 available |
| ROA | `returnOnAssets` | **fraction** | percent | `×100` | FY Net Income ÷ FY assets | **verified** 3/3 available |
| Dividend yield | `dividendYield` | **percent** | percent | none | `dividendRate` ÷ price ×100 | **verified** 8/8 reconstructible |
| Promoter holding | `heldPercentInsiders` | **fraction** | percent | `×100` | range only | **scale verified**, semantics approximate |
| Market cap | `marketCap` | **rupees** | ₹ cr | `÷1e7` | price × shares outstanding | **verified** 10/10 |
| CFO | cash-flow `Operating Cash Flow` | **statement currency** | ₹ cr | currency test, then `÷1e7` | cash-flow statement | **verified after fix** |
| EBIT | income `EBIT` / `Operating Income` | statement currency | — | exact label only | income statement | **verified after fix** |
| Equity | balance `Stockholders Equity` | statement currency | — | ratio use only | assets − liabilities | verified |
| ROCE | derived | — | percent | see below | recomputed by hand | verified, FY-consistent |
| Revenue growth | `revenueGrowth` | fraction | **NOT USED** | — | quarterly YoY, not annual | **deliberately unused** |
| Earnings growth | `earningsGrowth` | fraction | **NOT USED** | — | quarterly YoY, not annual | **deliberately unused** |

## Three defects the audit found

### 1. `Operating Income` resolved to a non-operating line — a wrong, scored number

`_row_from_frame` fell back to a case-insensitive substring match. HDFC Bank's
income statement has no `EBIT` and no `Operating Income` row, but it does have
**`Other Non Operating Income Expenses`** — and `"operating income"` is a
substring of `"non operating income"`. EBIT resolved to −₹36.8bn, a negative
non-operating line, and the adapter published:

```
Interest Coverage = -0.0198
```

for a healthy bank. That is worse than the missing value it replaced, because
an empty cell reads as "not measured" while −0.02 is *scored*.

Fixed by refusing a substring hit that contains a phrase inverting the request
(`non operating`, `non current`, `discontinued`, `pretax`) unless the caller
asked for that phrase. HDFC Bank now returns nothing for both fields, which is
the truth. The same trap sat on `Current Liabilities` / `Total Non Current
Liabilities`, which would have inverted the ROCE denominator.

### 2. Statement currency is not the quote currency — and not the label either

Infosys files in **USD** while its NSE price and market cap are in rupees.
Dividing a USD cash-flow figure by `RUPEES_PER_CRORE` understated Infosys's
operating cash flow by the exchange rate:

| | published | true |
|---|--:|--:|
| INFY cash flow from operations | ₹404 cr | **₹38,737 cr** |

a **96x** error, in a field whose absence or negativity is a hard red flag.

The obvious fix — trust `financialCurrency` — is itself wrong. That field
describes the `info` block, not the statements. **HCL Technologies reports
`info` in USD and its statements in rupees**, so converting on the label turned
a correct ₹19,975 cr into ₹19,15,702 cr.

So the currency is *measured*, not read: `info.totalRevenue` and the statement's
own revenue are the same quantity in the two units, and their ratio says which
is which. Ratio ≈ 1 means the statements share the info currency and need
converting; ratio ≈ 1/FX means they are already rupees. Anything else is
ambiguous and the field is emptied rather than guessed.

Blast radius, measured across the whole universe: **2 of 100** (INFY, HCLTECH),
and the two need *opposite* treatment.

Only absolute statement figures crossing into crore are exposed. Every ratio —
ROCE, interest coverage, derived ROE/ROA — cancels its unit and was never at
risk.

### 3. `trailingAnnualDividendRate` is not a cross-check

Infosys carries `trailingAnnualDividendRate` **0.52** against a real
`dividendRate` of **50.0**. An audit built on the trailing field reports a 100x
error in `dividendYield`, which is in fact correct. The lesson generalises: a
sibling field is not a verification, and the first version of this audit failed
on exactly that.

## ROCE, pinned down

Derived, so the definition is part of the contract:

```
ROCE = EBIT / (Total Assets − Current Liabilities) × 100
```

- **EBIT**: annual (FY), from the income statement. **Not TTM.**
- **Balance sheet**: annual (FY), same statement set, same period as EBIT.
- **Capital employed**: **ending**, not average.
- **Capital employed ≤ 0**: returns nothing. A negative denominator would
  otherwise produce a confident, sign-flipped ROCE.
- **Lease liabilities**: included in capital employed, because Yahoo's
  `Total Assets` carries the right-of-use asset and `Current Liabilities` only
  the current portion of the lease. Not adjusted out.
- **Units**: numerator and denominator are both in statement currency, so the
  ratio is currency-safe and no conversion happens before the division.
- **EBITDA fallback**: only when no `EBIT` row exists, and it is **flagged in
  the notes** because it overstates ROCE for asset-heavy companies.

A derived metric can be arithmetically right and economically incoherent if its
numerator and denominator refer to different periods. This one is FY-on-FY
throughout. Note the inconsistency that remains: Yahoo's *own* ROE and ROA are
TTM, so a row can carry an FY ROCE beside a TTM ROE.

## Known semantic gap: promoter holding

`heldPercentInsiders` is US-style **insider** holding, not the Indian
**promoter** concept the engine scores. It happens to coincide where a classic
promoter exists — TCS 0.718 against Tata Sons' real 71.8% — and is wrong *in
kind* where one does not: HDFC Bank returns 0.0015 where the true promoter
holding is nil. The scale is certain (10/10 inside [0,1]); the meaning is
approximate for professionally-managed companies.

This is not fixable from Yahoo. It is recorded so that a governance score built
on this column is read with it in mind.

## Range alarms, not clamps

`validate_row` warns on implausible values and **empties impossible ones**.
Nothing is silently pulled back inside a band: Vedanta really does yield 12.89%
and really is levered 3.15x, and a validator that "corrected" those would be
destroying the data this audit exists to protect. Only physical impossibilities
— a promoter holding of 140%, a negative capital adequacy ratio — are emptied,
because an impossible number is not a measurement.

## Raw snapshots

`scripts/yahoo_contract_audit.py` writes the **raw provider response** to
`data-store/fundamentals/raw/<SYMBOL>_<DATE>.json` before deriving anything:
the full `info` block plus every statement row and column.

That archive is the point. Yahoo cannot serve a past vintage, so if a convention
is later found to have been misread, historical exports can only be repaired
from a snapshot — never by re-querying. The fundamental archive is now the
scarce asset in this project, and a normalized-only archive would be
unrepairable.

## Related

- `scripts/yahoo_fundamentals.py` — `FIELD_CONTRACTS`, `FIELD_RANGES`,
  `SUBSTRING_TRAPS`, and `--self-test`.
- `scripts/yahoo_contract_audit.py` — the three-layer verification run.
- `knowledge/blocked.md` — why this file still cannot backtest the fundamental
  half: Yahoo carries no filing dates and no vintages.
