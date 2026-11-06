# Market Radar

**An analyst that never sleeps.** Market Radar watches your competitors, and your clients' competitors, and pings you as soon as one of them raises money, ramps up ads, starts or stops hiring, or starts losing customers, with what it probably means and what to do.

Built at **ContextCon 04, IIT Kanpur** (theme: *Services, Replaced*), on [Crustdata](https://crustdata.com) company data.

> **Status:** design and data validation done; product code in progress. See [Status](#status).

---

## The service it replaces

Companies find out a competitor is beating them months too late, usually when their own sales drop. Some pay competitive-intelligence analysts or research firms to track rivals by hand, slowly and patchily. Almost nobody tracks how **their clients** are doing against **the clients' own competitors**, even though that decides whether a client grows, cuts back or leaves.

Market Radar does that job continuously.

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

## Status

| Part | State |
|---|---|
| Competitor discovery from shared ad keywords | ✅ validated on 10 global companies and 2 markets (HR/payroll, monitoring) |
| Signal pull (traffic, search, ads, postings, funding) | ✅ validated on 14 companies |
| Data-problem checks | ✅ identified and documented; ⬜ not yet coded |
| Scoring and verdict rule | ⬜ designed, not coded |
| Watchers and webhooks | ⬜ not tested |
| Pings and dashboard | ⬜ not built |

## Setup (planned)

```bash
cp .env.example .env        # add CRUSTDATA_API_KEY
pip install -r requirements.txt
python -m market_radar.app  # then open the local URL
```

These commands will work once the package is in place.

## Limits

- Pings are only as fast as Crustdata's data updates (hiring and staff changes quickly, website traffic monthly).
- Competitor discovery works best for companies that advertise online. Others fall back to same industry and similar size.
- Search data is current values only. Market Radar stores snapshots to build history over time.
- Crustdata gives **counts** of search phrases won and lost, not the phrases themselves.
