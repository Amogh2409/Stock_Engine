# What the NSE monthly report fields mean

Determined empirically from the reports and cross-checked against an
independent full-market-cap source. Nothing here has been used in research.

## `Index Mcap (Rs. Crores)` = FREE-FLOAT market capitalisation

Not full market cap. The ratio of index mcap to full market cap on 2026-08-31
varies from **0.12 to 1.07** across constituents, and varies exactly the way
free float does:

| constituent | index / full | interpretation |
|---|--:|---|
| ICICIBANK | 1.065 | widely held, ~full free float (>1 is a date mismatch: index 31 Aug vs full 16 Sep) |
| HDFCBANK | 0.974 | widely held |
| INFY | 0.924 | widely held |
| **TCS** | **0.308** | Tata Sons holds ~71.8%, so free float ~28.2% — the ratio matches |
| HINDZINC | 0.119 | promoter-dominated |
| TATACAP | 0.127 | recent listing, small float |

TCS is the decisive case: its free float is independently known to be ~28%, and
the ratio is 0.308.

## `Weightage (%)` = weight WITHIN its own index

Sums to 100 across a single index's constituents.

**CAVEAT FOR RECONSTRUCTED MONTHS.** In the composite reconstruction
(2022-04 onward) the rows are the union of two sub-indices, each of whose
weights sum to 100 separately, so the union's weights sum to **200.02** on
2026-08-31. A Nifty 50 constituent's weight and a Next 50 constituent's weight
are therefore **on different bases and are not comparable** in reconstructed
months. Index mcap does not have this problem; it is an absolute figure.

Any use of `weight_pct` on reconstructed months must renormalise, and must do
so knowing the two halves were never weighted against each other.

## Suitability as a point-in-time SIZE variable

`index_mcap_cr` is genuinely point-in-time, covers 2015-2026 monthly, and is
free of the look-ahead that today's market cap would carry. That makes it the
only PIT size measure this project has.

But it is **free-float** size, not total size, and the two rank differently
wherever ownership structures differ — TCS at 0.31 of its full cap ranks far
below HDFC Bank at 0.97 for reasons that are about promoter holding, not about
company size. A cross-sectional rank on this field is a rank on *investable*
size, which is a defensible variable in its own right and is **not** a
substitute for full market cap.

Not used in any research. Recorded for a future registration to draw on.
