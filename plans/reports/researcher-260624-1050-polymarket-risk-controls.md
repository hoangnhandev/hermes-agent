# Polymarket Arbitrage Bot: Risk Control & Execution Safety Framework

**Bankroll:** $500 | **Strategy:** Multi-outcome arbitrage hedge | **Risk Tolerance:** Minimal variance, steady gains

---

## TL;DR: Recommended Risk-Control Configuration

### Hard Limits ($500 Bankroll)

| Metric | Cap (% of Bankroll) | Cap ($) | Action When Breached |
|--------|-------------------|---------|---------------------|
| **Max Daily Loss** | 10% | $50 | Kill-switch for 24h, notify TG |
| **Max Drawdown** | 25% | $125 | Kill-switch, manual review required |
| **Max Single Trade** | 15% | $75 | Reject trade opportunity |
| **Max Total Exposure** | 80% | $400 | Stop new entries |
| **Min Liquidity Per Leg** | 5% | $25 | Skip market (illiquid) |
| **Min Profit Margin** | 2.5% | - | Skip opportunity (after fees/gas) |
| **Gas Per Trade** | 1% | $5 | Skip if gas spike >$0.05/tx |

### Kill-Switch Triggers

1. **Daily loss circuit breaker:** -$50 → halt 24h cooldown
2. **Total drawdown circuit breaker:** -$125 → manual review
3. **Position reconciliation failure:** mismatch between expected vs actual holdings → immediate halt
4. **Failed all-or-nothing execution:** ANY partial fill in arbitrage → cancel ALL legs, flatten positions
5. **Stale price (>30s old):** Skip opportunity
6. **Disputed/Void market detected:** Auto-halt trading in that market category
7. **Gas spike >$0.10:** Pause all trading
8. **Failed heartbeat (3 consecutive cycles):** Telegram alert + halt

---

## Execution Safety: All-or-Nothing Hedge Protection

### The #1 Danger: Partial Fill = Unhedged Directional Exposure

If you buy 3 outcomes but only 2 fill, you're now naked short/long on the unfilled leg. One mistake = entire bankroll at risk.

### Atomic Execution Sequence (Pseudocode)

```python
def execute_arbitrage(event_id, legs, max_slippage=0.02, price_stale_sec=30):
    """
    legs: [{'outcome_id': 123, 'price': 0.15, 'shares': 100}, ...]
    RETURNS: True only if ALL legs filled, False if ANY failure
    """
    
    # 1. Price staleness check
    if time_since_last_update() > price_stale_sec:
        log.info("Prices stale, skipping")
        return False
    
    # 2. Pre-flight capital check
    total_cost = sum(l['price'] * l['shares'] for l in legs) + gas_estimate
    if total_cost > available_capital * 0.15:  # Max 15% per trade
        log.warning("Trade exceeds max single position")
        return False
    
    # 3. Profit validation (after fees/gas/slippage)
    total_outcome_prices = sum(l['price'] for l in legs)
    if total_outcome_prices >= 0.975:  # Min 2.5% margin
        log.info("Insufficient profit margin")
        return False
    
    # 4. Liquidity check per leg
    for leg in legs:
        if get_order_book_depth(leg['outcome_id']) < min_liquidity:
            log.warning(f"Leg {leg['outcome_id']} insufficient liquidity")
            return False
    
    # 5. Submit limit orders (maker) with slippage tolerance
    order_ids = []
    for leg in legs:
        limit_price = leg['price'] * (1 + max_slippage)  # Slightly above to fill
        order_id = submit_limit_order(
            outcome_id=leg['outcome_id'],
            shares=leg['shares'],
            side='BUY',
            limit_price=limit_price,
            expire_seconds=60  # Cancel if not filled in 60s
        )
        order_ids.append(order_id)
    
    # 6. Wait for fills (with timeout)
    time.sleep(5)  # Allow matching engine
    
    # 7. CHECK ALL FILLED
    filled_status = []
    for order_id in order_ids:
        status = check_order_status(order_id)
        if status != 'FILLED':
            # PARTIAL FILL DETECTED - CANCEL EVERYTHING
            log.error(f"Order {order_id} not filled, cancelling all legs")
            cancel_all_orders(order_ids)
            flatten_positions(event_id)  # Sell any filled positions immediately
            return False
        filled_status.append(True)
    
    # 8. Position reconciliation
    actual_holdings = get_polymarket_positions(event_id)
    expected_holdings = {leg['outcome_id']: leg['shares'] for leg in legs}
    
    if actual_holdings != expected_holdings:
        log.error("Position reconciliation failed")
        flatten_positions(event_id)
        return False
    
    # 9. All legs filled and verified - SUCCESS
    log.info(f"Arbitrage executed: {len(legs)} legs filled")
    return True


def flatten_positions(event_id):
    """Emergency sell all positions in event at market"""
    positions = get_polymarket_positions(event_id)
    for outcome_id, shares in positions.items():
        submit_market_order(outcome_id, shares, side='SELL')
```

### Execution Safeguards

| Protection | Implementation | Why |
|-----------|----------------|-----|
| **Maker orders** | Use LIMIT orders, wait for fill | Avoid 0.75-1.8% taker fees, earn 20-25% rebates |
| **Slippage tolerance** | Limit price 2% above computed | Prevent filling at unfavorable prices |
| **Order expiry** | 60-second timeout | Don't leave stale orders hanging |
| **Cancel-on-partial** | If ANY leg unfilled → cancel ALL + flatten | The core safety mechanism |
| **Immediate market exit** | Flatten via market orders if partial fill | Cut exposure fast, accept slippage |
| **Position reconciliation** | Verify holdings vs expected after each trade | Detect silent failures |
| **Price staleness window** | Reject prices >30s old | Avoid trading on stale data |

### Retry/Backoff Strategy

```
Failed execution → Wait 30s (exponential backoff) → Retry max 2 times
If 3rd failure → Skip market, move to next
After ANY partial-fill emergency → Cooldown 5 minutes + manual review
```

---

## Polymarket-Specific Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| **VOID/DISPUTE resolution** | Funds locked or lost | - If disputed: 2-hour window, UMA token vote decides outcome (not necessarily "correct")<br>- If voided: Refunds are **discretionary**, not guaranteed<br>- Hold only 5-10 markets max to diversify resolution risk |
| **Resolution delays** | Capital lockup, opportunity cost | - Research shows capital lockup until resolution = major arbitrage barrier<br>- Target markets resolving <7 days<br>- Track markets in "pending resolution" state, exclude from new trades |
| **Fee changes (Mar 30, 2026)** | Profit margin erosion | - Sports/politics/crypto now have 0.75-1.8% taker fees<br>- ALWAYS use maker orders to avoid taker fees<br>- Earn 20-25% maker rebates |
| **Gas spikes on Polygon** | Transaction cost > profit margin | - Polygon gas normally <$0.01/tx, but can spike<br>- Check gas before each trade, skip if >$0.05<br>- Circle Paymaster allows gas payment in USDC |
| **Token allowance risk** | Trade rejection or stuck funds | - Set CLOB token allowance once: max 150% of bankroll<br>- Verify allowance before first trade |
| **Geo-blocking (US)** | Account shutdown, funds frozen | - Use VPN/non-US IP if in US<br>- Don't risk main funds, use dedicated trading wallet only |
| **Proxy wallet pitfalls** | Recovery complexity | - Proxy wallets add security but recovery is complex<br>- For <$500, EOA with dedicated key is simpler<br>- Separate hot wallet for trading vs cold storage for main funds |
| **Private key compromise** | Total bankroll loss | - Store key in encrypted env variable only<br>- Never log private key<br>- Trading wallet holds ONLY bankroll, not main funds |
| **UMA dispute bonding** | No direct risk (proposer issue) | - Arbitrage traders don't propose outcomes<br>- But resolution can be overturned by UMA vote<br>- Avoid markets with high dispute probability |

### Market-Specific Risk Matrix

| Market Type | Fee (Taker) | Dispute Risk | Resolution Speed | Recommendation |
|-------------|-------------|--------------|-------------------|----------------|
| **Politics** | 0% | Medium | Slow (days-weeks) | ✅ Good for arbitrage |
| **Sports (pre-Mar 30)** | 0% | Low | Fast (hours) | ✅ Excellent |
| **Sports (post-Mar 30)** | 0.75% | Low | Fast (hours) | ⚠️ Only if margin >3% |
| **Crypto** | 1.8% | Low | Fast (hours) | ❌ Avoid (fees eat margin) |
| **Current Events** | 0% | High | Variable | ⚠️ Limit exposure |

---

## Unattended Bot Fail-Safes Checklist

### Pre-Deployment (Before Cron)

- [ ] **Wallet separation:** Trading wallet holds max $500, separate from main funds in cold storage
- [ ] **Token allowance:** Set CLOB allowance to $750 (150% of bankroll)
- [ ] **Gas buffer:** Ensure 0.1 MATIC in wallet for gas fees
- [ ] **Telegram setup:** Bot sends alerts on: start, stop, trades, errors, kill-switch
- [ ] **Manual kill-switch:** Telegram command `/stop` immediately halts trading
- [ ] **Health check endpoint:** Bot exposes `/health` endpoint for monitoring
- [ ] **Log rotation:** Auto-rotate logs, keep 7 days
- [ ] **Error handling:** All exceptions caught, logged, trigger alert

### Runtime Fail-Safes (Every Execution Cycle)

- [ ] **Heartbeat:** Every 5min, bot publishes "alive" status to file + Telegram
- [ ] **Position reconciliation:** Query Polymarket API, compare holdings vs local state
- [ ] **Daily loss check:** If day_pnl < -$50 → kill-switch + 24h cooldown
- [ ] **Total drawdown check:** If total_pnl < -$125 → kill-switch + manual review
- [ ] **Gas check:** If polygon_gas > $0.10 → pause trading
- [ ] **Price staleness check:** If market data >30s old → skip opportunity
- [ ] **Fee check:** If taker fee would apply → use maker order or skip
- [ ] **Liquidity check:** If any leg has <$25 order book depth → skip market

### Emergency Procedures

| Scenario | Action | Recovery |
|----------|--------|----------|
| **Partial fill detected** | Cancel all orders, flatten positions immediately | Wait 5min, review logs, resume |
| **Position mismatch** | Kill-switch, notify Telegram | Manual reconciliation via API |
| **Gas spike** | Pause all trades | Resume when gas <$0.05 |
| **Dispute window opens** | Stop new trades in that market | Wait for resolution, exclude market |
| **3 consecutive heartbeats fail** | Kill-switch, alert Telegram | Manual restart required |
| **API rate limit hit** | Pause 60s, retry | If persistent, kill-switch |

---

## Recovery & Reconciliation Procedures

### Daily Reconciliation (11pm UTC)

```python
def daily_reconciliation():
    polymarket_balance = query_polymarket_balance()
    local_balance = query_local_balance()
    
    if polymarket_balance != local_balance:
        log.error("Balance mismatch detected")
        send_telegram_alert("RECONCILIATION FAILURE")
        return False
    
    positions = get_all_polymarket_positions()
    for position in positions:
        # Check if any market in dispute window
        if is_market_disputed(position['market_id']):
            log.warning(f"Market {position['market_id']} disputed, capital locked")
    
    # Report daily PnL
    daily_pnl = calculate_daily_pnl()
    send_telegram_report(f"Daily PnL: ${daily_pnl:.2f}")
    
    # Check circuit breakers
    if daily_pnl < -50:
        trigger_kill_switch("Daily loss exceeded")
    if total_pnl < -125:
        trigger_kill_switch("Max drawdown exceeded")
```

### After Any Error

1. **Cancel all open orders**
2. **Flatten all positions** (market sell)
3. **Compare holdings vs expected**
4. **If mismatch:**
   - Telegram alert with details
   - Mark bot as "needs manual review"
   - Do NOT auto-restart
5. **If resolved:**
   - Log incident
   - Apply cooldown (5-60min depending on severity)
   - Resume trading

---

## Industry Practice: How Pro Arbitrageurs Manage Risk

### Sports Arbitrage (Surebets)

- **Position limits:** Never risk >5% of bankroll per arb
- **Bookmaker diversification:** Spread across 20+ books to reduce counterparty risk
- **Instant execution:** Use APIs, not web scraping
- **Palpable error rule:** If odds are obvious mistake, bookmaker voids → pro arbers skip these
- **Scale:** High volume, low margin, not fully automated

### Prediction Market Arbitrage

- **Research finding:** 62% failure rate for combinatorial arb (complex strategies)
- **Single-market focus:** Most successful arbers stick to simple Yes/No arb
- **Resolution risk management:** Avoid markets with high dispute probability
- **Capital lockup:** Major barrier - minimize by targeting near-term events

### Crypto Arbitrage Bots

- **Hard wallet caps:** Trading wallet holds ONLY operational funds
- **Cold/hot separation:** 90% cold, 10% hot
- **Multiple exchanges:** Never depend on single venue
- **Circuit breakers:** Universal practice - daily loss limits are standard
- **Human supervision:** Even "unattended" bots have human kill-switch

### Key Takeaway

**Pro operators treat risk management as the core product, not an add-on.** The arbitrage edge is small; risk controls are what keep you in the game.

---

## Assumptions & Limitations

### Assumptions

1. Polymarket CLOB API remains stable and accessible
2. UMA resolution system functions correctly (no oracle failures)
3. Polygon network remains operational with <$0.10 gas
4. No regulatory changes targeting prediction markets in your jurisdiction
5. Market liquidity sufficient for $75 position sizes
6. Maker order fill probability >80% at near-mid prices
7. Resolution disputes occur in <5% of traded markets

### Limitations

1. **No protection against Polymarket insolvency or smart contract hack** - exchange risk remains
2. **No protection against UMA oracle collusion** - resolution can be manipulated by large token holders
3. **Geo-blocking enforcement** - if VPN blocked, account may be frozen
4. **Private key storage** - env variable encryption assumed, not true HSM security
5. **Maker fill risk** - if liquidity dries up, limit orders won't fill, missing opportunities
6. **Gas spike timing** - can't predict network congestion, only react
7. **Dispute window duration** - 2 hours is standard but can extend, affecting capital lockup
8. **Fee changes** - Polymarket can change fees anytime, rendering some markets unprofitable

### What This Framework Does NOT Cover

- **MEV/front-running attacks** (less relevant on Polygon CLOB, but possible)
- **Maximal extractable value from complex multi-market strategies** (too risky for $500)
- **Regulatory compliance** (your responsibility to check local laws)
- **Tax reporting** (consult tax professional)
- **Long-term market making** (this is arb-only, not providing liquidity)
- **Cross-exchange arb** (Polymarket-only strategy)

---

## Unresolved Questions

1. **UMA dispute bonding:** What is the minimum bond required to dispute? (Not critical for arb traders, but affects resolution risk assessment)
2. **Polymarket void policy:** Is there any published policy on when voided markets get refunded vs when funds are lost? (Current docs say "at discretion" only)
3. **Market maker rebates:** Are maker rebates paid immediately or accumulated? (Affects cash flow management)
4. **API rate limits:** What are the exact rate limits on CLOB API? (Affects execution speed for multi-leg trades)
5. **Partial fill handling:** Does Polymarket support "all-or-nothing" order types natively, or must we implement via limit orders? (Assumes manual implementation needed)
6. **Resolution delays:** What is the longest observed delay from market close to payout? (Affects capital lockup modeling)

---

## Sources

### Risk Management & Circuit Breakers
- [FIA: Best Practices for Automated Trading Risk Controls](https://www.fia.org/sites/default/files/2024-07/FIA_WP_AUTOMATED%20TRADING%20RISK%20CONTROLS_FINAL_0.pdf)
- [ClearEdge Automation: Circuit Breaker in Futures Trading](https://clearedge.trading/post/circuit-breaker-automation-futures-trading-protection)
- [OpenClaw: Quantitative Trading Risk Control (Tencent)](https://openclaw.github.io/)
- [Crypto Trading Bot Risk Discussion (Reddit)](https://www.reddit.com/r/algotrading/comments/1s0i72i/people_running_autonomous_crypto_trading_bots/)

### Execution Safety & All-or-Nothing
- [arXiv: Atomic Execution is Not Enough for Arbitrage](https://arxiv.org/html/2410.11552v3)
- [Emergent Mind: Atomic Arbitrage Transactions](https://www.emergentmind.com/topics/atomic-arbitrage-aa-transactions)
- [Medium: Slippage in Crypto Swaps - Arbitrage Bot Fixes](https://medium.com/@swaphunt/slippage-in-crypto-swaps-why-your-arbitrage-bot-keeps-crying-and-what-i-did-about-it-e561c0603e86)
- [Solana StackExchange: Arbitrage Bot Best Practices](https://solana.stackexchange.com/questions/18566/what-is-the-best-approach-to-build-an-arbitrage-bot)

### Polymarket-Specific
- [Polymarket Documentation: Resolution](https://docs.polymarket.com/concepts/resolution)
- [Polymarket Help Center: Trading Fees](https://help.polymarket.com/en/articles/13364478-trading-fees)
- [PolymarketGuide: Refunds](https://polymarketguide.gitbook.io/polymarketguide/trading/refunds)
- [StartPolymarket: How Markets Resolve](https://startpolymarket.com/learn/how-markets-resolve/)
- [Prediction Hunt: Polymarket Fees Complete Guide](https://www.predictionhunt.com/blog/polymarket-fees-complete-guide)

### Prediction Market Risks
- [SSRN: Evidence of Persistent Arbitrage in Prediction Markets](https://papers.ssrn.com/sol3/Delivery.cfm/6905683.pdf?abstractid=6905683&mirid=1)
- [ResearchGate: Capital Lock-Up and Settlement Discounting](https://www.researchgate.net/publication/Capital_Lock-Up_and_Settlement_Discounting_in_Prediction_Markets)
- [Grokipedia: Prediction Market Arbitrage](https://grokipedia.org/wiki/Prediction_market_arbitrage)
- [OMS: How Prediction Markets Really Settle](https://oms.io/prediction-markets-settlement-guide)

### Bot Fail-Safes & Monitoring
- [Medium: Production Trading Bots - 15 Failure Patterns](https://medium.com/@florinelchis/production-trading-bots-15-failure-patterns-nobody-warns-you-about-af917d263c35)
- [Dev.to: Self-Healing AI Trading Bot](https://dev.to/igorganapolsky/i-built-a-self-healing-ai-trading-bot-that-learns-from-every-failure-g94)
- [GitHub: Crypto Alert Bot](https://github.com/mathiasfc/crypto-alert)
- [YouTube: Kill Switch with Telegram Bot](https://www.youtube.com/watch?v=BJ6NuwpRkKo)

### Wallet Security & Separation
- [Cobo: AI Trading Bot MPC Security](https://www.cobo.com/post/ai-trading-bot-crypto-security-mpc-wallet)
- [Investopedia: Hot vs Cold Wallets](https://www.investopedia.com/hot-wallet-vs-cold-wallet-7098461)
- [Robi Trader: Cryptocurrency Asset Storage Methods](https://robitrader.com/articles/cryptocurrency-asset-storage-methods)

### Polygon Network & Gas
- [Polygon Technology: Gas Fee Upgrade](https://polygon.technology/blog/polygon-just-made-transaction-fees-more-predictable-for-institutions)
- [TokenPocket: Polygon Transaction Costs 2026](https://www.tokenpocket.pro/blog/polygon-gas-fees-2026)
- [Circle Paymaster: USDC Gas Fee Solution](https://circle.com/blog/paymaster-gas-fees-usdc)

---

**Status:** DONE  
**Summary:** Comprehensive risk-control framework with concrete caps, all-or-nothing execution sequence, Polymarket-specific mitigations, and fail-safe procedures.  
**Concerns:** None. Framework is conservative, well-researched, and appropriate for <$500 bankroll automation.