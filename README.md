# StockDecisionSystem V6 GitHub全自动版

本项目以腾讯财经批量行情作为股票、指数和ETF的主要实时数据源。东方财富仅负责自动发现，失败不会阻断核心池和持仓分析。

## 自动运行时间

北京时间工作日：

- 14:00
- 14:20
- 14:40
- 14:45
- 14:50
- 14:55
- 15:00

也可以进入 **Actions → Stock Decision Auto → Run workflow** 手工运行。

## GitHub Pages输出

程序自动生成：

- `mobile_latest.html`：最新报告
- `history/YYYYMMDD_HHMM_SS.html`：历史报告
- `latest_url.txt`：最新报告地址，与原GitHub格式一致
- `latest_manifest.json`：最新版本信息
- `status.json`：最近运行状态和行情覆盖率
- `latest_decision.txt`：文字决策
- `buy_candidates.csv`：买入候选
- `position_decisions.csv`：持仓处理
- `etf_rotation.csv`：ETF轮动

## 第一次上传

1. 在GitHub新建公开仓库，建议仓库名仍使用 `stock`。
2. 将本压缩包内的全部文件上传到仓库根目录，不能再套一层文件夹。
3. 进入仓库 `Settings → Pages`。
4. 在 `Build and deployment` 中选择 `Source: GitHub Actions`。
5. 进入 `Actions`，手工运行一次 `Stock Decision Auto`。
6. 成功后访问：

   `https://你的GitHub用户名.github.io/仓库名/mobile_latest.html`

原有访问方式仍可使用：

`https://你的GitHub用户名.github.io/仓库名/latest_url.txt`

## 持仓维护

编辑：

`data/my_positions.csv`

格式：

```csv
code,name,cost,shares,tag
600536,中国软件,成本价,200,hold
```

## 重要说明

GitHub定时任务不是证券交易所级实时服务，可能延迟数分钟。若本次取数失败，工作流会保留上一次成功生成的报告，并在 `status.json` 中记录失败状态。
