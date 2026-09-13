# Track prediction — held-out test evaluation

7,400 forecasts from 301 test storms never seen in training or validation. Model gru v1.

## Track error (great-circle km, mean) — storm-bootstrap 95 % CI

| forecast | T+6h | T+12h | T+18h | T+24h |
|---|---|---|---|---|
| model | 34.319 (32.839–35.767) | 73.521 (70.437–76.742) | 119.524 (114.385–124.892) | 171.508 (164.044–179.463) |
| persistence | 105.997 (101.062–110.906) | 210.83 (200.82–220.811) | 315.554 (300.117–330.614) | 420.612 (399.754–440.859) |
| extrapolation | 39.745 (37.991–41.6) | 87.113 (83.095–91.35) | 143.179 (136.268–150.202) | 207.322 (197.169–217.495) |

## Intensity and pressure

| forecast | T+6h wind MAE kt | T+12h wind MAE kt | T+18h wind MAE kt | T+24h wind MAE kt | T+24h pressure MAE hPa |
|---|---|---|---|---|---|
| model | 3.513 | 5.862 | 8.086 | 10.002 | 7.284 |
| persistence | 4.085 | 7.806 | 11.247 | 14.324 | 10.277 |
| extrapolation | 4.085 | 7.806 | 11.247 | 14.324 | 10.277 |

## Skill of the model (% error reduction)

- vs persistence: track {'6': 67.6, '12': 65.1, '18': 62.1, '24': 59.2}, wind {'6': 14.0, '12': 24.9, '18': 28.1, '24': 30.2}, pressure {'6': 15.8, '12': 24.3, '18': 27.2, '24': 29.1}
- vs extrapolation: track {'6': 13.7, '12': 15.6, '18': 16.5, '24': 17.3}, wind {'6': 14.0, '12': 24.9, '18': 28.1, '24': 30.2}, pressure {'6': 15.8, '12': 24.3, '18': 27.2, '24': 29.1}

## Region-wise (model; counts always shown)

| area | samples | storms | T+24h track km | T+24h wind MAE kt |
|---|---|---|---|---|
| North Indian Ocean | 358 | 28 | 125.947 | 11.247 |
| Arabian Sea | 199 | 11 | 119.647 | 13.214 |
| Bay of Bengal | 159 | 19 | 133.832 | 8.483 |
| South Indian Ocean | 2006 | 67 | 174.223 | 10.725 |
| Pacific Ocean | 5036 | 212 | 173.666 | 9.634 |
| Western Pacific | 2695 | 107 | 193.522 | 10.002 |
| Eastern Pacific | 1484 | 72 | 122.92 | 8.708 |
| Southern Pacific | 857 | 38 | 199.1 | 10.596 |

## Uncertainty radii (fitted on validation) — coverage on test

| lead | radius km | track errors inside | wind band ± kt | wind errors inside |
|---|---|---|---|---|
| T+6h | 36.9 | 0.6649 | 3.8 | 0.6744 |
| T+12h | 80.1 | 0.6605 | 6.5 | 0.6773 |
| T+18h | 129.8 | 0.6568 | 8.8 | 0.6632 |
| T+24h | 184.9 | 0.6531 | 11.0 | 0.6708 |

Post-processing on test forecasts: {'skipped_no_current_intensity': 1228, 'accepted': 6172}

