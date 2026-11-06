# rivl: demo script (about 2 minutes)

For an audience from Crustdata: the product, and how it's built on Crustdata's data.
Spoken lines are plain text. **[What to show]** is in brackets.

## Before you record
- Run the app: `.venv/bin/flask --app market_radar.app run`, then open http://127.0.0.1:5000
- Make sure the Rippling demo is loaded (Setup → **Load the Rippling demo**, about 60 credits). It's already loaded on this machine.
- On the dashboard, press **Reset demo** so the clock starts on **Mon 6 Jul 2026**.
- Browser at full width, zoomed to 90–100%, light mode.

---

## 0:00–0:15 · The problem
Companies find out a competitor is beating them months too late, when their own sales drop. And almost nobody watches how their *clients* are doing against the *clients'* competitors, even though that decides whether a client grows or leaves.

rivl is an analyst that never sleeps. It watches both, and tells you what changed and what to do.

**[Show: the dashboard header and the "Your position" tiles for Rippling.]**

## 0:15–0:30 · Bring your own Crustdata key
It runs on your own Crustdata account. You paste your API key (we check it with the free credits endpoint), then enter your company and your clients. For this demo, we're Rippling, and our clients are Datadog, Canva and Stripe.

**[Show: the Setup page. Step 1 "Connected · key ending …" with the credit balance, then Step 2 with the company and client fields and the "Load the Rippling demo" button.]**

## 0:30–0:50 · How we find competitors with Crustdata
Nobody types in a competitor list. Company Enrich gives us `competitors.paid_seo`: the companies bidding on the same Google ads. That's the best competitor signal we found. Rippling came back with Deel, BambooHR, ADP, Remote and Justworks. The look-alike-name list (`all_domains`) gave us things like "dudewipes.com", so we ignore it.

Every candidate is checked with Company Identify, which is free. We screened 38 candidates across 4 markets and kept 24. Notion's old domain resolved to a 26-person company called "Hustá" at full confidence, so we check that the domain really belongs to the company. Site24x7 is a Zoho product line with 24 staff listed, so we check real headcount. And Paycor was dropped because Paychex bought it.

**[Show: Your market → open "How we found these competitors". Point at ✓ "Bids on the same Google ads" and ✕ paycor.com "Acquired by Paychex". If there's time, the same list in Datadog's market (Client accounts → Datadog) shows ✕ site24x7.com and the tiny "Too small to compare" sites.]**

## 0:50–1:15 · The signals, all from Crustdata
For each company, one Company Enrich call gives us 24 months of website visitors, where those visitors come from, Google Ads budget, search phrases won and lost, follower growth, headcount and funding. Hiring comes from Job Search aggregations: we counted 37,626 job postings by company and month, at no cost.

We never judge a number on its own. Each measure is ranked against the company's own competitors, grouped into four signals (demand, search, marketing push and company momentum), and a company is only called Rising or Falling when three of the four agree.

**[Show: the visitors chart (Rippling in blue, rivals in gray), then hover a scoreboard row to highlight its line, then the four small signal bars in the scoreboard.]**

## 1:15–1:40 · Watching it happen
Crustdata refreshes companies every few days to a month, so rivl is a weekly check, not a real-time feed. This clock lets us replay the weeks, using only data that existed on each date.

**[Show: press "Skip a month" from July. In August: "Your client Stripe is winning its market". In September: "Deel is making a push". Stop on the Deel ping.]**

Deel: Google Ads at about 8.4 million dollars a month, four times Rippling's, and job postings up from 92 to 483 in one quarter. rivl's advice: lock your biggest accounts into longer contracts before Deel's sales team reaches them.

**[Show: open the Deel ping's "Sources". Each number shows its Crustdata field and the date it was fetched.]**

## 1:40–1:55 · Your clients' competitors
The same engine runs on every client. Datadog is winning a shrinking market (it's the only monitoring company whose traffic grew over the year), so the account call is Upsell. When a client's competitor is growing fast, that's your next prospect.

**[Show: press "Jump to live data", open the Client accounts tab, click Datadog. Show the "Upsell" account call and the "client vs rivals" mini chart.]**

## 1:55–2:05 · Close
Everything you saw came from five Crustdata endpoints, cost about 62 credits to set up, and updates with one click.

**[Show: press "Fetch latest". The message says how many companies had new data and how many were unchanged. Nothing is pinged twice. End on the dashboard.]**

rivl: we watch your market so you don't have to.

---

## Crustdata, in one table (for Q&A)

| Crustdata endpoint | What rivl uses it for | Cost |
|---|---|---|
| **Company Identify** | Turn every domain into a verified company; screen competitor candidates | Free |
| **Company Enrich** (`competitors`, `web_traffic`, `seo`, `headcount`, `followers`, `funding`) | Competitor discovery from shared Google ads; 24 months of traffic and traffic sources; ad budget; search phrases won and lost; followers; funding; acquisitions | 2 credits per company |
| **Job Search** aggregations (`limit: 0`, group by company) | Monthly hiring counts per company (37,626 postings counted) | Free |
| **Company Search** (plain-English search + headcount range) | Fallback when a company has fewer than 3 ad-keyword competitors | ~0.03 per result |
| **Account Credits** | Validate the user's API key and show their balance | Free |

**What we learned about the data** (good questions to expect):
- `competitors.paid_seo` is the strongest competitor signal; `all_domains` is look-alike names.
- Website traffic is keyed by domain, and sometimes the record holds another site's traffic (HubSpot's came back for `gzconsulting.org`), so we only use the company's own domain.
- Search ranking data looks broken for some big brands (ADP lists 2,823 ranked phrases and $0 in ads), so rivl detects it and falls back to traffic.
- `funding.acquired_by` is noisy (Adobe "acquired by Adobe"), so a company is only dropped when another company in the same market bought it.
- Enrich has no "last updated" field, so rivl fingerprints each record to tell whether Crustdata has refreshed it since the last check.
- Search and ad figures have no history, so rivl stores a snapshot on every check to build its own.
