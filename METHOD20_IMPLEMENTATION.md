# METHOD 20: Implementation Notes (30 October 2026)

## Daily chart
Candles on 1D, SMA20 on price, separate Volume and CCI14 panels.
Only one black rectangle around the active bullish formation and one black horizontal entry trigger. Depending on state, show one red resistance zone (candidate/ready/triggered) or one green support zone (no setup and a falling/correcting price). No cluttered checklist.

## Setup/candidate logic
* 12 shapes: Hammer (green/red), Regular Doji, Dragonfly Doji, Bullish Belt Hold, Bullish Engulfing, Bullish Harami, Piercing Line, Tweezer Bottom, Morning Star, Three Inside Up, Three Outside Up, Inverted Hammer.
* Setup A: decline beneath SMA20. Setup B: a pullback toward SMA20 from an established rising trend, allowing a low within 2% above the average (or a test of the line).
* The candle pattern and market position alone create a CANDIDATE. CCI and volume are NOT prerequisites to drawing it.
* Signal can become READY on the completion day or during the following two trading sessions while neither high nor low breaks. Setup A also requires a recent CCI<-100. READY waits indefinitely while low stays intact. Original trigger is above the full pattern HIGH; stop below pattern LOW.
* Technical breakout on a later day gives TRIGGERED. If both original high and low are crossed on the same 1D bar, status is AMBIGUOUS, not a proven profitable trade. A breakout without confirmation is UNCONFIRMED_BREAKOUT.
* Only one active setup per ticker. Release when manually SKIPPED or when the linked real position is CLOSED. Technical trigger is not proof a real BUY occurred.

## Zones and role reversal
* Initial zones are identified from the 95 visible bars; choose strongest relevant proximity-and-volume cluster.
* Minimum two independent support responses, separated by 3 trading sessions and a 0.75 ATR move, with supporting volume.
* Rank by 35% touches, 25% volume, 25% proximity, 15% recency. Existing horizontal support overlapping SMA20 gets a small bonus, SMA20 alone never creates a horizontal zone.
* Use 2 consecutive daily closes below support / above resistance for an accepted break. Zone boundaries are fixed and stored in state/market_zones.json across sessions, including while hidden or outside the 95-bar window.
* Role reversal requires a new retest with 0.75 ATR reaction and volume support, after the two-close break. Stored zone states are monitored even while not visible.
* Display resistance above trigger, use the lower edge of resistance to calculate indicative reward/risk. This number is informational, never a filter.

## Trade tracking
* GitHub Actions > METHOD 20 Manual Trade Manager supports BUY, SELL_PARTIAL, UPDATE_STOP, CLOSE, SKIP_TRADE.
* Only one BUY per open ticker. Partial sells lower quantity; CLOSE sells the remainder. A long stop can only be raised or left unchanged.
* Ledger is data/trade_events.json. Tracked state is reconstructed by replaying those immutable events.
* Actual entry, quantity, revised stop, realized and unrealized P/L are tracked separately from technical trigger.
* Morning email shows portfolio table and crossed-stop alert based on preceding completed daily low, without auto-selling or auto-closing.
* Because only daily OHLCV is available, same-day stop changes and fills cannot be reconstructed reliably. Stop warnings do not prove actual executions.
* Optional fee input is stored but net-of-fee accounting is NOT yet provided, since fee accounting policy was not finalized.

## Operations
* The nightly workflow persists market zones in the repository and includes positions/alerts in portfolio.json inside the report artifact.
* Manual trade workflow serializes commits with the nightly report workflow.
* Validation workflow compiles Python and runs unit tests on code pushes.
* The report includes 1D charts, one active setup/trigger, selected zone and optional reward/risk, with morning portfolio information above charts.

## Remaining limitations to verify
* External live market data generation and SMTP delivery must be verified in GitHub Actions, separately from unit tests.
* Zone clustering and reversal thresholds are heuristic and need tuning on real historical tickers.
* Positions outside the watchlist can appear with missing market prices and no stop-crossing review until an OHLCV source is added for those symbols.
* One full live end-to-end manual trade entry and next-morning email should be tested before relying on operational alerts.
