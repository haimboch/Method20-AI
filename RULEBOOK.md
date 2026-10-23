# METHOD 20 | Rulebook v0.6 (prototype)

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
Candlestick recognition (hammer, bullish engulfing, bullish rejection), trend and volume thresholds remain provisional heuristics, not independently validated trading signals. A doji alone is neutral and does not generate a LONG reversal. State transition checks run on subsequent daily bars with no expiry; edge cases are covered by unit tests. The HTML still contains deterministic analysis only, **not multimodal AI chart review**. Validate setups against chart evidence before interpreting any label.

## v0.8: Support/resistance and next-day scenarios
Levels come from confirmed swing highs/lows in the trailing 90 daily bars (2-bar confirmation on each side). Nearby levels are grouped within a provisional 0.8% tolerance. Show up to two support and two resistance levels closest to current closing price. The next-session outlook is a **qualitative conditional scenario**, not a calibrated forecast or probability. Inputs: last five sessions' return, latest candle and volume compared to previous 20 bars, price versus SMA20. Include bullish and bearish invalidation/confirmation conditions and allow an explicitly neutral result. No predicted return percentage or execution orders. Parameters must be validated against chart evidence.
