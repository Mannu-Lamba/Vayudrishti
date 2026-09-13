# Baseline forecasts

- **persistence** — position, wind and pressure stay at their T0 values.
- **extrapolation** — the mean motion of the last 12 h continues; intensity and pressure persist.

## val — 7,248 samples from 301 storms

| baseline | T+6h track km | T+12h track km | T+18h track km | T+24h track km | T+24h wind MAE kt | T+24h pressure MAE hPa |
|---|---|---|---|---|---|---|
| persistence | 104.507 | 208.031 | 311.402 | 414.881 | 15.023 | 10.609 |
| extrapolation | 38.695 | 84.151 | 137.842 | 198.622 | 15.023 | 10.609 |

## test — 7,400 samples from 301 storms

| baseline | T+6h track km | T+12h track km | T+18h track km | T+24h track km | T+24h wind MAE kt | T+24h pressure MAE hPa |
|---|---|---|---|---|---|---|
| persistence | 105.997 | 210.83 | 315.554 | 420.612 | 14.324 | 10.277 |
| extrapolation | 39.745 | 87.113 | 143.179 | 207.322 | 14.324 | 10.277 |

