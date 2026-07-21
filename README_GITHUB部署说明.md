# V7 Pro GitHub 全自动版

## 一、上传

把压缩包内的所有文件上传到 GitHub 仓库根目录，必须保留 `.github/workflows/stock_auto.yml`。

## 二、开启 Actions

进入仓库的 **Actions** 页面，允许工作流运行。然后打开 **V7 Pro Stock Auto Run**，点击 **Run workflow** 做第一次手动测试。

## 三、开启 Pages

进入 **Settings → Pages**，在 **Build and deployment → Source** 选择 **GitHub Actions**。

发布后首页通常为：

- 项目仓库：`https://用户名.github.io/仓库名/`
- 用户主页仓库：`https://用户名.github.io/`

程序会自动生成：

- `mobile_latest.html`：最新报告
- `history/YYYYMMDD_HHMM_SS.html`：历史报告
- `latest_url.txt`：最新固定入口
- `latest_manifest.json`：最新历史版本和时间
- `status.json`：本次运行状态

## 四、自动运行时间

工作日北京时间：14:00、14:20、14:40、14:45、14:50、14:55、15:00。

GitHub 定时任务可能比设定时间延迟几分钟，这是平台调度特性。

## 五、修改持仓和人工判断

直接在仓库编辑：

- `data/my_positions.csv`
- `config/human_view.json`
- `data/stock_pool_seed.csv`
- `data/market_pool.csv`

提交后，下次运行自动生效。

## 六、失败保护

如果腾讯行情临时失败或程序异常：

- 不覆盖上一次成功的 `mobile_latest.html`
- `status.json` 写入失败状态
- `github_last_error.txt` 保存完整错误
- Pages 仍然显示上一次成功报告

## 七、手机读取

你原来的读取方式仍可继续使用：先读取 `latest_url.txt` 或 `latest_manifest.json`，再打开其中的网址。
