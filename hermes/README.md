# Hermes Agent 集成

## 安装

```bash
cd /path/to/daily_stock_analysis
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/pip install tickflow  # 可选：TickFlow 实时行情
```

配置环境变量（可选）：
```bash
export TICKFLOW_API_KEY="tk_xxxxxxxxxxxxxxxx"
```

## Skill 安装

```bash
cp -r hermes/skills/stock-analysis ~/.hermes/skills/
```

或在 Hermes 中直接加载：
```
/skill stock-analysis
```

## 使用

在 Hermes 中对任意股票进行多策略分析：

> "用缠论和波浪理论分析紫金矿业"
> "分析茅台趋势"
> "300308 情绪怎么样"

## 架构

```
dsa_cli/          CLI 工具
├── main.py       入口（click）：quote/history/indicators/resolve/index/position/analysis/source-status
├── multi_fetcher.py  多源并行获取（6 行情源 + 4 日线源）+ 熔断器
├── circuit_breaker.py 指数退避熔断器（SQLite 持久化）
├── indicators.py  技术指标计算（MA/MACD/RSI/KDJ/BOLL）
└── cache.py       内存缓存

dsa_db/           数据库
├── schema.py      表定义（stock_daily/analysis_results/positions/source_health）
├── stock_repo.py  股票日线仓库
├── analysis_repo.py 分析结果仓库
└── position_repo.py 持仓仓库

hermes/skills/    Hermes Skill
└── stock-analysis/SKILL.md  16 策略内联合并
```

## 测试

```bash
cd /path/to/daily_stock_analysis
mv tests/conftest.py tests/conftest_orig.py
mv tests/conftest_dsa.py tests/conftest.py
.venv/bin/python -m pytest tests/test_db_schema.py tests/test_db_repos.py tests/test_cli_indicators.py tests/test_circuit_breaker.py -v -p no:cacheprovider
mv tests/conftest.py tests/conftest_dsa.py
mv tests/conftest_orig.py tests/conftest.py
```

## 数据源

| 源 | 类型 | 优先级 | 说明 |
|----|------|--------|------|
| tickflow | 行情 | P0 | 付费 API，需 TICKFLOW_API_KEY |
| sohu | 日线 | P0 | 纯 HTTP，免费 |
| sina | 行情 | P1 | 免费，部分 IP 被墙 |
| efinance | 双用 | P2 | 免费，看网络 |
| akshare | 双用 | P3 | 免费，看网络 |
| yfinance | 双用 | P4 | 免费，美股强 |

熔断器：失败自动指数退避（5s→10s→20s…→1天），成功即清零。
