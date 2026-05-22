"""
G列车增量采集器
通过 search.12306.cn 搜索API发现G列车，通过 kyfw.12306.cn 获取经停站详情
增量合并到 train_stations.json
"""
import json
import time
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, ALL_COMPLETED
import logging
from pathlib import Path
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

PREFIX = "T"
SEARCH_API = "https://search.12306.cn/search/v1/train/search"
DETAIL_API = "https://kyfw.12306.cn/otn/queryTrainInfo/query"
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "super_traveller_mcp" / "data"
TRAIN_STATIONS_FILE = DATA_DIR / f"train_{PREFIX}.json"
MAX_WORKERS = 5


def search_trains(keyword: str, date: str = "20260521"):
    """通过搜索API发现车次"""
    try:
        resp = requests.get(SEARCH_API, params={"keyword": keyword, "date": date}, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
        return data.get("data", [])
    except Exception as e:
        logger.warning(f"搜索{keyword}失败: {e}")
        return []


def discover_all_g_trains(date: str = "20260521"):
    """使用树形遍历算法全面发现G列车"""
    all_trains = {}
    expanded = set()
    api_calls = 0

    from collections import deque
    queue = deque([PREFIX])

    while queue:
        keyword = queue.popleft()
        if keyword in expanded:
            continue
        expanded.add(keyword)

        trains = search_trains(keyword, date)
        api_calls += 1
        g_trains = [t for t in trains if t.get("station_train_code", "").startswith(PREFIX)]

        for t in g_trains:
            code = t.get("station_train_code", "")
            if code not in all_trains:
                all_trains[code] = t

        logger.info(f"  搜索{keyword:12s} -> {len(trains):4d}条结果, G车次: {len(g_trains):4d}, 累计: {len(all_trains):5d}")

        if len(g_trains) >= 95:
            for digit in "0123456789":
                next_kw = keyword + digit
                if next_kw not in expanded:
                    queue.append(next_kw)

        time.sleep(0.05)

    logger.info(f"API调用次数: {api_calls}")
    logger.info(f"去重后唯一G车次: {len(all_trains)}个")
    return all_trains


def get_train_detail(train_no: str, train_date: str = "2026-05-21"):
    """通过kyfw API获取列车经停站详情"""
    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': 'https://kyfw.12306.cn/otn/',
    }
    session.get('https://www.12306.cn/index/', headers=headers, timeout=10)
    
    params = {
        'leftTicketDTO.train_no': train_no,
        'leftTicketDTO.train_date': train_date,
        'rand_code': '',
    }
    try:
        resp = session.get(DETAIL_API, params=params, headers=headers, timeout=15)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data.get("status"):
            return None
        stations = data.get("data", {}).get("data", [])
        return stations
    except Exception as e:
        print(f"    [ERROR] 请求异常: {e}")
        return None


def convert_to_standard(train_code: str, stations: list) -> dict:
    """将kyfw API返回转换为标准格式"""
    if not stations:
        return None
    
    station_list = []
    
    for i, s in enumerate(stations):
        station_name = s.get("station_name", "")
        arrive_time = s.get("arrive_time", "----")
        depart_time = s.get("start_time", "----")
        station_list.append({
            "station_name": station_name,
            "arrive_time": arrive_time,
            "depart_time": depart_time,
            "stop_order": i + 1,
        })
    
    return {
        "train_code": train_code,
        "from_station": stations[0]["station_name"],
        "to_station": stations[-1]["station_name"],
        "station_count": len(station_list),
        "stations": station_list,
    }


def load_existing():
    """加载现有数据"""
    try:
        with open(TRAIN_STATIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"meta": {"total_trains": 0}, "trains": []}


def save_data(data):
    """保存数据"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data["meta"]["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data["meta"]["total_trains"] = len(data["trains"])
    data["meta"]["total_station_entries"] = sum(
        t.get("station_count", len(t.get("stations", []))) for t in data["trains"]
    )
    with open(TRAIN_STATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def build_existing_key_set(data):
    """构建已有车次的key集合（按train_code去重）"""
    return {t["train_code"] for t in data["trains"] if t.get("train_code")}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="G列车增量采集器")
    parser.add_argument("--search-date", default="20260521", help="搜索API使用的日期 (YYYYMMDD)")
    parser.add_argument("--detail-date", default="2026-05-21", help="详细API使用的日期 (YYYY-MM-DD)")
    parser.add_argument("--max-workers", type=int, default=MAX_WORKERS, help="并发数")
    parser.add_argument("--batch-size", type=int, default=50, help="每批处理数量")
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info(f"G列车增量采集器")
    logger.info(f"搜索日期: {args.search_date}")
    logger.info(f"详情日期: {args.detail_date}")
    logger.info("=" * 60)
    
    # 1. 加载现有数据
    logger.info("\n[1/4] 加载现有数据...")  
    existing = load_existing()
    existing_keys = build_existing_key_set(existing)
    existing_g_codes = set()
    for t in existing["trains"]:
        code = t.get("train_code", "")
        if code.startswith(PREFIX):
            existing_g_codes.add(code)
    
    g_existing = len(existing_g_codes)
    total_existing = existing["meta"]["total_trains"]
    logger.info(f"  现有数据: {total_existing}趟车次, 其中G列车: {g_existing}个唯一代码")
    
    # 2. 发现所有G列车
    logger.info("\n[2/4] 发现所有G列车...")
    all_g_trains = discover_all_g_trains(args.search_date)
    
    # 3. 找出缺失的
    logger.info("\n[3/4] 比对缺失车次...")
    missing = {}
    for code, info in all_g_trains.items():
        if code not in existing_g_codes:
            train_no = info.get("train_no", "")
            if train_no:
                missing[code] = train_no
    
    logger.info(f"  总G车次: {len(all_g_trains)}")
    logger.info(f"  已有: {len(existing_g_codes)}")
    logger.info(f"  缺失: {len(missing)}")
    
    if not missing:
        logger.info("  没有缺失车次，已完成！")
        return
    
    # 4. 采集缺失车次详情
    logger.info(f"\n[4/4] 采集缺失车次详情 ({len(missing)}趟)...")
    
    missing_items = list(missing.items())
    collected = 0
    failed = 0
    skipped_dup = 0
    
    batch_count = (len(missing_items) + args.batch_size - 1) // args.batch_size
    logger.info(f"  分 {batch_count} 批, 每批 {args.batch_size} 趟, 并发 {args.max_workers}")
    
    for batch_idx in range(batch_count):
        batch_start = batch_idx * args.batch_size
        batch_end = min(batch_start + args.batch_size, len(missing_items))
        batch = missing_items[batch_start:batch_end]
        
        logger.info(f"\n  --- 第{batch_idx+1}/{batch_count}批 ({len(batch)}趟) ---")
        
        # 并发采集
        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            future_to_code = {}
            for code, train_no in batch:
                future = executor.submit(get_train_detail, train_no, args.detail_date)
                future_to_code[future] = code
            
            batch_results = []
            for future in as_completed(future_to_code):
                code = future_to_code[future]
                try:
                    stations = future.result()
                    if stations and len(stations) > 0:
                        entry = convert_to_standard(code, stations)
                        if entry:
                            batch_results.append(entry)
                            collected += 1
                            logger.info(f"  [OK] {code:8s} {stations[0]['station_name']:10s}->{stations[-1]['station_name']:10s} ({len(stations)}站)")
                        else:
                            failed += 1
                            logger.warning(f"  [FAIL] {code:8s} 数据转换失败")
                    else:
                        failed += 1
                        logger.warning(f"  [FAIL] {code:8s} 无经停站数据")
                except Exception as e:
                    failed += 1
                    logger.warning(f"  [FAIL] {code:8s} 异常: {e}")
        
        # 合并到现有数据（每批保存一次，避免丢失）
        if batch_results:
            # 重新加载（可能有其他进程写入）
            current = load_existing()
            current_keys = build_existing_key_set(current)
            
            for entry in batch_results:
                tc = entry.get("train_code", "")
                if tc not in current_keys:
                    current["trains"].append(entry)
                    current_keys.add(tc)
                else:
                    skipped_dup += 1
            
            current["trains"].sort(key=lambda t: (t["train_code"],))
            save_data(current)
            print(f"  => 已保存，当前共{current['meta']['total_trains']}趟车次")
    
        logger.info(f"\n{'=' * 60}")
        logger.info(f"采集完成!")
        logger.info(f"  成功: {collected} 趟")
        logger.info(f"  失败: {failed} 趟")
        logger.info(f"  跳过重复: {skipped_dup} 趟")
    
    final = load_existing()
    logger.info(f"\n最终统计数据:")
    logger.info(f"  总车次: {final['meta']['total_trains']}")
    logger.info(f"  总经停: {final['meta']['total_station_entries']}")              


if __name__ == "__main__":
    main()