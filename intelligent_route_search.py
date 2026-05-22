"""
智能路线搜索 - 基于Dijkstra算法
以时间为优化目标，从train_stations.json直接搜索
"""

import json
import heapq
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "super_traveller_mcp" / "data"

MIN_TRANSFER_TIME = 0
MAX_TRANSFERS = 50
ORIGIN_CITY = "北京"
DEST_CITY = "合肥"
DEPART_DATE = "2026-05-31"
ARRIVAL_DATE = "2026-06-01"
DEPART_EARLIEST = "21:00"
ARRIVAL_LATEST = "12:00"

def _to_minutes(t: str) -> int:
    h, m = t.strip().split(":")
    return int(h) * 60 + int(m)


SAME_CITY_TRANSFER_MINUTES = 0


def my_leg(legs, frm, to, stn_city,t):
    """获取从frm到to的班次，支持同城中转"""
    direct = legs.get((frm, to),[])
    if stn_city.get(frm) and stn_city.get(frm) == stn_city.get(to):
        city = stn_city[frm]
        return direct+[{
            "train": f"S-{city}",
            "dep": (t+timedelta(minutes=0)).strftime("%H:%M"),
            "arr": (t+timedelta(minutes=30)).strftime("%H:%M"),
            "dur": SAME_CITY_TRANSFER_MINUTES,
            "_from": frm,
            "_to": to,
        }]
    return direct


def add_same_city(data):
    """给data['out']增加所有同城车站的虚拟连接"""
    stn_city = data.get("stn_city", {})
    city_stns = data.get("city_stns", {})
    out = data.get("out", {})
    for stn in list(stn_city.keys()):
        city = stn_city[stn]
        if isinstance(out.get(stn), list):
            out[stn] = set(out[stn])
        for other in city_stns.get(city, []):
            if other != stn:
                out.setdefault(stn, set()).add(other)


def load_train_data(filepaths: list[str | Path] = [DATA_DIR / "train_G.json", DATA_DIR / "train_Z.json", DATA_DIR / "train_D.json", DATA_DIR / "train_T.json", DATA_DIR / "train_C.json"],
                    stn_file: str | Path = DATA_DIR / "12306_station.json"):
    """加载train_stations.json，构建搜索所需的全部索引"""
    leg_index = defaultdict(list)
    outgoing = defaultdict(set)
    stn_to_city = dict()
    city_stns = defaultdict(set)
    with open(DATA_DIR / "train_station.json", encoding="utf-8") as f:
        stn_to_city = json.load(f)
    for filepath in filepaths:
        with open(filepath, encoding="utf-8") as f:
            raw = json.load(f)

        for train in raw.get("trains", []):
            tcode = train["train_code"]
            stns = train.get("stations", [])
            names = [s["station_name"] for s in stns]

            for i, fstn in enumerate(names):
                fdep = stns[i].get("depart_time", "")
                if not fdep or fdep == "----":
                    continue
                for j in range(i + 1, len(names)):
                    tarr = stns[j].get("arrive_time", "")
                    if not tarr or tarr == "----":
                        continue
                    sm = _to_minutes(fdep)
                    am = _to_minutes(tarr)
                    if am < sm:
                        am += 1440
                    dur = am - sm
                    leg_index[(fstn, names[j])].append({
                        "train": tcode,
                        "dep": fdep,
                        "arr": tarr,
                        "dur": dur,
                        "_from": fstn, "_to": names[j],
                    })
                    outgoing[fstn].add(names[j])

        total_legs = sum(len(v) for v in leg_index.values())

        logger.info(f"加载 {len(raw.get('trains', []))} 趟车次, "
                    f"{total_legs} 条站对, {len(stn_to_city)} 个车站")

    return {
        "legs": dict(leg_index),
        "out": {k: list(v) for k, v in outgoing.items()},
        "stn_city": stn_to_city,
        "city_stns": {k: list(v) for k, v in city_stns.items()},
    }


def dijkstra_search(data: dict) -> list:
    """简单Dijkstra搜索，以到达时间为优先级
    
    返回所有可行路线，每条路线格式:
    {"segments": [{train, from_stn, to_stn, dep, arr, dur}],
     "arrive_time": datetime,
     "hops": int}
    """
    legs = data["legs"]
    out = data["out"]
    stn_city = data["stn_city"]
    city_stns = data["city_stns"]

    origin_stns = city_stns.get(ORIGIN_CITY, [ORIGIN_CITY])
    dest_stns = set(city_stns.get(DEST_CITY, [DEST_CITY]))

    start_dt = datetime.strptime(f"{DEPART_DATE} {DEPART_EARLIEST}", "%Y-%m-%d %H:%M")
    deadline = datetime.strptime(f"{ARRIVAL_DATE} {ARRIVAL_LATEST}", "%Y-%m-%d %H:%M")

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
        
        if stn in best and t == best[stn]:
            pruned += 1
            continue

        best[stn] = t

        if hops >= MAX_TRANSFERS:
            continue

        for to_stn in out.get(stn, []):
            if to_stn in s.get("visited", set()):
                continue

            for leg in my_leg(legs, stn, to_stn, stn_city,t):
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
                prio = (arr_dt-start_dt).total_seconds()
                heapq.heappush(queue, (prio, id(ns), ns))

    logger.info(f"Dijkstra扩展{expanded}节点, 剪枝{pruned}次, 找到{len(results)}条路线")
    return results


def format_results(routes: list) -> dict:
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
            cities.append(s)

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
            "origin": ORIGIN_CITY, "dest": DEST_CITY,
            "depart_date": DEPART_DATE, "arrival_date": ARRIVAL_DATE,
            "depart_after": DEPART_EARLIEST, "arrive_before": ARRIVAL_LATEST,
        },
        "stats": {
            "routes": len(route_list),
            "direct": sum(1 for r in route_list if r["transfers"] == 0),
            "transfer": sum(1 for r in route_list if r["transfers"] > 0),
        },
        "routes": route_list,
    }


def main():
    import sys
    data_files = [
        DATA_DIR / "train_G.json",
        DATA_DIR / "train_Z.json",
        DATA_DIR / "train_D.json",
        DATA_DIR / "train_T.json",
        DATA_DIR / "train_C.json",
    ]
    for i, a in enumerate(sys.argv):
        if a == "--data" and i + 1 < len(sys.argv):
            data_files = [BASE_DIR / sys.argv[i + 1]]
    data = load_train_data(data_files)
    add_same_city(data)

    start = datetime.now()
    routes = dijkstra_search(data)
    elapsed = (datetime.now() - start).total_seconds()

    result = format_results(routes)

    out_path = BASE_DIR / "route_search_result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"  搜索完成! 耗时{elapsed:.2f}秒")
    print(f"  结果已保存: {out_path}")
    print(f"{'=' * 60}")

    s = result["stats"]
    print(f"\n统计: {s['routes']}条路线 (直达{s['direct']}, 中转{s['transfer']})")

    for r in result["routes"]:
        print(f"\n  路线 #{r['id']}: {' → '.join(r['cities'])}")
        print(f"    {r['depart']} → {r['arrival']} ({r['duration']}分钟)")
        for seg in r["segments"]:
            print(f"    {seg['train']}: {seg['from']} {seg['dep']} → {seg['to']} {seg['arr']}")


if __name__ == "__main__":
    main()