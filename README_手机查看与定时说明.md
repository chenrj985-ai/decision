# 股票决策 V5.1.2 手机查看最终版

本版本保留 V5.1.1 已验证的行情、ETF轮动、动态股票池和评分逻辑，只升级手机页面与 GitHub 定时运行。

## 北京时间运行安排（工作日）

- 11:10
- 13:20
- 13:50
- 14:20
- 14:40
- 14:50
- 14:56

YML 已换算为 UTC：

- 03:10
- 05:20、05:50
- 06:20、06:40、06:50、06:56

## 手机查看

GitHub Actions 成功运行并发布 Pages 后，固定地址通常为：

`https://你的GitHub用户名.github.io/仓库名/`

例如仓库名为 `decision`，用户名为 `chenrj985-ai`，地址就是：

`https://chenrj985-ai.github.io/decision/`

把该网页添加到手机主屏幕，以后像 App 一样直接打开。

## 手机页面新增

- 首页直接显示市场模式、风险、最高仓位和候选数量
- “今日候选”和“我的持仓”默认展开
- 其他长表格折叠，减少手机滚动
- 底部固定导航
- 一键刷新
- 极简文字版入口
- 数据超过 90 分钟自动提示可能过期

## 上传步骤

将本文件夹内部全部内容复制到本地 GitHub 仓库目录，覆盖旧文件，然后在 GitHub Desktop：

1. Commit to main
2. Push origin
3. GitHub 网页进入 Actions
4. 手动运行 `Stock Decision Mobile Final`

## Pages 设置

GitHub 仓库：

Settings → Pages → Source 选择 GitHub Actions

运行成功后，在 Actions 的 Deploy GitHub Pages 步骤或仓库 Settings → Pages 中可看到固定网址。
