import json
import logging
from collections import defaultdict
from importlib.resources import files

logger = logging.getLogger(__name__)

CITY_KEYWORDS = sorted([
    "北京", "天津", "上海", "重庆",
    "合肥", "南京", "杭州", "广州", "深圳", "成都",
    "武汉", "西安", "郑州", "济南", "沈阳", "哈尔滨",
    "昆明", "贵阳", "南宁", "兰州", "乌鲁木齐",
    "石家庄", "太原", "呼和浩特", "银川", "西宁", "拉萨",
    "阜阳", "六安", "蚌埠", "芜湖", "安庆", "马鞍山",
    "徐州", "常州", "无锡", "苏州", "镇江",
    "扬州", "南通", "淮安", "盐城", "泰州",
    "宁波", "温州", "嘉兴", "绍兴", "金华",
    "青岛", "烟台", "潍坊", "临沂", "济宁",
    "洛阳", "南阳", "新乡", "开封", "安阳",
    "株洲", "湘潭", "衡阳", "岳阳", "常德",
    "九江", "赣州", "上饶", "宜春", "吉安",
    "霍邱", "巢湖",
    "德州", "沧州", "保定", "邯郸", "秦皇岛",
    "大连", "鞍山", "抚顺", "锦州",
    "大庆", "齐齐哈尔", "牡丹江",
    "泉州", "厦门", "福州",
    "珠海", "佛山", "东莞", "惠州",
    "廊坊", "涿州",
    "张家口", "张家港",
], key=len, reverse=True)


def _to_minutes(t: str) -> int:
    h, m = t.strip().split(":")
    return int(h) * 60 + int(m)


def _extract_city(station_name: str) -> str:
    for city in CITY_KEYWORDS:
        if city in station_name:
            return city
    if len(station_name) >= 2:
        return station_name[:2]
    return station_name


def _load_single_json(filepath):
    with open(filepath, encoding="utf-8") as f:
        return json.load(f)


def load_train_data(data, filepath):
    raw = _load_single_json(filepath)

    leg_index = defaultdict(list, data.get("legs", {}))
    outgoing = defaultdict(set, {k: set(v) for k, v in data.get("out", {}).items()})
    stn_to_city = dict(data.get("stn_city", {}))
    city_stns = defaultdict(set, {k: set(v) for k, v in data.get("city_stns", {}).items()})

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

    for stn in set().union(*[set(v) for v in outgoing.values()],
                           *[k[0] for k in leg_index],
                           *[k[1] for k in leg_index]):
        city = _extract_city(stn)
        stn_to_city[stn] = city
        city_stns[city].add(stn)

    logger.info(f"加载 {len(raw.get('trains', []))} 趟车次, "
                f"{total_legs} 条站对, {len(stn_to_city)} 个车站")

    return {
        "legs": dict(leg_index),
        "out": {k: list(v) for k, v in outgoing.items()},
        "stn_city": stn_to_city,
        "city_stns": {k: list(v) for k, v in city_stns.items()},
    }


def build_data():
    data_dir = files("super_traveller_mcp.data")
    data_files = [
        data_dir / "train_g.json",
        data_dir / "train_z.json",
        data_dir / "train_d.json",
        data_dir / "train_C.json",
    ]
    data = {
        "legs": defaultdict(list),
        "out": defaultdict(set),
        "stn_city": {},
        "city_stns": defaultdict(set),
    }
    for fp in data_files:
        data = load_train_data(data, str(fp))
    add_same_city(data)
    return data


def add_same_city(data):
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