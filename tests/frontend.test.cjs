const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../custom_components/device_companion/frontend/device-companion-card.js'), 'utf8');
function runtime(extra = {}) {
  const context = vm.createContext({ HTMLElement: class {}, customElements: { get: () => true }, window: {}, ...extra });
  vm.runInContext(source + '\nthis.api = { dcBills, dcCsvCell, dcBillCsv, dcPaymentDate, dcBillNote, dcPerkCanRenew, dcPerkPayload, DeviceCompanionCard };', context);
  return context.api;
}
const api = runtime();
test('new billing surfaces inherit existing card palette instead of new accents', () => {
  const css = source.split('<style>')[1].split('</style>')[0];
  const panel = css.match(/\.payment-panel \{([^}]+)\}/)[1];
  const bills = css.match(/#bill-history \{([^}]+)\}/)[1];
  for (const rule of [panel, bills]) {
    assert.ok(rule.includes('background:var(--card-background-color,#ffffff)'));
    assert.ok(rule.includes('color:var(--dc-text-main)'));
    assert.ok(rule.includes('border-radius:14px'));
  }
  assert.ok(css.includes('.payment-panel button[type=submit] { background:var(--dc-theme)'));
  assert.ok(css.includes('#bill-history summary:focus-visible'));
  assert.ok(css.includes('color:var(--dc-text-sub); line-height:1.65'));
});
test('CSV uses recorded payments only and never invents legacy history', () => {
  const csv = api.dcBillCsv({ total_price: 800, service_payments: null, service_charges: [null, [], 'bad'] }, 'sensor.legacy');
  assert.ok(csv.startsWith('\ufeff'));
  assert.equal(csv.split('\r\n').length, 2);
  assert.ok(!csv.includes('800'));
});
test('CSV merges bills in descending date order without changing records', () => {
  const attrs = { friendly_name: '中文订阅', service_payments: [{id:'a', payment_type:'initial', amount:280, paid_at:'2026-09-12', period_start:'2026-09-12', period_end:'2026-11-12', months_covered:2}], service_charges: [{id:'b', charge_type:'upgrade', cost:25.5, paid_at:'2026-09-30', description:'套餐, "升级"\n备注'}] };
  const before = JSON.stringify(attrs);
  const csv = api.dcBillCsv(attrs, 'sensor.test');
  assert.ok(csv.indexOf('"b"') < csv.indexOf('"a"'));
  assert.ok(csv.includes('"280.00","2026-09-12","2026-11-12","2"'));
  assert.ok(csv.includes('"25.50","","","","套餐, ""升级""\n备注"'));
  assert.equal(JSON.stringify(attrs), before);
});
test('CSV neutralizes formula injection including leading whitespace', () => {
  for (const value of ['=1+1', '+SUM(A1)', '-cmd', '@SUM(A1)', '\t=1', '\r\n@x', '   =2']) assert.ok(api.dcCsvCell(value).startsWith('"\''));
  assert.equal(api.dcCsvCell(-2), '"-2"');
  assert.equal(api.dcCsvCell('正常中文'), '"正常中文"');
});
test('CSV leaves missing and corrupt amounts blank, preserves explicit zero', () => {
  const amounts = [null, '', undefined, 'NaN', Infinity, false, [], {}, 0];
  const attrs = {service_charges: amounts.map((cost, i) => ({id: String(i), cost}))};
  const csv = api.dcBillCsv(attrs, 'sensor.test');
  assert.equal((csv.match(/"0\.00"/g) || []).length, 1);
  assert.ok(!csv.includes('NaN') && !csv.includes('Infinity'));
});
test('active missing/permanent expiry retains charge entry; stopped services hide it', () => {
  const nodes = new Map();
  const content = {getElementById: id => {
    if (!nodes.has(id)) nodes.set(id, {style: {setProperty() {}}, classList: {add() {}, remove() {}}, setAttribute() {}, querySelector: () => null, querySelectorAll: () => [], appendChild() {}});
    return nodes.get(id);
  }};
  const card = new api.DeviceCompanionCard();
  card.content = content;
  card.config = {entity: 'sensor.test'};
  for (const expiration of ['', '永久', '2026-12-01']) {
    for (const status of ['active', 'canceled', 'expired']) {
      card._hass = {states: {'sensor.test': {state: '10', attributes: {kind: 'service', expiration_date: expiration, status, stored_status: status}}}};
      card.updateData();
      assert.equal(nodes.get('btn-record-service-charge').style.display, status === 'active' ? 'inline-flex' : 'none');
      assert.equal(nodes.get('bill-export').disabled, true);
    }
  }
});
test('legacy prepaid subscriptions do not show missing-history warning or invent bills', () => {
  const nodes = new Map();
  const card = new api.DeviceCompanionCard();
  card.content = {getElementById: id => {
    if (!nodes.has(id)) nodes.set(id, {style: {setProperty() {}}, classList: {add() {}, remove() {}}, setAttribute() {}, querySelector: () => null, querySelectorAll: () => [], appendChild() {}});
    return nodes.get(id);
  }};
  card.config = {entity: 'sensor.legacy'};
  const attrs = {kind:'service', status:'active', stored_status:'active', purchase_date:'2026-02-20', expiration_date:'2034-02-20', total_price:800, payment_coverage_status:'untracked'};
  const before = JSON.stringify(attrs);
  card._hass = {states: {'sensor.legacy': {state:'222', attributes:attrs}}};
  card.updateData();
  assert.ok(!nodes.get('cost-breakdown').innerHTML.includes('付款覆盖未追踪'));
  assert.equal(JSON.stringify(attrs), before);
  attrs.payment_coverage_status = 'mismatch';
  attrs.payment_coverage_end = '2033-02-20';
  card.updateData();
  assert.ok(nodes.get('cost-breakdown').innerHTML.includes('付款覆盖需核对'));
});
test('subscription actions center content and wrap apart from expiry information', () => {
  assert.ok(source.includes('class="progress-header service-progress-header"'));
  assert.ok(source.includes('class="service-progress-info"'));
  assert.ok(source.includes('class="service-progress-actions"'));
  assert.match(source, /\.service-progress-header \{[^}]*align-items:center;[^}]*flex-wrap:wrap/);
  assert.match(source, /#service-progress-container \.action-btn-outline \{[^}]*height:32px;[^}]*align-items:center;[^}]*line-height:1/);
  assert.match(source, /@media \(pointer:coarse\)[^\n]*height:44px/);
});
test('export downloads locally, releases URL, and never calls HA', () => {
  const events = [];
  const link = {click: () => events.push('click'), remove: () => events.push('remove')};
  const local = runtime({Blob, URL: {createObjectURL: blob => {assert.ok(blob.size > 0); return 'blob:test';}, revokeObjectURL: url => events.push(url)}, document: {createElement: () => link, body: {append: () => events.push('append')}}, setTimeout: callback => callback()});
  const card = new local.DeviceCompanionCard();
  card.config = {entity:'sensor.test'};
  card._lastAttrs = {service_charges:[{cost:5}]};
  card._hass = {callService: () => assert.fail('export must not mutate HA')};
  card._exportBills();
  assert.equal(link.download, 'HomeAsset-sensor.test-bills.csv');
  assert.deepEqual(events, ['append','click','remove','blob:test']);
  events.length = 0;
  card._busy = true;
  card._exportBills();
  card._busy = false;
  card._lastAttrs = {};
  card._exportBills();
  assert.equal(events.length, 0);
});
test('CSV includes linked signed adjustments as numbers, not formula text', () => {
  const csv = api.dcBillCsv({service_adjustments: [{id: 'refund-1', bill_id: 'bill-1', operation: 'refund', amount: -20, description: '=1+1', paid_at: '2026-09-30'}]}, 'sensor.test');
  assert.ok(csv.includes('"退款","-20.00"'));
  assert.ok(csv.includes('"\'=1+1","bill-1"'));
  assert.ok(csv.includes('"关联原账单ID"'));
});
test('refund/correction form requires bill and reason with distinct amount semantics', () => {
  const nodes = new Map();
  const fields = Object.fromEntries(['charge_type', 'bill_id', 'description', 'cost', 'months', 'new_monthly_price', 'paid_at'].map(name => [name, {}]));
  const card = new api.DeviceCompanionCard();
  card.content = {getElementById: id => {
    if (id === 'payment-form') return {elements: fields};
    if (!nodes.has(id)) nodes.set(id, {});
    return nodes.get(id);
  }};
  fields.charge_type.value = 'refund';
  card._paymentTypeChanged();
  assert.equal(fields.bill_id.required, true);
  assert.equal(fields.description.required, true);
  assert.equal(fields.cost.min, '0.01');
  assert.ok(nodes.get('payment-amount-label').textContent.includes('已收到退款'));
  fields.charge_type.value = 'correction';
  card._paymentTypeChanged();
  assert.ok(nodes.get('payment-amount-label').textContent.includes('原付款总金额'));
  assert.equal(nodes.get('payment-date-label').textContent, '更正后的实际付款日期');
  assert.ok(nodes.get('payment-help').textContent.includes('原错误账期将被替换'));
  fields.charge_type.value = 'extra_quota';
  card._paymentTypeChanged();
  assert.equal(fields.bill_id.required, false);
  assert.equal(fields.bill_id.disabled, true);
  assert.equal(fields.description.required, false);
});
test('date correction uses actual-payment revision, never adjustment timestamp', () => {
  assert.deepEqual({...api.dcPaymentDate('correction', '2026-10-09')}, {corrected_paid_at: '2026-10-09'});
  for (const type of ['refund', 'renewal', 'extra_quota']) {
    assert.deepEqual({...api.dcPaymentDate(type, '2026-10-09')}, {paid_at: '2026-10-09'});
  }
});
test('correction prefills effective date and corrected total, not original wrong fields', () => {
  const fields = {charge_type: {value:'correction'}, bill_id: {value:'current'}, cost: {}, paid_at: {}};
  const card = new api.DeviceCompanionCard();
  card.content = {getElementById: () => ({elements:fields})};
  card._lastAttrs = {
    service_payments:[{id:'current', amount:280, paid_at:'2026-10-09'}],
    service_adjustments:[{bill_id:'current', amount:-30}, {bill_id:'other', amount:100}]
  };
  card._prefillBillCorrection();
  assert.equal(fields.cost.value, '250.00');
  assert.equal(fields.paid_at.value, '2026-10-09');
  fields.charge_type.value = 'refund';
  fields.cost.value = '10';
  card._prefillBillCorrection();
  assert.equal(fields.cost.value, '10');
});
test('CSV keeps date revision audit while exporting only effective paid coverage', () => {
  const revision = {id:'fix', bill_id:'current', operation:'correction', amount:0, paid_at:'2026-10-11', description:'纠正付款日期', date_correction:{before:{paid_at:'2026-09-30', period_start:'2026-09-30', period_end:'2026-10-30'}, after:{paid_at:'2026-10-09', period_start:'2026-10-09', period_end:'2026-11-09'}}};
  const csv = api.dcBillCsv({service_payments:[{id:'current', payment_type:'renewal', amount:670, paid_at:'2026-10-09', period_start:'2026-10-09', period_end:'2026-11-09', months_covered:1}], service_adjustments:[revision]}, 'sensor.test');
  assert.ok(csv.includes('"670.00","2026-10-09","2026-11-09","1"'));
  assert.ok(csv.includes('原错误账期已替换'));
  assert.ok(csv.includes('2026-09-30 更正为 2026-10-09'));
  assert.ok(!csv.includes('"670.00","2026-09-30","2026-10-30"'));
});

test('expired gifts retain a renewal entry, canceled gifts and parents do not', () => {
  for (const status of ['active', 'expired']) {
    assert.equal(api.dcPerkCanRenew({id:'music', status, is_retired:status === 'expired'}, {stored_status:'active'}), true);
  }
  for (const status of ['canceled', 'archived', 'lost', 'gifted', 'sold', 'scrapped']) {
    assert.equal(api.dcPerkCanRenew({id:'music', status}, {stored_status:'active'}), false);
    assert.equal(api.dcPerkCanRenew({id:'music', status:'expired'}, {stored_status:status}), false);
  }
  assert.equal(api.dcPerkCanRenew({id:'music', is_retired:true}, {stored_status:'active'}), false);
  assert.equal(api.dcPerkCanRenew({status:'active'}, {stored_status:'active'}), false);
});

test('gift synchronization excludes independent dates and cash amounts', () => {
  const sync = {...api.dcPerkPayload('music', true, 'old', 'old')};
  assert.deepEqual(sync, {perk_id:'music', follow_main_renewal:true});
  const manual = {...api.dcPerkPayload('music', false, '2026-10-10', '2027-10-10')};
  assert.deepEqual(manual, {perk_id:'music', follow_main_renewal:false, start_date:'2026-10-10', expiration_date:'2027-10-10'});
  assert.ok(!('cost' in sync) && !('cost' in manual));
});

function perkFormCard() {
  const nodes = new Map();
  const fields = {follow_main:{value:'true', focus() {}}, start_date:{value:'2026-10-10'}, expiration_date:{value:'2027-10-10'}};
  const form = {elements:fields, hidden:false, reset() {}, reportValidity:() => true};
  const card = new api.DeviceCompanionCard();
  card.content = {getElementById: id => {
    if (id === 'perk-form') return form;
    if (!nodes.has(id)) nodes.set(id, {});
    return nodes.get(id);
  }};
  card._lastAttrs = {stored_status:'active', purchase_date:'2025-10-08', today:'2026-10-11', renewal_period_start:'2026-10-10', current_period_start:'2025-10-08', expiration_date:'2027-10-10', accessories_list:[{id:'music', name:'音乐VIP', status:'expired', is_retired:true, purchase_date:'2025-10-08'}]};
  card._perkId = 'music';
  return {card, fields, form, nodes};
}

test('gift form opens without writes and uses the registered renewal rather than old active period', () => {
  const {card, fields, form, nodes} = perkFormCard();
  card._callAction = () => assert.fail('opening must not save');
  card._openPerk('music');
  assert.equal(form.hidden, false);
  assert.equal(nodes.get('payment-form').hidden, true);
  assert.equal(nodes.get('perk-title').textContent, '续订权益 · 音乐VIP');
  assert.equal(nodes.get('perk-period').textContent, '同步为 2026-10-10 至 2027-10-10');
  assert.equal(fields.start_date.disabled, true);
  assert.equal(fields.expiration_date.required, false);
  fields.follow_main.value = 'false';
  card._perkModeChanged();
  assert.equal(fields.start_date.disabled, false);
  assert.equal(fields.expiration_date.required, true);
  assert.equal(nodes.get('perk-dates').hidden, false);
  assert.equal(nodes.get('perk-submit').textContent, '确认登记');
});

test('gift retry preserves inputs and request ID, success closes form, busy blocks submit', async () => {
  const {card, fields, form} = perkFormCard();
  const calls = [];
  card._callAction = async (action, payload) => {calls.push({action, payload}); return calls.length > 1;};
  await card._submitPerk({preventDefault() {}});
  assert.equal(form.hidden, false);
  await card._submitPerk({preventDefault() {}});
  assert.equal(calls.length, 2);
  assert.equal(calls[0].action, 'renew_service_perk');
  assert.equal(calls[0].payload.request_id, calls[1].payload.request_id);
  assert.ok(!('start_date' in calls[0].payload));
  assert.ok(!('cost' in calls[0].payload));
  assert.equal(form.hidden, true);
  fields.follow_main.value = 'false';
  await card._submitPerk({preventDefault() {}});
  assert.ok(calls[2].payload.request_id !== calls[1].payload.request_id);
  assert.equal(calls[2].payload.expiration_date, '2027-10-10');
  card._busy = true;
  await card._submitPerk({preventDefault() {}});
  assert.equal(calls.length, 3);
});

test('gift entry preserves incumbent neutral buttons, responsive height and focus', () => {
  assert.match(source, /\.perk-actions \.action-btn-outline \{[^}]*background:rgba\(128,128,128,\.05\)[^}]*min-height:32px/);
  assert.match(source, /@media \(pointer:coarse\)[^\n]*\.perk-actions[^\n]*min-height:44px/);
  assert.ok(source.includes('#accessories-container button:focus-visible'));
  assert.ok(source.includes('isService && dcPerkCanRenew(acc, attrs)'));
});
