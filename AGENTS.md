# AGENTS.md

Guidance for coding agents (Claude Code, Codex, etc.) working in this repo.

## What we're building

**Market Radar** watches a company's competitors, and its clients' competitors, and pings the user as soon as one of them does something important (raises money, ramps up ads, starts or stops hiring, loses website visitors). Each ping says what changed, what it probably means, what to do, and where every number came from.

The product overview, example pings and current status are in [`README.md`](README.md).

Built for ContextCon 04 (theme: *Services, Replaced*). The service it replaces is competitive-intelligence analysts and market-research reports.

## Event rules that affect code

- **Never contact real people.** The product may *draft* messages for the user's team. It must never send email, messages or calls to anyone outside our team. Pings go only to the user's own channels (dashboard, Slack, email we control).
- **Never commit secrets.** API keys go in `.env` (gitignored). Keep `.env.example` with placeholder values.
- **Commit as you go,** in small, descriptive commits.
- **Don't commit raw Crustdata responses.** Keep cached responses under `data/raw/` (gitignored).

## Architecture (target)

```
input: domain or client list (CSV)
   │
   ▼
1. resolve      company_identify (free) → verify name/domain/size before trusting
   │
   ▼
2. competitors  competitors.paid_seo + organic_seo → identify → filter → fallback
   │
   ▼
3. signals      company_enrich (seo, web_traffic, followers, funding, headcount)
                + job_search posting counts (free aggregations)
   │
   ▼
4. score        rank each signal within the competitor set → 4 family scores → verdict
   │
   ▼
5. check        weekly re-fetch (plus a "Fetch latest" button) → diff vs stored snapshot
                → re-score → ping only if meaningful. Not real-time: Crustdata
                refreshes companies every 1–30 days, and every ping shows data age.
   │
   ▼
6. output       ping text (what / meaning / action / sources) + dashboard
```

Keep each step a separate module with plain inputs and outputs, so steps can be tested and re-run alone.

## Domain rules (follow these exactly)

### Competitor discovery
1. Candidates come from `competitors.paid_seo` first, then `competitors.organic_seo`. **Ignore `competitors.all_domains`.** It's look-alike names (for example Rippling → dudewipes.com).
2. Resolve each candidate with `company_identify` (free).
3. Drop a candidate if any of these is true:
   - confidence < 0.9
   - its domain isn't the match's primary domain or one of its domains
   - no size data, or fewer than about 200 staff (catches blogs and product lines like Site24x7)
   - it was acquired by another company in the set (for example Paycor → Paychex)
4. If fewer than 3 competitors survive, fall back to same industry and similar size (0.3×–3× headcount).
5. Record **why** each candidate was kept or dropped. The UI shows this.

### Signals: four families
| Family | Measures |
|---|---|
| **A. Demand** | monthly visitors (3-month and 12-month trend), share of search (visitors × search % ÷ set total), direct-traffic % |
| **B. Search position** | net phrase momentum ((gained + new − lost) ÷ total), average organic rank, number of phrases ranked |
| **C. Marketing spend** | Google Ads budget, paid clicks, paid-traffic % |
| **D. The company** | job postings this quarter vs. last, follower growth, months since last raise, people joining vs. leaving, headcount (secondary only) |

### Verdict rule
- Rank every measure **as a percentile within the competitor set**. Never judge on absolute numbers.
- Average each family to get a family score. A family is **up** at ≥ 0.7 and **down** at ≤ 0.3 (0.6/0.4 let 2nd place in a 4-company set count as up).
- **Rising / Falling only if at least 3 of the 4 families agree.** Otherwise **Mixed**, with the explanation.
- On past dates only 2 families have data (search and ad fields have no history), so **both must agree**, and the UI says so.
- Every verdict lists the evidence behind it.
- Keep it deterministic: the same data must always produce the same verdict. The LLM writes the wording; it does not make the decision.

### Data problems: always check for these
| Problem | Example | Handling |
|---|---|---|
| Wrong company match at high confidence | `notion.so` → "Hustá"; `perfios.com` → "Superfios Textil" | Verify name, domain and size before enriching |
| Traffic attached to the wrong website | HubSpot → `gzconsulting.org`; Shopify → `dandelionchocolate.com` | Use only the `domain_traffic` entry for the company's own domain |
| Search data broken for big brands | ADP: 2,823 phrases, $0 ads; Paychex: 13 phrases | If search data is far out of line with traffic, mark it unreliable and use traffic-based measures |
| Headcount includes staff employed for clients | Remote 19,882; Deel 9,642 | Don't use headcount for employer-of-record and staffing companies |
| Acquired companies listed separately | Paycor | Check for mergers (web search) before comparing |
| Domain change breaks traffic history | Perfios `perfios.com` → `perfios.ai`: 1.1M → 30k visitors | Detect a sudden drop alongside a new domain; join the histories |
| "Net phrases won" positive for everyone | +31% to +74% | Only use it relative to competitors |
| Followers diverge from demand | SmartBear followers +84%, traffic −33% | Never let one measure drive a verdict |
| Job-posting coverage drift | India postings ~8× higher in 2026 as sources were added | Compare companies on the same basis; never use raw national totals |

If a fact can't be verified, **say so in the output**. Never guess.

### Pings
- Only ping on a **meaningful** change: a verdict changes, a family score moves a lot, a new competitor appears, a funding round, or a big jump in ad spend or postings.
- Each ping has: **what changed**, **what it probably means**, **suggested action**, **sources** (field, value, date fetched).
- **Never send the same ping twice.** Key each ping by company + event + period and check before sending.
- Store every ping, so later pings can reference history ("third warning sign in two months").

## Crustdata API

- Base URL `https://api.crustdata.com`. Headers: `authorization: Bearer $CRUSTDATA_API_KEY`, `x-api-version: 2025-11-01`.
- Docs: https://docs.crustdata.com (agents can read `llms.txt`). MCP: `https://install.crustdata.com/mcp`.
- **Costs:** `company_identify` and `job_search` aggregations (`limit: 0`) are free. `company_enrich` is 2 credits per **returned match**, so always enrich **by `crustdata_company_id`**, never by name or domain (fuzzy matches multiply cost).
- Batch up to 25 ids per enrich call.
- **Rate limits** are per endpoint (about 10–30 requests a minute, 200 a minute overall). Retry with backoff and honour `x-ratelimit-reset`.
- **Errors:** 401 bad key; 402 out of credits (don't retry); 403 endpoint or field not on the plan (don't retry); 429 back off.
- **Plan-gated fields:** asking for a gated field in `fields` fails the whole call. Gated on our plan: `technographics`, `maps`, `social_posts`, `hiring.recent_openings`, `social_profiles.crunchbase`, plus `headcount` and `locations` on identify.
- `seo` fields are **current values only**. Store a snapshot each refresh to build our own history.
- **Cache every response** locally (keyed by endpoint + params + date) during development. Don't re-fetch in loops.

## Coding principles

1. **Get it working end to end first:** domain in, verdicts and pings out, however rough. Polish later.
2. **Every number carries its source:** field name, value, date fetched.
3. **Deduplicate on `crustdata_company_id`,** never on names.
4. **Save progress** (SQLite) so an interrupted run resumes instead of restarting.
5. **Validate API output** before using it: missing fields, empty lists, nonsense values.
6. **Keep it simple:** readable modules over clever abstractions.
7. **Write tests** for the scoring and verdict logic, using saved responses rather than live calls.

## Repo layout (target)

```
market_radar/
  resolve.py       # identify + verification
  competitors.py   # discovery, filtering, fallback
  signals.py       # enrich + postings → normalised signal rows
  score.py         # percentiles, families, verdict rule
  pings.py         # change detection, dedupe, ping text
  check.py         # weekly check + "Fetch latest": re-fetch, diff, ping
  store.py         # SQLite: companies, snapshots, verdicts, pings
  charts.py        # server-rendered SVG charts
  sample.py        # demo data + demo clock (until the live pipeline replaces it)
  app.py           # Flask UI
templates/, static/  # one Jinja page, plain CSS and JS (no framework)
tests/
data/raw/          # cached API responses, gitignored
.env.example
```
