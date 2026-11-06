# rivl

**An analyst that never sleeps.** rivl watches your competitors, and your clients' competitors, and pings you as soon as one of them raises money, ramps up ads, starts or stops hiring, or starts losing customers, with what it probably means and what to do.

Built at **ContextCon 04, IIT Kanpur** (theme: *Services, Replaced*), on [Crustdata](https://crustdata.com) company data.

> **Status:** working end to end on live Crustdata data. Bring your own API key; see [Run it](#run-it).

---

## The service it replaces

Companies find out a competitor is beating them months too late, usually when their own sales drop. Some pay competitive-intelligence analysts or research firms to track rivals by hand, slowly and patchily. Almost nobody tracks how **their clients** are doing against **the clients' own competitors**, even though that decides whether a client grows, cuts back or leaves.

rivl does that job continuously.

## What it does

1. **Finds your competitors automatically:** companies that pay for the same Google search ads are chasing the same customers. Each candidate is checked to confirm it's a real, comparable company.
2. **Watches them all the time:** website visitors, share of search, Google Ads spend, search phrases won and lost, job postings, follower growth, funding, people joining and leaving.
3. **Compares everyone against each other:** if a whole market has a bad month, it still tells you who's actually winning.
4. **Pings you when something meaningful changes:** what changed, what it means, what to do, and the source of every number.

### Two uses, one engine
- **Your competitors:** who's pushing, who's slipping, who's new.
- **Your clients' competitors:** which clients are beating their rivals (sell them more), which are losing (protect the account), and which of their rivals is booming (your next customer).

## Example pings (real data, 6 Nov 2026)

> 🔴 **Deel is making a big push.** Just raised a Series E. Google Ads spend about **$8.4M/month** (4× Rippling). Job postings **92 → 483** in a quarter.
> *Likely meaning:* buying market share; price cuts likely. *Suggested move:* lock top accounts into longer contracts now.

> 🟢 **Oyster is losing ground.** Website visitors **−23%** this quarter while still spending about $740k/month on ads.
> *Likely meaning:* customers may be shopping around. *Suggested move:* run a "switch from Oyster" campaign.

> 🔴 **Your client New Relic looks like it's cutting back.** Job postings **454 → 153**, ads almost switched off, visitors −13% over the year.
> *Suggested move:* protect the account before renewal.

> 🟢 **Your client Datadog is winning its market.** The only monitoring company whose visitors grew over the year (+10.5%) while every rival fell.
> *Suggested move:* pitch an expansion.

### What a company does with these
| Ping type | Typical action |
|---|---|
| A competitor is **pushing hard** (raised money, more ads, more hiring) | Lock customers into longer contracts before it reaches them |
| A competitor is **weakening** | Go after its customers now |
| A competitor is **quietly cutting back** | Don't panic. Put effort elsewhere |
| A **new competitor** appears | Check it early, close the gap it's targeting |
| **Your client is shrinking** | Protect the account before renewal |
| **Your client is winning** | Sell them more |
| **Your client's competitor is growing** | That's your next customer |

## How it works

```
domain or client list
      │
      ▼
 resolve ─► competitors ─► signals ─► score ─► watch ─► ping
 (verify)   (shared ads,   (traffic,   (rank vs.  (Crustdata  (what / meaning /
            then checks)   search, ads, rivals,    watchers)   action / sources)
                           hiring,      3-of-4
                           funding)     rule)
```

### Rising or falling: the rule
Signals are grouped into four families:
- **Demand:** visitors, share of search, direct traffic
- **Search position:** phrases won vs. lost, rank, breadth
- **Marketing spend:** ads budget, paid clicks
- **The company:** hiring, funding, followers, people joining vs. leaving

Every measure is ranked **within the competitor set**. A company is **Rising** or **Falling** only if **at least 3 of the 4 families agree**; otherwise it's **Mixed**, with the explanation. The decision is rule-based and repeatable; the language model only writes the wording.

### Data problems it catches
Wrong company matches at high confidence (`notion.so` → a 26-person company), website traffic attached to the wrong site, broken search data for big brands, headcount inflated by employer-of-record platforms, acquired companies still listed separately, and domain changes that look like traffic collapses. The full list and how each is handled: [`AGENTS.md`](AGENTS.md).

## Who pays

| Buyer | Why |
|---|---|
| Heads of marketing and growth | See who's pushing and where competitors are weak, and spend accordingly |
| Heads of sales and account managers | Know which clients will grow, which might leave, and who to sell to next |
| Marketing agencies | Client reports, plus a feed of companies losing ground (likely new clients) |

**Model:** a monthly subscription, priced by markets and companies tracked. These prices are assumptions to test:

| Plan | For | Price |
|---|---|---|
| Starter | Startups, 1 market, up to 10 companies | ₹15,000/mo |
| Growth | Mid-size companies, 3 markets, up to 40 companies, Slack pings | ₹60,000/mo |
| Enterprise | Unlimited markets, client-list tracking, API | from ₹3,00,000/mo |
| Agency | Many client workspaces, white-label reports, prospect feed | ₹1,00,000/mo + per client |

## Run it

You need Python 3.11+ and your own [Crustdata](https://crustdata.com) API key.

```bash
git clone <this repo> && cd ycons
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/flask --app market_radar.app run
```

Open http://127.0.0.1:5000. It opens on **Setup**:

1. **Paste your Crustdata API key.** It's checked with a free balance lookup and saved only to the local `.env` (gitignored). Find it in the Crustdata dashboard under *API Keys*.
2. **Enter your company's website** and, optionally, your clients' websites (one per line, or upload a CSV). Or press **Load the Rippling demo**: Rippling as your company, with Datadog, Canva and Stripe as clients.

Setup takes about a minute and costs about **2 credits per company tracked** (roughly 60 for the demo). Lookups and job-posting counts are free.

## Using rivl

### The dashboard, top to bottom
| Part | What it shows | What to do with it |
|---|---|---|
| **Clock** | The date the dashboard is showing, how many new pings this week's check found, and when the next check runs | Use **Skip a week / Skip a month** to move forward, **Jump to live data** for today, **Reset demo** to start over |
| **Your position** (5 tiles) | Your verdict, visitors per month, share of the market's visitors, hiring, Google Ads spend, each compared with your rivals | A quick read on whether you're gaining or losing ground |
| **Your market** tab | You against your competitors: a visitors chart (you in blue, rivals in gray), share-of-visitors bars, a hiring-vs-demand chart, "market at a glance", and a scoreboard | Hover a scoreboard row to highlight that company's line. Open **How we found these competitors** to see who was kept or dropped, and why |
| **Client accounts** tab | One row per client: an account call (**Upsell / Protect / Steady**), how the client is growing against its rivals, prospects, new pings | Click a client to open its market below |
| **Pings** (right) | New this week, then earlier. Each says what changed, what it probably means, what to do, and its sources | Open **Sources** to see the exact field, value and date behind every number |
| **Filters** | Verdict (rising, falling, mixed), ping type (threats, opportunities, watch), 12 or 24 months of history | They apply to everything on the page |

**Verdict labels:** ▲ Rising and ▼ Falling mean at least 3 of the 4 signal groups agree. ◆ Mixed means they don't. A **!** next to a company opens a note about a data problem, for example "search data looks broken for this brand".

### A 2-minute demo
1. **Setup → Load the Rippling demo.** Wait about a minute.
2. On the dashboard, press **Reset demo** to go back to July, then **Skip a month** a few times. Pings arrive as new data lands: a client winning its market, a rival making a push, a rival losing ground.
3. Open a ping's **Sources** to show where each number comes from.
4. Switch to **Client accounts** and click a client to see its market and the account call.
5. Open **How we found these competitors** to show the checks, for example Paycor dropped as acquired and tiny product lines dropped.
6. Press **Fetch latest** to re-fetch live data. Companies Crustdata hasn't refreshed are skipped, and nothing is pinged twice.

### Your own company
**Setup** → enter your website and your clients' websites → **Start tracking**. This replaces whatever was tracked before. Come back to Setup at any time to change it, replace the API key, or check your credit balance.

### The demo clock
The dashboard has a clock. **Skip a week / Skip a month** moves it, and every number is recomputed from data that existed on that date. That way a weekly product can be shown in two minutes. Search and ad figures only exist from the day they were fetched (Crustdata keeps no history for them), and the dashboard says so.

### Keeping it current
- **Fetch latest** (top right) re-fetches every tracked company now.
- The **weekly check**, e.g. from cron every Monday:
  ```bash
  .venv/bin/flask --app market_radar.app check
  ```
- Or set up from the command line:
  ```bash
  .venv/bin/flask --app market_radar.app setup rippling.com --clients datadoghq.com,canva.com,stripe.com
  ```

A company whose data Crustdata hasn't refreshed since the last check is skipped. Pings are stored, and the same ping is never sent twice.

### Tests
```bash
.venv/bin/python -m unittest discover -s tests -t .
```
They use a fake Crustdata API, so they cost no credits.

## How it's built

| Module | Job |
|---|---|
| `crustdata.py` | API client: retries, clear errors (401/402/403/429), daily response cache |
| `resolve.py` | Domain to verified company (rejects confident-but-wrong matches like `notion.so` → "Hustá") |
| `competitors.py` | Candidates from shared ad keywords and search results, screened, every keep/drop reason logged; description-based fallback |
| `signals.py` | Normalises each company into a record; computes measures as of any date |
| `score.py` | Ranks each measure within the competitor set; 4 signal groups; 3-of-4 verdict rule |
| `pings.py` | Rule-based pings: what changed, what it means, what to do, sources |
| `view.py` | One dashboard builder for live data and the demo; drops product lines and in-market acquisitions |
| `check.py` | Weekly check and Fetch latest; setup |
| `store.py` | SQLite: markets, members, snapshots (our own history), pings |
| `app.py`, `templates/`, `static/` | Flask UI, plain CSS and JS, server-rendered SVG charts |

State lives in `data/radar.db`. Cached API responses live in `data/raw/`. Both are gitignored.

## Limits

- Not real-time: pings are as fast as Crustdata's updates (companies refresh every 1–30 days; website traffic is monthly). Every ping shows its data date.
- Competitor discovery works best for companies that advertise online. Others fall back to companies with a similar description and size, which is less precise (it can include consultancies).
- Crustdata's acquisition data is noisy, so a company is only dropped as "acquired" when the buyer is another company in the same market. Paycor is handled by a known-acquisitions list.
- Search and ad numbers are current values only. rivl stores a snapshot each check to build history over time.
- Crustdata gives **counts** of search phrases won and lost, not the phrases themselves.
