# Brainstorm — Polymarket LLM Signal Bot trên Hermes Agent

> Date: 2026-06-26 · Status: design (chờ approve) · Approach: B (calibration loop)

## 1. Problem & constraints

- Mục tiêu: trading bot Polymarket dùng Hermes Agent. **Educational, vốn nhỏ (<$100).**
- Quyết định đã chốt (từ discovery):
  - **Approach B** — calibration-driven signal system (LLM predict + tracking loop).
  - **Execution**: signal-only (alert qua Telegram), KHÔNG auto-execute, KHÔNG key trade trên server.
  - **Markets**: Crypto + Politics.
  - **Sources**: LLM + web search + crowd aggregates + data chuyên dụng (polling / on-chain / stats).
- Tài sản sẵn có: `skills/research/polymarket/` (read-only), Hermes deployed native trên Contabo (`withly-server`), gateway Telegram.

## 2. Brutal-honesty findings (research)

- **LLM naive ≈ không có edge.** Foresight-32B: base LLM *"slightly worse than ignorance"*; cần RL fine-tune mới lấp ~65% gap. ([LightningRod](https://blog.lightningrod.ai/p/foresight-32b-beats-frontier-llms-on-live-polymarket-predictions))
- **Accuracy ≠ profit.** Phải thắng market price + fee + spread. ([OpenReview — Beyond Accuracy](https://openreview.net/pdf?id=TSA5kRUKZv))
- Cạnh tranh cao: đã có multi-agent framework ([PolySwarm](https://arxiv.org/html/2604.03888v1)) + Polymarket self-hosted LLM meta-markets.
- **Arb deterministic** (sum≠100%, cross-platform) có edge thật nhưng mỏng, bị HFT ăn nhanh — không chọn làm core. ([arXiv arb paper](https://arxiv.org/html/2508.03474v1))
- **Kết luận:** build "LLM đoán → cược" = mất tiền. Build "LLM đoán → **đo lường calibration** → chỉ alert khi có evidence" = instrument học có giá trị. Scope signal-only + vốn nhỏ → sandbox an toàn.

## 3. Recommended architecture (Approach B)

```
Hermes cron (scan 1-2x/ngày)
   │
   ▼
[Data layer]  Gamma API → discover Crypto+Politics markets (filter liquidity/volume)
              CLOB API  → current price + history
   │
   ▼
[Signal layer] LLM (Hermes agent + web search) → P(event) + confidence + rationale
               + Crowd: Manifold / Metaculus aggregates → ensemble P
               + Data: polling (politics) / CoinGecko+on-chain (crypto)
   │
   ▼
[Tracking store] SQLite ~/.hermes/polymarket_signals.db
                 log mọi prediction: predicted_p, market_p, sources, category, confidence
   │
   ▼
[Scoring/gating] |edge| = predicted_p − market_p  (sau fee+spread)
                 chỉ alert khi |edge|>threshold AND category historically calibrated
                 resolution feed → Brier score + calibration curve → update gating
   │
   ▼
[Alert] Hermes gateway → Telegram (market, price, P, edge, confidence, calibration note)
```

Khớp triết lý Hermes (AGENTS.md): skill+scripts+cron+gateway = "capability at the edges", không đụng core. Tracking loop = đúng tinh thần "self-improving".

## 4. Components & files

Mới (skill mới, kế bên skill polymarket read-only hiện có):
- `skills/research/polymarket-signals/SKILL.md` — procedure cho agent.
- `scripts/markets_client.py` — discover + filter markets (Gamma). Reuse endpoint ref của skill cũ.
- `scripts/prices_client.py` — giá + history (CLOB, conditionId/clobTokenIds).
- `scripts/crowd_client.py` — Manifold/Metaculus aggregates.
- `scripts/data_client.py` — polling (politics) / CoinGecko (crypto).
- `scripts/predict.py` — orchestrate context → LLM → P + confidence (output JSON).
- `scripts/store.py` — SQLite schema + CRUD.
- `scripts/score.py` — Brier, calibration curve, edge gating, paper-trade PnL.
- `scripts/resolve_check.py` — cron: fetch resolved → fill outcome → recompute calibration.
- `references/api-endpoints.md` + `references/calibration.md`.

Reuse: `skills/research/polymarket/` (base endpoints). Config keys: `~/.hermes/hermes.env` (Manifold/CoinGecko keys — optional,大多 free). Cron job qua Hermes cron scheduler.

## 5. Phasing (YAGNI — build từng bước)

| Phase | Nội dung | Done khi |
|---|---|---|
| **0. Data + store skeleton** | markets/prices/resolve clients + SQLite + log. Chưa LLM. | Pipeline chạy, log được markets crypto+politics |
| **1. LLM predictor MVP** | predict.py (LLM+web) → log → alert khi lệch (flag "uncalibrated, paper trade") | Bắt đầu tích lũy prediction history |
| **2. Crowd aggregates** | Manifold/Metaculus ensemble → P tốt hơn | Calibration cải thiện rõ |
| **3. Data chuyên dụng + calibrated gating** | polling/on-chain + **chỉ alert khi calibrated** (cần đủ resolved history) | Alert có evidence calibration |
| **4. Evaluation** | calibration report → quyết có edge thật không | Go/no-go cho mọi automation (out-of-scope) |

Lưu ý: calibration cần **tuần** dữ liệu resolved. Set expectation rõ.

## 6. Calibration model

- **Brier score** = mean((predicted_p − outcome)²). Baseline always-0.5.
- **Calibration curve**: bucket predicted P theo decile, plot mean(predicted) vs empirical frequency. Lý tưởng = đường chéo.
- **Gating**: alert category C chỉ khi (trên N resolved gần nhất) |mean(pred)−mean(outcome)| trong bucket < tol AND realized edge > 0.
- **Paper-trade PnL**: mô phỏng bet fixed-fraction @ market price → track vs resolution → metric chính để biết có edge.

## 7. Risks & mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Tin signal có edge khi không có | Cao | Builtin: tracking + gating + paper-trade. Không skip. |
| Calibration cần thời gian | Trung bình | Phasing; phase 1-2 alert "uncalibrated". Set expectation. |
| LLM/scan cost | Trung bình | Bound market universe (filter liquidity/volume); cache prompt prefix (AGENTS.md: prompt cache sacred). |
| Data chuyên dụng khó/lỗi | Trung bình | Phase 3 cuối; fallback crowd aggregates. Polling free API hạn chế → honest note. |
| Geo-restrict (manual trade) | Thấp (signal-only) | Data read global OK. Manual trade = trách nhiệm user; tự verify VN không bị block. |
| Over-engineering | Trung bình | YAGNI: phase 0-1 trước, không build phase 3 sớm. |

## 8. Success metrics

- Số prediction tracked + % resolved.
- Brier score giảm theo thời gian (per category).
- Calibration curve tiệm đường chéo.
- Paper-trade PnL (dương sau fee+spread = edge thật).
- Signal quality: precision của alert (bao nhiêu alert đúng hướng).

## 9. Out of scope

- Auto-execute / đặt lệnh / key trade trên server (user chọn signal-only).
- Fine-tune model riêng (Foresight-style) — phức tạp, ngoài educational scope.
- Real-money automation — chỉ sau khi phase 4 chứng minh edge.

## 10. Open questions

- Polling data free API tốt nhất cho politics? (Manifold/Metaculus có thể đủ thay polling chuyên dụng.)
- Frequency scan phù hợp? (đề xuất 1-2x/ngày, bind theo cost.)
- Telegram gateway đã config trên `withly-server` chưa? (cần xác nhận để wire alert.)
- Có muốn paper-trade dashboard/report định kỳ qua Telegram không?
