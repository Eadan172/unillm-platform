#!/usr/bin/env node
/*
 * 前端「缺失值不落 0」逻辑检查（零依赖，纯 node）
 *
 * 说明：node 仅用于本检查脚本；**运行产品本身不需要 node**，本项目仍是零构建。
 *       之所以能用 node 直跑，是因为 app/web/assets/layout.js 会在末尾执行
 *       `window.Layout = Layout`，本脚本用最小 DOM shim 把它加载进 node 即可调用其纯函数。
 *
 * 用法：
 *   node scripts/frontend_logic_check.js
 *
 * 退出码 0 表示全部通过，非 0 表示存在失败项。
 */
'use strict';

var path = require('path');
var fs = require('fs');

// 同步写 stdout：避免 process.exit() 截断管道下的缓冲输出。
function say(line) {
  fs.writeSync(1, String(line) + '\n');
}

// ---------------------------------------------------------------------------
// 最小 DOM shim：仅满足 layout.js 在 node 下的加载需求。
// 绝不为了「让测试跑起来」去改 layout.js —— 它是浏览器产物。
// ---------------------------------------------------------------------------
function makeStub() {
  return {
    style: {},
    classList: { add: function () {}, remove: function () {} },
    setAttribute: function () {},
    getAttribute: function () { return null; },
    appendChild: function () {},
    removeChild: function () {},
    addEventListener: function () {},
    removeEventListener: function () {},
    querySelector: function () { return null; },
    innerHTML: '',
    textContent: ''
  };
}

global.window = global;
global.document = {
  createElement: function () { return makeStub(); },
  getElementById: function () { return null; },
  addEventListener: function () {},
  removeEventListener: function () {},
  body: makeStub()
};

var passed = 0;
var failed = 0;

function check(name, ok, detail) {
  if (ok) {
    passed += 1;
    say('  [PASS] ' + name + (detail ? ' -- ' + detail : ''));
  } else {
    failed += 1;
    say('  [FAIL] ' + name + (detail ? ' -- ' + detail : ''));
  }
}

// ---------------------------------------------------------------------------
// 加载 layout.js
// ---------------------------------------------------------------------------
var layoutPath = path.join(__dirname, '..', 'app', 'web', 'assets', 'layout.js');
try {
  require(layoutPath);
} catch (err) {
  say('  [FAIL] 加载 layout.js 失败 -- ' + err.message);
  say('');
  say('结果: 0/1 passed');
  process.exit(1);
}

var Layout = global.Layout;

// ---------------------------------------------------------------------------
// 断言表
// ---------------------------------------------------------------------------
check('Layout 已从 layout.js 导出', !!Layout && typeof Layout === 'object');
check('Layout.sumOrUnknown 是函数', typeof Layout.sumOrUnknown === 'function');

if (typeof Layout.sumOrUnknown === 'function') {
  // 正常求和
  check('sumOrUnknown([1,2,3]) === 6', Layout.sumOrUnknown([1, 2, 3]) === 6,
    'got=' + JSON.stringify(Layout.sumOrUnknown([1, 2, 3])));
  // 核心：任一缺失 -> 整体未知（不得落 0）
  check('sumOrUnknown([10, null]) === null（缺失不落 0）', Layout.sumOrUnknown([10, null]) === null,
    'got=' + JSON.stringify(Layout.sumOrUnknown([10, null])));
  // 顺序无关
  check('sumOrUnknown([null, 10]) === null（顺序无关）', Layout.sumOrUnknown([null, 10]) === null,
    'got=' + JSON.stringify(Layout.sumOrUnknown([null, 10])));
  check('sumOrUnknown([undefined]) === null', Layout.sumOrUnknown([undefined]) === null,
    'got=' + JSON.stringify(Layout.sumOrUnknown([undefined])));
  // asNumber 用 isFinite 拦掉 NaN
  check('sumOrUnknown([NaN]) === null', Layout.sumOrUnknown([NaN]) === null,
    'got=' + JSON.stringify(Layout.sumOrUnknown([NaN])));
  // 真实零必须保留为 0（与缺失的分界）
  check('sumOrUnknown([0, 0]) === 0（真实零保留）', Layout.sumOrUnknown([0, 0]) === 0,
    'got=' + JSON.stringify(Layout.sumOrUnknown([0, 0])));
  // 空数组不是 0
  check('sumOrUnknown([]) === null（无数据非 0）', Layout.sumOrUnknown([]) === null,
    'got=' + JSON.stringify(Layout.sumOrUnknown([])));
  // 字符串不是数字
  check("sumOrUnknown(['5']) === null（字符串不算数字）", Layout.sumOrUnknown(['5']) === null,
    'got=' + JSON.stringify(Layout.sumOrUnknown(['5'])));
}

// 0 与「未知」必须区分开
check("numOrUnknown(null) === '未知'", Layout.numOrUnknown(null) === '未知',
  'got=' + JSON.stringify(Layout.numOrUnknown(null)));
check("numOrUnknown(0) === '0'", Layout.numOrUnknown(0) === '0',
  'got=' + JSON.stringify(Layout.numOrUnknown(0)));

// ---------------------------------------------------------------------------
// 静态回归：datasets.html 不得再出现 `Layout.asNumber(...) || 0`
// ---------------------------------------------------------------------------
var datasetsPath = path.join(__dirname, '..', 'app', 'web', 'datasets.html');
try {
  var datasetsSource = fs.readFileSync(datasetsPath, 'utf8');
  var forbidden = /Layout\.asNumber\([^)]*\)\s*\|\|\s*0/;
  var hit = forbidden.test(datasetsSource);
  check('datasets.html 不再存在 asNumber(...) || 0 兜底写法', !hit,
    hit ? '发现违规写法' : '0 命中');
} catch (err) {
  check('读取 datasets.html', false, err.message);
}

// ---------------------------------------------------------------------------
// 汇总
// ---------------------------------------------------------------------------
var total = passed + failed;
say('');
say('结果: ' + passed + '/' + total + ' passed');
process.exit(failed === 0 ? 0 : 1);
