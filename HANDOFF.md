# HomeAsset Companion 项目交接

> 交接基线：v1.1.1 稳定性修复
> 远端仓库：<https://github.com/yymonday/HomeAsset-Companion>

## 项目简介

`device_companion` 是一个 Home Assistant 自定义集成，用 Config Entry 保存设备、家电、虚拟订阅、纪念珍藏和纪念事件。它通过传感器展示陪伴天数、历史投入、当前月度运行成本、耗材和附属项目状态，并通过日历提供周年和到期提醒。集成不连接外部云服务；图片上传是唯一的 HTTP 能力，文件保存到 HA 的 `www/device_companion/`。

## 当前版本与功能完成度

- 当前版本：`1.1.1`，Config Flow schema version `2`。
- 已完成：四种稳定业务类型、Config/Options Flow、生命周期状态、分期计算、耗材与配件、智能耗材监听、续订/换新/生命周期/图片服务、旧 `quick_action` 兼容层、日历、前端详情卡与汇总卡、认证图片上传、V1 → V2 迁移。
- 完成度：核心功能可用，当前阶段属于 v1.1.1 稳定性维护，不进行 2.0 交易流水或 Subentry 重构。

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
  └─ entry.options：类型、生命周期、服务周期/本期费用、耗材、附属项目、故事、日历开关
       ├─ sensor.py + hass.states → 主体/耗材/附属传感器
       ├─ calendar.py → 周年和到期事件
       └─ 集成服务/智能耗材监听 → async_update_entry(options) → entry reload

认证上传 → www/device_companion/ → /local/device_companion/... → data/options 保存 URL
```

## 关键实现与持久化

- `__init__.py` 在集成 setup 注册共享 HTTP 路由和服务，在 entry setup 只转发 sensor/calendar 平台；`async_unload_entry` 负责平台卸载和 entry 锁清理。
- `async_migrate_entry` 将 V1 旧字段推导为 `kind`、schema version 2、标准生命周期字段和服务周期字段；服务还会补齐 `current_period_cost`，默认保持原始总价。
- `current_period_cost` 位于 `entry.options`。初始服务记录使用主体初始价格，续订服务把本次费用写为当前周期费用；传感器据此计算当前月均成本。累计投入仍单独累加，不被替换。
- 主体 `unique_id` 使用 `companion_<entry_id>`；耗材/附属项目使用持久化项目 ID；设备标识使用 `(device_companion, entry_id)`。
- 旧 `device_companion.quick_action` 仍保留，并只转发新服务允许的字段。

## 本次 v1.1.1 已完成

- 修复 V1 迁移使用 `CONF_KIND` 但未导入，导致旧 Config Entry 迁移时出现 `NameError`。
- 增加配置入口专用 `CONFIG_SCHEMA`，整理 manifest 字段顺序并统一 manifest、常量、README、前端说明和 changelog 版本为 `1.1.1`。
- 修复续订后当前月度运行仍使用初始价格的问题；保留旧配置兼容回退。
- 增加迁移、续订服务、旧 quick_action、耗材换新、未知耗材 ID 和当前费用计算回归测试。
- 增加 HACS 品牌 `icon.png`，CI 增加 pytest 检查。

## 当前已知问题与风险

- 本地开发环境没有完整 Home Assistant 运行时，真实 Config Flow、实体注册、reload/unload、HTTP 上传和 Device Registry 行为仍需在用户的 HA 实例人工验证。
- `safe_date`/`safe_float` 为兼容旧数据保留默认回退；如果用户数据损坏，可能只能看到默认值，需要后续增加诊断日志而不能直接改变历史口径。
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
2. 在最小 HA fixture 中补实体注册、两条 Config Entry 的 setup/unload、上传 API 和智能耗材状态变化测试。
3. 再处理分类切换迁移、损坏数据诊断和图片孤儿文件清理；这些都需要保持旧用户数据兼容。
