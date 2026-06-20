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
MODEL = "glm-4.5-flash"
CHAT_ID = "6097430138"
TG_API = "https://api.telegram.org/bot{tok}/sendMessage"
TOPICS = [("llm", "🧠 LLM / Large Models"), ("ai-agent", "🤖 AI Agent"),
          ("crypto", "🪙 Crypto"), ("frontier-tech", "🚀 Frontier Tech")]
PER_TOPIC = 3   # 3 x 4 topics = 12 items
MAX_MSG = 3800  # Telegram cap 4096, leave margin


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
    r = subprocess.run(["python3", str(SKILL / "scripts/run-pipeline.py"), "--output", MERGED],
                       capture_output=True, text=True, timeout=150)
    return Path(MERGED).exists()


def select_items(d):
    items = []
    for key, _label in TOPICS:
        topic = d.get("topics", {}).get(key, {})
        arts = topic.get("articles", []) if isinstance(topic, dict) else []
        for a in sorted(arts, key=lambda a: a.get("quality_score", 0), reverse=True)[:PER_TOPIC]:
            items.append(a)
    return items


def load_persona():
    if SOUL.exists():
        txt = SOUL.read_text()
        # keep Identity + Core Personality + what-NOT-to-do (drop long vibe examples)
        cut = txt.find("## Two Modes")
        return (txt[:cut] if cut > 0 else txt[:1500])
    return "You are Violet-chan, a warm Vietnamese AI companion who calls the user 'anh'."


def llm_block(glm_key, persona, item, attempts=3):
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
            with urllib.request.urlopen(req, timeout=120) as resp:
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
    # summary line (best-effort — may be English) and a warm Violet take.
    title = (item.get("title") or "(no title)")[:120]
    src = item.get("source") or item.get("source_type") or ""
    link = item.get("link", "")
    snippet = " ".join((item.get("snippet") or "").split())  # collapse whitespace
    if len(snippet) > 200:
        snippet = snippet[:200].rstrip() + "…"
    summary = snippet or "(chưa có tóm tắt cho tin này)"
    take = "Tin này Violet chưa kịp đọc kỹ — anh xem qua rồi mình bàn thêm nha~"
    return (f'🔴 "{title}" — {src}\n'
            f'📝 {summary}\n'
            f'💬 {take}\n'
            f'🔗 {link}')


def send_tg(tok, text):
    body = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    req = urllib.request.Request(TG_API.format(tok=tok), data=body)
    with urllib.request.urlopen(req, timeout=120) as resp:
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
    sec = load_secrets()
    glm, tok = sec.get("GLM_API_KEY"), sec.get("TELEGRAM_BOT_TOKEN")
    if not glm or not tok:
        print("ERR: missing GLM_API_KEY/TELEGRAM_BOT_TOKEN", file=sys.stderr)
        sys.exit(0)
    if not run_pipeline():
        print("ERR: pipeline failed", file=sys.stderr)
        sys.exit(0)
    d = json.load(open(MERGED))
    items = select_items(d)
    if not items:
        sys.exit(0)
    persona = load_persona()
    today = datetime.date.today().isoformat()
    header = f"📰 Tech News Digest — {today}\n💜 Violet chọn cho anh {len(items)} tin đáng đọc nhất nè~"

    blocks = [None] * len(items)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        fut_idx = {ex.submit(llm_block, glm, persona, it): i for i, it in enumerate(items)}
        for f in concurrent.futures.as_completed(fut_idx):
            i = fut_idx[f]
            try:
                blocks[i] = f.result()
            except Exception:
                blocks[i] = fallback_block(items[i])
    blocks = [b for b in blocks if b]

    sent = 0
    for msg in build_msgs(header, blocks):
        try:
            if send_tg(tok, msg):
                sent += 1
        except Exception as e:
            print(f"tg send error: {e}", file=sys.stderr)
    print(f"digest: {len(blocks)} items -> {sent} messages sent")


if __name__ == "__main__":
    main()
