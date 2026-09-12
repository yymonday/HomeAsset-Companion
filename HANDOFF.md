# HomeAsset Companion 项目交接

> 交接基线：v1.2.0 订阅账期版
> 远端仓库：<https://github.com/yymonday/HomeAsset-Companion>

## 项目简介

`device_companion` 是一个 Home Assistant 自定义集成，用 Config Entry 保存设备、家电、虚拟订阅、纪念珍藏和纪念事件。它通过传感器展示陪伴天数、历史投入、当前月度运行成本、耗材和附属项目状态，并通过日历提供周年和到期提醒。集成不连接外部云服务；图片上传是唯一的 HTTP 能力，文件保存到 HA 的 `www/device_companion/`。

## 当前版本与功能完成度

- 当前版本：`1.2.0`，Config Flow schema version `2`。
- 已完成：四种稳定业务类型、Config/Options Flow、生命周期状态、分期计算、耗材与配件、智能耗材监听、续订/换新/生命周期/图片服务、旧 `quick_action` 兼容层、日历、前端详情卡与汇总卡、认证图片上传、V1 → V2 迁移。
- 完成度：核心功能可用，当前阶段属于 v1.2.0 订阅账期维护，不进行 2.0 交易流水或 Subentry 重构。

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

- `__init__.py` 在集成 setup 注册共享 HTTP 路由和服务，在 entry setup 只转发 sensor/calendar 平台；`async_unload_entry` 负责平台卸载和 entry 锁清理。
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

- 自动测试已接入真实 Home Assistant fixture，并覆盖 Config Entry setup、实体注册、服务调用和 reload/unload；完整 Config Flow、HTTP 上传、Device Registry 及用户实际环境仍需人工验证。
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

## 下一阶段建议

1. 由用户在实际 HA 中验证 V1 条目迁移、旧 quick_action 续订、续订后的当前月均费用、重载/重启和日历。
2. 在实际 HA 中验证完整 Config Flow、Device Registry、上传界面和智能耗材通知展示。
3. 再处理分类切换迁移、损坏数据诊断、上传磁盘异常和图片孤儿文件清理；这些都需要保持旧用户数据兼容。
