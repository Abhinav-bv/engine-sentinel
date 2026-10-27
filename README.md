# Engine Sentinel

**A small, explainable engine telemetry triage prototype.**

[View the demo report](https://abhinav-bv.github.io/engine-sentinel/) · [Read the analysis code](engine_sentinel.py)

Fleet alerts can be noisy: one odd reading may be a sensor glitch, while missing data can make a confident looking score unreliable. Engine Sentinel looks for *sustained* changes, compares recent readings with each engine's own baseline, checks fault persistence, and shows exactly why each engine received its status.

This was built as a portfolio project inspired by the kinds of monitoring problems described in [Cummins Connected Solutions](https://connectedsolutions.cummins.com/) and [Cummins Remote Diagnostics](https://www.cummins.com/parts-and-service/digital-products-and-services/remote-diagnostics). It is independent, uses entirely synthetic data, and is not affiliated with Cummins.

## Run it

Python 3.10+ is the only requirement.

```bash
python engine_sentinel.py
```

This creates `data/synthetic_fleet.csv` and `report.html`. Open `report.html` in a browser. The demo is deterministic, so the same input produces the same report.

To analyze a CSV of your own:

```bash
python engine_sentinel.py --input your_data.csv --output your_report.html
```

Required columns: `engine_id,timestamp_utc,rpm,coolant_temp_c,oil_pressure_kpa,battery_v,fault_code`. Timestamps need a timezone, for example `2026-10-26T00:00:00Z`. Sensor values may be blank. `fault_code` may be blank. The program does not upload data anywhere.

## The demo story

| Engine | Injected scenario | Expected result |
| --- | --- | --- |
| ENG-101 | Stable readings | Normal |
| ENG-102 | Sustained cooling trend plus recurring fault | Service soon |
| ENG-103 | Sustained oil pressure drop plus recurring fault | Service soon |
| ENG-104 | Charging voltage drift | Watch |
| ENG-105 | Missing recent sensor readings | Insufficient data |
| ENG-106 | One isolated coolant spike | Normal |

## How it decides

- Uses the latest 12 samples for repeated threshold checks and telemetry coverage.
- Compares them with the first 24 samples as a simple baseline.
- Adds score points for sustained temperature, oil pressure and voltage changes, plus repeated fault codes.
- Refuses a status decision when fewer than 24 samples exist or recent sensor coverage falls below 75%.
- Displays the reasons, coverage, score and sensor trends together.

The thresholds are **illustrative**, not calibrated to an engine model, duty cycle or operating state. In a real project I would normalize readings by RPM/load, validate against labeled service outcomes, measure false alarms and lead time, and review thresholds with domain engineers. This tool must not be used for actual vehicle operation or maintenance decisions.

## Design decisions

| Decision | Why it matters |
| --- | --- |
| Score repeated breaches, not one value | Reduces reaction to an isolated sensor spike. |
| Compare with an engine's own early samples | Makes the change visible even when a universal threshold is not crossed. |
| Count recent sensor coverage | Missing values should lower confidence, never silently become zero. |
| Show reason text beside every score | A maintenance reviewer can inspect the evidence instead of trusting a black box. |
| Use a fixed random seed | Anyone can reproduce the demo and tests. |

The six scenario checks are automated in `test_engine_sentinel.py`. The code also checks that a malformed CSV gets a useful error message. Run them with `python -m unittest -v` from this folder.

## What I would discuss in an interview

1. Why an isolated spike should not create a high-priority maintenance alert.
2. Why the system exposes missing data instead of treating blanks as zero.
3. The trade-off between early warning and false alarms, and how I would test it with real labeled data.
4. Why an engine-specific baseline can be more useful than one fleet-wide threshold.

## Project status

Working prototype with a generated dataset and static HTML report. It does not claim predictive accuracy or use proprietary engine data. The code and report were created with AI assistance; I can explain and modify the rules, data generation and limitations.

