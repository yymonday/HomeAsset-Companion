# HomeAsset Companion 维护规则

## 项目定位

这是 Home Assistant 自定义集成 `device_companion`，用于把个人设备、家电、虚拟订阅、纪念珍藏和纪念事件保存为 Config Entry，并提供陪伴天数、费用、耗材状态、附加项目以及周年/到期日历事件。它不控制外部设备，也没有独立云端 API；智能耗材和实时估值只读取 Home Assistant 中用户选择的实体状态。

集成源码位于 `custom_components/device_companion/`，安装时应放入 Home Assistant 配置目录的同名路径。

## 开发原则

- 优先保持现有用户配置、实体状态、服务调用和前端卡片兼容。
- 不随意修改已有 `entity_id`、`unique_id`、Config Entry data/options 键名或子项目 `id`。
- Config Entry 数据结构变化必须有明确的迁移策略，并区分 `data` 与 `options`。
- 修改前沿着 Config Flow/Options Flow → Config Entry → 平台实体 → 服务或事件回写的完整调用链检查。
- 不为代码风格进行大规模重构；优先修复有证据的根因。
- 不删除看似无用的兼容字段、旧服务或历史分支，除非确认没有数据依赖并提供迁移/替代方案。
- 金额、日期和状态计算必须补边界测试，避免静默改变历史数据含义。

## Home Assistant 约定

- 基础字段存于 `entry.data`，可变设置、列表和生命周期字段存于 `entry.options`；使用 `hass.config_entries.async_update_entry` 写回。
- `kind`、子项目 ID 和实体 `unique_id` 必须稳定；不要在 reload 或列表重建时重新生成已有 ID。
- 主体、耗材和配件通过 `(DOMAIN, entry.entry_id)` 关联同一设备。实体只在平台 setup 创建，并在 entry unload 时释放监听器。
- 服务和 HTTP 路由属于集成级共享资源，必须避免多 entry 重复注册，并考虑 reload/unload 竞争。
- 服务输入必须有 schema 和可诊断的 `ServiceValidationError`；不要静默接受未知实体、项目或非法金额。
- Entity property 不做 I/O；网络、文件和其他阻塞操作必须走 Home Assistant 异步接口或 executor。
- 日历使用 Home Assistant 时区，全天事件遵循起止边界，并覆盖闰年和查询窗口边界。
- 修改 Config Flow、Options Flow 或字段时同步检查 `strings.json` 与 `translations/`。
- 上传接口必须保留认证、大小限制、类型/签名校验、随机文件名和安全错误响应。

## 修改完成要求

每次开发后至少：

1. 检查 `git diff` 和 `git status`，不要覆盖用户已有改动。
2. 验证 JSON、Python 语法、前端语法、导入和可运行的测试。
3. 检查异常处理、空值、未知实体、重复注册、并发更新、reload/unload 和重启恢复。
4. 确认 entity ID、unique ID、Device Registry、Config Entry data/options 和旧配置迁移没有被破坏。
5. 更新 `HANDOFF.md`、`docs/PLAN.md` 和相关用户文档。
6. 提交或推送只有在用户明确要求时进行；本次发布任务已明确授权推送。
