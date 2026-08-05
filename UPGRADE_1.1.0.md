# v1.1.0 升级清单

## 升级前

- [ ] 创建 Home Assistant 备份。
- [ ] 记录现有仪表盘资源 URL。
- [ ] 确认当前条目和图片均可正常显示。

## 更新文件

- [ ] 覆盖 `/config/custom_components/device_companion/`。
- [ ] 不删除 `/config/www/device_companion/` 中已有图片。
- [ ] 重启 Home Assistant。

## 更新资源

删除旧资源：

```text
/local/device-companion-card.js
/local/device-companion-summary.js
```

添加新资源：

```text
/device_companion/device-companion-card.js?v=1.1.0
/device_companion/device-companion-summary.js?v=1.1.0
```

资源类型：JavaScript Module。

## 升级后检查

- [ ] 原有记录仍存在。
- [ ] 详情卡能显示状态、金额、耗材和附件。
- [ ] 汇总卡显示“累计净投入、历史月均成本、当前月度运行”。
- [ ] 服务记录到期日和续订按钮正常。
- [ ] 终止状态的陪伴天数不再变化。
- [ ] 智能耗材实体不可用时显示异常，而不是 0%。
- [ ] 浏览器已强制刷新。

## 回退

发生异常时：

1. 恢复升级前 Home Assistant 备份；
2. 恢复旧前端资源 URL；
3. 重启 Home Assistant。

由于 v1.1.0 会迁移 Config Entry 数据结构，不建议只覆盖回旧 Python 文件而不恢复备份。
