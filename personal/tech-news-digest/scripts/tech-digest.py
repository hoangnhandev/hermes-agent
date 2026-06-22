#!/usr/bin/env python3
"""Tech News Digest — Violet-chan flavored (cron --no-agent mode).
Pipeline -> 12 items -> per-item GLM call (Violet persona from SOUL.md)
-> auto-chunk -> direct Telegram send (multi-message)."""
import json, subprocess, os, sys, urllib.request, urllib.parse
import concurrent.futures, datetime, time
from pathlib import Path

ENV_FILE = Path("/opt/data/hermes.env")     # ~/.hermes/hermes.env (host) in container
SOUL = Path("/opt/data/SOUL.md")            # ~/.hermes/SOUL.md
SKILL = Path("/opt/data/skills/tech-news-digest")
MERGED = "/tmp/td-merged.json"
GLM_URL = "https://api.z.ai/api/coding/paas/v4/chat/completions"
MODEL = "glm-5.2"
CHAT_ID = "6097430138"
TG_API = "https://api.telegram.org/bot{tok}/sendMessage"
TOPICS = [("llm", "🧠 LLM / Large Models"), ("ai-agent", "🤖 AI Agent"),
          ("crypto", "🪙 Crypto"), ("frontier-tech", "🚀 Frontier Tech")]
PER_TOPIC = 3   # 3 x 4 topics = 12 items
MAX_MSG = 3800  # Telegram cap 4096, leave margin
# Cross-run dedup: remember links already sent so the same GitHub-trending / RSS
# article (which stays in the pipeline's 48h window and re-scores high) doesn't
# reappear in every digest of the day. TTL matches the pipeline window.
SENT_CACHE = Path("/opt/data/scripts/tech-digest-sent.json")
SENT_TTL_S = 48 * 3600


def load_secrets():
    d = dict(GLM_API_KEY=os.environ.get("GLM_API_KEY"),
             TELEGRAM_BOT_TOKEN=os.environ.get("TELEGRAM_BOT_TOKEN"))
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            s = line.strip()
            if s and not s.startswith("#") and "=" in s:
                k, v = s.split("=", 1)
                d.setdefault(k.strip(), v.strip())
    return d


def run_pipeline():
    # Twitter backend is flaky (always 0 items) yet burns ~105s on its own timeout —
    # that alone ate the entire 120s cron budget and caused the job to be killed.
    # Skip it, and cap each source step so no single source can stall past the budget.
    # subprocess timeout (80s) sits well under the 120s cron hard limit.
    r = subprocess.run(["python3", str(SKILL / "scripts/run-pipeline.py"),
                        "--output", MERGED,
                        "--skip", "twitter",
                        "--step-timeout", "45"],
                       capture_output=True, text=True, timeout=80)
    return Path(MERGED).exists()


def select_items(d, sent=None, now_ts=0.0):
    """Pick top PER_TOPIC articles per topic, skipping links already sent recently.
    sent = {link: sent_epoch}. If filtering leaves too few fresh items in a topic,
    fall back to the full pool so the topic (and the digest) is never empty."""
    sent = sent or {}
    items = []
    for key, _label in TOPICS:
        topic = d.get("topics", {}).get(key, {})
        arts = topic.get("articles", []) if isinstance(topic, dict) else []
        fresh = [a for a in arts if not _recently_sent(a.get("link", ""), sent, now_ts)]
        pool = fresh if len(fresh) >= PER_TOPIC else arts
        for a in sorted(pool, key=lambda a: a.get("quality_score", 0), reverse=True)[:PER_TOPIC]:
            items.append(a)
    return items


def _recently_sent(link, sent, now_ts):
    if not link:
        return False
    ts = sent.get(link)
    return bool(ts and now_ts and (now_ts - ts) < SENT_TTL_S)


def load_sent():
    if not SENT_CACHE.exists():
        return {}
    try:
        return {k: float(v) for k, v in json.load(open(SENT_CACHE)).items()}
    except Exception:
        return {}


def save_sent(links, sent, now_ts):
    # record new links + prune entries older than 2×TTL to bound the cache size
    cutoff = now_ts - SENT_TTL_S * 2
    kept = {k: v for k, v in sent.items() if v > cutoff}
    for l in links:
        if l:
            kept[l] = now_ts
    try:
        SENT_CACHE.write_text(json.dumps(kept))
    except Exception as e:
        print(f"sent-cache write error: {e}", file=sys.stderr)


def load_persona():
    if SOUL.exists():
        txt = SOUL.read_text()
        # keep Identity + Core Personality + what-NOT-to-do (drop long vibe examples)
        cut = txt.find("## Two Modes")
        return (txt[:cut] if cut > 0 else txt[:1500])
    return "You are Violet-chan, a warm Vietnamese AI companion who calls the user 'anh'."


def llm_block(glm_key, persona, item, attempts=2):
    sys_p = persona + "\n\nYou write concise, warm Vietnamese. Keep tech titles and proper nouns in English."
    user_p = (
        "Write EXACTLY 4 lines for this tech news item, nothing else. Rules:\n"
        "- Line 1 starts with 🔴: keep the original title VERBATIM (do NOT translate), then ' — ' and the source\n"
        "- Line 2 starts with 📝: Vietnamese summary, 2-3 sentences (the gist)\n"
        "- Line 3 starts with 💬: Violet's personal take, Vietnamese, 1-2 sentences, address 'anh', warm tone, why it matters\n"
        "- Line 4 starts with 🔗: the link as-is\n\n"
        "Format:\n"
        "🔴 \"<original title verbatim>\" — <source>\n"
        "📝 <Vietnamese summary>\n"
        "💬 <Violet's take>\n"
        "🔗 <link>\n\n"
        "Item:\n"
        f"title: {item.get('title', '')}\n"
        f"source: {item.get('source') or item.get('source_type') or ''}\n"
        f"snippet: {item.get('snippet', '')}\n"
        f"link: {item.get('link', '')}"
    )
    body = json.dumps({"model": MODEL, "max_tokens": 800, "temperature": 0.7,
                       "messages": [{"role": "system", "content": sys_p},
                                    {"role": "user", "content": user_p}]}).encode()
    # GLM can be flaky (timeouts / 429 / 5xx / empty body). Retry with backoff
    # before falling back, so transient errors don't drop the 📝/💬 lines.
    last_err = None
    for n in range(attempts):
        try:
            req = urllib.request.Request(GLM_URL, data=body,
                                         headers={"Authorization": f"Bearer {glm_key}",
                                                  "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)
            content = (data["choices"][0]["message"].get("content") or "").strip()
            if content:
                return content
            last_err = RuntimeError("empty GLM response")
        except Exception as e:
            last_err = e
        if n < attempts - 1:
            time.sleep(2 * (n + 1))   # backoff: 2s, then 4s
    raise last_err


def fallback_block(item):
    # Always emit a FULL 4-line block so the digest format stays consistent
    # even when GLM failed for this item. Use the pipeline snippet for the
    # summary line (best-effort — may be English). When there's no snippet
    # (common for RSS items that the pipeline didn't enrich), fall back to a
    # warm honest line instead of the unhelpful "(chưa có tóm tắt)" placeholder.
    title = (item.get("title") or "(no title)")[:120]
    src = item.get("source") or item.get("source_type") or ""
    link = item.get("link", "")
    snippet = " ".join((item.get("snippet") or "").split())  # collapse whitespace
    if len(snippet) > 200:
        snippet = snippet[:200].rstrip() + "…"
    if snippet:
        summary = snippet
    else:
        summary = f"Violet chưa nắm đủ nội dung tin này, chỉ thấy tiêu đề \"{title}\" — anh mở link xem chi tiết nha."
    take = "Tin này Violet chưa kịp đọc kỹ — anh xem qua rồi mình bàn thêm nha~"
    return (f'🔴 "{title}" — {src}\n'
            f'📝 {summary}\n'
            f'💬 {take}\n'
            f'🔗 {link}')

def send_tg(tok, text):
    body = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    req = urllib.request.Request(TG_API.format(tok=tok), data=body)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp).get("ok") is True


def build_msgs(header, blocks):
    msgs, cur = [], header + "\n\n"
    for b in blocks:
        cand = cur + b + "\n\n"
        if len(cand) > MAX_MSG and cur.strip() != header.strip():
            msgs.append(cur.rstrip())
            cur = b + "\n\n"
        else:
            cur = cand
    if cur.strip():
        msgs.append(cur.rstrip())
    return msgs


def main():
    t_start = time.monotonic()
    sec = load_secrets()
    glm, tok = sec.get("GLM_API_KEY"), sec.get("TELEGRAM_BOT_TOKEN")
    if not glm or not tok:
        print("ERR: missing GLM_API_KEY/TELEGRAM_BOT_TOKEN", file=sys.stderr)
        sys.exit(0)
    if not run_pipeline():
        print("ERR: pipeline failed", file=sys.stderr)
        sys.exit(0)
    d = json.load(open(MERGED))
    now_ts = time.time()
    sent_cache = load_sent()
    items = select_items(d, sent_cache, now_ts)
    if not items:
        sys.exit(0)
    persona = load_persona()
    today = datetime.date.today().isoformat()
    header = f"📰 Tech News Digest — {today}\n💜 Violet chọn cho anh {len(items)} tin đáng đọc nhất nè~"

    # GLM budget = whatever is left of the 120s cron window after the pipeline,
    # reserving ~15s for Telegram send + slack. GLM latency is bursty (2-30s/call)
    # and the endpoint 429s at 3+ concurrent calls, so we run 2 workers under a
    # hard deadline: complete as many real summaries as fit, fall back for the
    # rest. This guarantees we ALWAYS finish under 120s and deliver a digest.
    glm_budget = max(20, 105 - int(time.monotonic() - t_start))
    n_fallback = 0
    blocks = [None] * len(items)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        fut_idx = {ex.submit(llm_block, glm, persona, it): i for i, it in enumerate(items)}
        try:
            for f in concurrent.futures.as_completed(fut_idx, timeout=glm_budget):
                i = fut_idx[f]
                try:
                    blocks[i] = f.result()
                except Exception as e:
                    n_fallback += 1
                    print(f"glm fallback [{i}]: {type(e).__name__}: {str(e)[:120]}", file=sys.stderr)
                    blocks[i] = fallback_block(items[i])
        except concurrent.futures.TimeoutError:
            print(f"glm deadline hit after {glm_budget}s; falling back remaining items", file=sys.stderr)
        # cancel not-yet-started futures; fall back any item not completed in time
        for f in fut_idx:
            f.cancel()
        for i in range(len(items)):
            if blocks[i] is None:
                n_fallback += 1
                blocks[i] = fallback_block(items[i])
    # pair each surviving block with its source link for the sent-cache
    chosen = [(blocks[i], items[i].get("link", "")) for i in range(len(items)) if blocks[i]]
    blocks = [b for b, _ in chosen]
    chosen_links = [ln for _, ln in chosen]

    sent = 0
    for msg in build_msgs(header, blocks):
        try:
            if send_tg(tok, msg):
                sent += 1
        except Exception as e:
            print(f"tg send error: {e}", file=sys.stderr)
    # only remember links we actually delivered (at least one TG message went out)
    if sent > 0:
        save_sent(chosen_links, sent_cache, now_ts)
    # Summary to STDERR, not stdout. Hermes' no_agent path delivers any non-empty
    # stdout as an extra "Cronjob Response" Telegram message (cron/scheduler.py);
    # since this script already sends the digest itself via send_tg, a stdout
    # summary would arrive as a redundant follow-up message. Empty stdout =
    # silent run (no extra delivery). stderr is still captured on failure.
    print(f"digest: {len(blocks)} items -> {sent} messages sent (glm fallbacks: {n_fallback})",
          file=sys.stderr)


if __name__ == "__main__":
    main()
