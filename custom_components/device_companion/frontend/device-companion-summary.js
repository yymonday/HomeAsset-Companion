/**
 * HomeAsset Companion Summary Card v1.1.1
 * Uses explicit net-investment, historical-average, and current-running-cost metrics.
 */

const dcsNumber = (value, fallback = 0) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

class DeviceCompanionSummaryCard extends HTMLElement {
  static getStubConfig() {
    return { title: "我的家庭资产", include_entities: [], exclude_entities: [] };
  }

  static async getConfigElement() {
    return document.createElement("device-companion-summary-editor");
  }

  set hass(hass) {
    this._hass = hass;
    if (!this.content) this.initView();
    this.updateData();
  }

  setConfig(config) {
    this.config = config;
  }

  initView() {
    const shadow = this.attachShadow({ mode: "open" });
    shadow.innerHTML = `
      <style>
        :host {
          --dc-bg-color: var(--card-background-color, #FCFBF9);
          --dc-text-main: var(--primary-text-color, #333);
          --dc-text-sub: var(--secondary-text-color, #8C8C8C);
          --dc-progress-bg: var(--secondary-background-color, #EAE6DF);
          --dc-shadow: 8px 8px 24px rgba(0,0,0,.05), -8px -8px 24px rgba(255,255,255,.8);
        }
        ha-card {
          background: var(--dc-bg-color);
          border-radius: 24px;
          border: none;
          box-shadow: var(--dc-shadow);
          padding: 24px;
          display: flex;
          flex-direction: column;
          gap: 20px;
          overflow: hidden;
        }
        .header { display:flex; align-items:center; gap:12px; }
        .header-icon {
          width:44px; height:44px; border-radius:12px;
          background:linear-gradient(135deg,#4A90E2,#9013FE);
          color:white; display:flex; align-items:center; justify-content:center;
          box-shadow:0 4px 10px rgba(74,144,226,.3);
        }
        .header-title { font-size:1.4rem; font-weight:800; color:var(--dc-text-main); }
        .header-sub { font-size:.8rem; color:var(--dc-text-sub); font-weight:600; margin-top:2px; }
        .dashboard-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }
        @media (max-width:900px) { .dashboard-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } }
        @media (max-width:500px) { .dashboard-grid { grid-template-columns:1fr; } }
        .dash-card {
          background:var(--card-background-color,#fff); border-radius:16px; padding:16px;
          border:1px solid rgba(128,128,128,.08); position:relative; overflow:hidden;
          box-shadow:inset 1px 1px 4px rgba(0,0,0,.03),0 2px 8px rgba(0,0,0,.04);
        }
        .dash-card::before { content:""; position:absolute; top:0; left:0; right:0; height:4px; }
        .dash-net::before { background:#4A90E2; }
        .dash-history::before { background:#7E57C2; }
        .dash-current::before { background:#E53935; }
        .dash-saved::before { background:linear-gradient(90deg,#FFD700,#FFA500); }
        .dash-title { font-size:.75rem; color:var(--dc-text-sub); font-weight:700; display:flex; align-items:center; gap:4px; }
        .dash-value { font-size:1.45rem; font-weight:900; color:var(--dc-text-main); margin-top:8px; letter-spacing:-.5px; }
        .dash-breakdown {
          font-size:.7rem; color:var(--dc-text-sub); margin-top:6px; padding-top:6px;
          border-top:1px dashed rgba(128,128,128,.15); display:flex; flex-direction:column; gap:3px;
        }
        .dash-breakdown div { display:flex; justify-content:space-between; gap:8px; }
        .dash-sub { font-size:.7rem; color:var(--dc-text-sub); margin-top:5px; }
        .category-section {
          background:var(--card-background-color,#fff); border-radius:16px; padding:16px;
          border:1px solid rgba(128,128,128,.08); box-shadow:0 4px 12px rgba(0,0,0,.02);
        }
        .category-header { font-size:.9rem; font-weight:800; color:var(--dc-text-main); margin-bottom:16px; display:flex; align-items:center; gap:6px; }
        .cat-item { display:flex; flex-direction:column; gap:6px; margin-bottom:12px; }
        .cat-item:last-child { margin-bottom:0; }
        .cat-info { display:flex; justify-content:space-between; gap:12px; font-size:.8rem; font-weight:700; color:var(--dc-text-main); }
        .cat-count { color:var(--dc-text-sub); font-size:.7rem; font-weight:500; }
        .cat-bar-bg { height:8px; background:var(--dc-progress-bg); border-radius:4px; overflow:hidden; }
        .cat-bar-fill { height:100%; border-radius:4px; transition:width 1s ease; }
        .empty { text-align:center; color:var(--dc-text-sub); font-size:.8rem; padding:12px; }
        .footer-note { font-size:.7rem; text-align:center; color:var(--dc-text-sub); font-weight:500; opacity:.75; }
      </style>
      <ha-card>
        <div class="header">
          <div class="header-icon"><ha-icon icon="mdi:finance" style="--mdc-icon-size:24px;"></ha-icon></div>
          <div>
            <div class="header-title" id="card-title">家庭资产</div>
            <div class="header-sub" id="scan-info">正在扫描实体…</div>
          </div>
        </div>

        <div class="dashboard-grid">
          <div class="dash-card dash-net">
            <div class="dash-title"><ha-icon icon="mdi:cash-multiple" style="--mdc-icon-size:14px;"></ha-icon> 累计净投入</div>
            <div class="dash-value" id="total-net">￥0.00</div>
            <div class="dash-breakdown">
              <div><span>主体与配件</span><span id="sub-main">￥0.00</span></div>
              <div><span>历史耗材</span><span id="sub-cons">￥0.00</span></div>
              <div><span>累计回收</span><span id="sub-recovery">-￥0.00</span></div>
            </div>
          </div>

          <div class="dash-card dash-history">
            <div class="dash-title"><ha-icon icon="mdi:chart-timeline-variant" style="--mdc-icon-size:14px;"></ha-icon> 历史月均成本</div>
            <div class="dash-value" id="historical-monthly">￥0.00</div>
            <div class="dash-sub">按各项目历史日均成本折算，不代表本月现金支出</div>
          </div>

          <div class="dash-card dash-current">
            <div class="dash-title"><ha-icon icon="mdi:calendar-month" style="--mdc-icon-size:14px;"></ha-icon> 当前月度运行</div>
            <div class="dash-value" id="current-monthly">￥0.00</div>
            <div class="dash-sub">有效订阅与当前耗材消耗速度的预计月成本</div>
          </div>

          <div class="dash-card dash-saved">
            <div class="dash-title"><ha-icon icon="mdi:gift-open-outline" style="--mdc-icon-size:14px;color:#FFA500;"></ha-icon> 附加权益价值</div>
            <div class="dash-value" id="total-saved" style="color:#FFA500;">￥0.00</div>
            <div class="dash-sub">赠送会员、权益和附加服务的标称价值</div>
          </div>
        </div>

        <div class="category-section">
          <div class="category-header"><ha-icon icon="mdi:chart-donut" style="--mdc-icon-size:16px;"></ha-icon> 分类净投入占比</div>
          <div id="category-container"></div>
        </div>
        <div class="footer-note" id="footer-note">全量自动扫描</div>
      </ha-card>
    `;
    this.content = shadow;
  }

  updateData() {
    if (!this._hass || !this.content) return;
    const states = this._hass.states;
    const includeList = this.config?.include_entities || [];
    const excludeList = this.config?.exclude_entities || [];

    let targetEntities = Object.keys(states).filter((entityId) => {
      if (!entityId.startsWith("sensor.")) return false;
      const attrs = states[entityId].attributes || {};
      return attrs.integration_domain === "device_companion"
        || (attrs.category && attrs.friendly_name && attrs.daily_base !== undefined);
    });
    if (includeList.length) targetEntities = targetEntities.filter((id) => includeList.includes(id));
    if (excludeList.length) targetEntities = targetEntities.filter((id) => !excludeList.includes(id));

    this.content.getElementById("card-title").textContent = this.config?.title || "家庭资产";
    this.content.getElementById("scan-info").textContent = `共统计 ${targetEntities.length} 个记录`;
    let footer = includeList.length ? `白名单 ${includeList.length} 项` : "全局自动扫描";
    if (excludeList.length) footer += ` · 排除 ${excludeList.length} 项`;
    this.content.getElementById("footer-note").textContent = footer;

    let totalNet = 0;
    let totalMainAndAccessory = 0;
    let totalConsumables = 0;
    let totalRecovery = 0;
    let historicalMonthly = 0;
    let currentMonthly = 0;
    let totalSaved = 0;
    const categories = new Map();

    targetEntities.forEach((entityId) => {
      const attrs = states[entityId].attributes || {};
      const isEvent = attrs.kind === "event" || attrs.is_event === true;
      const consumables = dcsNumber(attrs.total_consumable_cost);
      const legacyMain = dcsNumber(attrs.net_price ?? attrs.total_price) + dcsNumber(attrs.total_accessory_net);
      const recovery = dcsNumber(attrs.total_recovery ?? attrs.recovery_amount);
      const net = isEvent ? 0 : dcsNumber(attrs.net_investment, legacyMain + consumables);
      const mainAndAccessory = Math.max(0, net - consumables);

      totalNet += net;
      totalMainAndAccessory += mainAndAccessory;
      totalConsumables += consumables;
      totalRecovery += recovery;
      historicalMonthly += dcsNumber(attrs.historical_monthly_cost, dcsNumber(attrs.daily_cost) * 30.4375);
      currentMonthly += dcsNumber(attrs.current_monthly_cost);
      totalSaved += dcsNumber(attrs.total_saved_value);

      if (!isEvent && net > 0) {
        const category = attrs.category || "其他类别";
        const current = categories.get(category) || { value: 0, count: 0 };
        current.value += net;
        current.count += 1;
        categories.set(category, current);
      }
    });

    this.content.getElementById("total-net").textContent = `￥${totalNet.toFixed(2)}`;
    this.content.getElementById("sub-main").textContent = `￥${totalMainAndAccessory.toFixed(2)}`;
    this.content.getElementById("sub-cons").textContent = `￥${totalConsumables.toFixed(2)}`;
    this.content.getElementById("sub-recovery").textContent = `-￥${totalRecovery.toFixed(2)}`;
    this.content.getElementById("historical-monthly").textContent = `￥${historicalMonthly.toFixed(2)}`;
    this.content.getElementById("current-monthly").textContent = `￥${currentMonthly.toFixed(2)}`;
    this.content.getElementById("total-saved").textContent = `￥${totalSaved.toFixed(2)}`;

    const container = this.content.getElementById("category-container");
    container.replaceChildren();
    const sorted = [...categories.entries()]
      .map(([name, data]) => ({ name, ...data }))
      .sort((a, b) => b.value - a.value);
    if (!sorted.length) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "暂无可统计的金额数据";
      container.appendChild(empty);
      return;
    }

    const totalCategoryValue = sorted.reduce((sum, item) => sum + item.value, 0) || 1;
    const colors = {
      "数码产品": "#4A90E2",
      "生活家电": "#D35400",
      "交通出行": "#50E3C2",
      "虚拟服务": "#9013FE",
      "纪念珍藏": "#E91E63",
      "其他类别": "#C4A484",
    };

    sorted.forEach((category) => {
      const row = document.createElement("div");
      row.className = "cat-item";
      const info = document.createElement("div");
      info.className = "cat-info";
      const left = document.createElement("span");
      left.textContent = category.name;
      const count = document.createElement("span");
      count.className = "cat-count";
      count.textContent = `（${category.count}项）`;
      left.appendChild(count);
      const amount = document.createElement("span");
      amount.textContent = `￥${category.value.toFixed(2)}`;
      info.append(left, amount);

      const background = document.createElement("div");
      background.className = "cat-bar-bg";
      const fill = document.createElement("div");
      fill.className = "cat-bar-fill";
      fill.style.width = `${Math.max(2, Math.min(100, category.value / totalCategoryValue * 100))}%`;
      fill.style.backgroundColor = colors[category.name] || colors["其他类别"];
      background.appendChild(fill);
      row.append(info, background);
      container.appendChild(row);
    });
  }

  getCardSize() {
    return 4;
  }
}

class DeviceCompanionSummaryEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  setConfig(config) {
    this._config = config;
    this.updateForm();
  }

  set hass(hass) {
    this._hass = hass;
    this.updateForm();
  }

  updateForm() {
    if (!this._hass || !this._config) return;
    let form = this.shadowRoot.querySelector("ha-form");
    if (!form) {
      const note = document.createElement("div");
      note.style.cssText = "margin-bottom:12px;font-size:.85rem;color:var(--secondary-text-color);";
      note.textContent = "留空白名单时自动统计全部 HomeAsset Companion 主传感器；纪念事件不参与金额统计。";
      form = document.createElement("ha-form");
      form.schema = [
        { name: "title", selector: { text: {} } },
        { name: "include_entities", selector: { entity: { multiple: true, domain: "sensor" } } },
        { name: "exclude_entities", selector: { entity: { multiple: true, domain: "sensor" } } },
      ];
      form.computeLabel = (schema) => ({
        title: "大盘标题",
        include_entities: "统计白名单（留空自动扫描）",
        exclude_entities: "排除实体",
      }[schema.name] || schema.name);
      form.addEventListener("value-changed", (event) => {
        this.dispatchEvent(new CustomEvent("config-changed", {
          detail: { config: event.detail.value },
          bubbles: true,
          composed: true,
        }));
      });
      this.shadowRoot.append(note, form);
    }
    form.hass = this._hass;
    form.data = this._config;
  }
}

if (!customElements.get("device-companion-summary-editor")) {
  customElements.define("device-companion-summary-editor", DeviceCompanionSummaryEditor);
}
if (!customElements.get("device-companion-summary-card")) {
  customElements.define("device-companion-summary-card", DeviceCompanionSummaryCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "device-companion-summary-card")) {
  window.customCards.push({
    type: "device-companion-summary-card",
    name: "HomeAsset Companion 资产大盘",
    preview: true,
    description: "v1.1.1：净投入、历史月均、当前运行成本和分类占比。",
  });
}
