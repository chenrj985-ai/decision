V5.1.1 更新说明：新闻模块已改为单次合并查询、6小时缓存、429限流保护和RSS备用源。

股票决策系统 V5.1 AutoRisk（自动风险版）

一、第一次使用
1. 解压整个文件夹，不要只复制某几个文件。
2. 双击 install_once.cmd，等待出现安装完成。
3. 双击 run_once.cmd。

二、以后使用
只双击 run_once.cmd。程序会自动执行：
1. 获取海外市场风险价格；
2. 获取近两日重大国际新闻并去重；
3. 获取持仓和核心股票池的近期公告；
4. 生成自动风险文件；
5. 再运行ETF轮动、持仓和选股决策；
6. 自动打开 output\mobile_latest.html。

三、正常情况下你只需维护
data\my_positions.csv
其中 shares 填股数，2手通常填200。

四、自动生成文件
data\global_risk_auto.csv：全球行情和国际新闻风险
data\event_risk_auto.csv：个股公告风险
logs\risk_update.log：自动风险采集日志

五、容错说明
任何一个新闻或公告接口失败，主程序仍会继续运行，不会因单一网站打不开而闪退。
若所有自动风险源暂时失败，程序会使用ETF、指数和股票行情继续决策；人工文件仍可作为补充：
data\global_risk_manual.csv
data\event_risk.csv

六、重要说明
自动新闻判断用于风险提示，不保证完全正确。程序会把价格、ETF趋势、新闻和公告综合使用，不会仅凭一条新闻直接推荐重仓。
