# METHOD 20 | Rulebook v0.5 draft

**Daily candles, LONG only, research only, SMA20 only (no SMA150).**

## Inputs
Daily OHLCV, SMA20, Volume/20-day average, CCI(14), open gaps, reversal candlesticks, week/month trends and support/resistance.

## A: MEAN_REVERSION
Downward price trend; price below SMA20; bullish reversal; volume elevated or rising; CCI(14) turns upward after an oversold reading below -100; possible move toward SMA20.

## B: SMA20_BOUNCE
Pullback toward SMA20; bullish reversal near SMA20; volume elevated or rising; CCI(14) turns upward. **Oversold CCI is NOT required for B.**

## Signal state
Reversal candle produces `READY`, not an executed long. Keep its original high and low. Only a **later** daily bar strictly above high changes to `TRIGGERED`; breaking below low first changes to `INVALIDATED`. If both extremes occur in the same later daily bar, use `AMBIGUOUS`. Equal price is not a break. READY does not expire by time.

## Report
Every watchlist symbol, including no-setup and failed-data symbols, needs a clear daily chart and rationale. No trading, no brokerage connection, no backtest.

## Limitations in current prototype
Candlestick recognition and trend/volume thresholds are provisional heuristics, not a validated implementation of every rule. Current HTML contains deterministic analysis only, **not multimodal AI chart review**. The historical signal tracking currently uses a simplified state model; validate against actual TradingView before relying on flags.
