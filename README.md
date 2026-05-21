# super-traveller-mcp

智能列车路线搜索 MCP 服务 — 基于 Dijkstra 算法搜索最优乘车路线。

内置 **G/D/C/Z** 共计 **9382 趟列车**的时刻表数据，覆盖 **2300+ 城市**、**2697 个车站**，可在毫秒级完成多城市间的最优路线规划。

## 安装

### 前提条件

- Python >= 3.11
- pipx（推荐）或 pip

### 安装步骤

```bash
# 克隆项目后进入目录
cd super-traveller-mcp

# 方法一：pipx 安装（推荐，自动创建隔离环境）
pipx install .

# 方法二：pip 安装
pip install .
```

安装完成后，查看帮助：

```bash
super-traveller-mcp --help
```

## MCP 服务配置

### 在 Cursor 中配置

编辑 `~/.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "super-traveller": {
      "command": "super-traveller-mcp"
    }
  }
}
```

### 在 Claude Desktop 中配置

编辑 `~/Library/Application Support/Claude/claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "super-traveller": {
      "command": "super-traveller-mcp"
    }
  }
}
```

### 手动启动

```bash
# stdio 模式（默认，供 MCP 客户端使用）
super-traveller-mcp
```

## 可用工具

| 工具 | 说明 |
|------|------|
| `search_routes` | 搜索从出发城市到目的城市的列车路线 |
| `get_available_cities` | 获取所有可搜索的城市列表 |
| `get_city_stations` | 查询指定城市的所有车站 |
| `get_data_stats` | 获取列车数据统计信息 |

### search_routes 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `origin_city` | string | 必填 | 出发城市名，如 `"北京"` |
| `dest_city` | string | 必填 | 目的城市名，如 `"上海"` |
| `depart_date` | string | `"2026-05-31"` | 出发日期，格式 `yyyy-MM-dd` |
| `arrival_date` | string | `"2026-06-01"` | 最晚到达日期，格式 `yyyy-MM-dd` |
| `depart_earliest` | string | `"00:00"` | 最早出发时间，格式 `HH:MM` |
| `arrive_latest` | string | `"23:59"` | 最晚到达时间，格式 `HH:MM` |
| `max_transfers` | int | `5` | 最大中转次数 |

## 使用示例

### 搜索路线

```
从北京到合肥，5月31日早6点后出发，当日中午12点前到达
```

MCP 客户端将调用 `search_routes` 工具，结果示例：

```
搜索完成! 耗时0.61秒
统计: 263条路线 (直达0, 中转263)

  路线 #1: 北京 → 石家庄 → 郑州 → 合肥
    2026-05-31 06:08 → 2026-05-31 13:00 (396分钟)
    G6703: 北京西 06:08 → 石家庄 07:37
    G3215: 石家庄 07:38 → 郑州东 09:42
    G3127: 郑州东 09:57 → 合肥南 13:00

  路线 #2: 北京 → 石家庄 → 合肥
    2026-05-31 06:08 → 2026-05-31 13:24 (389分钟)
    G6703: 北京西 06:08 → 石家庄 07:37
    G2811: 石家庄 08:24 → 合肥 13:24
```

### 查询可用城市

```
当前可搜索哪些城市？
```

MCP 客户端将调用 `get_available_cities` 工具，返回所有城市列表。

## 数据说明

| 文件 | 车次类型 | 车次数 |
|------|----------|--------|
| `train_g.json` | G 字头高速铁路 | 3,017 趟 |
| `train_d.json` | D 字头动车组 | 3,187 趟 |
| `train_C.json` | C 字头城际列车 | 2,904 趟 |
| `train_z.json` | Z 字头直达特快 | 274 趟 |

数据来源：12306 公开时刻表数据。

## 搜索算法

使用 **Dijkstra 最短路径算法**，以**到达时间**为优先级进行搜索：

- 支持同城车站虚拟连接（同一城市内不同车站间可步行/地铁换乘，约 30 分钟）
- 自动处理跨日车次（如夜间过夜列车）
- 结果按到达时间排序，优先推荐最早到达的路线
- 支持剪枝优化，避免无效扩展

## 本地开发

```bash
# 克隆项目
git clone <repo-url>
cd super-traveller-mcp

# 安装为 editable 模式
pip install -e .

# 测试数据加载与搜索
python -c "
from super_traveller_mcp.loader import build_data
from super_traveller_mcp.engine import dijkstra_search, format_results

data = build_data()
routes = dijkstra_search(data, '北京', '上海', '2026-05-31', '2026-06-01', '06:00', '12:00')
result = format_results(routes, '北京', '上海', '2026-05-31', '2026-06-01', '06:00', '12:00')
print(result['stats'])
"
```

## License

MIT