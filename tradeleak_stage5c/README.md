# TradeLeak Stage-5c (Frozen)

Purpose: estimate passive cognitive-state leakage under natural market histories published with the pinned Agent Trading Arena repository.

- ATA commit: `6b49ee837ebc1fa0d5bf99d655dc3adc352a77d3`
- Model: DeepSeek V4 Flash
- Secret: naturalistic `confirmation_style` pair fixed in prior stages
- Passive source: all 18 rolling 5-day windows from the 3 price histories in `save/sim01/stocks.json`
- ATA native `analysis -> buy decision` prompt stack; reflection disabled
- 2 calibration reps + 2 held-out reps per secret/window
- Metrics: held-out passive inference accuracy, diagnostic-window fraction, expected number of windows to first diagnostic state
- No attacker market order is present in passive trials
- Stage-4 active q=20 result is referenced unchanged; it is not retuned in this stage
