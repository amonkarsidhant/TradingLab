# Skill: Momentum Trading
Activated when user asks about momentum strategies, entry signals, or trend following.

## Core Strategy: simple_momentum
- Lookback period: 5 days (default)
- Signal: BUY if price % change > 1% with confirmation
- Signal: SELL if price % change < 0% (declining momentum)
- Confidence scales with magnitude of momentum

## Parameters
- `--lookback`: number of days for price change calculation
- `--momentum-threshold`: minimum % change for BUY signal (default 1.0)

## Usage
```
python -m trading_lab.cli run-strategy --strategy simple_momentum --ticker <TICKER> --data-source chained --dry-run
```

## When to use
- Trending markets (bull regime)
- Strong sector performance
- Post-earnings continuation patterns
- Avoid: choppy/sideways markets, pre-Fed announcements

## Risk notes
- Momentum can reverse sharply
- Always combine with stop-loss at -7%
- Don't chase +10%+ moves without consolidation
- Check volume confirmation when available
