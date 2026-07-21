StockDecisionSystem V6 腾讯主源完整工程
========================================

一、这次是完整工程
不是补丁，也不是只有一个主文件。程序包括：
- app/providers.py：腾讯实时行情、东方财富自动发现
- app/risk.py：市场风险和ETF轮动
- app/scoring.py：个股评分、爆雷指数、持仓建议
- app/events.py：事件风险
- app/state.py：动态池、风险池、推荐跟踪
- app/report.py：HTML报告
- app/pipeline.py：完整运行流程
- main.py：Windows入口

二、数据源
1. 股票、指数、ETF实时行情全部以腾讯财经为主。
2. 东方财富只承担全市场自动发现，失败不影响核心池和持仓。
3. 腾讯失败时可使用15分钟以内的行情缓存。
4. 行情覆盖率低于75%时自动关闭新开仓，只保留观察和持仓分析。
5. 不依赖Yahoo，也不要求AKShare。

三、首次运行
1. 完整解压ZIP。
2. 双击 INSTALL_V6.cmd。
3. 双击 TEST_TENCENT.cmd，确认能获取行情。
4. 双击 RUN_V6.cmd。

四、主要文件
- data\my_positions.csv：持仓
- data\stock_pool_seed.csv：核心股票池
- data\market_pool.csv：指数和ETF池
- data\event_risk.csv：手工个股风险
- data\global_risk_manual.csv：手工国际事件
- output\mobile_latest.html：最新报告
- output\source_health.json：腾讯行情覆盖率
- logs\last_error.txt：最近一次错误

五、持仓格式
code,name,cost,shares,tag
600536,中国软件,成本价,200,hold

六、爆雷指数
程序会对以下情况加风险分：
- 当日涨幅超过6%、7%或接近涨停
- 换手率异常
- 量比异常
- 冲高回落
- 所属ETF为D或E
- 手工事件风险
爆雷指数达到60，非持仓股票直接禁止推荐。

七、运行结果
- buy_candidates.csv：正式新开仓候选
- position_decisions.csv：持仓建议
- etf_rotation.csv：ETF强弱
- all_scores.csv：全部评分
- mobile_latest.html：手机和电脑均可查看的页面

本程序是交易纪律与风险辅助工具，不保证收益。
