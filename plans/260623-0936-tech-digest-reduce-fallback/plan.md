# Plan: Giảm fallback "Violet chưa kịp đọc kỹ" trong tech-digest

## Context
- **Symptom:** digest hay có nhiều item với dòng tĩnh `💬 Tin này Violet chưa kịp đọc kỹ...`
- **Root cause (đo được):** `fallback_block()` kích hoạt khi `llm_block()` raise.
  Nguyên nhân 100% = **GLM HTTP 429 (rate limit RPM)**, không phải deadline, không phải format sai.
- **Dòng tĩnh đó đến từ:** `tech-digest.py:166` `take = "Tin này Violet chưa kịp đọc..."` trong `fallback_block()`.

## Research findings (đo trực tiếp trên VPS, 12 items)
| Cấu hình | OK/12 | 429 | elapsed | budget 98s |
|---|---|---|---|---|
| Hiện tại (workers=2) | 9 | 3 | 96s | FITS |
| Approach B (workers=1) | 9 | **3** | 106s | **OVER 8s** |

**B thuần phản tác dụng:** 429 là giới hạn RPM quota, không do concurrent → giảm workers không giúp. Worse: 1-worker chậm hơn 10s → OVER budget → thêm deadline-fallback (cùng dòng tĩnh).

## Selected approach: B+ (workers=2 giữ nguyên + backoff dài để quota reset)
B thuần thất bại vì nó giảm concurrent nhưng **không** giải quyết quota bão hòa.
Fix đúng: giữ 2 workers (tránh deadline) + tăng retry/backoff để mỗi 429 có thời gian
chờ quota reset trước khi retry.

## Changes (single file: `personal/tech-news-digest/scripts/tech-digest.py`)

### Change 1 — Tăng retry + backoff dài (hàm `llm_block`)
**Hiện tại (line 132-146):**
```python
def llm_block(glm_key, persona, item, attempts=2):
    ...
    for n in range(attempts):
        try: ...
        except Exception as e: last_err = e
        if n < attempts - 1:
            time.sleep(2 * (n + 1))   # backoff: 2s, then 4s
    raise last_err
```
**Thành:**
```python
def llm_block(glm_key, persona, item, attempts=4):
    ...
    for n in range(attempts):
        try: ...
        except Exception as e:
            last_err = e
            is_429 = "429" in str(e)
        if n < attempts - 1:
            time.sleep((10 if is_429 else 2) * (n + 1))  # 429: 10/20/30s, khác: 2/4/6s
    raise last_err
```
- `attempts=2 → 4`: 429 transient có cơ hội retry sau khi quota reset.
- Backoff 429 riêng (10s × n) vì RPM quota cần ~10-30s reset; backoff cũ 2s/4s quá ngắn.

### Change 2 — Nâng `glm_budget` (line 218) hấp thụ retry dài
**Hiện tại:** `glm_budget = max(20, 105 - int(time.monotonic() - t_start))`
**Thành:** `glm_budget = max(40, 220 - int(time.monotonic() - t_start))`
- Retry dài cần nhiều thời gian; budget cũ ~98s sẽ cause deadline-fallback.
- Cron timeout đã raise 600s (commit be61a80a6) nên budget 220s an toàn (dư ~380s cho pipeline + TG).

### Change 3 — (đã có từ fix trước) select_items filter + format validate
Không động; đã commit (ebd180ffc).

## Risk assessment
| Rủi ro | Khả năng | Mitigation |
|---|---|---|
| Retry dài → tràn budget | Trung | Change 2 nâng budget lên 220s |
| Quota reset >30s → retry vẫn 429 | Thấp | attempts=4 × backoff tối đa 30s = đủ cover đa số transient |
| Cron timeout 600s | Thấp | 220s GLM + ~7s pipeline + ~30s TG tail << 600s |
| **KHÔNG giảm 429** nếu quota nghiêm cố định | Có thể | Sau deploy, đo lại; nếu vẫn 25% → chuyển sang model rẻ hơn (glm-4.5-flash) |

## Validation method (post-deploy, KHÔNG gửi TG spam)
1. Probe script (như research): mock send_tg, chạy `llm_block` 12 items, đếm 429/ok.
2. Mục tiêu: 429 fallback < 2/12 (từ 3/12 → <2).
3. Verify elapsed < glm_budget mới (220s).

## Implementation order
1. Edit Change 1 (retry/backoff) trong `tech-digest.py`
2. Edit Change 2 (budget) trong `tech-digest.py`
3. `python3 -m py_compile` check
4. Delegate tester → probe trên VPS (no TG), đo fallback rate
5. Code-review (dual-verdict)
6. Simplify
7. Finalize: commit + push + sync VPS

## Unresolved questions
- Quota GLM Coding Plan: RPM chính xác bao nhiêu? (Không public; đo empirically)
- Nếu retry dài vẫn không giảm 429: fallback sang Change model glm-4.5-flash? (quyết định sau đo post-deploy)
