# Stock Decision System V6 正式版

这是可直接部署到 GitHub Actions + GitHub Pages 的云端股票辅助决策系统。

## 它会自动生成并保留

- `site/index.html`：手机网页
- `site/latest.json`：网页数据
- `output/latest.json`：最新完整结果
- `output/history/*.json`：历史快照
- `logs/latest.log`：运行日志
- `reports/latest_summary.txt`：简要结论
- `cache/news.json`：新闻缓存

所有目录已放置 `.gitkeep`，因此第一次上传后就能在 GitHub 中看见。第一次 Actions 成功后，生成文件会被自动提交回仓库。

## 上传更新

将本文件夹中的全部内容复制到本地 `decision` 仓库根目录，覆盖旧文件；在 GitHub Desktop 中：

1. Summary 填 `Replace with V6 formal`
2. 点击 `Commit to main`
3. 点击 `Push origin`

## GitHub 设置

1. `Settings → Actions → General → Workflow permissions → Read and write permissions`
2. `Settings → Pages → Source → GitHub Actions`
3. `Actions → Stock Decision V6 Formal → Run workflow`

## 修改持仓

编辑 `data/my_positions.csv`。真实持仓若不希望公开，请不要把仓库设为 Public，或将真实持仓改用私有数据方案。

## 本地运行

双击 `scripts/run_local.cmd`。

> 本系统只提供量化辅助信息，不构成投资建议。
