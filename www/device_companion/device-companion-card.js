/**
 * Device Companion Card (Ultimate V153 Logic Loop Edition)
 * 特性：彻底修复封存/退役 UI 不生效 Bug，引入智能状态印章与自动纠错引擎
 */

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
        this._callAction("renew_service");
    });
  }

  _callAction(action, data = {}) { this._hass.callService("device_companion", "quick_action", { entity_id: this.config.entity, action: action, ...data }); }
  updateData() {
    const shadow = this.content;
    const entityId = this.config.entity;
    if (!entityId || !this._hass.states[entityId]) {
        shadow.getElementById("content-area").style.display = "none";
        shadow.getElementById("empty-area").style.display = "block";
        return;
    }
    shadow.getElementById("content-area").style.display = "block";
    shadow.getElementById("empty-area").style.display = "none";

    const attrs = this._hass.states[entityId].attributes || {};
    const state = this._hass.states[entityId].state;
    const isService = attrs.category && attrs.category.includes("服务");
    const isMemorial = attrs.category === "纪念珍藏";

    const themeColors = { "数码产品": "#4A90E2", "生活家电": "#D35400", "交通出行": "#50E3C2", "虚拟服务": "#9013FE", "纪念珍藏": "#E91E63", "其他类别": "#C4A484" };
    const mainCard = shadow.getElementById("main-card");
    const themeColor = themeColors[attrs.category] || "#C4A484";
    mainCard.style.setProperty('--dc-theme', themeColor);
    
    let hex = themeColor.replace('#', '');
    if(hex.length === 3) hex = hex[0]+hex[0]+hex[1]+hex[1]+hex[2]+hex[2];
    const r = parseInt(hex.substring(0,2), 16), g = parseInt(hex.substring(2,4), 16), b = parseInt(hex.substring(4,6), 16);
    mainCard.style.setProperty('--dc-theme-rgb', `${r}, ${g}, ${b}`);

    shadow.getElementById("category-tag").textContent = attrs.category || "陪伴";
    shadow.getElementById("device-name").textContent = this.config.name || attrs.friendly_name || "设备";
    shadow.getElementById("days-value").textContent = state;
    shadow.getElementById("start-date-val").textContent = attrs.purchase_date || "...";
    
    shadow.getElementById("wearing-badge").style.display = attrs.is_wearing ? "block" : "none";

    const unitEl = shadow.getElementById("days-unit");
    const stampEl = shadow.getElementById("retire-stamp");
    
    // 🔥 V153 主设备状态智能纠错：绝对服从 is_retired，并自动纠正“正常”文案
    const isActuallyRetired = attrs.status === "retired";

    if (isActuallyRetired) {
      mainCard.classList.add("is-retired"); stampEl.style.display = "flex";
      let mainReason = attrs.retire_reason || "封存";
      if (mainReason.includes("正常")) mainReason = isService ? "已失效" : "已封存";

      let stampHtml = `<span class="stamp-main">${mainReason}</span>`;
      if (mainReason === "二手回血" && attrs.recovery_amount > 0) stampHtml += `<span class="stamp-sub">+￥${attrs.recovery_amount}</span>`;
      stampEl.innerHTML = stampHtml;
      unitEl.textContent = (mainReason.includes("闲置") || mainReason.includes("封存")) ? "天 (封存中)" : "天 (已定格)";
    } else {
      mainCard.classList.remove("is-retired"); stampEl.style.display = "none";
      unitEl.textContent = isService ? "天 (服务中)" : (isMemorial ? "天 (相伴)" : "天的陪伴");
    }

    if (isService && attrs.expiration_date) {
        shadow.getElementById("end-tag").style.display = "inline-flex";
        shadow.getElementById("end-date-val").textContent = attrs.expiration_date;
    } else { shadow.getElementById("end-tag").style.display = "none"; }

    const iconBox = shadow.getElementById("icon-box");
    let rawMainImg = this.config.image || attrs.entity_picture || "";
    if (rawMainImg) {
        if(rawMainImg.startsWith("/local/")) { rawMainImg += (rawMainImg.includes("?") ? "&" : "?") + "t=" + Date.now(); }
        let safeUrl = encodeURI(rawMainImg);
        if (!iconBox.querySelector("img")) { 
            const img = document.createElement("img"); img.className = "device-photo"; img.src = safeUrl; 
            img.onerror = function(){ this.style.display='none'; shadow.getElementById("device-icon").style.display='block'; };
            iconBox.appendChild(img); shadow.getElementById("device-icon").style.display = "none"; 
        } else { 
            const img = iconBox.querySelector("img");
            img.src = safeUrl; img.style.display = "block";
            shadow.getElementById("device-icon").style.display = "none"; 
        }
    } else { 
        const imgEl = iconBox.querySelector("img"); if (imgEl) imgEl.remove(); shadow.getElementById("device-icon").style.display = "block"; 
    }

    const finZone = shadow.getElementById("financial-zone");
    const memorialDiary = shadow.getElementById("memorial-diary");
    
    const dailyCost = parseFloat(attrs.daily_cost) || 0;
    const netPrice = parseFloat(attrs.net_price || attrs.total_price) || 0;
    const totalConsCost = parseFloat(attrs.total_consumable_cost) || 0;
    const totalAccNet = parseFloat(attrs.total_accessory_net) || 0;
    const instInterest = parseFloat(attrs.installment_interest) || 0;
    const earlyFee = parseFloat(attrs.early_payoff_fee) || 0;

    if (isMemorial) {
        finZone.style.display = "none";
        memorialDiary.style.display = "block";
        let storyStr = attrs.story ? attrs.story : "这里还没有写下你们的故事...";
        shadow.getElementById("diary-story").innerHTML = storyStr.replace(/\\n/g, "<br>");
        let locEl = shadow.getElementById("diary-location");
        if (attrs.location) { locEl.style.display = "flex"; locEl.innerHTML = `<ha-icon icon="mdi:map-marker-radius"></ha-icon> ${attrs.is_wearing ? '随身佩戴中' : '存放在：'+attrs.location}`; } 
        else { locEl.style.display = "none"; }
    } else {
        finZone.style.display = "block";
        memorialDiary.style.display = "none";
        
        const finGrid = shadow.getElementById("financial-grid");
        const breakdownEl = shadow.getElementById("cost-breakdown");
        const hasCons = totalConsCost > 0;
        const hasAcc = (attrs.accessories_list && attrs.accessories_list.length > 0);
        const extraTotal = instInterest + earlyFee;
        
        let gridItems = [];
        gridItems.push(`<div class="stat-item"><span class="stat-label">总日均摊</span><span class="stat-value">￥${dailyCost.toFixed(2)}</span></div>`);
        const baseLabel = isService ? (instInterest > 0 ? '服务造价(含息)' : '服务造价') : (instInterest > 0 ? '机身造价(含息)' : '机身造价');
        gridItems.push(`<div class="stat-item"><span class="stat-label">${baseLabel}</span><span class="stat-value">￥${netPrice.toFixed(2)}</span></div>`);
        
        if (hasAcc && !isService) { gridItems.push(`<div class="stat-item"><span class="stat-label">套装总价(机+配)</span><span class="stat-value" style="color:var(--dc-theme)">￥${(netPrice + totalAccNet).toFixed(2)}</span></div>`); }
        if (hasCons) { gridItems.push(`<div class="stat-item"><span class="stat-label">累计耗材</span><span class="stat-value" style="color:var(--dc-theme)">￥${totalConsCost.toFixed(2)}</span></div>`); }

        if (gridItems.length === 4) finGrid.style.gridTemplateColumns = "repeat(2, 1fr)";
        else finGrid.style.gridTemplateColumns = `repeat(${gridItems.length}, 1fr)`;
        finGrid.innerHTML = gridItems.join("");

        let savedValueHtml = "";
        if (isService && attrs.total_saved_value > 0) {
            savedValueHtml = `<div class="saved-value-tag"><ha-icon icon="mdi:gift-open" style="--mdc-icon-size:14px; color:white;"></ha-icon>累计白嫖价值: ￥${attrs.total_saved_value.toFixed(2)}</div>`;
        }

        if (!hasCons && !hasAcc && extraTotal <= 0 && !savedValueHtml) { breakdownEl.style.display = "none"; } 
        else {
            breakdownEl.style.display = "flex";
            const capBase = isService ? "服务均摊" : "机身均摊";
            let tagsHtml = savedValueHtml;
            tagsHtml += `<div class="cost-tag">${capBase} <span class="hl">￥${(parseFloat(attrs.daily_base) || 0).toFixed(2)}</span></div>`;
            if (hasAcc && !isService) tagsHtml += `<div class="cost-tag">配件均摊 <span class="hl">￥${(parseFloat(attrs.daily_accessory) || 0).toFixed(2)}</span></div>`;
            if (hasCons) tagsHtml += `<div class="cost-tag">耗材均摊 <span class="hl">￥${(parseFloat(attrs.daily_consumable) || 0).toFixed(2)}</span></div>`;
            if (extraTotal > 0) {
                let label = "额外息费";
                if (instInterest > 0 && earlyFee > 0) label = "利息+违约金";
                else if (instInterest > 0) label = "分期利息";
                else if (earlyFee > 0) label = "结清手续费";
                tagsHtml += `<div class="cost-tag">${label} <span class="hl">￥${extraTotal.toFixed(2)}</span></div>`;
            }
            breakdownEl.innerHTML = tagsHtml;
        }
    }

    const installmentSection = shadow.getElementById("installment-section");
    if (attrs.installment_months && attrs.installment_months > 0 && !attrs.is_paid_off && !attrs.early_payoff) {
        installmentSection.style.display = "block";
        const monthsPaid = attrs.months_paid || 0;
        const totalMonths = attrs.installment_months;
        let instText = instInterest <= 0 ? "分期进度 (免息)" : "分期进度";
        const fillEl = shadow.getElementById("progress-fill");
        let instColor = (monthsPaid / totalMonths) >= 0.33 ? "#2196F3" : "#FFC107";
        fillEl.style.width = `${(monthsPaid / totalMonths) * 100}%`;
        fillEl.style.setProperty('background-color', instColor, 'important');
        const balanceElement = shadow.getElementById("outstanding-balance");
        shadow.getElementById("installment-text").textContent = `${instText} (${monthsPaid}/${totalMonths})`;
        balanceElement.textContent = `待还: ￥${(parseFloat(attrs.outstanding_balance) || 0).toFixed(2)}`;
    } else { 
        installmentSection.style.display = "none"; 
    }

    const serviceContainer = shadow.getElementById("service-progress-container");
    if (isService) {
        serviceContainer.style.display = "block";
        let expDate = attrs.expiration_date;
        const renewBtn = shadow.getElementById("btn-renew-service");
        
        if (expDate && expDate !== "永久" && expDate !== "") {
            shadow.getElementById("service-header-text").innerHTML = `<ha-icon icon="mdi:calendar-clock" style="--mdc-icon-size:14px; margin-right:4px;"></ha-icon>订阅至 ${expDate}`;
            shadow.getElementById("service-remain-text").textContent = `剩 ${attrs.service_remain_days} 天`;
            
            let srvPercent = attrs.service_percent || 0;
            let remDays = parseInt(attrs.service_remain_days) || 0;
            let srvColor = '#4CAF50'; 
            
            if (remDays <= 15 || srvPercent <= 10) {
                srvColor = '#E53935'; 
            } else if (remDays <= 60 || srvPercent <= 25) {
                srvColor = '#FF9800'; 
            } else if (remDays <= 180 || srvPercent <= 50) {
                srvColor = '#FFC107'; 
            }
            
            const fillEl = shadow.getElementById("service-fill");
            fillEl.style.width = `${srvPercent}%`;
            fillEl.style.setProperty('background-color', srvColor, 'important');
            
            if (!isActuallyRetired) renewBtn.style.display = "inline-flex";
            else renewBtn.style.display = "none";
        } else {
            shadow.getElementById("service-header-text").innerHTML = `<ha-icon icon="mdi:calendar-clock" style="--mdc-icon-size:14px; margin-right:4px; color:#E53935;"></ha-icon><span style="color:#E53935;">尚未配置或永久</span>`;
            shadow.getElementById("service-remain-text").textContent = `-`;
            shadow.getElementById("service-fill").style.width = `100%`;
            shadow.getElementById("service-fill").style.setProperty('background-color', '#E53935', 'important');
            renewBtn.style.display = "none";
        }
    } else { serviceContainer.style.display = "none"; }

    const consContainer = shadow.getElementById("consumables-container");
    const consumables = attrs.consumables_list || [];
    if (this._lastConsFingerprint !== JSON.stringify(consumables)) {
      this._lastConsFingerprint = JSON.stringify(consumables);
      consContainer.innerHTML = "";
      consumables.forEach(cons => {
          const section = document.createElement("div"); section.className = "progress-section";
          let rawConsImg = cons.image || "";
          if(rawConsImg.startsWith("/local/")) { rawConsImg += (rawConsImg.includes("?") ? "&" : "?") + "t=" + Date.now(); }
          let safeUrl = encodeURI(rawConsImg);
          
          let iconHtml = safeUrl 
              ? `<div class="consumable-icon-box"><img src="${safeUrl}" onerror="this.style.display='none'; this.nextElementSibling.style.display='block';"/><ha-icon icon="mdi:filter-outline" style="display:none;"></ha-icon></div>` 
              : `<div class="consumable-icon-box"><ha-icon icon="mdi:filter-outline"></ha-icon></div>`;
          
          let btnHtml = (!isActuallyRetired && !cons.is_smart && cons.percent <= 10) ? `<button class="action-btn" id="btn-show-rep-${cons.id}">换新</button><div class="inline-input-wrap" id="wrap-rep-${cons.id}"><input type="number" id="inp-rep-${cons.id}" value="${cons.price}" step="0.01"><button class="action-btn" id="btn-cfm-${cons.id}">✓</button></div>` : "";
          let barColor = cons.percent <= 25 ? "#E53935" : (cons.percent <= 50 ? "#FFC107" : "#8BC34A");
          
          let remainText = cons.is_smart ? `<span style="color:var(--dc-theme); font-weight:600;">实时: ${cons.percent}%</span>` : `剩 ${cons.remain} 天`;
          let dailyText = cons.is_smart ? `(动态均摊 ￥${cons.daily_cost}/天)` : `(理论均摊 ￥${cons.daily_cost}/天)`;
          let titleIcon = cons.is_smart ? `<ha-icon icon="mdi:flash" style="--mdc-icon-size:12px; color:#FFC107; margin-left:4px;"></ha-icon>` : "";
          
          section.innerHTML = `<div class="progress-header"><span class="consumable-title-wrapper" style="display:flex; align-items:center; gap:8px;">${iconHtml} <span style="font-weight:600;">${cons.name}${titleIcon}</span></span><span style="display:flex; gap:8px; align-items:center;"><span>${remainText} <span style="opacity:0.6; font-weight:normal;">${dailyText}</span></span>${btnHtml}</span></div><div class="progress-bar-bg"><div class="progress-bar-fill" style="width: ${cons.percent}%; background-color: ${barColor} !important;"></div></div>`;
          consContainer.appendChild(section);
          if (btnHtml !== "") {
              section.querySelector(`#btn-show-rep-${cons.id}`).addEventListener("click", (e) => { e.target.style.display = "none"; section.querySelector(`#wrap-rep-${cons.id}`).style.display = "flex"; });
              section.querySelector(`#btn-cfm-${cons.id}`).addEventListener("click", () => { this._callAction("replace_consumable", { cost: parseFloat(section.querySelector(`#inp-rep-${cons.id}`).value) || 0, cons_id: cons.id }); });
          }
      });
    }

    const accContainer = shadow.getElementById("accessories-container");
    const accessories = attrs.accessories_list || [];
    if (this._lastAccFingerprint !== JSON.stringify(accessories)) {
        this._lastAccFingerprint = JSON.stringify(accessories);
        
        accContainer.className = `accessories-grid ${((isMemorial || isService) && accessories.length > 1) ? 'grid-2' : 'grid-1'}`;
        
        accContainer.innerHTML = "";
        accessories.forEach(acc => {
            const div = document.createElement("div"); 
            
            // 🔥 V153 附件智能状态引擎：只要勾选了，绝对服从退役/变灰指令
            let accIsActuallyRetired = acc.is_retired === true;
            let rawReason = acc.reason || "";
            let displayReason = rawReason;
            
            // 智能纠错：如果退役了但没选理由，强制纠正
            if (accIsActuallyRetired && rawReason.includes("正常")) {
                displayReason = isService ? "已失效" : "已封存";
            }
            
            div.className = `accessory-item ${accIsActuallyRetired ? 'acc-lost' : ''}`;
            
            let extraHtml = "";
            // 多维印章匹配，不再局限于“遗失”
            if (accIsActuallyRetired) {
                let stampText = "封存";
                if (displayReason.includes("遗失")) stampText = "遗失";
                else if (displayReason.includes("回血") || displayReason.includes("二手")) stampText = "售出";
                else if (displayReason.includes("报废")) stampText = "报废";
                else if (displayReason.includes("失效")) stampText = "失效";
                else if (displayReason.includes("馈赠")) stampText = "赠出";
                
                extraHtml = `<div class="lost-overlay"></div><div class="lost-stamp-mini">${stampText}</div>`;
            }

            let defaultIcon = isService ? "mdi:gift" : (isMemorial ? "mdi:ring" : "mdi:puzzle-outline");
            
            let rawAccImg = acc.image || "";
            if(rawAccImg.startsWith("/local/")) { rawAccImg += (rawAccImg.includes("?") ? "&" : "?") + "t=" + Date.now(); }
            let safeAccImg = encodeURI(rawAccImg);

            let iconHtml = safeAccImg 
                ? `<img class="acc-actual-img" src="${safeAccImg}" onerror="this.style.display='none'; this.nextElementSibling.style.display='block';" /><ha-icon class="acc-fallback-icon" icon="${defaultIcon}" style="display:none;"></ha-icon>` 
                : `<ha-icon class="acc-fallback-icon" icon="${defaultIcon}"></ha-icon>`;
            
            let metaHtml = "";
            let priceHtml = "";
            let instHtml = "";

            if (isService) {
                let expTxt = acc.expiration_date ? `至 ${acc.expiration_date}` : '至 主服到期';
                metaHtml = `<span>${acc.purchase_date} ${expTxt}</span>`;
                priceHtml = `<div class="acc-value">价值 ￥${(parseFloat(acc.price) || 0).toFixed(2)}</div>`;
                if (accIsActuallyRetired) metaHtml += `<span style="background:rgba(229,57,53,0.1); color:#E53935; border:none;">${displayReason}</span>`;
            } else {
                let accDaysText = isMemorial ? `相伴 ${acc.days} 天` : `服役 ${acc.days} 天`;
                metaHtml = `<span>${acc.purchase_date}</span><span>${accDaysText}</span>`;
                priceHtml = `<div class="acc-price">￥${(parseFloat(acc.price) || 0).toFixed(2)}</div>`;
                if (accIsActuallyRetired) metaHtml += `<span style="background:rgba(229,57,53,0.1); color:#E53935; border:none;">${displayReason}</span>`;
                
                if (!isMemorial && acc.is_installment && acc.installment_months > 0 && !acc.is_paid_off && !acc.early_payoff) {
                    let instColor = (acc.months_paid / acc.installment_months) >= 0.33 ? "#2196F3" : "#FFC107";
                    let width = (acc.months_paid / acc.installment_months) * 100;
                    let statusText = `待还￥${(parseFloat(acc.outstanding_balance) || 0).toFixed(2)}`;
                    let instLabel = acc.installment_interest <= 0 ? "免息" : "分期";
                    instHtml = `
                        <div style="display:flex; justify-content:space-between; font-size:0.7rem; margin-top:8px; color:var(--dc-text-sub); width:100%;">
                            <span>${instLabel} (${acc.months_paid}/${acc.installment_months})</span><span>${statusText}</span>
                        </div>
                        <div class="acc-inst-bar" style="width:100%;"><div class="acc-inst-fill" style="width:${width}%; background-color:${instColor} !important;"></div></div>
                    `;
                }
            }

            let mainContent = `
                <div class="acc-top">
                    <div class="acc-img-box">${iconHtml}</div>
                    <div class="acc-info">
                        <div class="acc-name">${acc.is_wearing ? '✨ ' : ''}${acc.name}</div>
                        ${priceHtml}
                    </div>
                </div>
                <div class="acc-meta">${metaHtml}</div>
                ${instHtml}
            `;
            div.innerHTML = extraHtml + mainContent;
            accContainer.appendChild(div);
        });
    }

    const badgeDiv = shadow.getElementById("badges-container");
    const badges = attrs.badges || [];
    if (this._lastBadgeFP !== JSON.stringify(badges)) {
        this._lastBadgeFP = JSON.stringify(badges);
        badgeDiv.innerHTML = "";
        if (badges.length > 0) {
            badgeDiv.style.display = "flex";
            badges.forEach(b => {
                const s = document.createElement("div"); s.className = "badge-item"; s.style.color = b.color;
                s.innerHTML = `<ha-icon icon="${b.icon}" style="--mdc-icon-size:14px"></ha-icon><span>${b.label}</span>`;
                badgeDiv.appendChild(s);
            });
        } else { badgeDiv.style.display = "none"; }
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
      let html = `<option value="main">主物件/设备 (卡片左侧大图)</option>`;
      consumables.forEach(c => { html += `<option value="${c.id}">附属耗材：${c.name}</option>`; });
      accessories.forEach(a => { html += `<option value="${a.id}">专属单品/权益：${a.name}</option>`; });
      
      sel.innerHTML = html;
      if (Array.from(sel.options).some(opt => opt.value === currentVal)) { sel.value = currentVal; }
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
            <div style="font-weight:bold; font-size:0.9rem; color:var(--primary-text-color);">📷 极速图片绑定</div>
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
        uploadBtn.disabled = true; statusText.textContent = `上传中...`; 
        const formData = new FormData(); formData.append("file", file); formData.append("device_name", this._config.name || this._config.entity || "device");
        try {
          let token = ''; if (this._hass && this._hass.auth) token = this._hass.auth.accessToken || (this._hass.auth.data && this._hass.auth.data.access_token) || '';
          const response = await fetch('/api/device_companion/upload', { method: 'POST', body: formData, headers: token ? { 'Authorization': `Bearer ${token}` } : {} });
          const result = await response.json();
          if (result.success) { 
              statusText.textContent = "绑定成功 ✓"; statusText.style.color = "green"; 
              const target = targetSelector.value;
              if (target === "main") {
                  this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: { ...this._config, image: result.url } }, bubbles: true, composed: true })); 
              } else {
                  this._hass.callService("device_companion", "quick_action", { entity_id: this._config.entity, action: "update_image", cons_id: target, image_url: result.url });
              }
          }
        } catch (err) { statusText.textContent = `失败`; statusText.style.color = "red"; } finally { uploadBtn.disabled = false; fileInput.value = ''; setTimeout(() => { statusText.textContent = ""; }, 3000); }
      });
    }
    form.hass = this._hass; form.data = this._config;
  }
}

customElements.define("device-companion-editor-v2", DeviceCompanionCardEditor);
customElements.define("device-companion-card", DeviceCompanionCard);

// 彻底闭环注册器
window.customCards = window.customCards || [];
window.customCards.push({
  type: "device-companion-card",
  name: "设备陪伴管家 (Device Companion)",
  preview: true,
  description: "V153: 状态引擎重构，无论任何选项只要勾选立即退役/封存并智能纠错印章。"
});