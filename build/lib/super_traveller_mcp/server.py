import logging
import sys
from datetime import datetime

from mcp.server.fastmcp import FastMCP

from super_traveller_mcp.engine import dijkstra_search, format_results
from super_traveller_mcp.loader import build_data, _extract_city

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA = None


def get_data():
    global DATA
    if DATA is None:
        logger.info("正在加载列车数据...")
        DATA = build_data()
        logger.info(f"数据加载完成: {len(DATA['stn_city'])} 个车站, "
                    f"{len(DATA['legs'])} 条站对")
    return DATA


server = FastMCP(
    name="super-traveller",
    instructions="智能列车路线搜索MCP服务. 基于Dijkstra算法搜索最优乘车路线.",
)


@server.tool()
def search_routes(
    origin_city: str,
    dest_city: str,
    depart_date: str = "2026-05-31",
    arrival_date: str = "2026-06-01",
    depart_earliest: str = "00:00",
    arrive_latest: str = "23:59",
    max_transfers: int = 5,
) -> str:
    """搜索从出发城市到目的城市的列车路线

    Args:
        origin_city: 出发城市名, 如 "北京"
        dest_city: 目的城市名, 如 "上海"
        depart_date: 出发日期, 格式 "yyyy-MM-dd"
        arrival_date: 最晚到达日期, 格式 "yyyy-MM-dd"
        depart_earliest: 最早出发时间, 格式 "HH:MM"
        arrive_latest: 最晚到达时间, 格式 "HH:MM"
        max_transfers: 最大中转次数, 默认5
    """
    try:
        datetime.strptime(f"{depart_date} {depart_earliest}", "%Y-%m-%d %H:%M")
        datetime.strptime(f"{arrival_date} {arrive_latest}", "%Y-%m-%d %H:%M")
    except ValueError as e:
        return f"日期时间格式错误: {e}"

    data = get_data()

    if origin_city not in data["city_stns"]:
        available = list(data["city_stns"].keys())[:20]
        return f"未找到出发城市 '{origin_city}'. 可用城市示例: {', '.join(available)}"
    if dest_city not in data["city_stns"]:
        available = list(data["city_stns"].keys())[:20]
        return f"未找到目的城市 '{dest_city}'. 可用城市示例: {', '.join(available)}"

    start = datetime.now()
    routes = dijkstra_search(
        data, origin_city, dest_city,
        depart_date, arrival_date,
        depart_earliest, arrive_latest,
        max_transfers=max_transfers,
    )
    elapsed = (datetime.now() - start).total_seconds()

    result = format_results(
        routes, origin_city, dest_city,
        depart_date, arrival_date,
        depart_earliest, arrive_latest,
    )

    lines = [f"搜索完成! 耗时{elapsed:.2f}秒"]
    s = result["stats"]
    lines.append(f"统计: {s['routes']}条路线 (直达{s['direct']}, 中转{s['transfer']})")

    for r in result["routes"][:20]:
        lines.append("")
        lines.append(f"  路线 #{r['id']}: {' → '.join(r['cities'])}")
        lines.append(f"    {r['depart']} → {r['arrival']} ({r['duration']}分钟)")
        for seg in r["segments"]:
            lines.append(f"    {seg['train']}: {seg['from']} {seg['dep']} → {seg['to']} {seg['arr']}")

    if len(result["routes"]) > 20:
        lines.append(f"\n... 共 {len(result['routes'])} 条路线, 仅显示前20条")

    return "\n".join(lines)


@server.tool()
def get_available_cities() -> str:
    """获取所有可搜索的城市列表"""
    data = get_data()
    cities = sorted(data["city_stns"].keys())
    lines = [f"共有 {len(cities)} 个可用城市:"]
    for i in range(0, len(cities), 8):
        lines.append("  " + ", ".join(cities[i:i+8]))
    return "\n".join(lines)


@server.tool()
def get_city_stations(city: str) -> str:
    """获取指定城市的所有车站

    Args:
        city: 城市名, 如 "北京"
    """
    data = get_data()
    stations = data["city_stns"].get(city)
    if not stations:
        return f"未找到城市 '{city}'"
    return f"{city}的车站: {', '.join(sorted(stations))}"


@server.tool()
def get_data_stats() -> str:
    """获取列车数据统计信息"""
    data = get_data()
    total_trains = 0
    for fp in ["train_g.json", "train_z.json", "train_d.json", "train_C.json"]:
        import json
        from importlib.resources import files
        try:
            with open(str(files("super_traveller_mcp.data") / fp), encoding="utf-8") as f:
                raw = json.load(f)
                total_trains += len(raw.get("trains", []))
        except Exception:
            pass

    cities = len(data["city_stns"])
    stations = len(data["stn_city"])
    leg_pairs = len(data["legs"])

    return (f"列车数据统计:\n"
            f"  车次总数: {total_trains}\n"
            f"  车站数: {stations}\n"
            f"  城市数: {cities}\n"
            f"  站对(直达关系)数: {leg_pairs}")


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print("super-traveller-mcp - 智能列车路线搜索MCP服务")
        print("")
        print("用法:")
        print("  super-traveller-mcp         以stdio模式启动MCP服务")
        print("  super-traveller-mcp --help   显示帮助信息")
        return

    logger.info("启动 super-traveller MCP 服务 (stdio)...")
    server.run(transport="stdio")


if __name__ == "__main__":
    main()