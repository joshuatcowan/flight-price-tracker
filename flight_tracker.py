#!/usr/bin/env python3
"""
Personal flight price tracker — Josh Cowan
Data source: SerpApi Google Flights engine (your own API key, free tier).

Rules enforced:
  Round trip SEA -> HKG / PEK / PVG / CKG
  Outbound: depart 2026-09-11 or 2026-09-12, must arrive by end of 2026-09-13
  Return:   2026-09-20
  Business class on every international leg (US-domestic connections exempt)
  Max 1 stop per direction
  oneworld alliance carriers only

Env var required:  SERPAPI_KEY
Usage:             python3 flight_tracker.py [--json results.json]

Quota note: 8 searches per run (4 destinations x 2 departure dates).
Daily runs = ~240 searches/month, inside SerpApi's 250/month free tier.
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

ORIGIN = "SEA"
DESTINATIONS = {"HKG": "Hong Kong", "PEK": "Beijing", "PVG": "Shanghai", "CKG": "Chongqing"}
DEPART_DATES = ["2026-09-11", "2026-09-12"]
RETURN_DATE = "2026-09-20"
LATEST_ARRIVAL_DATE = "2026-09-13"   # outbound must arrive by end of this day, local time
CURRENCY = "USD"

# oneworld members (mid-2026): used to double-check what the alliance filter returns
ONEWORLD_AIRLINES = {
    "AA": "American", "AS": "Alaska", "AY": "Finnair", "AT": "Royal Air Maroc",
    "BA": "British Airways", "CX": "Cathay Pacific", "FJ": "Fiji Airways",
    "IB": "Iberia", "JL": "Japan Airlines", "MH": "Malaysia Airlines",
    "QF": "Qantas", "QR": "Qatar Airways", "RJ": "Royal Jordanian",
    "UL": "SriLankan", "WY": "Oman Air",
}

US_AIRPORTS = {
    "SEA", "PDX", "SFO", "LAX", "SAN", "SJC", "ONT", "LAS", "PHX", "DEN", "SLC",
    "ORD", "DFW", "IAH", "AUS", "MSP", "DTW", "ATL", "MIA", "MCO", "TPA", "CLT",
    "JFK", "EWR", "LGA", "BOS", "PHL", "IAD", "DCA", "BWI", "HNL", "ANC",
}

BIZ_OK = ("business", "first")


def search(dest, outbound_date):
    key = os.environ.get("SERPAPI_KEY")
    if not key:
        sys.exit("ERROR: set the SERPAPI_KEY env var.")
    params = urllib.parse.urlencode({
        "engine": "google_flights",
        "departure_id": ORIGIN,
        "arrival_id": dest,
        "outbound_date": outbound_date,
        "return_date": RETURN_DATE,
        "type": "1",              # round trip
        "travel_class": "3",      # business
        "stops": "2",             # nonstop or 1 stop
        "include_airlines": "ONEWORLD",
        "adults": "1",
        "currency": CURRENCY,
        "hl": "en",
        "api_key": key,
    })
    url = f"https://serpapi.com/search.json?{params}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                data = json.loads(r.read().decode())
            if "error" in data:
                raise RuntimeError(data["error"])
            return data
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))


def carrier_code(flight):
    # flight_number looks like "CX 857"
    fn = flight.get("flight_number", "")
    return fn.split()[0] if fn else "?"


def check_option(opt, depart_date):
    """Apply Josh's rules to one outbound option. Returns (ok, reason)."""
    flights = opt.get("flights", [])
    if not flights:
        return False, "no segments"
    if len(flights) > 2:
        return False, "more than 1 stop"
    # arrival by Sep 13 local
    arr = flights[-1].get("arrival_airport", {}).get("time", "")[:10]
    if arr and arr > LATEST_ARRIVAL_DATE:
        return False, f"arrives {arr} (too late)"
    for f in flights:
        code = carrier_code(f)
        if code not in ONEWORLD_AIRLINES:
            return False, f"{f.get('airline', code)} not oneworld"
        dep_ap = f.get("departure_airport", {}).get("id", "")
        arr_ap = f.get("arrival_airport", {}).get("id", "")
        domestic = dep_ap in US_AIRPORTS and arr_ap in US_AIRPORTS
        cabin = (f.get("travel_class") or "").lower()
        if not domestic and cabin and not any(b in cabin for b in BIZ_OK):
            return False, f"international leg {dep_ap}-{arr_ap} is {f.get('travel_class')}"
    return True, ""


def describe(opt):
    flights = opt["flights"]
    route = " → ".join([flights[0]["departure_airport"]["id"]] +
                       [f["arrival_airport"]["id"] for f in flights])
    legs = "; ".join(
        f"{f.get('airline', '?')} {f.get('flight_number', '')} "
        f"({(f.get('travel_class') or '?')})"
        for f in flights)
    dep_t = flights[0]["departure_airport"].get("time", "?")
    arr_t = flights[-1]["arrival_airport"].get("time", "?")
    tot = opt.get("total_duration", 0)
    lay = opt.get("layovers") or []
    lay_s = ", ".join(f"{l.get('id', '?')} {l.get('duration', 0)//60}h{l.get('duration', 0)%60:02d}m"
                      for l in lay) or "nonstop"
    return (f"  {route} | {dep_t} → {arr_t} | {tot//60}h{tot%60:02d}m in air+layover"
            f" | layover: {lay_s}\n    legs: {legs}")


def main():
    results = []
    errors = []
    for dest, city in DESTINATIONS.items():
        for dep in DEPART_DATES:
            try:
                data = search(dest, dep)
            except Exception as e:
                errors.append(f"SEA-{dest} {dep}: {e}")
                continue
            options = (data.get("best_flights") or []) + (data.get("other_flights") or [])
            for opt in options:
                ok, why = check_option(opt, dep)
                if not ok or "price" not in opt:
                    continue
                results.append({
                    "dest": dest, "city": city, "depart": dep,
                    "price": opt["price"],
                    "total_duration_min": opt.get("total_duration", 0),
                    "text": describe(opt),
                })
            time.sleep(1)

    stamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    print(f"FLIGHT PRICE TRACKER — {stamp}")
    print("SEA ↔ China/HK round trip | out 9/11-9/12 (arrive ≤9/13) | back 9/20"
          " | BUSINESS | oneworld | ≤1 stop")
    print("NOTE: prices are full ROUND-TRIP fares for that outbound paired with"
          " the best available return.")
    print("=" * 78)

    if errors:
        print("\n[warnings]")
        for e in errors:
            print(f"  {e}")

    if not results:
        print("\nNo qualifying itineraries found today.")
        return

    results.sort(key=lambda r: r["price"])

    print("\n*** CHEAPEST QUALIFYING (top 10 overall) ***")
    for r in results[:10]:
        print(f"\n${r['price']:,} — SEA↔{r['dest']} ({r['city']}), depart {r['depart']}")
        print(r["text"])

    print("\n*** BEST PER DESTINATION ***")
    for dest, city in DESTINATIONS.items():
        sub = [r for r in results if r["dest"] == dest]
        if not sub:
            print(f"\n{city} ({dest}): NO qualifying option found today")
            continue
        cheapest = min(sub, key=lambda r: r["price"])
        fastest = min(sub, key=lambda r: r["total_duration_min"] or 10**9)
        fm = fastest["total_duration_min"]
        print(f"\n{city} ({dest}): cheapest ${cheapest['price']:,} (dep {cheapest['depart']})"
              f" | fastest {fm//60}h{fm%60:02d}m at ${fastest['price']:,} (dep {fastest['depart']})")

    if "--json" in sys.argv:
        path = sys.argv[sys.argv.index("--json") + 1]
        with open(path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\n[saved {len(results)} results to {path}]")

    if "--history" in sys.argv:
        path = sys.argv[sys.argv.index("--history") + 1]
        today = datetime.utcnow().strftime("%Y-%m-%d")
        new = not os.path.exists(path)
        with open(path, "a") as f:
            if new:
                f.write("date,destination,cheapest_usd,fastest_usd,fastest_minutes\n")
            for dest in DESTINATIONS:
                sub = [r for r in results if r["dest"] == dest]
                if not sub:
                    f.write(f"{today},{dest},,,\n")
                    continue
                cheapest = min(sub, key=lambda r: r["price"])
                fastest = min(sub, key=lambda r: r["total_duration_min"] or 10**9)
                f.write(f"{today},{dest},{cheapest['price']},{fastest['price']},"
                        f"{fastest['total_duration_min']}\n")


if __name__ == "__main__":
    main()
