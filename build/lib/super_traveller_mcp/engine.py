import heapq
import logging
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)

MIN_TRANSFER_TIME = 0
MAX_TRANSFERS = 10
SAME_CITY_TRANSFER_MINUTES = 0


def _to_minutes(t: str) -> int:
    h, m = t.strip().split(":")
    return int(h) * 60 + int(m)


def my_leg(legs, frm, to, stn_city, t):
    direct = legs.get((frm, to), [])
    if stn_city.get(frm) and stn_city.get(frm) == stn_city.get(to):
        city = stn_city[frm]
        return direct + [{
            "train": f"S-{city}",
            "dep": (t + timedelta(minutes=0)).strftime("%H:%M"),
            "arr": (t + timedelta(minutes=30)).strftime("%H:%M"),
            "dur": SAME_CITY_TRANSFER_MINUTES,
            "_from": frm,
            "_to": to,
        }]
    return direct


def dijkstra_search(data, origin_city, dest_city, depart_date, arrival_date,
                    depart_earliest, arrive_latest, max_transfers=10):
    legs = data["legs"]
    out = data["out"]
    stn_city = data["stn_city"]
    city_stns = data["city_stns"]

    origin_stns = city_stns.get(origin_city, [origin_city])
    dest_stns = set(city_stns.get(dest_city, [dest_city]))

    start_dt = datetime.strptime(f"{depart_date} {depart_earliest}", "%Y-%m-%d %H:%M")
    deadline = datetime.strptime(f"{arrival_date} {arrive_latest}", "%Y-%m-%d %H:%M")

    queue = []
    for stn in origin_stns:
        state = {
            "segments": [],
            "stn": stn,
            "time": start_dt,
            "hops": 0,
            "visited": {stn},
        }
        heapq.heappush(queue, (0, id(state), state))

    best = {}
    results = []

    expanded = 0
    pruned = 0

    while queue:
        _, _, s = heapq.heappop(queue)
        stn, t, hops = s["stn"], s["time"], s["hops"]

        expanded += 1

        if stn in dest_stns:
            results.append(s)
            continue

        if stn in best and t >= best[stn]:
            pruned += 1
            continue

        best[stn] = t

        if hops >= max_transfers:
            continue

        for to_stn in out.get(stn, []):
            if to_stn in s.get("visited", set()):
                continue

            for leg in my_leg(legs, stn, to_stn, stn_city, t):
                dm = _to_minutes(leg["dep"])
                dep_dt = t.replace(hour=dm // 60, minute=dm % 60)
                if dep_dt < t:
                    dep_dt += timedelta(days=1)
                if dep_dt > deadline:
                    continue

                am = _to_minutes(leg["arr"])
                arr_dt = dep_dt.replace(hour=am // 60, minute=am % 60)
                if arr_dt <= dep_dt:
                    arr_dt += timedelta(days=1)

                if arr_dt > deadline:
                    continue

                seg = {
                    "train": leg["train"],
                    "from": leg["_from"],
                    "to": leg["_to"],
                    "dep": leg["dep"],
                    "arr": leg["arr"],
                    "dur": leg["dur"],
                    "dep_dt": dep_dt.strftime("%Y-%m-%d %H:%M"),
                    "arr_dt": arr_dt.strftime("%Y-%m-%d %H:%M"),
                }
                ns = {
                    "segments": s["segments"] + [seg],
                    "stn": to_stn,
                    "time": arr_dt,
                    "hops": hops + 1,
                    "visited": s["visited"] | {to_stn},
                }
                prio = (arr_dt - start_dt).total_seconds()
                heapq.heappush(queue, (prio, id(ns), ns))

    logger.info(f"Dijkstra扩展{expanded}节点, 剪枝{pruned}次, 找到{len(results)}条路线")
    return results


def format_results(routes, origin_city, dest_city, depart_date, arrival_date,
                   depart_earliest, arrive_latest):
    from .loader import _extract_city

    route_list = []
    for i, r in enumerate(routes):
        stns = [r["segments"][0]["from"]] if r["segments"] else []
        for seg in r["segments"]:
            stns.append(seg["to"])
        arrival = r["time"].strftime("%Y-%m-%d %H:%M")
        depart = r["segments"][0]["dep_dt"] if r["segments"] else arrival
        total_dur = sum(seg["dur"] for seg in r["segments"])
        cities = []
        for s in stns:
            c = _extract_city(s)
            if not cities or c != cities[-1]:
                cities.append(c)

        route_list.append({
            "id": i + 1,
            "transfers": r["hops"],
            "cities": cities,
            "stations": stns,
            "depart": depart,
            "arrival": arrival,
            "duration": total_dur,
            "segments": r["segments"],
        })

    route_list.sort(key=lambda x: x["arrival"])

    return {
        "params": {
            "origin": origin_city, "dest": dest_city,
            "depart_date": depart_date, "arrival_date": arrival_date,
            "depart_after": depart_earliest, "arrive_before": arrive_latest,
        },
        "stats": {
            "routes": len(route_list),
            "direct": sum(1 for r in route_list if r["transfers"] == 0),
            "transfer": sum(1 for r in route_list if r["transfers"] > 0),
        },
        "routes": route_list,
    }