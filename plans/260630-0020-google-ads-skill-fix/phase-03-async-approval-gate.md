# Phase 03 — Async Headless Approval Gate (CLI-first)

> **DECISION (user-confirmed 2026-06-30):** Approval gate = **CLI-first** (`--approve <uuid> --indices 1,3`, works via cron/SSH/Telegram text reply). **Telegram inline-button flow DEFERRED to Phase 09** (polish). Do NOT build Telegram callback handler or inline keyboard in this phase. Telegram is **notify-only** (plain text message).

## Context Links
- Plan: [`plan.md`](plan.md)
- Finding: M6 (`creator.present_for_approval` uses `input()` → stalls headless Hermes agent)
- Resolves: Q1 (skill runs headless via cron + Telegram)

## Overview
- **Priority**: P1 (design decision — without this the skill cannot run in Hermes)
- **Status**: pending
- **Effort**: 2h
- Replace blocking `input()` with an async approval workflow: generate ad copy → persist to a pending file → send a **plain-text Telegram notification** (with the approve command) → **resume via CLI `--approve`**.

## Key Insights
- Hermes skills run headless (cron, no TTY). `input()` hangs forever → cron job stuck, no deploy.
- **Mechanism = CLI `--approve <uuid> --indices 1,3,5`** — guaranteed to work from cron/SSH/Telegram text reply. This is the load-bearing approve path.
- Telegram = **notify-only** in this phase: a text message tells the human a plan awaits approval + the exact command to run. No inline buttons, no callback handler (those are Phase 09 polish).
- Two-step workflow: (a) `creator.py` generates + policy-screens copy, writes `data/pending-approvals/<uuid>.json`, sends a Telegram **text** notification, exits 0. (b) Human runs `creator.py --approve <uuid> --indices 1,3,5` (or `--reject <uuid>`) → reads pending file → on approve → Phase 02 deploy.

## Requirements
### Functional
- `creator.py` must NOT call `input()`. Must write pending approval to disk + send Telegram **text** notification + exit 0 (not blocked).
- `creator.py --approve <uuid> --indices <csv>` reads the pending file, validates indices, deploys approved variations via Phase 02 path.
- `creator.py --reject <uuid>` marks the pending file rejected.
- Pending approval record persists: niche, variations, selected_indices, plan_path, expiry (24h), status (`pending`/`approved`/`deployed`/`rejected`/`expired`).
### Non-functional
- Idempotent: re-running creator on same plan reuses pending file if unexpired.
- Telegram notify text ≤4096 chars (chunk if many variations); must include the literal approve command for copy-paste.

## Architecture
```
creator.py --plan X.json (headless, no input())
  → generate + policy screen
  → write data/pending-approvals/<uuid>.json (status=pending)
  → telegram_notify.send_text("Ad copy ready for <niche>.\nApprove: creator.py --approve <uuid> --indices 1,3,5\nReject: creator.py --reject <uuid>")
  → exit 0  (prints uuid + command to stdout too)

creator.py --approve <uuid> --indices 1,3,5
  → read pending file; reject if expired/already-actioned
  → deploy.deploy_full_campaign(client, customer_id, plan, selected_variations)  [Phase 02]
  → mark status=deployed (or failed) in pending file
  → telegram_notify.send_text("Deployed <campaign> ✓" / "Deploy failed: <err>")
```

## Interfaces
**Consumes:**
- `deploy.deploy_full_campaign(client, customer_id, plan, variations)` (Phase 02)
- env: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

**Produces:**
- `approval_gate.write_pending(plan_path, variations, niche) -> str` (returns uuid)
- `approval_gate.read_pending(uuid) -> dict | None`
- `approval_gate.mark_status(uuid, status, selected_indices) -> bool`
- `telegram_notify.send_text(text) -> bool`  (plain text only; no inline keyboard this phase)

## Related Code Files
- **Modify**: `scripts/creator.py` (remove `present_for_approval` input loop; add `--approve`/`--reject` subcommands; call approval_gate)
- **Create**: `scripts/approval_gate.py` (pending-file CRUD + expiry sweep)
- **Create**: `scripts/telegram_notify.py` (`send_text` only — no inline buttons/callbacks)
- **Read-only**: `scripts/deploy.py`, `scripts/policy_check.py`

## Implementation Steps
1. `telegram_notify.py`: `send_text(text)` using `requests` (stdlib-first; already a dep). Chunk to ≤4096 chars. **No inline keyboard, no callback handling in this phase.**
2. `approval_gate.py`: pending dir = `data/pending-approvals/`. Schema: `{uuid, plan_path, niche, variations, selected_indices, status, created_at, expires_at}`. Functions per Interfaces. Atomic write (tmp+rename).
3. `creator.py`: replace `present_for_approval` → write pending + send Telegram text + `sys.exit(0)` with stdout message "Awaiting approval — run: creator.py --approve <uuid> --indices ...".
4. Add resume subcommands: `creator.py --approve <uuid> --indices 1,3,5` (validate indices exist + pending + not expired → deploy) and `creator.py --reject <uuid>`.
5. Expiry sweep: pending files >24h marked `expired`; `--approve` on expired → error, no deploy.

## Todo List
- [ ] Create telegram_notify.py (`send_text` only)
- [ ] Create approval_gate.py (pending-file CRUD + expiry)
- [ ] Remove input() from creator.py, wire async notify flow
- [ ] Add `--approve <uuid> --indices` + `--reject <uuid>` subcommands
- [ ] End-to-end test: creator writes pending + notifies Telegram text; approve via CLI → real deploy (Phase 02)

## Success Criteria
- `creator.py --plan X.json` exits 0 within seconds (no input() stall); prints uuid + approve command.
- Telegram receives a **plain-text** notification containing the approve command (no inline buttons).
- `creator.py --approve <uuid> --indices 1,3,5` triggers real deploy via Phase 02; pending file → `deployed`.
- `creator.py --reject <uuid>` marks `rejected`, no deploy.
- Expired (>24h) pending approvals: `--approve` errors, deploy does not fire.

## Risk Assessment
- **Low** — CLI path needs no gateway-side wiring (unlike inline callbacks), works from cron/SSH/Telegram text reply. This is why CLI-first was chosen.
- **Low** — pending file corruption. **Mitigation**: atomic write (tmp+rename).

## Security Considerations
- `--approve` runs unattended once invoked — ensure it only acts on a valid, non-expired pending uuid (no guessing useful uuids: use secrets.token_hex).
- Pending files contain ad copy (not secrets) — `data/` stays gitignored.

## Next Steps
- Depends on Phase 02 (deploy). Telegram **inline-button** flow (callback handler, gateway route) added in **Phase 09** as UX polish on top of this CLI gate.
