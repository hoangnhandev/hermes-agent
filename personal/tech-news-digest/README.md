# tech-news-digest — Violet-chan setup (backup)

Custom deployment of the [tech-news-digest](https://github.com/draco-agent/tech-news-digest) skill on a Hermes Agent instance, producing a daily Vietnamese tech-news digest (Violet-chan persona) delivered to Telegram.

This folder backs up the **custom parts** (wrapper, config, patches, deploy guide) so the setup is reproducible on a fresh Hermes instance. The upstream skill itself is reinstalled from clawhub/GitHub (see `setup.md`).

## Contents

```
personal/tech-news-digest/
├── README.md                       # this file
├── setup.md                        # step-by-step redeploy guide
├── scripts/tech-digest.py          # cron wrapper (pipeline + GLM + Telegram)
├── config/hermes.env.example       # env template (NO real secrets)
├── config/config-additions.yaml    # ~/.hermes/config.yaml additions
└── docs/skill-env-rename.md        # TND_* rename patches (bypass Hermes blocklist)
```

## TL;DR

- **Skill**: `tech-news-digest` @dinosaur (clawhub) = github `draco-agent/tech-news-digest`
- **Cron**: `0 8,21 * * *` (8 AM + 9 PM, container TZ) → Telegram
- **Mode**: `--no-agent` script (reliable — no LLM-agent variance)
- **Format**: 12 items (3/topic), each 🔴 title · 📝 summary · 💬 Violet take · 🔗 link, auto-chunked into 2-3 messages

See [`setup.md`](./setup.md) for full redeploy steps.
