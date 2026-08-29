# HomeAsset Companion（资产与陪伴管家）

HomeAsset Companion 是一个 Home Assistant 自定义集成，用于记录家庭设备、家电、订阅服务、耗材、配件与纪念物品的生命周期。

> 当前版本：**v1.1.1 稳定性兼容版**
> 最低建议 Home Assistant：**2026.6.0**

## v1.1.1 主要变化

- 修复旧版 Config Entry 迁移时缺少 `kind` 常量导入导致的迁移失败。
- 修复续订后“当前月度运行”仍按初始价格计算的问题；续订费用会成为当前周期费用。
- 补充迁移、服务、耗材和续订成本回归测试。
- 增加 HACS 品牌图标和 GitHub 自动测试检查。

## v1.1.0 主要变化

- 保留旧条目和旧卡片配置，首次加载时自动迁移数据结构。
- 引入稳定业务类型：设备资产、虚拟服务、纪念珍藏、纪念事件。
- 生命周期改为统一状态，不再依赖前端根据“退役原因”猜测状态。
- 将通用 `quick_action` 拆成明确服务，并保留旧服务兼容层。
- 修复多个智能耗材监听串错对象、不可用状态被当成 0、重复记账等问题。
- 财务名称改为“累计净投入、历史月均成本、当前月度运行”，避免把累计投入误称为资产估值。
- 前端卡片随集成发布，不再要求手动把 JS 文件复制到 `www` 根目录。
- 图片上传增加 5 MB 限制、文件签名校验和随机文件名。
- 增加 Home Assistant 日历、中文表单、服务描述和 GitHub 自动校验工作流。

完整变更见 [CHANGELOG.md](CHANGELOG.md)。

## 安装

### HACS 自定义存储库

1. 在 HACS 中添加自定义存储库：
   `https://github.com/yymonday/HomeAsset-Companion`
2. 类别选择 **Integration**。
3. 下载 HomeAsset Companion。
4. 重启 Home Assistant。
5. 前往 **设置 → 设备与服务 → 添加集成**，搜索 `HomeAsset Companion`。

### 手动安装

将以下目录复制到 Home Assistant 配置目录：

```text
custom_components/device_companion
```

最终路径应为：

```text
/config/custom_components/device_companion/manifest.json
```

然后重启 Home Assistant。

## 添加前端卡片资源

集成会提供两张卡片的静态资源，但仍需在仪表盘资源中注册一次。

前往 **设置 → 仪表盘 → 右上角菜单 → 资源**，添加：

```text
/device_companion/device-companion-card.js?v=1.1.1
/device_companion/device-companion-summary.js?v=1.1.1
```

资源类型均选择 **JavaScript Module**。

### 详情卡

```yaml
type: custom:device-companion-card
entity: sensor.example_companion
name: 可选覆盖名称
icon: mdi:calendar-heart
```

### 汇总卡

```yaml
type: custom:device-companion-summary-card
title: 家庭资产与陪伴
include_entities: []
exclude_entities: []
```

留空白名单时，汇总卡会自动扫描 HomeAsset Companion 主传感器。

## 从旧版升级

升级前建议先创建 Home Assistant 备份。

1. 用 v1.1.1 覆盖旧的 `custom_components/device_companion`。
2. 在仪表盘资源中删除或停用旧资源：

```text
/local/device-companion-card.js
/local/device-companion-summary.js
```

3. 添加新的 `/device_companion/` 资源路径。
4. 重启 Home Assistant。
5. 打开现有记录。旧 Config Entry 会自动迁移到 V2 生命周期结构。
6. 强制刷新浏览器或清除前端缓存。

已有详情卡和汇总卡的 `type` 不变，因此 Lovelace 卡片配置可以继续使用。

## 核心数据口径

### 累计净投入

```text
主体及续费投入 + 分期费用 + 配件净投入 + 历史耗材投入 - 二手回收金额
```

它表示累计现金投入，不等同于当前二手市场价值。

### 历史月均成本

```text
各记录历史日均成本 × 30.4375
```

它用于回顾长期平均成本，不代表本月真实扣款。

### 当前月度运行

当前版本统计：

- 有效订阅折算月费；
- 当前耗材消耗速度折算月成本。

闲置、封存、售出、报废、遗失、赠出、取消或到期记录不再计入当前月度运行。

## 生命周期状态

| 状态 | 含义 | 是否继续累计天数 | 是否计入当前运行成本 |
|---|---|---:|---:|
| 正常使用 | 正常在役或服务有效 | 是 | 是 |
| 闲置持有 | 仍持有但不再运行 | 是 | 否 |
| 已封存 | 主动停止记录使用 | 否 | 否 |
| 二手售出 | 已出售，可填写回收金额 | 否 | 否 |
| 已报废 | 无法继续使用 | 否 | 否 |
| 已遗失 | 已不再持有 | 否 | 否 |
| 已赠出 | 转交他人 | 否 | 否 |
| 已取消 | 服务取消或不再续订 | 否 | 否 |
| 已到期 | 根据服务到期日自动推导 | 否 | 否 |

## 服务动作

v1.1.0 提供：

- `device_companion.renew_service`
- `device_companion.replace_consumable`
- `device_companion.set_lifecycle`
- `device_companion.update_item_image`

旧版 `device_companion.quick_action` 暂时保留，用于兼容旧自动化和旧卡片，后续大版本可能移除。

## 智能耗材逻辑

当前支持：

- 手动周期：按启用日期和理论天数计算剩余比例；
- 关联实体：支持百分比状态，以及 `on → off` 的二值复位识别；
- 低余量恢复到高余量时检测为“可能换新”；
- 默认只发送确认提醒，不自动增加费用；
- 开启“检测到复位后自动记账”后，按默认价格记录更换。

`unknown`、`unavailable` 和无法解析的状态会显示为不可用，不会被当成耗尽或健康状态。

## 图片说明

卡片编辑器上传的图片保存在：

```text
/config/www/device_companion/
```

并通过 `/local/device_companion/` 访问。该路径属于静态资源，**不建议上传包含敏感个人信息的私密照片**。

## 当前边界

v1.1.0 以兼容与稳定为目标，仍沿用“每条记录一个 Config Entry”的结构，也尚未引入完整交易流水。交易流水、主 Config Entry + Subentry、撤销操作和历史价格记录计划放到后续 2.0 架构中，避免在本次升级中破坏现有数据。

## 开发校验

仓库包含 Hassfest 与 HACS GitHub Actions。提交前也可以执行：

```bash
python -m compileall custom_components/device_companion
node --check custom_components/device_companion/frontend/device-companion-card.js
node --check custom_components/device_companion/frontend/device-companion-summary.js
```

## License

MIT
