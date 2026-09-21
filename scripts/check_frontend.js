// 用 Node + 极简 DOM 桩执行 frontend/index.html 里的内联脚本。
//
// 用法: node scripts/check_frontend.js   （从哪个目录跑都可以）
//
// 三层检查，从弱到强：
//   1) 顶层执行不抛异常 —— 顶层抛异常会打断整个脚本，后面的 addEventListener
//      全都绑不上。这个 bug 真实发生过：mcpFooter 的 TDZ 崩溃让发送按钮完全没反应。
//   2) getElementById 引用的 id 在 HTML 里都存在 —— 桩是「什么都能设」的假元素，
//      所以 id 打错时这层照样通过，浏览器里却会崩。
//   3) 交互路径真跑一遍（绑定 / 登录 / 退出）—— 只看顶层不抛，
//      说明不了这些分支是对的。
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const HTML_PATH = path.join(__dirname, '..', 'frontend', 'index.html');
const html = fs.readFileSync(HTML_PATH, 'utf8');

// 取出所有「不带 src」的内联 <script> 块
const blocks = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi)]
  .map(m => m[1])
  .filter(s => s.trim());

console.log(`内联 <script> 块数量: ${blocks.length}`);
if (blocks.length === 0) { console.error('找不到内联脚本'); process.exit(2); }

// 一个「什么都能点、什么都能设」的假元素，避免 DOM 缺失造成的误报
function fakeEl() {
  const t = {
    style: {},
    classList: { add() {}, remove() {}, contains: () => false, toggle() {} },
    dataset: {}, children: [], parentNode: null,
    scrollTop: 0, scrollHeight: 0, value: '',
    textContent: '', innerHTML: '', disabled: false, hidden: false,
    append(...kids) { for (const k of kids) t.children.push(k); },
    appendChild(k) { t.children.push(k); return k; },
    prepend(...kids) { t.children.unshift(...kids); },
    remove() {}, insertBefore() {},
    addEventListener() {}, removeEventListener() {},
    setAttribute() {}, getAttribute: () => null, removeAttribute() {},
    querySelector: () => null, querySelectorAll: () => [],
    focus() {}, blur() {}, click() {}, scrollIntoView() {},
  };
  return new Proxy(t, {
    get(o, p) {
      if (p in o) return o[p];
      if (typeof p === 'symbol') return undefined;
      return () => {};              // 未知成员当空方法，防止桩不完整造成误报
    },
    set(o, p, v) { o[p] = v; return true; },
  });
}

// 按 id 记住同一个元素 —— 真实 DOM 就是这样，也只有这样才验证得了
// 「面板里到底有没有渲染出东西」
const els = {};
const el = (id) => (els[id] = els[id] || fakeEl());

// fetch 桩：按 URL 返回不同响应，好把绑定 / 登录 / 退出三条路都走完
const fetchCalls = [];
const NAMED = () => ({
  user_id: 'u-named', name: 'bob', created_at: 't',
  username: 'bob', is_anonymous: false, token: 'tok-named',
});
const ANON = () => ({
  user_id: 'u-anon', name: '', created_at: 't',
  username: null, is_anonymous: true, token: 'tok-anon',
});

async function fakeFetch(url, opts) {
  const u = String(url);
  const method = ((opts && opts.method) || 'GET').toUpperCase();
  fetchCalls.push(`${method} ${u}`);
  let payload = { ok: true };
  if (u.includes('/api/auth/register')) payload = ANON();
  else if (u.includes('/api/auth/bind')) payload = NAMED();
  else if (u.includes('/api/auth/login')) payload = NAMED();
  else if (u.includes('/api/auth/logout')) payload = { ok: true };
  else if (u.includes('/api/auth/me')) payload = NAMED();
  else if (u.includes('/health')) payload = { mcp: 'connected' };
  else if (u.includes('/api/sessions/')) payload = { messages: [], next_cursor: null, total: 0 };
  else if (u.includes('/api/sessions')) payload = [];
  return { ok: true, status: 200, json: async () => payload };
}

const sandbox = {
  console, setTimeout, clearTimeout, setInterval, clearInterval,
  Math, JSON, Object, Array, String, Number, Boolean, Date, Promise,
  Error, TypeError, ReferenceError, Map, Set, RegExp, Symbol, parseInt, parseFloat, isNaN,
  encodeURIComponent, decodeURIComponent, TextDecoder: globalThis.TextDecoder,
  document: {
    getElementById: el,
    createElement: () => fakeEl(),
    createTextNode: () => fakeEl(),
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener() {},
    body: fakeEl(),
  },
  sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  localStorage: { getItem: () => '', setItem() {}, removeItem() {} },
  fetch: fakeFetch,
  location: { href: 'http://test/', origin: 'http://test' },
  navigator: { userAgent: 'node' },
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;

const ctx = vm.createContext(sandbox);
let failed = false;

// ── 第 1 层：顶层是否抛异常 ──
blocks.forEach((code, i) => {
  try {
    vm.runInContext(code, ctx, { filename: `inline-script-${i + 1}.js` });
    console.log(`\n内联块 #${i + 1}: 顶层执行完成，没有抛异常   ✓`);
  } catch (e) {
    failed = true;
    console.log(`\n内联块 #${i + 1}: 顶层抛出异常   ✗`);
    console.log(`    ${e.name}: ${e.message}`);
    const m = /inline-script-\d+\.js:(\d+)/.exec(e.stack || '');
    if (m) {
      const n = Number(m[1]);
      const line = code.split('\n')[n - 1];
      console.log(`    出错位置: 内联脚本第 ${n} 行`);
      if (line) console.log(`    该行内容: ${line.trim()}`);
    }
  }
});

// ── 第 2 层：id 引用 ──
const idsInHtml = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(m => m[1]));
const idsReferenced = new Set(
  [...blocks.join('\n').matchAll(/getElementById\(\s*'([^']+)'\s*\)/g)].map(m => m[1])
);
const missingIds = [...idsReferenced].filter(x => !idsInHtml.has(x));

console.log(`\nDOM id 引用检查: 脚本引用了 ${idsReferenced.size} 个 id`);
if (missingIds.length) {
  failed = true;
  console.log(`  HTML 里不存在的 id: ${missingIds.join(', ')}   ✗`);
} else {
  console.log(`  全部存在   ✓  (${[...idsReferenced].sort().join(', ')})`);
}

// ── 第 3 层：交互路径 ──
let stepFailed = 0;
async function step(name, fn) {
  try {
    await fn();
    console.log(`  [PASS] ${name}`);
  } catch (e) {
    stepFailed++;
    console.log(`  [FAIL] ${name} — ${e.name}: ${e.message}`);
  }
}

(async () => {
  const g = sandbox;
  const isEmpty = id => el(id).children.length === 0;

  console.log('\n账号面板交互模拟（绑定 / 登录 / 退出）:');

  await step('openAccount() 能打开面板，并渲染出匿名视图', () => {
    g.openAccount();
    if (el('acctPanel').hidden !== false) throw new Error('面板没有显示');
    if (isEmpty('acctBody')) throw new Error('面板里没渲染出任何内容');
  });
  await step('renderAccount("login") 渲染登录视图', () => {
    g.renderAccount('login');
    if (isEmpty('acctBody')) throw new Error('登录视图为空');
  });
  await step('renderAccount("named") 渲染已登录视图', () => {
    g.renderAccount('named');
    if (isEmpty('acctBody')) throw new Error('已登录视图为空');
  });
  await step('submitBind() 走完绑定流程', () => g.submitBind('bob', 'pw123456', fakeEl()));
  await step('submitLogin() 走完登录流程（含换账号、重载任务）',
    () => g.submitLogin('bob', 'pw123456', fakeEl()));
  await step('submitLogout() 走完退出流程', () => g.submitLogout(fakeEl()));
  await step('closeAccount() 能关上', () => {
    g.closeAccount();
    if (el('acctPanel').hidden !== true) throw new Error('面板没有 hidden');
  });

  console.log('\n  期间调用的接口:');
  [...new Set(fetchCalls)].forEach(c => console.log(`    ${c}`));

  if (stepFailed) failed = true;
  console.log(`\n结果: ${failed ? '有失败项 —— 见上面的 ✗ / [FAIL]' : '全部通过'}`);
  process.exit(failed ? 1 : 0);
})();
