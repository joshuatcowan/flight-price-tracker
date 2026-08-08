# Flight Price Tracker

Personal automated tracker for a round-trip business-class fare:

- **Route:** Seattle (SEA) → Hong Kong (HKG), Beijing (PEK), Shanghai (PVG), or Chongqing (CKG)
- **Outbound:** depart Sept 11 or 12, 2026 — must arrive by end of Sept 13 local time
- **Return:** Sept 20, 2026
- **Rules:** oneworld alliance carriers only, business class on all international legs,
  max 1 stop each direction

## How it works

- `flight_tracker.py` queries Google Flights (via your SerpApi key) for all 8
  destination/date combos, filters to itineraries that pass every rule, and prints a report.
- `.github/workflows/daily-check.yml` runs it every day at 6:30am Pacific,
  commits the results to `results/`, and posts the report as a comment on the
  "Daily flight price reports" issue (which emails you).
- A Claude scheduled task reads `results/latest.txt` each morning and sends a
  summary email + push notification.

## Files

- `results/latest.txt` — most recent human-readable report
- `results/latest.json` — most recent results as JSON
- `results/history.csv` — daily best price per destination, for spotting trends

## Secrets

`SERPAPI_KEY` — stored as an encrypted GitHub Actions secret. Free tier is 250
searches/month; this tracker uses 8/day (~240/month).

## Run manually

Actions tab → "Daily flight price check" → Run workflow.
