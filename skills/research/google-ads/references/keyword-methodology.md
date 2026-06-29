# Google Ads Keyword Research Methodology

## Overview

This document outlines the methodology for Google Ads keyword research used in the google-ads-research skill. The approach combines web search data with LLM reasoning to provide comprehensive keyword analysis.

## Seed Keyword Generation Framework

### Core Seed Keyword Types

1. **Service/Category Keywords**
   - Primary service terms (e.g., "plumbing", "dentist", "roofing")
   - Category modifiers (e.g., "services", "company", "contractor")

2. **Location Modifiers**
   - Geographic terms (city, state, neighborhood)
   - Proximity terms ("near me", "local", "in [location]")

3. **Intent Modifiers**
   - Commercial intent ("best", "top-rated", "affordable")
   - Urgency intent ("emergency", "24/7", "same day")
   - Quality intent ("professional", "expert", "certified")

### Seed Keyword Expansion

The skill generates seed keywords using this pattern structure:
```
[service] + [modifier] + [location]
```

Examples:
- "plumbing services near me"
- "emergency dentist New York"
- "best roofing contractor Chicago"

## Search Intent Classification

### Intent Categories

1. **Transactional Intent**
   - High commercial intent
   - User ready to make a purchase or hire a service
   - Keywords: "buy", "hire", "schedule", "book", "quote", "price"

2. **Informational Intent**
   - Research and information gathering
   - User seeking knowledge before decision
   - Keywords: "how to", "what is", "cost of", "benefits"

3. **Navigational Intent**
   - Brand or company specific searches
   - User looking for specific business
   - Keywords: business names, brand terms

### Intent Classification Rules

A keyword is classified as transactional if it contains:
- Commercial intent words (buy, hire, book, schedule)
- Service-specific action words (repair, install, replace)
- Urgency indicators (emergency, immediate, fast)

Informational keywords typically contain:
- Research words (how, what, why, cost, benefits)
- Educational terms (guide, tutorial, learn)

Navigational keywords are:
- Brand names
- "Near me" + service terms
- Business-specific terms

## Competition Estimation Heuristic

### Competition Level Indicators

1. **High Competition**
   - Industry-wide service terms
   - Major geographic areas
   - High commercial intent keywords
   - Average CPC > $15

2. **Medium Competition**
   - Niche-specific services
   - Suburban/rural areas
   - Moderate commercial intent
   - Average CPC $8-15

3. **Low Competition**
   - Long-tail keywords
   - Specific service types
   - Less commercial intent
   - Average CPC < $8

### Competition Factors Considered

- Keyword popularity in the niche
- Geographic competition density
- Commercial intent strength
- Industry standard CPC benchmarks

## Match Type Recommendations

### Default Strategy
- **New Accounts**: Phrase match primarily
- **Established Accounts**: Mix of phrase and exact match
- **Mature Accounts**: Broad match modifier with negative controls

### Match Type Guidelines

**Phrase Match (Recommended for New Accounts)**
- Prevents irrelevant matches while allowing variation
- Balances control and reach
- Good for building initial keyword data

**Exact Match**
- Use for high-converting keywords
- Precise control over ad triggering
- Best after performance data exists

**Broad Match Modifier**
- Use for established campaigns with history
- Requires extensive negative keyword lists
- Maximizes reach potential

### Negative Keyword Strategy

**Universal Negatives**
- "jobs", "careers", "employment"
- "free", "cheap", "diy"
- "school", "training", "course"

**Industry-Specific Negatives**
- Keywords indicating wrong service type
- Geographic exclusions
- Competitor brand names (optional)

## Search Volume Estimation

### Volume Categories

1. **High Volume**
   - Industry core terms
   - Major geographic areas
   - Broad commercial intent

2. **Medium Volume**
   - Specific service types
   - Suburban/city-level terms
   - Moderate commercial intent

3. **Low Volume**
   - Long-tail combinations
   - Specific geographic modifiers
   - Niche service terms

### Estimation Methodology

Search volume is estimated using:
- Web search result counts
- Industry benchmarks
- Geographic population data
- Commercial intent strength

## CPC Estimation Framework

### Base CPC Calculation

The skill uses industry benchmarks and competition levels to estimate CPC:

```
Base CPC = Industry Average × Competition Multiplier × Geographic Modifier
```

**Industry Averages (USD):**
- Home Services: $8-15
- Healthcare: $10-20
- Professional Services: $12-25
- Retail: $5-12

**Competition Multipliers:**
- High: 1.5x
- Medium: 1.0x
- Low: 0.7x

**Geographic Modifiers:**
- Major Metro: 1.3x
- Suburban: 1.0x
- Rural: 0.8x

## Quality Score Optimization

### Keyword Quality Factors

1. **Relevance**
   - Keyword matches ad text
   - Keyword matches landing page
   - Clear user intent alignment

2. **Landing Page Experience**
   - Page content matches keyword
   - Fast loading speed
   - Mobile-friendly design
   - Clear conversion path

3. **Expected CTR**
   - Ad text includes keyword
   - Strong ad extensions
   - Competitive positioning
   - Historical performance data

## Performance Monitoring

### Key Metrics to Track

1. **Keyword-Level Metrics**
   - Impressions and clicks
   - CTR and CPC
   - Conversion rate and cost per conversion
   - Quality score trends

2. **Campaign-Level Metrics**
   - Overall ROI
   - Budget utilization
   - Geographic performance
   - Device performance

### Optimization Cycles

1. **Weekly Checks**
   - Search term reports
   - Negative keyword additions
   - Bid adjustments based on performance

2. **Monthly Reviews**
   - Keyword performance analysis
   - Budget allocation optimization
   - Geographic performance review
   - Match type strategy evaluation

This methodology provides a systematic approach to Google Ads keyword research that balances data-driven insights with practical campaign management considerations.