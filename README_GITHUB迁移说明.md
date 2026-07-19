# Stock Decision V5.1.1 GitHub 原核迁移版

这是把昨天已经能正常抓取数据的 V5.1.1 本地程序迁移到 GitHub 的版本。

## 核心原则

- `main.py` 的腾讯行情、ETF轮动、动态股票池、评分和HTML逻辑保持原样。
- `update_risk_data.py` 保持原样；新闻接口限流时不会阻止主报告生成。
- 新增 `cloud_runner.py`，只负责依次运行原程序并把结果复制到 `site/`。
- 新增 GitHub Actions 和 GitHub Pages 发布。
- 没有改成 Yahoo，也没有重写历史行情算法。

## 本地运行

双击：

`RUN_LOCAL.cmd`

它首先直接使用你电脑中可运行的 `python` 命令。

## GitHub 更新

1. 将本文件夹内部全部内容覆盖到本地 `decision` 仓库。
2. GitHub Desktop 中填写 Summary：`Restore V5.1.1 original core`
3. 点击 `Commit to main`
4. 点击 `Push origin`
5. GitHub Actions 中运行 `Stock Decision V5.1.1 Original Core`

## 页面文件

运行后：

- 原始本地页面：`output/mobile_latest.html`
- GitHub Pages 页面：`site/index.html`
- 手机清单：`output/latest_decision.txt`

## 真实持仓

修改：

`data/my_positions.csv`

## 说明

本包的目标不是继续发明新算法，而是恢复昨天已验证的本地核心，只增加云端运行能力。
