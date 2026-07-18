# Stock Decision System V6（GitHub 云端版）

这是一套可直接部署到 GitHub Actions 与 GitHub Pages 的 A 股辅助决策程序。电脑关机后，GitHub 仍会按计划运行并发布手机网页。

## 最快部署

1. 在 GitHub 新建仓库。
2. 点击空仓库蓝框中的 **uploading an existing file**。
3. 解压本压缩包，把解压目录内的全部内容上传。必须包含隐藏目录 `.github`，不要上传 ZIP 本身。
4. 仓库进入 `Settings → Actions → General → Workflow permissions`，选择 `Read and write permissions`。
5. 进入 `Settings → Pages → Source`，选择 `GitHub Actions`。
6. 进入 `Actions → Stock Decision V6 Cloud → Run workflow`，第一次手工运行。
7. 全部绿色后，在 `Settings → Pages` 查看手机网址。

## 日常只改一个文件

`data/my_positions.csv`

格式：

```csv
code,name,cost,shares
300394,天孚通信,271,200
```

`shares` 是股数，2 手通常填写 200。

## 自动运行时间

工作日北京时间：08:45、13:55、14:20、14:40、14:50、14:58。GitHub 定时任务可能有数分钟延迟，不适合秒级交易。

## 输出

- 首页：GitHub Pages 根网址
- `files/latest_decision.txt`
- `files/buy_candidates.csv`
- `files/position_decisions.csv`
- `files/etf_rotation.csv`
- `files/all_scores.csv`
- `status.json`

## 隐私

仓库若公开，`data/my_positions.csv` 和发布网页都可能被别人看到。真实持仓建议使用私有仓库；但 Pages 对私有仓库的可用性取决于 GitHub 账户方案。若必须用公开仓库，请删除成本和股数或改用模拟持仓。

## 风险说明

本程序依赖公开行情和新闻接口。接口中断时会尽量使用缓存及价格风险继续运行。输出仅供辅助判断，不构成收益承诺或投资建议。
