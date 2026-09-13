# Prediction data audit

Source: `H:/ibtracs.since1980.list.v04r01.csv` (read only). 2,156 storms, 66,528 six-hourly fixes, 1999-12-09 → 2025-10-31.

## Funnel

| step | rows |
|---|---|
| ibtracs_rows | 309,258 |
| basins_and_seasons | 139,829 |
| main_track | 132,085 |
| synoptic_6_hourly | 66,528 |
| after_validation | 66,528 |

Validation: {'rows_in': 66528, 'dropped_invalid_time': 0, 'dropped_invalid_position': 0, 'wind_set_missing_out_of_range': 0, 'pressure_set_missing_out_of_range': 0, 'dropped_duplicate_times': 0, 'rows_out': 66528}

## Missing values

| field | missing |
|---|---|
| wind_kt | 16.9% |
| pressure_hpa | 20.7% |
| dist2land_km | 0.0% |
| storm_speed_kt | 0.0% |

| basin | storms | fixes | wind missing | pressure missing |
|---|---|---|---|---|
| EP | 612 | 13,971 | 1.0% | 1.7% |
| NI | 257 | 4,389 | 26.0% | 28.2% |
| SI | 449 | 16,796 | 22.9% | 29.3% |
| SP | 260 | 7,247 | 25.1% | 29.4% |
| WP | 752 | 24,125 | 17.9% | 21.7% |

## Environmental / meteorological fields

- **sea_surface_temperature**: NOT AVAILABLE — IBTrACS has no SST and no SST product is in the project
- **vertical_wind_shear**: NOT AVAILABLE — needs reanalysis winds (e.g. ERA5 200/850 hPa), not in the project
- **relative_humidity**: NOT AVAILABLE — needs reanalysis, not in the project
- **environmental_pressure**: NOT AVAILABLE — only the storm's central pressure (USA_PRES) exists
- **distance_to_land**: AVAILABLE — IBTrACS DIST2LAND (km), used as a feature

**Satellite features:** NOT USED — GridSat crops exist only for the fixes sampled for the identification and classification datasets (the NOAA server outage stopped further downloads). A temporal window needs an image for every 6-hourly step, so there are no per-fix satellite features yet; the feature list has no satellite group until per-fix embeddings exist.

## Samples

Window 24 h every 6 h, horizons [6, 12, 18, 24] h → 49,559 samples over all storms (before the split). Skipped: {'future_position_missing': 8345, 'storm_too_short': 220}.
