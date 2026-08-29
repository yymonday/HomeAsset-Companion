# HomeAsset Companion 开发计划

> 基线：v1.1.1 稳定性修复

## 已完成

- P0：修复 V1 → V2 迁移遗漏 `CONF_KIND` 导入导致的 `NameError`。
- P1：新增 `options.current_period_cost`，使续订后的本期费用参与当前月均成本计算，并保留旧数据回退。
- P1：覆盖迁移、续订服务、旧 `quick_action`、耗材实际费用、未知耗材 ID 和续订成本计算测试。
- P2：补 `CONFIG_SCHEMA`、整理 manifest、统一 v1.1.1 版本信息、增加 HACS 品牌图标和 pytest CI。

## P0：阻断使用、数据损坏或严重兼容问题

当前没有已确认的 P0。若发现旧 Config Entry 无法迁移、实体唯一标识变化、配置被覆盖或服务导致持久化数据损坏，应暂停功能扩展并优先处理。

## P1：核心功能和数据正确性

- 在实际 HA 中验证旧 V1 条目迁移、旧卡片 `quick_action` 续订、显式费用/周期和续订后 `current_monthly_cost`。
- 增加真实 Config Entry fixture，覆盖服务目标解析、实体注册、unknown/unavailable 状态和服务异常。
- 覆盖智能耗材 `on/off`、数值阈值、unknown/unavailable、重复事件和 entry reload 后监听器生命周期。
- 明确分类编辑的保留/清理矩阵；若允许切换，必须设计 data/options migration，不可只改变展示分类。

## P2：稳定性、错误处理和架构

- 覆盖多 Config Entry setup/unload/reload、共享服务与 HTTP view 的重复注册和最后一个 entry 卸载。
- 为损坏日期、非法金额、缺失子项目增加可诊断日志；保持兼容回退但避免静默掩盖数据问题。
- 验证图片上传的尺寸、签名、扩展名、磁盘错误和旧文件清理策略。
- 评估附属项目分期到期语义、日历查询边界和所有 HA 时区/闰年边界。
- 如确实需要，再加入与目标 HA 版本匹配的类型检查；不要为了工具而重构业务模块。

## P3：体验和非必要重构

- 补充英文 fallback 翻译和更多用户文档。
- 改善前端对当前周期费用、服务剩余和错误服务调用的提示。
- 评估配置条目删除后上传图片的清理体验。
- 只有在测试保护充分后，才考虑拆分 `sensor.py` 的纯计算函数。

## 验收要求

任何后续 P1/P2 修复都应：

1. 提供可复现条件和影响范围；
2. 覆盖成功、空值、不可用、重复调用、并发/reload 和异常路径；
3. 检查 entity ID、unique ID、Device Registry、旧 Config Entry data/options；
4. 执行可用测试和静态检查，并检查最终 diff/status；
5. 同步更新 `HANDOFF.md`、本计划和用户文档。
