# HomeAsset Companion 项目交接

> 交接基线：v1.4.0 账单导出与纠错版
> 远端仓库：<https://github.com/yymonday/HomeAsset-Companion>

## 项目简介

`device_companion` 是一个 Home Assistant 自定义集成，用 Config Entry 保存设备、家电、虚拟订阅、纪念珍藏和纪念事件。它通过传感器展示陪伴天数、历史投入、当前月度运行成本、耗材和附属项目状态，并通过日历提供周年和到期提醒。集成不连接外部云服务；图片上传是唯一的 HTTP 能力，文件保存到 HA 的 `www/device_companion/`。

## 当前版本与功能完成度

- 当前源码与发布版本：`1.4.0`；本机最后由代理安装并核对的版本为 `1.4.0b1` 加 `ui2` 卡片修复。Config Flow schema version 仍为 `2`。
- 已完成：四种稳定业务类型、Config/Options Flow、生命周期状态、分期计算、耗材与配件、智能耗材监听、续订/换新/生命周期/图片服务、旧 `quick_action` 兼容层、日历、前端详情卡与汇总卡、认证图片上传、V1 → V2 迁移。
- 完成度：v1.4.0 包含账单导出、原账单退款与金额更正、无到期日记账和原风格 UI 修复；未引入 2.0 交易流水或 Subentry 重构。

## 2026-10-03 验收与发布

- 用户明确确认“已经验收，可以发布”，实机验收阶段关闭；该结论来自用户确认，不是本轮重新运行实机写入测试。
- 正式版本统一为 `1.4.0`，升级资源使用 `?v=1.4.0`。发布说明见 [RELEASE_v1.4.0.md](docs/RELEASE_v1.4.0.md)。
- 发布前复核：76 项 Python、11 项前端测试全部通过，Python/前端语法、JSON/YAML、版本一致性与 diff 检查通过。
- 发布执行顺序：本地检查 → 提交并推送 main → GitHub Validate 成功 → 标签与正式 Release → 核对远端提交、标签和发布源码。
- 本轮发布不等同于把用户本机测试安装替换为正式版本；本机可按发布说明通过 HACS 升级。

## 2026-09-30 本机测试版安装

- 后续 UI 修复已同步到本机：旧订阅不再显示“付款覆盖未追踪”，不补造历史流水；仍保留明确账单覆盖不一致的核对提示。订阅操作按钮改为桌面 32px 高、内容居中，窄卡片日期/余天与操作分行，触屏保留 44px 点击高度。
- 此修复仅替换详情卡，资源缓存标识为 `1.4.0b1-ui2`，无需重启 HA；旧卡片备份 `/config/.homeasset-code-backups/card-before-ui-fix-20260930-213339.js`，新文件 SHA256 `9e76ec7eab7f73a82ad368d875e673ac4096600fc05f7db2ac93a2c015dbc946`。实机桌面与 390px 窄屏核对通过，最新回归 76 项 Python、11 项前端测试通过。
- 用户授权更新 `192.168.51.9:7277`，已手动安装 `1.4.0b1`，完成配置检查、完整重启与两张前端资源缓存版本更新。
- 订阅页面正常加载，原有金额、到期日与图片保留，新增区域延续原设计；无到期日订阅显示“记一笔”。
- 安装前本地设置备份 `c187127a`（排除数据库）；旧代码保留在 `/config/.homeasset-code-backups/20260930-210208-v1.3.0`。
- 自动验证：76 项 Python、9 项前端测试通过。重启后仅见原有服务 `idle` 状态兼容警告，未见 HomeAsset 加载错误。
- 安装当日代理未提交真实账单或启用真实提醒；后续实机验收已由用户于 2026-10-03 确认完成，保留 [测试记录](docs/TEST_1.4.0b1.md)。
- 以上为测试安装历史；手动安装可能使 HACS 下载记录仍显示旧版本，正式升级按 v1.4.0 发布说明操作。

## 目录结构

```text
custom_components/device_companion/
├── __init__.py              # 集成 setup/unload、共享服务、上传 API、迁移
├── const.py                 # 域、版本和 Config Entry 字段常量
├── config_flow.py           # Config Flow 与 Options Flow
├── sensor.py                # 主体、耗材、附属项目实体和费用计算
├── calendar.py              # 周年、服务到期和附属项目到期事件
├── services.yaml            # 服务 UI 描述与选择器
├── strings.json             # Config/Options Flow 文本
├── translations/zh-Hans.json
├── frontend/                # 两张 Lovelace 卡片
├── brand/icon.png           # HACS/HA 品牌图标
└── manifest.json
tests/                       # 迁移、服务、耗材和费用回归测试
.github/workflows/validate.yml
```

## 关键数据流

```text
Config Flow / Options Flow
  ├─ entry.data：主体标识、分类、购入日、初始价格、分期、主体图片
  └─ entry.options：类型、生命周期、服务周期/本期费用、订阅附加支出、耗材、附属项目、故事、日历开关
       ├─ sensor.py + hass.states → 主体/耗材/附属传感器
       ├─ calendar.py → 周年和到期事件
       └─ 集成服务/智能耗材监听 → async_update_entry(options) → entry reload

认证上传 → www/device_companion/ → /local/device_companion/... → data/options 保存 URL
```

## 关键实现与持久化

- `__init__.py` 在集成 setup 注册共享 HTTP 路由和服务，在 entry setup 转发 sensor/calendar 平台并注册可选提醒；卸载释放平台和监听，写锁跨 reload 保留，删除记录时清理。
- `async_migrate_entry` 将 V1 旧字段推导为 `kind`、schema version 2、标准生命周期字段和服务周期字段；服务还会补齐 `current_period_cost`，默认保持原始总价。
- `plan_monthly_price`、`service_period_months` 和 `current_period_cost` 位于 `entry.options`：前者是参考月费，中者是当前实际预付覆盖月数，后者是当前周期实际基础付款。传感器按 `current_period_cost / service_period_months` 计算基础月费，不再从到期日跨度猜测 140 元/月或 280 元覆盖几个月。
- `service_payments` 位于 `entry.options`，新建和续订会记录付款类型、实际金额、付款覆盖起止日和覆盖月数。旧条目不伪造历史明细；若付款覆盖结束日早于仍有效的到期日，传感器会给出“付款覆盖需核对”提示。
- `service_charges` 位于 `entry.options`，记录升级差价或额外额度的实际付款。`record_service_charge` 只增加累计投入，不延长到期日；落在当前服务周期的附加支出会计入 `current_period_extra_cost` 和 `current_period_total_cost`，并作为本月一次性增量计入当前月度运行。
- 主体 `unique_id` 使用 `companion_<entry_id>`；耗材/附属项目使用持久化项目 ID；设备标识使用 `(device_companion, entry_id)`。
- 旧 `device_companion.quick_action` 仍保留，并只转发新服务允许的字段。

## 本次 v1.2.0 已完成

- 修复 V1 迁移使用 `CONF_KIND` 但未导入，导致旧 Config Entry 迁移时出现 `NameError`。
- 增加配置入口专用 `CONFIG_SCHEMA`，整理 manifest 字段顺序并统一 manifest、常量、README、前端说明和 changelog 版本为 `1.2.0`。
- 修复续订后当前月度运行仍使用初始价格的问题；保留旧配置兼容回退。
- 修复续订未填写费用时错误使用初始总价的问题；现在优先沿用当前单期费用，并增加连续续订回归测试。
- 续订服务现在拒绝今天及过去的明确到期日；续订和耗材更换服务拒绝负数费用。
- 修复真实 HA setup 中上传目录创建调用 executor 关键字参数导致集成无法加载的问题。
- 智能耗材检测现在会持久化当天去重标记，自动记账和手动提醒共用去重逻辑；后台任务会在实体卸载时取消，状态监听使用 HA callback。
- 兼容旧配置中耗材/附属项目列表为空值或包含非对象记录，避免传感器平台 setup 失败导致主体实体统一显示 `unavailable`。
- 兼容历史订阅条目误保存为 `idle` 的状态；服务实体会按有效订阅处理，不会显示错误的“闲置持有”徽章。
- 增加 `record_service_charge` 服务和卡片入口，区分续订付款与升级/额外额度付款；升级可记录新的后续套餐月费，并保留旧条目无附加支出记录时的兼容回退。
- 增加迁移、续订服务、旧 quick_action、耗材换新、未知耗材 ID 和当前费用计算回归测试。
- 增加 HACS 品牌 `icon.png`，CI 增加 pytest 检查。

## 当前已知问题与风险

- 自动测试已接入真实 Home Assistant fixture，覆盖 Config/Options Flow、Config Entry setup、实体注册、HTTP 上传、服务调用和 reload/unload；用户实际环境中的卡片、Device Registry 展示、通知及完整重启仍需安装后验证。
- 多 Config Entry 测试已确认不同条目的实体互不冲突，卸载一个条目后共享服务和其他条目仍可正常工作。
- 上传接口已通过真实 HA HTTP 测试，覆盖认证配置、签名、大小限制、磁盘异常、随机文件名和实际落盘；孤立文件清理仍待处理。
- `safe_date`/`safe_float` 为兼容旧数据保留默认回退；如果用户数据损坏，可能只能看到默认值，需要后续增加诊断日志而不能直接改变历史口径。列表型旧数据现在会安全过滤非法记录。
- Options Flow 仍允许部分历史字段并存；分类切换和旧字段清理需要先定义兼容矩阵，暂不做破坏性清理。
- 图片文件在删除或替换记录后的清理策略仍未建立，现阶段优先保证上传安全边界和旧 URL 可用。
- 当前项目没有独立 type check；静态检查以 Python/前端语法、pytest、Hassfest 和 HACS 为主。

## 本地开发与测试

在仓库根目录执行：

```bash
python -m pip install -r requirements_test.txt
python -m pytest -q
python -m compileall custom_components/device_companion
node --check custom_components/device_companion/frontend/device-companion-card.js
node --check custom_components/device_companion/frontend/device-companion-summary.js
```

GitHub Actions 还会执行 Hassfest 和 HACS 校验。测试依赖使用 `pytest-homeassistant-custom-component` 提供 Home Assistant 测试运行时。

## v1.4.0 开发与验证记录

### UI 设计统一

- 按用户要求延续原设计，仅调整详情卡新增区域 CSS：复用 `--dc-text-main/sub`、`--dc-progress-bg`、`--card-background-color`；账单与付款表单使用原进度卡的 14px 圆角、轻阴影和透明细边。
- 记账/续订、CSV 导出、退款/更正与取消使用柔和灰阶按钮；只在确认操作和可见焦点上使用既有分类色。原分类配色、主体卡片、费用与业务逻辑不变。
- 本地内置浏览器验证 390px、桌面和明暗主题；表单打开/取消正常，未提交真实付款。前端回归增加样式继承检查，共 9 项通过，集成回归 76 项通过。
- 后续已安装到实际 HA，安装与验收结果见本文顶部。预览主题切换仅存在于本地模拟 fixture，不改变用户主题设置。

### 第二轮：退款/更正

- 新共享服务 `adjust_service_bill`，schema 要求 `entity_id`、`bill_id`、`operation`（refund/correction）、`cost`、`description` 和 `request_id`，可选 `paid_at`。复用 entry 写锁和持久化请求编号去重；失败不持久化账单或请求回执。
- `options.service_adjustments` 是按需新增的关联调整列表，记录独立 ID、原账单 ID、操作、正负差额、日期、原因。原 data、付款/附加支出记录及 entity/unique ID 不变，无需迁移旧条目；Options Flow 基于最新 options 深拷贝，保留新字段。
- 退款为负差额，更正为新原付款金额减去已有更正后的原金额。退款不能超出净余额；有退款后不能更正。净额用于累计投入和原账期费用，不产生退款月负运行费用，也不自动撤回覆盖/修改月费。
- UI 表单支持关联选择、必填原因、不同金额含义说明和失败重试；账单与 CSV 保留原值及调整，负金额仍为数值单元格。旧无流水记录不可直接调整，调整流水暂不可撤销。
- 阶段验证：76 项 Python + 8 项 Node 自动测试通过；本地手机模拟显示原 280、更正 -30、退款 -25，净额 225，保存后断线重试仍只有两笔调整。后续 UI 修复将前端测试增至 11 项，实机验收与发布记录见本文顶部。
- 若产生调整后退回 v1.3.0，旧代码不会计算新调整字段，费用展示会回到原口径；请以升级前备份和完整配置备份作为回滚依据，不把 CSV 当作恢复工具。

### 第一轮：导出与记账入口

- 详情卡新增本地 CSV 导出，复用显示账单的排序和类型映射，保留账单 ID、付款日期、覆盖日期/月数和说明。无旧流水时禁用导出，不把累计投入转换为虚构账单；坏金额留空，显式零金额保留。
- 文本字段加 CSV 引号/双引号转义并防公式注入，UTF-8 BOM 便于中文识别；下载完成后释放临时 URL，不请求 HA 服务或外部网络。
- 已确认后端允许有效的无到期日/永久服务记附加支出；修复前端误隐藏入口，并增加对应服务测试，不改 data/options schema 或实体标识。
- 自动验证：57 Python + 6 Node 测试通过。内置浏览器在 390px 模拟页面验证按钮、表单取消及账单布局；不是新版本实机部署证明。
- 本轮功能已纳入 v1.4.0；后续测试安装与用户验收结果见本文顶部。

### v1.3.0 实现与验收

- 2026-09-30 已在用户 HA 完成本地设置备份（31.07 MB）、HACS v1.3.0 安装和完整重启；前端资源已由旧 `/local/device_companion/` 路径更新至集成内置路径。原三条订阅的可见累计投入/到期日/附属权益保持一致，账单和中文表单切换、取消通过。未提交真实付款，未开启真实提醒；独立测试写入、提醒及重启去重尚未完成。详见 `docs/ACCEPTANCE_v1.3.0.md`。

- 稳定性：提前续订按当前日期选择付款覆盖账期，首次提前续订保留旧账期计算快照；锁跨 reload 保留，付款请求编号在 options 持久化去重；日期按 HA 时区转换，服务金额拒绝非有限数值。
- 体验：详情卡中文付款表单、实际付款日期和账单明细，处理中禁用按钮，失败保留表单和同一请求编号；取消不保存。
- 提醒：`reminders.py` 在开启后注册本地 09:00 监听，提前 7 天、3 天及到期日创建站内通知；去重标记存入 options，卸载取消监听和待执行任务。
- 新 options：`service_period_snapshots`、`payment_requests`、`expiry_reminders`、`expiry_reminder_sent`。不修改旧字段或实体 ID，不伪造旧付款。旧无请求编号的服务调用保留原行为。
- 已验证：真实 Config/Options Flow、实体标识保持、付款并发重试、提前多期续订、补记付款月份、非有限金额、月末/闰年及日历时区边界、提醒去重；本地卡片模拟页面用于浏览器验收。
- 本轮最终全量回归：55 passed；Python、两张卡片、JSON/YAML 与 diff 检查通过。内置浏览器验证 390px 手机布局、升级字段、取消不保存及保存后连接中断的同笔重试；临时预览服务已停止。
- 用户实际 HA 的卡片更新、站内提醒展示、重启与手机通知仍需安装后验收。发布前再次全量回归 55 passed；生产安装与实机验收状态见 `docs/ACCEPTANCE_v1.3.0.md`。

## 下一阶段建议

1. 账单纠错补充调整撤销，保留完整操作历史。
2. 维修/保修管理与耗材低余量提醒。
3. 分类切换迁移、损坏数据诊断和图片孤儿文件清理；保持旧用户数据兼容。
