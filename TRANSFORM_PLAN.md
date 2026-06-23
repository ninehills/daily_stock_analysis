# Daily Stock Analysis → Hermes Agent 转换方案

## 目标

将 `daily_stock_analysis` 仓库转换为 Hermes Agent 可调用的股票分析系统：

1. **股票信息获取** → 独立 CLI 工具（带 SQLite 缓存）
2. **分析逻辑** → Hermes Skills（15 个策略 skill + 1 个编排 skill）
3. **历史数据** → SQLite 数据库（分析结果 + 持仓信息）

---

## 一、功能点清单

### F1: CLI 股票信息工具 `stock-info`

| 编号 | 功能点 | 描述 |
|------|--------|------|
| F1.1 | 实时行情查询 | `stock-info quote <code>` 返回实时价格、涨跌幅、换手率等 |
| F1.2 | 历史日线查询 | `stock-info history <code> --days 60` 返回 OHLCV 数据 |
| F1.3 | 股票名称解析 | `stock-info resolve <name>` 通过名称/拼音查找股票代码 |
| F1.4 | 大盘指数查询 | `stock-info index <market>` 查询上证/深证/创业板等指数 |
| F1.5 | 板块排名查询 | `stock-info sector` 返回板块涨跌排名 |
| F1.6 | 技术指标计算 | `stock-info indicators <code>` 返回 MA/MACD/RSI/KDJ 等 |
| F1.7 | JSON 输出 | 所有命令支持 `--json` 输出结构化数据供 Hermes 解析 |
| F1.8 | SQLite 缓存 | 自动缓存查询结果，避免重复网络请求 |

### F2: 分析 Skills（15 个策略）

| 编号 | Skill 名称 | 策略 | 来源 YAML |
|------|-----------|------|-----------|
| F2.1 | `stock-bull-trend` | 默认多头趋势 | bull_trend.yaml |
| F2.2 | `stock-chan-theory` | 缠论 | chan_theory.yaml |
| F2.3 | `stock-wave-theory` | 波浪理论 | wave_theory.yaml |
| F2.4 | `stock-emotion-cycle` | 情绪周期 | emotion_cycle.yaml |
| F2.5 | `stock-dragon-head` | 龙头策略 | dragon_head.yaml |
| F2.6 | `stock-hot-theme` | 热点题材 | hot_theme.yaml |
| F2.7 | `stock-shrink-pullback` | 缩量回踩 | shrink_pullback.yaml |
| F2.8 | `stock-volume-breakout` | 放量突破 | volume_breakout.yaml |
| F2.9 | `stock-ma-golden-cross` | 均线金叉 | ma_golden_cross.yaml |
| F2.10 | `stock-box-oscillation` | 箱体震荡 | box_oscillation.yaml |
| F2.11 | `stock-one-yang-three-yin` | 一阳三阴 | one_yang_three_yin.yaml |
| F2.12 | `stock-event-driven` | 事件驱动 | event_driven.yaml |
| F2.13 | `stock-expectation-repricing` | 预期重定价 | expectation_repricing.yaml |
| F2.14 | `stock-growth-quality` | 成长质量 | growth_quality.yaml |
| F2.15 | `stock-bottom-volume` | 底部放量 | bottom_volume.yaml |
| F2.16 | `stock-analysis` | **编排 Skill**：接收用户请求，选择合适策略并调度分析 |

### F3: SQLite 存储层

| 编号 | 功能点 | 描述 |
|------|--------|------|
| F3.1 | 股票日线数据表 | `stock_daily` 存储历史 OHLCV 及技术指标 |
| F3.2 | 分析结果表 | `analysis_results` 存储每次分析结论(评分/建议/摘要) |
| F3.3 | 持仓信息表 | `positions` 存储用户持仓(代码/成本/数量/时间) |
| F3.4 | 策略元数据表 | `strategy_meta` 存储策略配置与参数 |
| F3.5 | 查询历史表 | `query_log` 记录所有 API 调用日志 |
| F3.6 | 数据过期策略 | 实时行情缓存 TTL=5min，历史日线 TTL=1day |

### F4: 集成能力

| 编号 | 功能点 | 描述 |
|------|--------|------|
| F4.1 | Hermes 工具调用 | CLI 输出 JSON，Hermes 通过 `terminal()` 调用 |
| F4.2 | 策略选择 | skill 根据用户问题自动选择合适的分析策略 |
| F4.3 | 批量分析 | 支持一次分析多只股票 |
| F4.4 | 历史回溯 | 查询某只股票的历史分析记录 |
| F4.5 | 持仓管理 | 记录/查询/更新用户持仓 |

---

## 二、测试用例

### T1: CLI 工具测试

| 编号 | 测试用例 | 输入 | 预期输出 |
|------|----------|------|----------|
| T1.1 | 实时行情-有效代码 | `stock-info quote 600519` | JSON 含 code/name/price/change_percent |
| T1.2 | 实时行情-无效代码 | `stock-info quote 999999` | 错误信息 + exit_code!=0 |
| T1.3 | 历史日线-默认天数 | `stock-info history 600519` | 60 条 OHLCV 记录 |
| T1.4 | 历史日线-指定天数 | `stock-info history 600519 --days 10` | 10 条记录 |
| T1.5 | 名称解析-拼音 | `stock-info resolve guizhoumaotai` | 返回 600519/贵州茅台 |
| T1.6 | 名称解析-中文 | `stock-info resolve 茅台` | 返回 600519/贵州茅台 |
| T1.7 | 名称解析-港股 | `stock-info resolve tencent` | 返回 HK00700/腾讯控股 |
| T1.8 | 大盘指数 | `stock-info index sh` | 返回上证指数数据 |
| T1.9 | 技术指标 | `stock-info indicators 600519` | 含 MA5/MA10/MA20/MACD/RSI |
| T1.10 | JSON 输出格式 | `stock-info quote 600519 --json` | 合法 JSON，可被 jq 解析 |
| T1.11 | 缓存命中 | 连续两次 `stock-info quote 600519` | 第二次速度显著更快 |
| T1.12 | 缓存过期 | 等待 >5min 再次查询 | 重新获取数据（非缓存） |

### T2: SQLite 存储测试

| 编号 | 测试用例 | 输入 | 预期输出 |
|------|----------|------|----------|
| T2.1 | 创建数据库 | 首次运行 | 自动创建 stock.db 及所有表 |
| T2.2 | 保存日线数据 | 写入 stock_daily | 数据正确保存 |
| T2.3 | 日线唯一约束 | 重复写入同 code+date | 自动 upsert，不报错 |
| T2.4 | 保存分析结果 | 写入 analysis_results | 含 score/advice/summary |
| T2.5 | 查询分析历史 | 按 code 查询 | 返回该股所有历史分析 |
| T2.6 | 保存持仓 | 写入 positions | 含 code/cost/shares/date |
| T2.7 | 更新持仓 | 同 code 更新成本价 | 自动 upsert |
| T2.8 | 盈亏计算 | 查询持仓 + 当前价 | 正确计算浮动盈亏 |

### T3: Skill 测试

| 编号 | 测试用例 | 描述 | 预期 |
|------|----------|------|------|
| T3.1 | SKILL.md 格式 | 所有 skill 文件必须有合法 frontmatter | 通过 yaml 解析 |
| T3.2 | skill 加载 | Hermes 能通过 `skill_view()` 加载 | 无报错 |
| T3.3 | 策略选择 | 输入"分析贵州茅台趋势" | 自动路由到 stock-bull-trend |
| T3.4 | 缠论分析 | 输入"用缠论分析 600519" | 路由到 stock-chan-theory |
| T3.5 | 情绪分析 | 输入"600519 情绪如何" | 路由到 stock-emotion-cycle |

### T4: 集成测试

| 编号 | 测试用例 | 描述 | 预期 |
|------|----------|------|------|
| T4.1 | 端到端分析 | Hermes 调用分析贵州茅台 | 返回结构化分析结果 |
| T4.2 | 历史保存 | 分析完成后 | 结果自动存入 SQLite |
| T4.3 | 多策略分析 | 同一股票多策略连续分析 | 各自独立存储 |
| T4.4 | 持仓联动 | 分析持仓股票 | 自动引入持仓成本信息 |

---

## 三、目录结构

```
daily_stock_analysis/
├── dsa_cli/                         # CLI 工具包 (新)
│   ├── __init__.py
│   ├── main.py                      # CLI 入口 (click)
│   ├── stock_info.py                # 股票信息查询
│   ├── indicators.py                # 技术指标计算
│   ├── cache.py                     # SQLite 缓存层
│   └── resolver.py                  # 名称→代码解析
├── dsa_skills/                      # Hermes Skills (新)
│   ├── stock-analysis/SKILL.md      # 编排 skill
│   ├── stock-bull-trend/SKILL.md
│   ├── stock-chan-theory/SKILL.md
│   ├── stock-wave-theory/SKILL.md
│   ├── stock-emotion-cycle/SKILL.md
│   ├── stock-dragon-head/SKILL.md
│   ├── stock-hot-theme/SKILL.md
│   ├── stock-shrink-pullback/SKILL.md
│   ├── stock-volume-breakout/SKILL.md
│   ├── stock-ma-golden-cross/SKILL.md
│   ├── stock-box-oscillation/SKILL.md
│   ├── stock-one-yang-three-yin/SKILL.md
│   ├── stock-event-driven/SKILL.md
│   ├── stock-expectation-repricing/SKILL.md
│   ├── stock-growth-quality/SKILL.md
│   └── stock-bottom-volume/SKILL.md
├── dsa_db/                          # 数据库模块 (新)
│   ├── __init__.py
│   ├── schema.py                    # 表定义
│   ├── stock_repo.py               # 股票数据仓库
│   ├── analysis_repo.py            # 分析结果仓库
│   └── position_repo.py            # 持仓仓库
├── tests/                           # 测试 (扩展)
│   ├── test_cli_stock_info.py
│   ├── test_cli_indicators.py
│   ├── test_db_schema.py
│   ├── test_db_stock_repo.py
│   ├── test_db_analysis_repo.py
│   ├── test_db_position_repo.py
│   └── test_integration.py
├── src/                             # (原仓库代码，保留)
├── data_provider/                   # (原数据源，保留)
├── strategies/                      # (原策略 YAML，保留)
└── requirements-dsa.txt             # 新增依赖
```
