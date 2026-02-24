# API Rate Limits

Rate limits relevant to `scripts/generate_sample_cards.py` and the app's AI analysis feature.

Last updated: 2026-02-23

## Anthropic Claude API

[Official docs](https://platform.claude.com/docs/en/api/rate-limits)

Limits are per-model, per-organization. Cached input tokens do NOT count towards ITPM (big advantage for prompt caching).

| Tier | Deposit | Sonnet 4.x RPM | Sonnet 4.x ITPM | Sonnet 4.x OTPM | Haiku 4.5 RPM | Haiku 4.5 ITPM | Haiku 4.5 OTPM |
|------|---------|----------------|------------------|------------------|----------------|-----------------|-----------------|
| Tier 1 | $5 | 50 | 30,000 | 8,000 | 50 | 50,000 | 10,000 |
| Tier 2 | $40 | 1,000 | 450,000 | 90,000 | 1,000 | 450,000 | 90,000 |
| Tier 3 | $200 | 2,000 | 800,000 | 160,000 | 2,000 | 1,000,000 | 200,000 |
| Tier 4 | $400 | 4,000 | 2,000,000 | 400,000 | 4,000 | 4,000,000 | 800,000 |

Opus 4.x limits match Sonnet 4.x. Tiers advance automatically based on cumulative credit purchases.

### Impact on our usage

- **generate_sample_cards.py**: Makes 1 Claude call for all card specs — not a concern.
- **App AI analysis**: One call per card. Batch-analyzing 50+ cards at Tier 1 (50 RPM) could hit limits. Tier 2+ is comfortable for any realistic workload.

## OpenAI Image Generation (gpt-image-1 / 1.5)

[Official docs](https://platform.openai.com/docs/guides/rate-limits)

| Tier | Spend Required | RPM | TPM |
|------|---------------|-----|-----|
| Tier 1 | $5+ | 6 | 250,000 |
| Tier 2 | $50+ | 15 | 500,000 |
| Tier 3 | $500+ | 25 | 1,000,000 |
| Enterprise | Custom | 60+ | Custom |

RPM is the practical bottleneck — you'll hit request caps before token limits.

### Impact on our usage

- **generate_sample_cards.py**: Each card needs 1–2 image generations (front, optionally back). At Tier 1 (6 RPM), generating 20 cards (~30 images) takes ~5 minutes from rate limiting alone.
- The script processes cards sequentially, which naturally throttles requests. If we ever parallelize, we'd need explicit rate limiting (e.g., `asyncio.Semaphore` or token bucket).
- The script's retry logic (3 attempts with exponential backoff) already handles transient 429 errors.

## Tier Advancement

| Provider | How to advance |
|----------|---------------|
| Anthropic | Cumulative credit purchases ($5 → $40 → $200 → $400) |
| OpenAI | Cumulative spend ($5 → $50 → $500), account age matters too |

Check your current limits:
- Anthropic: [Console limits page](https://console.anthropic.com/settings/limits)
- OpenAI: [Platform limits page](https://platform.openai.com/settings/organization/limits)
