# Phase 04 — Real Research (Web Search + LLM)

## Context Links
- Plan: [`plan.md`](plan.md)
- Finding: C3 (`research.py:9-34` 100% mock; SKILL.md claims "web search + LLM")
- Parent: [`../260629-1125-hermes-ads-copilot/phase-01-skill-research.md`](../../260629-1125-hermes-ads-copilot/phase-01-skill-creator.md)

## Overview
- **Priority**: P1 (skill is marketed as real research; currently lies)
- **Status**: pending
- **Effort**: 5h
- Replace hardcoded keywords/competitors with real data: web search for keyword expansion + competitor discovery, LLM for analysis/structuring.

## Key Insights
- Current `research_keywords`, `analyze_competitors`, `determine_audience` all return literal Python dicts — zero external calls.
- SKILL.md frontmatter `description: "...via web search + LLM"` is false advertising. Either implement it or rename (YAGNI: implement, it's the skill's purpose).
- **Web search options**: Hermes agent-browser skill (CDP docker, already available) OR HTTP API (Serper/SerpAPI) OR direct Google search scrape. **Recommend**: HTTP API (Serper has free tier, reliable JSON) for keyword/competitor discovery; fallback to agent-browser if no API key. Stdlib-first: use `urllib`/`requests`.
- **LLM**: Hermes runtime exposes LLM (z.ai GLM per memory). Use it for intent classification, gap analysis, copy angle generation.

## Requirements
### Functional
- `research_keywords` returns keywords derived from real search data (not f-strings of the niche).
- `analyze_competitors` returns competitors found via search (real names/URLs), not `f"Leading {niche.title()} Co"`.
- LLM classifies intent, estimates competition, suggests match types.
- Graceful degradation: if no search API key, fail loudly (no silent mock) OR documented `--mock` flag.
### Non-functional
- `research.py` stays <200 lines → split web/LLM into `_research_web.py`, `_research_llm.py`.
- Cache search results per niche+location (avoid re-querying; store in `data/research-cache/`).

## Architecture
```
research.py (orchestrator, <200 lines)
  → _research_web.fetch_keywords(niche, location)   [Serper/agent-browser]
  → _research_web.fetch_competitors(niche, location)
  → _research_llm.classify_intent(keywords)         [Hermes LLM]
  → _research_llm.analyze_competitors(competitors)
  → _research_llm.suggest_audience(niche, location, goal)
  → calculate_budget (unchanged, real math)
  → save + summary
```

## Interfaces
**Consumes:**
- env: `SERPER_API_KEY` (optional), Hermes LLM endpoint
- `requests` (already a dep)

**Produces:**
- `_research_web.fetch_keywords(niche, location) -> list[dict]`
- `_research_web.fetch_competitors(niche, location) -> list[dict]`
- `_research_llm.classify_intent(keywords: list[str]) -> dict[str,str]`
- `_research_llm.analyze_competitors(competitors: list[dict]) -> list[dict]`
- Output schema unchanged (consumed by creator.py): `{niche, location, monthly_budget, keywords[], competitors[], audience, budget_plan}`

## Related Code Files
- **Modify**: `scripts/research.py` (become orchestrator)
- **Create**: `scripts/_research_web.py`
- **Create**: `scripts/_research_llm.py`
- **Read-only**: SKILL.md (Phase 09 updates)

## Implementation Steps
1. `_research_web.py`: implement Serper client (`fetch_keywords` via autocomplete/search, `fetch_competitors` via organic results). No-key → raise `RuntimeError("SERPER_API_KEY missing")` (no mock).
2. `_research_llm.py`: Hermes LLM calls via existing gateway/SDK. Prompts for intent classification + competitor gap analysis. Structured JSON output.
3. `research.py`: orchestrate; keep CLI args identical (`--niche --location --budget --goal`); preserve output schema.
4. Add `data/research-cache/<hash>.json` (24h TTL) keyed by niche+location.
5. Update `google-ads.env.example` to add `SERPER_API_KEY`.

## Todo List
- [ ] Implement _research_web.py (Serper)
- [ ] Implement _research_llm.py (Hermes LLM)
- [ ] Refactor research.py to orchestrator
- [ ] Add research cache
- [ ] Update env example
- [ ] Test real run, verify non-mock output

## Success Criteria
- `research.py --niche "plumber" --location "Austin TX"` returns keywords/competitors NOT containing literal `"plumber"`/`"Leading Plumber Co"` placeholders.
- Output validated by human spot-check against actual search results.
- Each file <200 lines.

## Risk Assessment
- **Medium** — Serper free-tier quota. **Mitigation**: cache aggressively; document quota; agent-browser fallback path noted (not built unless needed — YAGNI).
- **Medium** — LLM output format drift. **Mitigation**: strict JSON schema + retry on parse fail.

## Security Considerations
- `SERPER_API_KEY` in env file, gitignored.
- No PII in research queries.

## Next Steps
- Independent of 02/03 — can run in parallel. Phase 09 updates SKILL.md claims to match reality.
