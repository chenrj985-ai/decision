# V7 Pro GitHub 稳定运行版

## 一、上传方式

将压缩包解压后，把内部全部文件上传到 GitHub 仓库根目录。  
仓库根目录必须直接看到：

```text
.github/
app/
config/
data/
output/
public/
github_run.py
verify_outputs.py
main.py
requirements.txt
```

不要只上传 ZIP 文件，也不要多套一层文件夹。

## 二、第一次运行

1. 进入仓库的 `Actions`。
2. 选择 `V7 Pro Stock Auto Run`。
3. 点击 `Run workflow`。
4. 等待运行结束。
5. 在仓库根目录查看 `output/`。

成功后，`output/` 至少包含：

```text
mobile_latest.html
latest_decision.txt
buy_candidates.csv
position_decisions.csv
all_scores.csv
etf_rotation.csv
index_snapshot.csv
market_snapshot.csv
source_health.json
history/
```

失败时也会生成：

```text
output/github_last_error.txt
status.json
```

## 三、自动运行时间

GitHub 使用 UTC，本工作流已换算为北京时间：

- 工作日 11:00
- 工作日 14:00
- 工作日 14:20
- 工作日 14:40
- 工作日 14:50

## 四、开启 Pages

进入：

```text
Settings → Pages → Build and deployment → Source
```

选择：

```text
GitHub Actions
```

Pages 发布内容来自 `public/`，不会把源代码作为网页发布。

## 五、常用地址

项目仓库页面通常为：

```text
https://用户名.github.io/仓库名/
```

固定最新报告：

```text
https://用户名.github.io/仓库名/mobile_latest.html
```

程序接口：

```text
latest_url.txt
latest_manifest.json
status.json
```

## 六、修改持仓

编辑：

```text
data/my_positions.csv
```

修改后提交，再在 Actions 中手动运行一次即可。

## 七、人工盘面设置

编辑：

```text
config/human_view.json
```

注意 JSON 中不能添加注释，最后一项后面不要多写逗号。
