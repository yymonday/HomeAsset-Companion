const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../custom_components/device_companion/frontend/device-companion-card.js'), 'utf8');
function runtime(extra = {}) {
  const context = vm.createContext({ HTMLElement: class {}, customElements: { get: () => true }, window: {}, ...extra });
  vm.runInContext(source + '\nthis.api = { dcBills, dcCsvCell, dcBillCsv, DeviceCompanionCard };', context);
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
  const fields = Object.fromEntries(['charge_type', 'bill_id', 'description', 'cost', 'months', 'new_monthly_price'].map(name => [name, {}]));
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
  fields.charge_type.value = 'extra_quota';
  card._paymentTypeChanged();
  assert.equal(fields.bill_id.required, false);
  assert.equal(fields.bill_id.disabled, true);
  assert.equal(fields.description.required, false);
});
