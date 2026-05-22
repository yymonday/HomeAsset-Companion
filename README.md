# 📦 HomeHomeAsset Companion (资产与陪伴管家) for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Version](https://img.shields.io/github/v/release/YOUR_USERNAME/device_companion?style=flat-square)](https://github.com/YOUR_USERNAME/device_companion/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**HomeHomeAsset Companion** 远不止是一个设备追踪器。它是一个为你量身打造的 **「家庭资产与生活记忆聚合中枢」**。
从数码产品的分期折旧、净水器滤芯的智能耗损，到虚拟服务的白嫖统计，再到结婚纪念日的日历注入。它将你生活中冰冷的“开销”和“物品”，转化为充满温度的陪伴记录和极度硬核的财务大盘。

## ✨ 核心特性 (Core Features)

* 📊 **双轨制财务大盘 (Dual-Track Finance)**：彻底分离“硬件无形折旧”与“耗材真实烧钱”，为你提供极度精准的「月度燃烧率」看板。
* 💧 **AI 智能耗材托管 (Smart Consumables)**：支持关联 HA 实体状态（如智能插座、传感器），动态折算滤芯/耗材的真实寿命与日均花费。
* 🎁 **虚拟服务与白嫖统计 (Virtual Services)**：专为 Netflix、88VIP 等服务打造。记录附加权益价值，生成“累计白嫖”成就，并支持一键续费。
* 💍 **情感记忆与原生日历注入 (Memories & Calendar)**：录入纯纪念事件或实体纪念品（如婚戒）。自动向 Home Assistant 原生日历注入带有专属冠名的“N周年纪念日”及服务到期提醒（实现中）。
* 🛡️ **多维防呆与图锁引擎 (Anti-Idiot & Image Anchor)**：底层的绝对时间戳图锁彻底解决 HA 配置表单覆盖导致的“掉图Bug”；退役/遗失/二手回血状态自动流转并冻结计费。
* 🎨 **拟物化交互卡片 (Neumorphism UI)**：自带两款高度定制的 Lovelace 卡片（单品详情卡 + 全局大盘卡（实现中）），防越狱排版，色彩随分类智能响应。

---

## 📸 界面预览 (Screenshots)
<img width="1076" height="1184" alt="image" src="https://github.com/user-attachments/assets/bb8ced56-d948-4fbc-9d13-1f4b2a2ec54a" />
<img width="1051" height="1194" alt="0e7d1df78b936dc1dfbac7d02978f652" src="https://github.com/user-attachments/assets/8591079d-e53c-4cde-a2c5-65ee9f368527" />


---

## 🚀 安装指南 (Installation)

### 方法一：通过 HACS 安装 (推荐)
1. 打开 Home Assistant，进入 HACS。
2. 点击右上角三个点，选择 `自定义存储库 (Custom repositories)`。
3. 填入本仓库 URL：`https://github.com/yymonday/HomeAsset-Companion`，类别选择 `集成 (Integration)`。
4. 在 HACS 中搜索 `HomeAsset Companion` 并点击下载。
5. 重启 Home Assistant。

### 方法二：手动安装
1. 下载本仓库的 `Release` 压缩包。
2. 将 `custom_components/device_companion` 文件夹复制到你 HA 配置目录下的 `custom_components/` 文件夹中。
3. 将 `www/device-companion-card.js` 和 `www/device-companion-summary.js` 复制到你 HA 配置目录下的 `www/` 文件夹中。
4. 重启 Home Assistant。

---

## ⚙️ 配置与使用 (Configuration & Usage)

### 1. 核心集成配置
1. 前往 HA 的 **配置 -> 设备与服务 -> 添加集成**。
2. 搜索 `HomeAsset Companion` 。
3. 根据极致纯净的 **向导流表单**，选择你要录入的类型（数码产品 / 虚拟服务 / 纪念珍藏 / 纪念事件），并按提示完成录入。

### 2. 前端面板 (Lovelace UI) 挂载
在设置好集成后，你需要将随附的两张精美卡片挂载到前端面板：

**第一步：引入资源**
1. 前往 **配置 -> 仪表盘 -> 资源 (Resources)**。
2. 添加以下 URL（类型均为 `JavaScript Module`）：
   * `/local/device-companion-card.js`

**第二步：添加卡片**
在仪表盘中点击“添加卡片”，搜索以下两张卡片并进行可视化配置：
* **设备陪伴管家详情卡**：支持下拉选择绑定图片，实时显示进度条与徽章。

---

## 🔮 未来畅想与更新路线 (Roadmap)

这个项目正在快速进化中，以下是未来可能的更新方向。欢迎提交 PR 一起共建！

- [ ] **纪念日功能**：支持HomeAssistant原生日历🗓。
- [ ] **AI 资产诊断周报**：接入 LLM（如 OpenAI/本地模型），每月自动读取大盘数据，生成“生活消费降级/升级建议”语音播报。
- [ ] **家庭共享账本体系**：在实体中加入“所属人(Owner)”标签，在大盘中可以筛选“老公的数码私房钱” vs “家庭公用开销”。
- [ ] **二手行情 API 抓取**：尝试接入外部商品价格数据库，对于未退役的数码产品，实时显示当前二手残值曲线。
- [ ] **陪伴管家资产大盘**：支持黑白名单隔离、分类排行、双轨月度燃烧率。

---

## 🐛 常见问题 (FAQ)

**Q: 上传的图片保存在哪里？**
A: 图片会生成安全的随机 UUID 纯英文文件名，保存在 `www/device_companion/` 目录下。

## 📄 许可协议 (License)
本项目基于 [MIT License](LICENSE) 开源。

*Crafted with ❤️ for the Home Assistant Community.*
