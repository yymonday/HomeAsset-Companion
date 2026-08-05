/**
 * HomeAsset Companion Detail Card v1.1.0
 * Compatible with legacy V153 entities and the V2 lifecycle schema.
 */

const dcEscape = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
const dcNumber = (value, fallback = 0) => { const parsed = Number(value); return Number.isFinite(parsed) ? parsed : fallback; };
const dcSafeIcon = (value) => /^mdi:[a-z0-9-]+$/i.test(String(value || "")) ? String(value) : "mdi:information-outline";
const dcSafeImageUrl = (value) => { const raw = String(value || "").trim(); return raw.startsWith("/local/") || raw.startsWith("http://") || raw.startsWith("https://") ? encodeURI(raw) : ""; };

class DeviceCompanionCard extends HTMLElement {
  static getStubConfig() { return { entity: "", name: "", icon: "mdi:calendar-heart" }; }
  static async getConfigElement() { return document.createElement("device-companion-editor-v2"); }

  set hass(hass) {
    this._hass = hass;
    if (!this.content) this.initView();
    this.updateData();
  }
  setConfig(config) { this.config = config; }

  initView() {
    const shadow = this.attachShadow({ mode: "open" });
    shadow.innerHTML = `
      <style>
        :host { --dc-theme: #C4A484; --dc-bg-color: var(--card-background-color, #FCFBF9); --dc-text-main: var(--primary-text-color, #4A4A4A); --dc-text-sub: var(--secondary-text-color, #8C8C8C); --dc-progress-bg: var(--secondary-background-color, #EAE6DF); --dc-shadow: 8px 8px 24px rgba(0,0,0,0.06), -8px -8px 24px rgba(255,255,255,0.7); }
        ha-card { position: relative; background-color: var(--dc-bg-color); border-radius: 24px; border: none; box-shadow: var(--dc-shadow); padding: 24px; font-family: 'Helvetica Neue', Arial, sans-serif; display: flex; flex-direction: column; gap: 16px; transition: all 0.5s ease; overflow: hidden; }
        #content-area { transition: all 0.5s ease; }
        ha-card.is-retired #content-area { filter: grayscale(85%) opacity(0.85) sepia(15%); }
        
        .category-tag { position: absolute; top: 0; left: 0; z-index: 5; background: var(--dc-theme); color: white; padding: 5px 14px; border-radius: 24px 0 16px 0; font-size: 0.75rem; font-weight: bold; letter-spacing: 1px; box-shadow: 2px 2px 8px rgba(0,0,0,0.1); }
        
        .wearing-badge { position: absolute; top: 14px; right: 14px; color: #FFD700; filter: drop-shadow(0 0 4px rgba(255,215,0,0.6)); animation: pulse 2s infinite; }
        @keyframes pulse { 0% { transform: scale(1); opacity: 0.8; } 50% { transform: scale(1.2); opacity: 1; } 100% { transform: scale(1); opacity: 0.8; } }

        .retire-stamp { position: absolute; top: 25px; right: 30px; z-index: 10; pointer-events: none; color: #E53935; border: 3px solid #E53935; border-radius: 5px 8px 4px 6px / 7px 3px 6px 4px; padding: 6px 14px; transform: rotate(-15deg); display: flex; flex-direction: column; align-items: center; justify-content: center; line-height: 1.1; mix-blend-mode: multiply; opacity: 0.9; animation: stampDown 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275) forwards; }
        .stamp-main { font-size: 1.2rem; font-weight: 900; letter-spacing: 2px; margin-right: -2px; }
        .stamp-sub { font-size: 0.75rem; font-weight: 700; border-top: 2px dashed rgba(229,57,53, 0.85); margin-top: 4px; padding-top: 4px; }
        @keyframes stampDown { 0% { transform: scale(1.3) rotate(0deg); opacity: 0; } 100% { transform: scale(1) rotate(-15deg); opacity: 0.9; } }

        .header { display: flex; align-items: center; gap: 14px; margin-top: 8px; }
        .icon-wrapper { width: 56px; height: 56px; border-radius: 16px; position: relative; overflow: hidden; background: var(--dc-bg-color); box-shadow: 4px 4px 10px rgba(0,0,0,0.06), inset 2px 2px 4px rgba(255,255,255,0.5); display: flex; align-items: center; justify-content: center; color: var(--dc-theme); border: 1px solid rgba(128,128,128,0.05); }
        .device-photo { width: 100%; height: 100%; object-fit: cover; position: absolute; top: 0; left: 0; }
        .device-name { font-size: 1.3rem; font-weight: 700; color: var(--dc-text-main); max-width: 65%; line-height:1.2;}
        
        .main-stats { display: flex; align-items: baseline; margin: 12px 0; }
        .days-value { font-size: 3.8rem; font-weight: 800; line-height: 1; color: var(--dc-text-main); letter-spacing: -1px; }
        .days-unit { font-size: 1rem; color: var(--dc-text-sub); margin-left: 8px; font-weight: 600; }
        
        .tags-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 4px; }
        .soft-tag { font-size: 0.7rem; font-weight: 600; padding: 4px 10px; border-radius: 8px; background: var(--dc-progress-bg); color: var(--dc-text-main); display: inline-flex; align-items: center; gap: 4px; box-shadow: inset 1px 1px 3px rgba(0,0,0,0.02); }
        .soft-tag ha-icon { --mdc-icon-size: 12px; color: var(--dc-theme); }

        .financial-grid { display: grid; gap: 14px; margin-top: 12px; padding-top: 18px; border-top: 1px dashed rgba(128,128,128,0.2); }
        .stat-item { background: var(--card-background-color, #ffffff); padding: 12px 14px; border-radius: 14px; display: flex; flex-direction: column; gap: 4px; box-shadow: 0 4px 12px rgba(0,0,0,0.03); border: 1px solid rgba(128,128,128,0.06); }
        .stat-label { font-size: 0.75rem; color: var(--dc-text-sub); font-weight: 500; }
        .stat-value { font-size: 1.15rem; font-weight: 800; color: var(--dc-text-main); }
        
        .cost-tags-wrapper { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
        .cost-tag { font-size: 0.7rem; padding: 4px 12px; border-radius: 8px; background: rgba(128,128,128,0.05); color: var(--dc-text-sub); display: inline-flex; align-items: baseline; gap: 4px; font-weight: 500; border: 1px solid rgba(128,128,128,0.08); }
        .cost-tag .hl { color: var(--dc-theme); font-weight: 800; }
        .saved-value-tag { font-size: 0.75rem; padding: 4px 12px; border-radius: 8px; background: linear-gradient(90deg, #FFD700, #FFA500); color: #fff; display: inline-flex; align-items: center; gap: 4px; font-weight: 700; box-shadow: 0 2px 6px rgba(255,165,0,0.3); }
        
        .memorial-diary { margin-top: 16px; padding: 18px; border-radius: 16px; background: linear-gradient(135deg, rgba(var(--dc-theme-rgb), 0.08) 0%, rgba(var(--dc-theme-rgb), 0.02) 100%); border: 1px solid rgba(var(--dc-theme-rgb), 0.2); box-shadow: inset 2px 2px 10px rgba(0,0,0,0.02); }
        .diary-story { font-size: 0.9rem; color: var(--dc-text-main); line-height: 1.6; font-style: italic; white-space: pre-wrap; font-weight: 500; }
        .diary-location { font-size: 0.75rem; color: var(--dc-theme); margin-top: 14px; display: flex; align-items: center; gap: 6px; font-weight: 700; background: rgba(255,255,255,0.5); padding: 4px 8px; border-radius: 6px; width: fit-content; }

        .progress-section { padding: 14px 16px; border-radius: 14px; border: 1px solid rgba(128,128,128,0.1); background: var(--card-background-color, #ffffff); box-shadow: 0 4px 12px rgba(0,0,0,0.03); margin-top: 14px; }
        .progress-header { display: flex; justify-content: space-between; font-size: 0.8rem; color: var(--dc-text-main); font-weight: 700; margin-bottom: 10px; }
        .progress-bar-bg { height: 8px; background-color: var(--dc-progress-bg); border-radius: 4px; overflow: hidden; box-shadow: inset 1px 1px 3px rgba(0,0,0,0.05); }
        .progress-bar-fill { height: 100%; border-radius: 4px; transition: width 1s ease, background-color 0.5s ease; }

        .accessories-grid { display: grid; gap: 14px; margin-top: 16px; }
        .grid-1 { grid-template-columns: 1fr; }
        .grid-2 { grid-template-columns: repeat(2, 1fr); }
        @media (max-width: 380px) { .grid-2 { grid-template-columns: 1fr; } }
        
        .accessory-item { background: var(--card-background-color, #ffffff); border-radius: 16px; padding: 16px; box-shadow: 0 4px 15px rgba(0,0,0,0.04); border: 1px solid rgba(128,128,128,0.08); position: relative; display: flex; flex-direction: column; gap: 12px; transition: transform 0.2s ease; overflow: hidden; }
        .accessory-item:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(0,0,0,0.06); }
        
        /* 🔥 全局化退役样式：无论是封存、遗失还是失效，全部变灰 */
        .acc-lost { filter: grayscale(1) opacity(0.7); background: #f9f9f9; }
        
        .acc-top { display: flex; flex-direction: row; align-items: center; gap: 16px; z-index: 5; position: relative; }
        
        .acc-img-box { width: 56px; height: 56px; border-radius: 12px; background: var(--dc-progress-bg); display: flex; align-items: center; justify-content: center; overflow: hidden; flex-shrink: 0; box-shadow: inset 0 2px 4px rgba(0,0,0,0.05); border: 1px solid rgba(128,128,128,0.1); position: relative; }
        .acc-img-box img.acc-actual-img { width: 100%; height: 100%; object-fit: cover; position: absolute; inset: 0; z-index: 2; }
        .acc-img-box ha-icon.acc-fallback-icon { color: var(--dc-text-sub); --mdc-icon-size: 28px; position: relative; z-index: 1; }
        
        .consumable-icon-box { width: 28px; height: 28px; border-radius: 8px; background: var(--dc-progress-bg); display: flex; align-items: center; justify-content: center; overflow: hidden; position: relative; box-shadow: 1px 1px 4px rgba(0,0,0,0.08); }
        .consumable-icon-box img { width: 100%; height: 100%; object-fit: cover; position: absolute; inset: 0; z-index: 2; }
        .consumable-icon-box ha-icon { --mdc-icon-size: 18px; color: var(--dc-theme); position: relative; z-index: 1; }

        .acc-info { display: flex; flex-direction: column; gap: 4px; justify-content: center; flex-grow: 1; overflow: hidden; align-items: flex-start; }
        .acc-name { font-size: 1.0rem; font-weight: 800; color: var(--dc-text-main); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; width: 100%; }
        .acc-price { font-size: 1.15rem; font-weight: 800; color: var(--dc-theme); line-height: 1; margin-top: 2px; }
        .acc-value { font-size: 1.05rem; font-weight: 800; color: #FF9800; line-height: 1; margin-top: 2px; }
        
        .acc-meta { display: flex; flex-wrap: wrap; gap: 8px; font-size: 0.75rem; color: var(--dc-text-sub); margin-top: 4px; }
        .acc-meta span { background: rgba(128,128,128,0.06); padding: 4px 8px; border-radius: 6px; font-weight: 600; border: 1px solid rgba(128,128,128,0.05); }
        
        .acc-inst-bar { height: 6px; background-color: var(--dc-progress-bg); border-radius: 3px; overflow: hidden; margin-top: 4px; box-shadow: inset 1px 1px 2px rgba(0,0,0,0.05); }
        .acc-inst-fill { height: 100%; border-radius: 3px; transition: width 1s ease; }

        .lost-overlay { position: absolute; inset: 0; background: rgba(255,255,255,0.4); z-index: 1; pointer-events: none; }
        .lost-stamp-mini { position: absolute; top: 12px; right: 12px; z-index: 2; color: #E53935; border: 2px solid #E53935; border-radius: 6px; padding: 2px 8px; font-size: 0.75rem; font-weight: 900; transform: rotate(-15deg); opacity: 0.85; background: rgba(255,255,255,0.9); box-shadow: 2px 2px 6px rgba(0,0,0,0.1); }

        .badges-container { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; padding-top: 16px; border-top: 1px dashed rgba(128,128,128,0.2); }
        .badge-item { display: flex; align-items: center; gap: 4px; padding: 5px 12px; border-radius: 12px; font-size: 0.75rem; font-weight: 700; background: var(--card-background-color, #ffffff); box-shadow: 0 2px 6px rgba(0,0,0,0.05); border: 1px solid rgba(128,128,128,0.08); }
        .empty-state { text-align: center; color: var(--dc-theme); font-size: 1rem; padding: 20px 0; font-weight: 600; }
        .action-btn { background: var(--dc-theme); color: white; border: none; padding: 4px 10px; border-radius: 6px; cursor: pointer; font-size: 0.75rem; font-weight: bold; }
        .action-btn-outline { background: transparent; color: var(--dc-theme); border: 1px solid var(--dc-theme); padding: 4px 10px; border-radius: 6px; cursor: pointer; font-size: 0.75rem; font-weight: bold; transition: all 0.2s; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
        .action-btn-outline:hover { background: var(--dc-theme); color: white; }
        .inline-input-wrap { display: none; gap: 4px; align-items: center; }
        .inline-input-wrap input { width: 45px; padding: 2px 4px; border: 1px solid var(--dc-theme); border-radius: 4px; background: transparent; color: var(--dc-text-main); font-size: 0.75rem; text-align: center; outline: none; }
      </style>

      <ha-card id="main-card">
        <div id="category-tag" class="category-tag"></div>
        <div id="wearing-badge" class="wearing-badge" style="display:none;"><ha-icon icon="mdi:sparkles"></ha-icon></div>
        <div id="retire-stamp" class="retire-stamp" style="display:none;"></div>
        
        <div id="content-area">
          <div class="header">
            <div class="icon-wrapper" id="icon-box"><ha-icon id="device-icon" icon="mdi:calendar-heart"></ha-icon></div>
            <div class="device-name" id="device-name">...</div>
          </div>
          <div class="main-stats">
            <div class="days-value" id="days-value">-</div>
            <div class="days-unit" id="days-unit">天的陪伴</div>
          </div>
          
          <div class="tags-row" id="tags-row">
             <div class="soft-tag"><ha-icon icon="mdi:calendar-import"></ha-icon>起始: <span id="start-date-val">...</span></div>
             <div id="end-tag" class="soft-tag" style="display:none;"><ha-icon icon="mdi:calendar-export"></ha-icon>到期: <span id="end-date-val">...</span></div>
          </div>

          <div id="financial-zone">
            <div id="financial-grid" class="financial-grid"></div>
            <div id="cost-breakdown" class="cost-tags-wrapper" style="display:none;"></div>
          </div>

          <div id="memorial-diary" class="memorial-diary" style="display:none;">
             <div class="diary-story" id="diary-story"></div>
             <div class="diary-location" id="diary-location"></div>
          </div>

          <div id="installment-section" class="progress-section" style="display:none;">
            <div class="progress-header" style="margin-bottom:8px;"><span id="installment-text">分期进度</span><span id="outstanding-balance">待还: ￥0.00</span></div>
            <div class="progress-bar-bg"><div class="progress-bar-fill" id="progress-fill"></div></div>
          </div>

          <div id="service-progress-container" class="progress-section" style="display:none;">
            <div class="progress-header">
                <span id="service-header-text" style="display:flex; align-items:center;">服务有效期</span>
                <div style="display:flex; gap:8px; align-items:center;">
                    <span id="service-remain-text">...</span>
                    <button class="action-btn-outline" id="btn-renew-service" style="display:none;"><ha-icon icon="mdi:refresh" style="--mdc-icon-size:12px; margin-right:2px;"></ha-icon>一键续订</button>
                </div>
            </div>
            <div class="progress-bar-bg"><div class="progress-bar-fill" id="service-fill"></div></div>
          </div>

          <div id="consumables-container"></div>
          <div id="accessories-container" class="accessories-grid"></div>
          <div class="badges-container" id="badges-container" style="display:none;"></div>
        </div>
        <div id="empty-area" class="empty-state" style="display:none;">配置加载中或未选择设备 ⚙️</div>
      </ha-card>
    `;
    this.content = shadow;

    const shadowRoot = this.content;
    shadowRoot.getElementById("btn-renew-service").addEventListener("click", () => {
      const price = dcNumber(this._lastAttrs?.renewal_price ?? this._lastAttrs?.total_price);
      const expiration = this._lastAttrs?.expiration_date || "当前到期日";
      const confirmed = window.confirm(`确认按原周期续订？\n当前到期：${expiration}\n本次预计费用：￥${price.toFixed(2)}`);
      if (confirmed) this._callAction("renew_service");
    });
  }

  _callAction(action, data = {}) {
    const services = {
      renew_service: "renew_service",
      replace_consumable: "replace_consumable",
      set_lifecycle: "set_lifecycle",
    };
    const service = services[action];
    if (!service || !this.config?.entity) return;
    Promise.resolve(this._hass.callService("device_companion", service, {
      entity_id: this.config.entity,
      ...data,
    })).catch((error) => {
      console.error("HomeAsset Companion service call failed", error);
      window.alert("操作失败，请检查 Home Assistant 日志或服务参数。");
    });
  }

  updateData() {
    const shadow = this.content;
    const entityId = this.config?.entity;
    const stateObj = entityId ? this._hass.states[entityId] : undefined;
    if (!stateObj) {
      shadow.getElementById("content-area").style.display = "none";
      shadow.getElementById("empty-area").style.display = "block";
      return;
    }

    shadow.getElementById("content-area").style.display = "block";
    shadow.getElementById("empty-area").style.display = "none";

    const attrs = stateObj.attributes || {};
    this._lastAttrs = attrs;
    const state = stateObj.state;
    const kind = attrs.kind || (attrs.category === "虚拟服务" ? "service" : attrs.category === "纪念珍藏" ? "memorial" : "asset");
    const isService = kind === "service";
    const isMemorial = kind === "memorial";
    const isEvent = kind === "event" || attrs.is_event === true;
    const terminalStatuses = new Set(["archived", "sold", "scrapped", "lost", "gifted", "canceled", "expired"]);
    const isTerminal = attrs.is_terminal === true || terminalStatuses.has(attrs.status);

    const themeColors = {
      "数码产品": "#4A90E2",
      "生活家电": "#D35400",
      "交通出行": "#50E3C2",
      "虚拟服务": "#9013FE",
      "纪念珍藏": "#E91E63",
      "纪念事件": "#E91E63",
      "其他类别": "#C4A484",
    };
    const mainCard = shadow.getElementById("main-card");
    const themeColor = themeColors[attrs.category] || "#C4A484";
    mainCard.style.setProperty("--dc-theme", themeColor);
    const hex = themeColor.replace("#", "");
    const r = parseInt(hex.slice(0, 2), 16);
    const g = parseInt(hex.slice(2, 4), 16);
    const b = parseInt(hex.slice(4, 6), 16);
    mainCard.style.setProperty("--dc-theme-rgb", `${r}, ${g}, ${b}`);

    shadow.getElementById("category-tag").textContent = attrs.category || "陪伴";
    shadow.getElementById("device-name").textContent = this.config.name || attrs.friendly_name || "设备";
    shadow.getElementById("days-value").textContent = state;
    shadow.getElementById("start-date-val").textContent = attrs.purchase_date || "...";
    shadow.getElementById("wearing-badge").style.display = attrs.is_wearing ? "block" : "none";

    const fallbackIcon = shadow.getElementById("device-icon");
    fallbackIcon.setAttribute("icon", dcSafeIcon(this.config.icon || "mdi:calendar-heart"));

    const unitEl = shadow.getElementById("days-unit");
    const stampEl = shadow.getElementById("retire-stamp");
    if (isTerminal) {
      mainCard.classList.add("is-retired");
      stampEl.style.display = "flex";
      const label = attrs.status_label || attrs.retire_reason || "已停止";
      let stampHtml = `<span class="stamp-main">${dcEscape(label)}</span>`;
      if (attrs.stored_status === "sold" && dcNumber(attrs.recovery_amount) > 0) {
        stampHtml += `<span class="stamp-sub">回收 ￥${dcNumber(attrs.recovery_amount).toFixed(2)}</span>`;
      }
      stampEl.innerHTML = stampHtml;
      unitEl.textContent = attrs.status === "expired" ? "天（服务已到期）" : "天（已定格）";
    } else {
      mainCard.classList.remove("is-retired");
      stampEl.style.display = "none";
      if (attrs.status === "idle") unitEl.textContent = "天（闲置持有）";
      else if (isService) unitEl.textContent = "天（服务中）";
      else if (isMemorial || isEvent) unitEl.textContent = "天（已记录）";
      else unitEl.textContent = "天的陪伴";
    }

    const endTag = shadow.getElementById("end-tag");
    if (isService && attrs.expiration_date) {
      endTag.style.display = "inline-flex";
      shadow.getElementById("end-date-val").textContent = attrs.expiration_date;
    } else {
      endTag.style.display = "none";
    }

    const iconBox = shadow.getElementById("icon-box");
    const imageUrl = dcSafeImageUrl(this.config.image || attrs.entity_picture || "");
    let image = iconBox.querySelector("img.device-photo");
    if (imageUrl) {
      if (!image) {
        image = document.createElement("img");
        image.className = "device-photo";
        image.addEventListener("error", () => {
          image.style.display = "none";
          fallbackIcon.style.display = "block";
        });
        iconBox.appendChild(image);
      }
      if (image.src !== new URL(imageUrl, window.location.origin).href) image.src = imageUrl;
      image.style.display = "block";
      fallbackIcon.style.display = "none";
    } else {
      if (image) image.remove();
      fallbackIcon.style.display = "block";
    }

    const financialZone = shadow.getElementById("financial-zone");
    const memorialDiary = shadow.getElementById("memorial-diary");
    if (isEvent) {
      financialZone.style.display = "none";
      memorialDiary.style.display = "none";
    } else if (isMemorial) {
      financialZone.style.display = "none";
      memorialDiary.style.display = "block";
      shadow.getElementById("diary-story").textContent = attrs.story || "这里还没有写下这件物品的故事。";
      const location = shadow.getElementById("diary-location");
      if (attrs.location || attrs.is_wearing) {
        location.style.display = "flex";
        location.replaceChildren();
        const icon = document.createElement("ha-icon");
        icon.setAttribute("icon", "mdi:map-marker-radius");
        const text = document.createElement("span");
        text.textContent = attrs.is_wearing ? "随身佩戴中" : `存放在：${attrs.location}`;
        location.append(icon, text);
      } else {
        location.style.display = "none";
      }
    } else {
      financialZone.style.display = "block";
      memorialDiary.style.display = "none";
      const historicalDaily = dcNumber(attrs.historical_daily_cost ?? attrs.daily_cost);
      const historicalMonthly = dcNumber(attrs.historical_monthly_cost, historicalDaily * 30.4375);
      const currentMonthly = dcNumber(attrs.current_monthly_cost);
      const mainNet = dcNumber(attrs.main_net_investment ?? attrs.net_price ?? attrs.total_price);
      const totalCons = dcNumber(attrs.total_consumable_cost);
      const totalAcc = dcNumber(attrs.total_accessory_net);
      const accessories = attrs.accessories_list || [];
      const hasAccessories = accessories.length > 0;
      const hasConsumables = totalCons > 0;

      const gridItems = [
        `<div class="stat-item"><span class="stat-label">历史日均成本</span><span class="stat-value">￥${historicalDaily.toFixed(2)}</span></div>`,
        `<div class="stat-item"><span class="stat-label">${isService ? "服务累计投入" : "主体净投入"}</span><span class="stat-value">￥${mainNet.toFixed(2)}</span></div>`,
      ];
      if (hasAccessories && !isService) {
        gridItems.push(`<div class="stat-item"><span class="stat-label">主体与配件净投入</span><span class="stat-value" style="color:var(--dc-theme)">￥${(mainNet + totalAcc).toFixed(2)}</span></div>`);
      }
      if (hasConsumables) {
        gridItems.push(`<div class="stat-item"><span class="stat-label">历史耗材投入</span><span class="stat-value" style="color:var(--dc-theme)">￥${totalCons.toFixed(2)}</span></div>`);
      }
      const finGrid = shadow.getElementById("financial-grid");
      finGrid.style.gridTemplateColumns = gridItems.length > 2 ? "repeat(2, 1fr)" : `repeat(${gridItems.length}, 1fr)`;
      finGrid.innerHTML = gridItems.join("");

      const breakdown = shadow.getElementById("cost-breakdown");
      const breakdownItems = [
        `<div class="cost-tag">历史月均 <span class="hl">￥${historicalMonthly.toFixed(2)}</span></div>`,
        `<div class="cost-tag">当前月度运行 <span class="hl">￥${currentMonthly.toFixed(2)}</span></div>`,
      ];
      if (isService && dcNumber(attrs.total_saved_value) > 0) {
        breakdownItems.unshift(`<div class="saved-value-tag"><ha-icon icon="mdi:gift-open" style="--mdc-icon-size:14px;color:white;"></ha-icon>附加权益价值 ￥${dcNumber(attrs.total_saved_value).toFixed(2)}</div>`);
      }
      breakdown.style.display = "flex";
      breakdown.innerHTML = breakdownItems.join("");
    }

    const installment = shadow.getElementById("installment-section");
    if (attrs.installment_months > 0 && !attrs.is_paid_off && !attrs.early_payoff) {
      installment.style.display = "block";
      const paid = dcNumber(attrs.months_paid);
      const total = Math.max(1, dcNumber(attrs.installment_months, 1));
      const ratio = Math.max(0, Math.min(1, paid / total));
      shadow.getElementById("installment-text").textContent = `${dcNumber(attrs.installment_interest) <= 0 ? "免息分期" : "分期进度"} (${paid}/${total})`;
      shadow.getElementById("outstanding-balance").textContent = `待还：￥${dcNumber(attrs.outstanding_balance).toFixed(2)}`;
      const fill = shadow.getElementById("progress-fill");
      fill.style.width = `${ratio * 100}%`;
      fill.style.backgroundColor = ratio >= 0.33 ? "#2196F3" : "#FFC107";
    } else {
      installment.style.display = "none";
    }

    const serviceContainer = shadow.getElementById("service-progress-container");
    if (isService) {
      serviceContainer.style.display = "block";
      const header = shadow.getElementById("service-header-text");
      const remain = shadow.getElementById("service-remain-text");
      const fill = shadow.getElementById("service-fill");
      const renew = shadow.getElementById("btn-renew-service");
      const expiration = attrs.expiration_date;
      if (expiration === "永久") {
        header.textContent = "永久有效";
        remain.textContent = "∞";
        fill.style.width = "100%";
        fill.style.backgroundColor = "#4CAF50";
        renew.style.display = "none";
      } else if (expiration) {
        header.textContent = `订阅至 ${expiration}`;
        remain.textContent = attrs.status === "expired" ? "已到期" : `剩 ${dcNumber(attrs.service_remain_days)} 天`;
        const percent = Math.max(0, Math.min(100, dcNumber(attrs.service_percent)));
        const days = dcNumber(attrs.service_remain_days);
        fill.style.width = `${percent}%`;
        fill.style.backgroundColor = attrs.status === "expired" || days <= 15 ? "#E53935" : days <= 60 ? "#FF9800" : days <= 180 ? "#FFC107" : "#4CAF50";
        renew.style.display = attrs.stored_status === "canceled" ? "none" : "inline-flex";
      } else {
        header.textContent = "尚未配置到期日";
        remain.textContent = "-";
        fill.style.width = "0%";
        fill.style.backgroundColor = "#E53935";
        renew.style.display = "none";
      }
    } else {
      serviceContainer.style.display = "none";
    }

    const consumablesContainer = shadow.getElementById("consumables-container");
    const consumables = attrs.consumables_list || [];
    const consumableFingerprint = JSON.stringify({ consumables, isTerminal });
    if (this._lastConsFingerprint !== consumableFingerprint) {
      this._lastConsFingerprint = consumableFingerprint;
      consumablesContainer.innerHTML = "";
      consumables.forEach((cons) => {
        const section = document.createElement("div");
        section.className = "progress-section";
        const percent = Number.isFinite(Number(cons.percent)) ? Math.max(0, Math.min(100, Number(cons.percent))) : null;
        const image = dcSafeImageUrl(cons.image || "");
        const iconHtml = image
          ? `<div class="consumable-icon-box"><img src="${dcEscape(image)}"/><ha-icon icon="mdi:filter-outline" style="display:none;"></ha-icon></div>`
          : `<div class="consumable-icon-box"><ha-icon icon="mdi:filter-outline"></ha-icon></div>`;
        const remainText = cons.tracking_available === false ? "实体不可用" : (cons.is_smart ? `${percent ?? "-"}%` : `剩 ${dcEscape(cons.remain || "-")}`);
        const dailyText = `预计 ￥${dcNumber(cons.current_daily_cost ?? cons.daily_cost).toFixed(2)}/天`;
        const barColor = percent === null ? "#9E9E9E" : percent <= 25 ? "#E53935" : percent <= 50 ? "#FFC107" : "#8BC34A";
        const buttonHtml = isTerminal ? "" : `<button class="action-btn-outline" id="btn-show-rep-${dcEscape(cons.id)}">确认换新</button><div class="inline-input-wrap" id="wrap-rep-${dcEscape(cons.id)}"><input type="number" id="inp-rep-${dcEscape(cons.id)}" value="${dcNumber(cons.price).toFixed(2)}" step="0.01" min="0"><button class="action-btn" id="btn-cfm-${dcEscape(cons.id)}">✓</button></div>`;
        section.innerHTML = `<div class="progress-header"><span style="display:flex;align-items:center;gap:8px;">${iconHtml}<span>${dcEscape(cons.name || "耗材")}</span></span><span style="display:flex;gap:8px;align-items:center;"><span>${remainText} <span style="opacity:.6;font-weight:normal;">${dailyText}</span></span>${buttonHtml}</span></div><div class="progress-bar-bg"><div class="progress-bar-fill" style="width:${percent ?? 0}%;background-color:${barColor}!important;"></div></div>`;
        consumablesContainer.appendChild(section);
        const imageElement = section.querySelector(".consumable-icon-box img");
        if (imageElement) imageElement.addEventListener("error", () => {
          imageElement.style.display = "none";
          imageElement.nextElementSibling.style.display = "block";
        });
        if (!isTerminal) {
          const showButton = section.querySelector(`#btn-show-rep-${CSS.escape(cons.id)}`);
          const confirmButton = section.querySelector(`#btn-cfm-${CSS.escape(cons.id)}`);
          showButton?.addEventListener("click", () => {
            showButton.style.display = "none";
            section.querySelector(`#wrap-rep-${CSS.escape(cons.id)}`).style.display = "flex";
          });
          confirmButton?.addEventListener("click", () => {
            const cost = dcNumber(section.querySelector(`#inp-rep-${CSS.escape(cons.id)}`).value);
            this._callAction("replace_consumable", { cons_id: cons.id, cost });
          });
        }
      });
    }

    const accessoriesContainer = shadow.getElementById("accessories-container");
    const accessories = attrs.accessories_list || [];
    const accessoryFingerprint = JSON.stringify({ accessories, kind, isTerminal });
    if (this._lastAccFingerprint !== accessoryFingerprint) {
      this._lastAccFingerprint = accessoryFingerprint;
      accessoriesContainer.className = `accessories-grid ${((isMemorial || isService) && accessories.length > 1) ? "grid-2" : "grid-1"}`;
      accessoriesContainer.innerHTML = "";
      accessories.forEach((acc) => {
        const div = document.createElement("div");
        const accTerminal = acc.is_retired === true || terminalStatuses.has(acc.status);
        div.className = `accessory-item ${accTerminal ? "acc-lost" : ""}`;
        const statusLabel = acc.status_label || acc.reason || "已停止";
        const stamp = accTerminal ? `<div class="lost-overlay"></div><div class="lost-stamp-mini">${dcEscape(statusLabel)}</div>` : "";
        const defaultIcon = isService ? "mdi:gift" : isMemorial ? "mdi:ring" : "mdi:puzzle-outline";
        const image = dcSafeImageUrl(acc.image || "");
        const iconHtml = image
          ? `<img class="acc-actual-img" src="${dcEscape(image)}"><ha-icon class="acc-fallback-icon" icon="${defaultIcon}" style="display:none;"></ha-icon>`
          : `<ha-icon class="acc-fallback-icon" icon="${defaultIcon}"></ha-icon>`;
        let priceHtml;
        let metaHtml;
        if (isService) {
          priceHtml = `<div class="acc-value">权益价值 ￥${dcNumber(acc.price).toFixed(2)}</div>`;
          metaHtml = `<span>${dcEscape(acc.purchase_date || "")}</span><span>${acc.expiration_date ? `至 ${dcEscape(acc.expiration_date)}` : "跟随主服务"}</span>`;
        } else {
          priceHtml = `<div class="acc-price">净投入 ￥${dcNumber(acc.net_investment ?? acc.price).toFixed(2)}</div>`;
          metaHtml = `<span>${dcEscape(acc.purchase_date || "")}</span><span>${isMemorial ? "相伴" : "记录"} ${dcNumber(acc.days)} 天</span>`;
        }
        if (accTerminal) metaHtml += `<span style="background:rgba(229,57,53,.1);color:#E53935;border:none;">${dcEscape(statusLabel)}</span>`;

        let installmentHtml = "";
        if (!isMemorial && !isService && acc.is_installment && acc.installment_months > 0 && !acc.is_paid_off && !acc.early_payoff) {
          const ratio = Math.max(0, Math.min(1, dcNumber(acc.months_paid) / Math.max(1, dcNumber(acc.installment_months, 1))));
          installmentHtml = `<div style="display:flex;justify-content:space-between;font-size:.7rem;margin-top:8px;color:var(--dc-text-sub);width:100%;"><span>${dcNumber(acc.installment_interest) <= 0 ? "免息" : "分期"} (${dcNumber(acc.months_paid)}/${dcNumber(acc.installment_months)})</span><span>待还￥${dcNumber(acc.outstanding_balance).toFixed(2)}</span></div><div class="acc-inst-bar" style="width:100%;"><div class="acc-inst-fill" style="width:${ratio * 100}%;background-color:${ratio >= .33 ? "#2196F3" : "#FFC107"}!important;"></div></div>`;
        }
        div.innerHTML = `${stamp}<div class="acc-top"><div class="acc-img-box">${iconHtml}</div><div class="acc-info"><div class="acc-name">${acc.is_wearing ? "✨ " : ""}${dcEscape(acc.name || "附属项目")}</div>${priceHtml}</div></div><div class="acc-meta">${metaHtml}</div>${installmentHtml}`;
        accessoriesContainer.appendChild(div);
        const imageElement = div.querySelector("img.acc-actual-img");
        if (imageElement) imageElement.addEventListener("error", () => {
          imageElement.style.display = "none";
          imageElement.nextElementSibling.style.display = "block";
        });
      });
    }

    const badgeContainer = shadow.getElementById("badges-container");
    const badges = attrs.badges || [];
    const badgeFingerprint = JSON.stringify(badges);
    if (this._lastBadgeFP !== badgeFingerprint) {
      this._lastBadgeFP = badgeFingerprint;
      badgeContainer.innerHTML = "";
      badgeContainer.style.display = badges.length ? "flex" : "none";
      badges.forEach((badge) => {
        const item = document.createElement("div");
        item.className = "badge-item";
        if (/^#[0-9a-f]{6}$/i.test(badge.color || "")) item.style.color = badge.color;
        const icon = document.createElement("ha-icon");
        icon.setAttribute("icon", dcSafeIcon(badge.icon || "mdi:information-outline"));
        icon.style.setProperty("--mdc-icon-size", "14px");
        const label = document.createElement("span");
        label.textContent = badge.label || "";
        item.append(icon, label);
        badgeContainer.appendChild(item);
      });
    }
  }

  getCardSize() { return 4; }
}

class DeviceCompanionCardEditor extends HTMLElement {
  constructor() { super(); this.attachShadow({ mode: "open" }); }
  setConfig(config) { this._config = config; this._updateDropdown(); this.updateForm(); }
  set hass(hass) { this._hass = hass; this._updateDropdown(); this.updateForm(); }
  
  _updateDropdown() {
      if (!this.shadowRoot) return;
      const sel = this.shadowRoot.getElementById('target-selector');
      if (!sel) return;
      const entityId = this._config ? this._config.entity : null;
      const stateObj = (entityId && this._hass) ? this._hass.states[entityId] : null;
      
      const consumables = stateObj ? (stateObj.attributes.consumables_list || []) : [];
      const accessories = stateObj ? (stateObj.attributes.accessories_list || []) : [];
      
      const currentVal = sel.value;
      sel.replaceChildren();
      const mainOption = document.createElement("option");
      mainOption.value = "main";
      mainOption.textContent = "主物件/设备（卡片主图）";
      sel.appendChild(mainOption);
      consumables.forEach((item) => {
        const option = document.createElement("option");
        option.value = item.id;
        option.textContent = `耗材：${item.name || "未命名"}`;
        sel.appendChild(option);
      });
      accessories.forEach((item) => {
        const option = document.createElement("option");
        option.value = item.id;
        option.textContent = `附属项目：${item.name || "未命名"}`;
        sel.appendChild(option);
      });
      if (Array.from(sel.options).some((option) => option.value === currentVal)) sel.value = currentVal;
  }

  updateForm() {
    if (!this._hass || !this._config) return;
    let form = this.shadowRoot.querySelector('ha-form');
    if (!form) {
      form = document.createElement('ha-form');
      form.schema = [ { name: "entity", selector: { entity: { domain: "sensor" } } }, { name: "name", selector: { text: {} } }, { name: "icon", selector: { icon: {} } } ];
      form.computeLabel = (s) => ({ 'entity': '关联陪伴传感器', 'name': '覆盖显示名称', 'icon': '覆盖默认图标' }[s.name] || s.name);
      form.addEventListener('value-changed', (ev) => this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: ev.detail.value }, bubbles: true, composed: true })));
      
      const uploaderSection = document.createElement('div');
      uploaderSection.innerHTML = `
        <style>
          .uploader-wrapper { margin-top: 16px; padding: 16px; background: var(--secondary-background-color, #EAE6DF); border-radius: 8px; display: flex; flex-direction: column; gap: 12px; } 
          .target-selector { padding: 8px; border-radius: 6px; border: 1px solid var(--divider-color); font-family: inherit; font-size: 0.9rem; background: var(--card-background-color); color: var(--primary-text-color); width: 100%; box-sizing: border-box; }
          .upload-row { display: flex; align-items: center; gap: 8px; }
          .upload-btn { background: var(--primary-color); color: var(--text-primary-color, white); border: none; border-radius: 4px; padding: 8px 16px; font-weight: 500; cursor: pointer; display: flex; align-items: center; gap: 8px; } 
          .upload-btn:disabled { background: var(--disabled-text-color); cursor: not-allowed; } 
          .status { font-size: 0.85rem; color: var(--secondary-text-color); font-weight: 500;} 
          input[type="file"] { display: none; }
        </style>
        <div class="uploader-wrapper">
            <div style="font-weight:bold; font-size:0.9rem; color:var(--primary-text-color);">📷 图片上传与绑定</div>
            <select id="target-selector" class="target-selector"><option value="main">主设备/物件 (卡片左侧大图)</option></select>
            <div class="upload-row">
              <input type="file" id="file-input" accept="image/png, image/jpeg, image/webp" />
              <button class="upload-btn" id="upload-btn"><ha-icon icon="mdi:upload" style="--mdc-icon-size: 18px;"></ha-icon>上传并绑定</button>
              <span class="status" id="upload-status"></span>
            </div>
        </div>
      `;
      this.shadowRoot.innerHTML = ''; this.shadowRoot.appendChild(form); this.shadowRoot.appendChild(uploaderSection);
      this._updateDropdown(); 
      
      const fileInput = this.shadowRoot.getElementById('file-input'); 
      const uploadBtn = this.shadowRoot.getElementById('upload-btn'); 
      const statusText = this.shadowRoot.getElementById('upload-status');
      const targetSelector = this.shadowRoot.getElementById('target-selector');
      
      uploadBtn.addEventListener('click', () => fileInput.click());
      
      fileInput.addEventListener('change', async (ev) => {
        const file = ev.target.files[0]; if (!file) return;
        if (file.size > 5 * 1024 * 1024) {
          statusText.textContent = "图片不能超过 5 MB";
          statusText.style.color = "red";
          fileInput.value = "";
          return;
        }
        uploadBtn.disabled = true; statusText.textContent = `上传中...`; 
        const formData = new FormData(); formData.append("file", file); formData.append("device_name", this._config.name || this._config.entity || "device");
        try {
          let token = ''; if (this._hass && this._hass.auth) token = this._hass.auth.accessToken || (this._hass.auth.data && this._hass.auth.data.access_token) || '';
          const response = await fetch('/api/device_companion/upload', { method: 'POST', body: formData, headers: token ? { 'Authorization': `Bearer ${token}` } : {} });
          const result = await response.json();
          if (!response.ok || !result.success) throw new Error(result.error || "upload_failed");
          statusText.textContent = "绑定成功 ✓"; statusText.style.color = "green";
          const target = targetSelector.value;
          if (target === "main") {
              this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: { ...this._config, image: result.url } }, bubbles: true, composed: true }));
          } else {
              this._hass.callService("device_companion", "update_item_image", { entity_id: this._config.entity, item_id: target, image_url: result.url });
          }
        } catch (err) { statusText.textContent = `失败`; statusText.style.color = "red"; } finally { uploadBtn.disabled = false; fileInput.value = ''; setTimeout(() => { statusText.textContent = ""; }, 3000); }
      });
    }
    form.hass = this._hass; form.data = this._config;
  }
}

if (!customElements.get("device-companion-editor-v2")) customElements.define("device-companion-editor-v2", DeviceCompanionCardEditor);
if (!customElements.get("device-companion-card")) customElements.define("device-companion-card", DeviceCompanionCard);

// 彻底闭环注册器
window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "device-companion-card")) {
  window.customCards.push({
    type: "device-companion-card",
    name: "HomeAsset Companion 详情卡",
    preview: true,
    description: "v1.1.0：统一生命周期状态、准确成本口径与显式服务调用。"
  });
}