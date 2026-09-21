// 用 Node + 极简 DOM 桩执行 frontend/index.html 里的内联脚本。
//
// 用法: node scripts/check_frontend.js   （从哪个目录跑都可以）
//
// 四层检查，从弱到强：
//   1) 顶层执行不抛异常 —— 顶层抛异常会打断整个脚本，后面的 addEventListener
//      全都绑不上。这个 bug 真实发生过：mcpFooter 的 TDZ 崩溃让发送按钮完全没反应。
//   2) getElementById 引用的 id 在 HTML 里都存在 —— 桩是「什么都能设」的假元素，
//      所以 id 打错时这层照样通过，浏览器里却会崩。
//   3) 交互路径真跑一遍（绑定 / 登录 / 退出 / 技能增删）—— 只看顶层不抛，
//      说明不了这些分支是对的。
//   4) 事件真的能触发 —— 桩会记录 addEventListener 的回调，于是「点按钮」
//      这件事可以被驱动，异步结果也能等。Escape 键这类路径就是这么测的。
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

// 一个「什么都能点、什么都能设」的假元素，避免 DOM 缺失造成的误报。
// 记录事件回调，并让 querySelector 对同一个父元素返回同一个孩子 ——
// 只有这样才能驱动「点按钮 → 跑异步 → 看结果」这条链。
function fakeEl() {
  const t = {
    style: {},
    classList: { add() {}, remove() {}, contains: () => false, toggle() {} },
    dataset: {}, children: [], parentNode: null,
    scrollTop: 0, scrollHeight: 0, value: '',
    textContent: '', innerHTML: '', disabled: false, hidden: false,
    firstChild: null,
    __handlers: {},
    __attrs: {},
    append(...kids) { for (const k of kids) t.children.push(k); },
    appendChild(k) { t.children.push(k); return k; },
    prepend(...kids) { t.children.unshift(...kids); },
    insertBefore(node, ref) {
      const i = ref ? t.children.indexOf(ref) : -1;
      if (i >= 0) t.children.splice(i, 0, node);
      else t.children.unshift(node);
      return node;
    },
    remove() {
      const p = t.parentNode;
      if (p && Array.isArray(p.children)) {
        const i = p.children.indexOf(t);
        if (i >= 0) p.children.splice(i, 1);
      }
    },
    addEventListener(type, fn) {
      (t.__handlers[type] = t.__handlers[type] || []).push(fn);
    },
    removeEventListener() {},
    setAttribute(k, v) { t.__attrs[k] = String(v); },
    getAttribute(k) { return k in t.__attrs ? t.__attrs[k] : null; },
    removeAttribute(k) { delete t.__attrs[k]; },
    querySelector(sel) {
      t.__q = t.__q || {};
      return (t.__q[sel] = t.__q[sel] || fakeEl());
    },
    querySelectorAll: () => [],
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

// 触发元素上的某个事件，并等回调里的异步全部结束。
// 返回快照，方便断言「触发了几个回调」。
async function fire(el, type, event) {
  const fns = (el.__handlers && el.__handlers[type]) || [];
  const results = fns.map(fn => fn(Object.assign({ preventDefault() {} }, event)));
  await Promise.all(results.map(r => Promise.resolve(r)));
  await new Promise(r => setTimeout(r, 0));
  return results.length;
}

// 按 id 记住同一个元素 —— 真实 DOM 就是这样，也只有这样才验证得了
// 「面板里到底有没有渲染出东西」
const els = {};
const el = (id) => (els[id] = els[id] || fakeEl());

// fetch 桩：按 URL 返回不同响应，好把各条路都走完
const fetchCalls = [];
const NAMED = () => ({
  user_id: 'u-named', name: 'bob', created_at: 't',
  username: 'bob', is_anonymous: false, token: 'tok-named',
});
const ANON = () => ({
  user_id: 'u-anon', name: '', created_at: 't',
  username: null, is_anonymous: true, token: 'tok-anon',
});
const BUILTIN_SKILLS = () => ([
  { skill_id: '', slug: 'frontend-design', name: '前端设计',
    description: '给界面定方向', body: '', builtin: true },
]);
const MY_SKILLS = () => ([
  { skill_id: 'sk-1', slug: 'team-review', name: '团队评审标准',
    description: '写方案时对照的清单', body: '## 什么时候用\n评审时。', builtin: false },
]);

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
  else if (u.includes('/api/mcp')) payload = {
    status: 'connected', name: 'web_search_service', transport: 'streamable_http',
    host: 'dashscope.aliyuncs.com', tools: ['web_search', 'bailian_web_search'], detail: '',
  };
  else if (u.includes('/api/skills')) {
    if (method === 'POST') payload = MY_SKILLS()[0];
    else if (method === 'DELETE') payload = { ok: true };
    else payload = [...BUILTIN_SKILLS(), ...MY_SKILLS()];   // GET 列表（含内置）
  }
  else if (u.includes('/api/sessions/')) payload = { messages: [], next_cursor: null, total: 0 };
  else if (u.includes('/api/sessions')) payload = [];
  return { ok: true, status: 200, json: async () => payload };
}

// document 也要能记录事件（Escape 键挂在 document 上）
const doc = {
  __handlers: {},
  getElementById: el,
  createElement: () => fakeEl(),
  createTextNode: () => fakeEl(),
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener(type, fn) { (doc.__handlers[type] = doc.__handlers[type] || []).push(fn); },
  body: fakeEl(),
};

const sandbox = {
  console, setTimeout, clearTimeout, setInterval, clearInterval,
  Math, JSON, Object, Array, String, Number, Boolean, Date, Promise,
  Error, TypeError, ReferenceError, Map, Set, RegExp, Symbol, parseInt, parseFloat, isNaN,
  encodeURIComponent, decodeURIComponent, TextDecoder: globalThis.TextDecoder,
  document: doc,
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
  // 递归取文本：表单字段的文字嵌在 label > span 里，浅层 textContent 取不到
  const deepText = (node) => {
    if (!node) return '';
    if (typeof node.textContent === 'string' && node.textContent) return node.textContent;
    return (node.children || []).map(deepText).join(' ');
  };
  const texts = id => deepText(el(id));

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

  console.log('\n侧栏导航 + 技能抽屉:');

  await step('点「技能」→ 打开抽屉、列出内置与我建的技能', async () => {
    await fire(el('navSkills'), 'click');
    if (el('drawer').hidden !== false) throw new Error('抽屉没打开');
    if (el('drawerTitle').textContent !== '技能') throw new Error('标题不对');
    const body = texts('drawerBody');
    if (!body.includes('frontend-design')) throw new Error('没列出内置技能');
    if (!body.includes('team-review')) throw new Error('没列出我的技能');
  });
  await step('侧栏显示我的技能数量', () => {
    if (el('navSkillsCount').textContent !== '1') {
      throw new Error('数量应为 1，实际 ' + JSON.stringify(el('navSkillsCount').textContent));
    }
  });
  await step('点「新建技能」→ 渲染出四个表单字段', async () => {
    // 列表底部那个「新建技能」按钮就是走 renderSkillForm(null)
    g.renderSkillForm(null);
    const body = texts('drawerBody');
    for (const label of ['目录名', '名称', '描述', '正文']) {
      if (!body.includes(label)) throw new Error('表单缺少字段: ' + label);
    }
  });
  await step('提交新技能 → 发出 POST 并提示「下一次提问就会用上」', async () => {
    const before = fetchCalls.filter(c => c.startsWith('POST /api/skills')).length;
    const fields = {
      slug: { input: { value: 'weekly-report' } },
      name: { input: { value: '周报' } },
      desc: { input: { value: '写周报时对照' } },
      body: { input: { value: '## 结构\n1. 结论' } },
    };
    await g.submitSkillForm(null, fakeEl(), fakeEl(), fields);
    const after = fetchCalls.filter(c => c.startsWith('POST /api/skills')).length;
    if (after !== before + 1) throw new Error('没有发出 POST /api/skills');
    if (!texts('drawerBody').includes('下一次提问')) throw new Error('没有成功提示');
  });
  await step('删除要先确认 → 点「确认删除」才发出 DELETE', async () => {
    const card = fakeEl();
    g.confirmDelete(MY_SKILLS()[0], card);
    const acts = card.querySelector('.acts');
    if (!acts.children.some(c => String(c.textContent).includes('确认删除'))) {
      throw new Error('没有渲染出确认按钮');
    }
    const yes = acts.children.find(c => String(c.textContent).includes('确认删除'));
    await fire(yes, 'click');
    if (!fetchCalls.some(c => c.startsWith('DELETE /api/skills/sk-1'))) {
      throw new Error('没有发出 DELETE');
    }
    if (!texts('drawerBody').includes('已删除')) throw new Error('没有删除提示');
  });
  await step('点「MCP 服务」→ 抽屉切到 MCP 视图，并列出实测到的工具', async () => {
    await fire(el('navMcp'), 'click');
    if (el('drawerTitle').textContent !== 'MCP 服务') throw new Error('标题没切过去');
    const body = texts('drawerBody');
    if (!body.includes('web_search_service')) throw new Error('没显示服务名');
    if (!body.includes('bailian_web_search')) throw new Error('没列出工具');
    if (!body.includes('这里是只读的')) throw new Error('没说明这一页是只读的');
  });
  await step('按 Escape → 抽屉关上，且不影响账号面板', async () => {
    await fire(doc, 'keydown', { key: 'Escape' });
    if (el('drawer').hidden !== true) throw new Error('抽屉没关上');
    // 账号面板此时本来就是关的，这里确认 Escape 没把它打开
    if (el('acctPanel').hidden !== true) throw new Error('账号面板被误开');
  });
  await step('关掉抽屉后侧栏回到「对话」高亮', () => {
    if (el('navChat').getAttribute('aria-current') !== 'true') {
      throw new Error('对话项没有高亮');
    }
  });

  console.log('\n  期间调用的接口:');
  [...new Set(fetchCalls)].forEach(c => console.log(`    ${c}`));

  if (stepFailed) failed = true;
  console.log(`\n结果: ${failed ? '有失败项 —— 见上面的 ✗ / [FAIL]' : '全部通过'}`);
  process.exit(failed ? 1 : 0);
})();
