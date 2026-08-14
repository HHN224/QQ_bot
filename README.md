# QQ 群聊每日简报

一个只在 Windows 本机运行的 QQ 群聊简报 MVP：把当天复制出的数百条群消息压缩成最多 3 条“必看”和 7 条“可能感兴趣”。同一天可以多次追加，已处理消息不会重复计费或重复展示。

## 当前能力

- 粘贴文字和链接，兼容常见的“发送者 + 时间 + 正文”导出格式；未知格式会按行处理
- SQLite 消息指纹去重与同日增量处理
- 廉价模型初筛，只抓取候选消息中的公开网页，再由较强模型输出结构化 JSON
- 链接抓取拦截本机、私网、保留地址和带认证信息的 URL，并限制重定向与页面大小
- 最终输出 0–10 条；不凑数；支持“今天没有必看内容”
- 成功保存简报后删除原始消息正文，失败时保留以便重试；去重指纹继续保留
- 历史简报、搜索、可选反馈、模型与预算设置
- 默认保留历史 30 天，默认月度预算 ¥30
- 未配置 API Key 时使用本地规则回退，方便先验证完整流程

聊天和网页内容始终被当作不可信数据。程序不会提供工具给模型，也不会执行群消息或网页中的命令和提示词。

## 最方便的启动方式

依赖已经准备好时，直接双击项目根目录的 `启动 QQ 群聊每日简报.vbs`。它不会显示命令行窗口，会在后台启动本地服务并自动打开浏览器；重复双击只会重新打开页面，不会重复启动服务。

如果想放到桌面，双击一次 `创建桌面快捷方式.vbs`。以后直接使用桌面的“QQ 群聊每日简报”快捷方式即可。需要手动关闭后台服务时，双击 `停止 QQ 群聊每日简报.vbs`。

首次换到一台新电脑时，双击启动器也会自动准备环境，只是会先提示需要等待一两分钟。

## 命令行启动

需要 Python 3.11+、Node.js 20+ 和 npm。

1. 将 `.env.example` 复制为 `.env`。
2. 在 `.env` 中填写 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、初筛模型和最终模型。API Key 不会通过网页读取或展示。
3. 在 PowerShell 中运行：

```powershell
.\start.ps1
```

首次运行会创建 `.venv`、安装依赖并构建前端，然后打开 `http://127.0.0.1:8000`。服务只监听回环地址，不部署公网。后续依赖与前端没有变化时可以运行：

```powershell
.\start.ps1 -SkipInstall
```

若只想体验流程，可不创建 `.env`；程序会明确标记“本地规则回退”，该结果不等同于正式模型摘要。

## 手动开发

后端：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r .\backend\requirements.txt
Set-Location .\backend
..\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

前端（另一个终端）：

```powershell
Set-Location .\frontend
npm install
npm run dev
```

Vite 开发服务会把 `/api` 转发到本机 8000 端口。

## 支持的粘贴格式

```text
张三 09:31
发现一个开源工具 https://github.com/example/project

09:35 李四：这个版本解决了 timeout 报错
```

```text
2026-08-11 09:31 张三：正文内容
```

不同 QQ 版本导出的文本可能不同。无法识别头部时，每个非空行会作为一条未知发送者消息处理，不要求预先准备历史聊天样本。

## 数据与隐私

- 数据库默认位于 `data/qq_digest.db`，已被 Git 忽略。
- `.env` 已被 Git 忽略。
- 原始消息只存到本次简报成功生成；成功后按日期删除原始正文。
- 为避免重复处理，会保留不可逆 SHA-256 指纹，以及发送者/时间定位元数据。
- 简报正文默认保留 30 天，启动时自动清理过期数据。
- 图片、文件、视频首版不抓取、不理解；若聊天文字提到这些内容，简报只会保留回群定位信息。

## 预算说明

模型响应中的 token 用量会记录到 SQLite。请按照供应商价格填写输入和输出的“人民币/百万 token”单价；本月估算费用达到上限后，后续云端调用立即停止。单价为 `0` 时只能记录 token，无法形成可靠的人民币费用估算。

初筛与最终生成之间也会再次检查预算。若初筛后达到上限，最终调用不会继续，任务会失败并保留原始文本。

## 测试与构建

```powershell
.\.venv\Scripts\python -m pytest .\backend\tests
Set-Location .\frontend
npm run build
```

## 项目结构

```text
backend/app/
  main.py               FastAPI 路由和静态前端托管
  db.py                 SQLite 数据生命周期、去重与预算
  services/parser.py    QQ 文本解析与规范化哈希
  services/fetcher.py   候选网页安全抓取
  services/llm.py       OpenAI 兼容结构化 JSON 调用
  services/pipeline.py  增量处理管线
frontend/src/           React 四区域界面
data/                   本地 SQLite 数据
start.ps1               Windows 单命令启动
```

## MVP 边界

首版不自动读取 QQ 数据库、不登录 QQ、不发送消息、不做 OCR/视频理解、不提供公网部署、多用户系统或模型微调。



<!-- 111 -->