# Windows 本地 QQ 群聊记录自动获取可行性研究

研究日期：2026-08-11  
目标环境：Windows、NTQQ、本地单用户“QQ 群聊每日简报”  
结论置信度：官方机器人实时接入为高；既有历史记录的无侵入自动导入为低

## 结论先行

在“不冒主账号封禁风险、不注入 QQ、不解密本地数据库、不部署公网”的约束下，**可以安全自动获取启用之后的新群消息，但不能安全、稳定地直接补拉已有历史聊天记录**。

最合适的路线是新增一个可选的 **QQ 官方机器人只收不发接入**：把机器人加入目标群，由群主在 QQ 中开启“接收所有消息”，本地程序通过官方 WebSocket Gateway 接收后续群消息。QQ 官方文档现在明确提供 `GROUP_MESSAGE_CREATE` 全量事件；事件包含消息 ID、发送者昵称与群成员 OpenID、文本、群 OpenID、RFC3339 时间及附件信息，足以支撑本项目的文字/链接日报。官方 WebSocket 是从本机主动连到 QQ，无需给本机开放公网回调地址。[群消息（全量模式）](https://bot.q.qq.com/wiki/develop/api-v2/autogen/event/group_message_create.html) · [事件订阅与通知](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/interface-framework/event-emit.html) · [WebSocket 方式](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/event-emit/websocket.html)

但该路径有三个重要限制：

1. 它是一个显式加入群的机器人，不是悄悄读取用户当前登录的个人 QQ；群主需开启“接收所有消息”。
2. 它适合从启用时开始持续收集。所审阅的官方消息 API 是事件推送、发送和撤回模型，没有发现“按群和日期拉取历史消息”的接口；`Resume` 只说明短时断线后按已保存的序列号补发遗漏事件。因此“不能补拉启用前历史”是根据当前公开接口作出的判断。[消息收发概述](https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/overview.html) · [WebSocket 方式](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/event-emit/websocket.html)
3. 需要 QQ 开放平台的 AppID、ClientSecret、机器人权限与群主配合；不是所有群都能由本项目用户自行开启。

因此建议保留现有“复制粘贴”作为兼容入口，同时把官方机器人作为 opt-in 的自动收件箱。**不建议为当前 MVP 接入 NapCat、Lagrange、LiteLoaderQQNT、数据库密钥提取或进程注入。**

## 研究边界与安全约束

本次只进行了官方文档、项目仓库/项目自身文档阅读，以及对本机 QQ 安装和数据文件的只读观察。没有：

- 登录或切换任何 QQ 账号；
- 向好友或群发送任何消息；
- 调用非官方 QQ 协议；
- 读取任何聊天消息行；
- 提取密钥、解密数据库、读取进程内存；
- 修改 QQ 安装目录、加载插件、注入进程；
- 自动点击或操纵 QQ 客户端。

风险评级是工程判断，不等于腾讯对某个工具作出的正式保证，也不是法律意见。

## 方案比较

| 方案 | 能否自动获得新消息 | 能否补已有历史 | 账号风险 | 可维护性 | 对本 MVP 的判断 |
|---|---:|---:|---|---|---|
| QQ 官方机器人全量事件 | 是 | 未发现公开接口 | 低 | 高 | **推荐，可选接入** |
| QQ 官方备份/迁移/导入 | 否，需人工操作 | 可能备份/迁移，但非稳定机器可读导出 | 最低 | 中 | 仅作为用户人工备份，不作为采集 API |
| 直接只读 NTQQ 本地数据库 | 理论上可轮询 | 理论上可能 | 文件读取本身低；解密/密钥提取风险高 | 低 | **不做** |
| UI Automation / 剪贴板 | 半自动且脆弱 | 仅屏幕已加载范围 | 较低 | 低 | 保留人工复制；不建议后台自动抓取 |
| NapCat / QQ Chat Exporter | 是 | 可导出本机已有记录 | 中高且不确定 | 中低 | **不接主账号** |
| Lagrange.Core 等协议登录 | 是 | 视实现而定 | 高且不确定 | 低 | **不做** |
| LiteLoaderQQNT / 客户端插件注入 | 是 | 视插件而定 | 高 | 很低 | **明确排除** |

## 1. QQ 官方机器人开放平台

### 能做什么

QQ 官方文档当前同时列出两种普通群消息事件：

- `GROUP_AT_MESSAGE_CREATE`：用户在群里 @ 机器人时触发；[官方说明](https://bot.q.qq.com/wiki/develop/api-v2/autogen/event/group_at_message_create.html)
- `GROUP_MESSAGE_CREATE`：机器人开启“接收所有消息”后，群里每条消息都会推送，不限于 @ 机器人；[官方说明](https://bot.q.qq.com/wiki/develop/api-v2/autogen/event/group_message_create.html)

全量事件的数据已经覆盖当前日报所需的采集字段：

- `id`：消息 ID；
- `author.username`、`author.member_openid`、`author.member_role`：发送者信息；
- `content`：文字内容；
- `group_openid`：群标识；
- `timestamp`：RFC3339 时间；
- `attachments`、`ark_data`、`msg_elements`：附件、分享卡片和组合消息。

本项目首版可以只保存 `content` 和可验证链接；附件只记录“建议回群查看”。消息事件可能重复推送，官方文档要求结合 `msg_id` 和 `msg_seq` 去重，正好可接入现有哈希去重层。[消息收发概述：消息去重](https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/overview.html)

### 为什么适合“本地但不部署公网”

官方支持 Webhook 和 WebSocket 两种事件接收方式。Webhook 需要 HTTPS 回调地址，而 WebSocket 由本地服务主动连接 `wss://api.bot.qq.com/websocket/`，完成 `Identify`、心跳和断线 `Resume` 即可；因此应用仍只监听 `127.0.0.1`，不需要把 FastAPI 暴露到公网。[事件订阅与通知](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/interface-framework/event-emit.html) · [WebSocket 方式](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/event-emit/websocket.html)

Access Token 由 AppID 和 ClientSecret 换取，默认有效期约两小时，官方要求凭证只能放在服务端，不能放在前端。本项目应把它放在本机 `.env`，继续由 `.gitignore` 排除。[获取访问凭证](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/access-token.html)

### 只读实现边界

为了满足“严格只读”，建议代码层面只实现以下出站调用：

1. 换取 Access Token；
2. 获取 Gateway；
3. WebSocket `Identify` / `Heartbeat` / `Resume`；
4. 接收 `GROUP_MESSAGE_CREATE`。

不要实现发送、撤回、禁言或群管理 API；配置中也不提供这些开关。这样即使聊天内容包含提示词注入，也没有可调用的 QQ 写操作。

### 限制

- 必须创建开放平台机器人，并把机器人显式加入群；这会改变群成员可见状态。
- “接收所有消息”必须在 QQ 侧开启；若用户不是群主或群不允许机器人，就无法使用。
- 公开文档没有显示启用前的历史拉取接口。断线 `Resume` 只补当前会话序列之后的遗漏事件，不是任意日期历史查询。[WebSocket 方式](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/event-emit/websocket.html)
- 官方能力很新，文档在 2026-07 更新，仍应把人工粘贴保留为可靠兜底。[群消息（全量模式）](https://bot.q.qq.com/wiki/develop/api-v2/autogen/event/group_message_create.html)

## 2. 官方客户端备份、迁移与导入

官方客户端中的“备份/恢复/迁移”面向 QQ 客户端之间的数据转移，不应假定其产物是长期稳定、可供第三方解析的 TXT/JSON API。

对本机 Windows QQ `9.9.21.38711` 的安装资源做只读字符串检查，仅发现旧版导入提示：“请通过 6.9.95 及以上版本的 QQ 导出聊天记录，并重新进行导入”；没有发现当前版本可供本项目调用的结构化导出入口。该观察不能证明所有账号、灰度版本或 UI 都没有导出功能，只能说明**不能把它当成稳定集成接口**。

即使用户能在 QQ UI 中手动完成备份或旧版导出，也更适合提供一个“导入用户主动选择的文件”功能，而不是后台监视 QQ 备份目录。实施前应先拿到真实的、由用户主动导出的样例格式；当前项目要求不预先提供历史样本，因此现阶段保持粘贴入口更稳妥。

## 3. 直接只读 NTQQ 本地数据库

### 本机只读观察

在本机 QQ `9.9.21.38711` 的用户数据目录 `Documents/Tencent Files/<uin>/nt_qq/nt_db/` 中观察到：

- `nt_msg.db`，约 180 MB；
- `group_msg_fts.db`，约 57 MB；
- `group_info.db`。

三个文件的前 16 字节都是 `SQLite header 3\0`，而标准 SQLite 魔数应为 `SQLite format 3\0`。用 SQLite 只读 URI / `mode=ro` 查询 `sqlite_master` 时，三个文件也均返回 `DatabaseError: file is not a database`。这说明它们不是可由标准 SQLite 直接读取的普通数据库，至少修改了文件头，并可能同时使用加密页或自定义 codec；仅凭这一现象不能进一步断言具体算法。

测试到此停止：没有复制消息内容、没有尝试密钥提取、没有读进程内存、没有解密，也没有在 QQ 运行时写入数据库。

### 判断

“仅复制数据库快照”本身对账号的网络风控触发面较小，但它不能产出可用消息。下一步若要获得明文，通常会落入逆向格式、提取运行时密钥、挂钩客户端或读取内存，既违背本次安全边界，也会随 QQ 升级频繁失效。

QQ 当前协议也明确限制未经许可对软件反向工程，以及用第三方软件/插件/外挂获取软件或服务数据、干扰组件或通过非腾讯授权工具登录。官方协议页面为 JavaScript 应用，正文可能需浏览器查看：[QQ 软件许可及服务协议](https://rule.tencent.com/rule/preview/46a15f24-e42c-4cb6-a308-2347139b1201)。因此不应把“能找到数据库文件”误解为腾讯提供了受支持的数据接口。

结论：不进入解密研究，不在 MVP 中实现本地数据库扫描器。

## 4. UI Automation 与剪贴板

### 本机只读观察

对 NTQQ 主窗口做只读 UI Automation 枚举时，仅暴露 9 个 `ControlType.Pane`，没有可读取的消息文本，也没有可用的文本/调用模式。没有执行点击、滚动、选择或复制。

这意味着传统 Windows Accessibility/UIA 无法稳定按“群、日期、发送者、正文”提取消息。继续做只能依赖坐标点击、滚动、OCR 或模拟快捷键，容易受到 QQ 更新、缩放、窗口尺寸、虚拟列表和消息类型影响；滚动采集还很难证明无漏页、无重复。

### 判断

- **人工复制粘贴**：风险最低，用户确认了采集范围，继续作为默认入口。
- **半自动复制当前可见区域**：可作为未来辅助工具，但价值有限。
- **后台自动滚动并复制整天消息**：可维护性低，且自动化焦点错误时可能误触输入框或其他控件；不满足本项目“严格只读”的高可信要求。

因此不建议把 UI Automation 作为无人值守每日采集器。

## 5. NapCat 与 QQ Chat Exporter

[NapCatQQ](https://github.com/NapNeko/NapCatQQ) 自称“基于 NTQQ 的 Bot 协议端实现”，提供丰富接口；它不是腾讯官方开放平台。其版本与 QQ 客户端版本紧密耦合，Release 文档会指定推荐的 QQ build，说明客户端升级会带来兼容维护成本。[NapCatQQ Releases](https://github.com/NapNeko/NapCatQQ/releases)

[QQ Chat Exporter](https://github.com/shuakami/qq-chat-exporter) 是基于 NapCat 的本地聊天记录导出工具。项目文档显示它确实能完成用户想要的能力：扫码登录后列出好友和群聊，按时间范围导出 HTML/JSON/TXT/Excel，也支持每天定时导出“昨天”的增量记录。[项目 README](https://github.com/shuakami/qq-chat-exporter) · [使用手册](https://shuakami.github.io/qq-chat-exporter/docs/guide.html)

但它有两种关键运行方式：

- Shell/一键包：运行无界面 QQ 或自带 QQ 环境并扫码/快捷登录；
- Framework 模式：项目文档明确写明“作为插件注入到电脑上现有的桌面版 QQ 中”。[使用手册](https://shuakami.github.io/qq-chat-exporter/docs/guide.html)

因此它可以证明“技术上能导出”，却不能满足本次“别搞到封号”的风险偏好。即使只调用读取接口，底层仍是非官方协议端或客户端挂载；账号风控由底层登录/运行方式决定，并不会因为上层业务只读而消失。

建议：不把 NapCat/QCE 嵌入本项目，也不让用户的常用主账号扫码登录这些组件。如果用户未来主动接受风险，可把 QCE 当作**独立的手动导出工具**，再把它生成的 JSON/TXT 交给本项目导入；这仍不应成为默认或“低风险”方案。

## 6. Lagrange.Core 等非官方协议实现

[Lagrange.Core](https://github.com/LagrangeDev/Lagrange.Core) 的项目说明是“NTQQ Protocol 的纯 C# 实现”，并提供 Bot 框架和 Web 服务适配。这类方案绕过官方开放平台，以普通 QQ 身份连接协议；它能接收更多普通账号消息，但登录、设备指纹、协议变更和服务端风控都不受腾讯官方支持。[项目 README](https://github.com/LagrangeDev/Lagrange.Core)

对当前项目而言，它的收益是“不必让群里出现官方机器人”，代价是把用户主账号交给非官方协议栈。由于用户明确要求避免封号，本次不做登录实验，也不建议集成。

## 7. LiteLoaderQQNT 与客户端插件注入

[LiteLoaderQQNT](https://github.com/LiteLoaderQQNT/LiteLoaderQQNT) 是 QQNT 插件加载器。仓库 README 明确警告：QQ 安全中心可能把它当作“非法外挂工具”，导致设备下线，甚至封禁账号；安装说明还包含绕过 QQNT 文件校验、修改 `package.json` 或修补 QQNT DLL。该仓库已于 2026-05-17 归档为只读。[仓库 README](https://github.com/LiteLoaderQQNT/LiteLoaderQQNT)

这是所有候选里最明确不符合用户风险要求的一类，直接排除，不做任何测试。

## 推荐落地方案

### A. 当前版本：不改采集方式

继续使用粘贴收件箱。这是唯一能覆盖任意既有历史、又不需要账号/群权限变化的低风险方法。

### B. 下一迭代：官方机器人“自动收件箱”

建议把自动接入做成完全可选的第二入口：

1. 用户在 QQ 开放平台创建机器人，并手工把它加入目标群；
2. 群主在 QQ 中开启“接收所有消息”；
3. 用户在本地 `.env` 填写 AppID、ClientSecret；
4. FastAPI 启动只读 WebSocket collector；
5. 收到事件后只提取文字、链接、发送者、时间和回群定位片段；
6. 以官方消息 ID + 群 OpenID 去重，落入现有增量处理管线；
7. 原始消息沿用“成功生成后删除正文、只留不可逆去重指纹”的策略；
8. 配置页明确显示“只能收集启用后的消息”，并保留粘贴入口补历史。

建议额外加两道防线：

- collector 模块不包含任何发送/群管理 HTTP 客户端；
- 对事件正文沿用“不执行消息中的指令”的数据隔离，链接仍只在初筛入选后抓取。

### C. 暂不实施

- 扫描或解密 `nt_msg.db`；
- 读取 QQ 进程内存或提取密钥；
- NapCat / Lagrange 主账号登录；
- LiteLoaderQQNT、DLL patch、Framework 注入；
- 坐标/OCR 驱动的整日后台 UI 抓取。

## 最终判断

如果“直接获取”指**无须每天复制，并从现在开始自动收集**，答案是：**可以，优先用 QQ 官方机器人全量群消息事件，且可以保持本地运行、不开放公网。**

如果“直接获取”指**悄悄读取当前个人 QQ 里的任意群和已有历史记录**，答案是：**在当前低封号风险约束下不应做。** 已知可行方案都需要不稳定的数据库解密、非官方协议或客户端注入；UI Automation 又没有暴露可读消息树。最稳妥的产品组合是“官方机器人收未来消息 + 人工粘贴补历史”。

## 一手来源索引

- QQ 机器人官方文档：[群消息（全量模式）](https://bot.q.qq.com/wiki/develop/api-v2/autogen/event/group_message_create.html)
- QQ 机器人官方文档：[群 @ 机器人消息](https://bot.q.qq.com/wiki/develop/api-v2/autogen/event/group_at_message_create.html)
- QQ 机器人官方文档：[消息收发概述](https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/overview.html)
- QQ 机器人官方文档：[事件订阅与通知](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/interface-framework/event-emit.html)
- QQ 机器人官方文档：[WebSocket 方式](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/event-emit/websocket.html)
- QQ 机器人官方文档：[获取访问凭证](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/access-token.html)
- 腾讯规则中心：[QQ 软件许可及服务协议](https://rule.tencent.com/rule/preview/46a15f24-e42c-4cb6-a308-2347139b1201)
- NapCatQQ 项目：[仓库](https://github.com/NapNeko/NapCatQQ) · [Releases](https://github.com/NapNeko/NapCatQQ/releases)
- QQ Chat Exporter 项目：[仓库](https://github.com/shuakami/qq-chat-exporter) · [使用手册](https://shuakami.github.io/qq-chat-exporter/docs/guide.html)
- Lagrange.Core 项目：[仓库](https://github.com/LagrangeDev/Lagrange.Core)
- LiteLoaderQQNT 项目：[仓库](https://github.com/LiteLoaderQQNT/LiteLoaderQQNT)

