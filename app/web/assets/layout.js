/* UniLLM 控制台 · 共享布局与通用组件
 * 顶栏 / 左侧导航 / 降级横幅 / toast / 空态 / 错误态 / 加载态 —— 全部在此一处注入。
 * 页面不得复制这些 DOM。
 *
 * 关键约束（架构硬要求）：
 * - guard() 必须**始终**调用 /api/auth/verify 再决定去留，不得因 localStorage 无 Token
 *   就短路跳登录（否则 auth_enabled=false 的本地开发环境永远进不去）。
 * - 降级横幅只依赖 /health.degraded，一处渲染，全站一致。
 * - 前端零默认值兜底：数值字段缺失/非数字时渲染「未知 / 不可用」，绝不落 0。
 */
(function () {
  'use strict';

  var NAV_ITEMS = [
    { page: 'index', label: '总览', href: 'index.html' },
    { page: 'datasets', label: '数据集', href: 'datasets.html' },
    { page: 'annotation', label: '标注', href: 'annotation.html', tag: 'P1' },
    { page: 'models', label: '模型', href: 'models.html' },
    { page: 'playground', label: '推理试验台', href: 'playground.html' },
    { page: 'finetune', label: '微调', href: 'finetune.html', tag: 'P1' },
    { page: 'evaluate', label: '评测', href: 'evaluate.html' }
  ];

  var Layout = {
    health: null,

    /* ------------------------- 工具 ------------------------- */

    esc: function (s) {
      return String(s === null || s === undefined ? '' : s).replace(/[&<>"']/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
      });
    },

    /* 仅当值是真正的数字时才返回数字，否则 null（用于「不造假」渲染） */
    asNumber: function (v) {
      return (typeof v === 'number' && isFinite(v)) ? v : null;
    },

    /* 数字或「未知」——缺失/非数字一律不落 0 */
    numOrUnknown: function (v) {
      var n = this.asNumber(v);
      return n === null ? '未知' : String(n);
    },

    /* 求和但绝不把缺失当 0：任一参与项为「未知」→ 整体亦为「未知」(null)。
       空数组同样返回 null（无数据不等于 0） */
    sumOrUnknown: function (values) {
      var sum = 0;
      for (var i = 0; i < values.length; i++) {
        var n = this.asNumber(values[i]);
        if (n === null) { return null; }
        sum += n;
      }
      return values.length ? sum : null;
    },

    fmtDate: function (iso) {
      if (!iso) { return '—'; }
      var d = new Date(iso);
      if (isNaN(d.getTime())) { return String(iso); }
      try { return d.toLocaleString('zh-CN'); } catch (e) { return d.toISOString(); }
    },

    page: function () {
      return document.body.getAttribute('data-page') || '';
    },

    /* ------------------------- 启动与守卫 ------------------------- */

    /* 标准入口：登录页不在此处理；其余页面先守卫，再渲染框架，最后跑页面逻辑 */
    boot: function (loader) {
      var self = this;
      if (this.page() === 'login') { return; }
      return this.guard().then(function (ok) {
        if (!ok) { return; }
        self.renderChrome();
        if (typeof loader === 'function') { return loader(); }
      });
    },

    /* 始终调用 verify 决定去留；不得用 localStorage 短路 */
    guard: function () {
      var self = this;
      if (this.page() === 'login') { return Promise.resolve(true); }
      return API.verify().then(function (ok) {
        if (!ok) {
          var next = location.pathname.replace(/^.*\/console\//, '') + location.search;
          location.href = 'login.html?next=' + encodeURIComponent(next || 'index.html');
          return false;
        }
        return true;
      });
    },

    /* ------------------------- 框架渲染 ------------------------- */

    renderChrome: function () {
      this.renderTopbar();
      this.renderSidebar();
      this.renderToastHost();
      return this.refreshHealth();
    },

    renderTopbar: function () {
      var host = document.getElementById('app-topbar');
      if (!host) { return; }
      host.innerHTML =
        '<div class="ullm-topbar">' +
          '<div class="ullm-topbar-inner">' +
            '<div class="ullm-brand">UniLLM 控制台</div>' +
            '<div class="ullm-topbar-right">' +
              '<span class="ullm-status" id="ullm-status" title="加载中…">' +
                '<span class="ullm-status-dot" id="ullm-status-dot"></span>' +
                '<span id="ullm-status-text">状态检查中…</span>' +
              '</span>' +
              '<span>登录身份：Token 用户</span>' +
              '<button type="button" class="ullm-btn ullm-btn-sm" id="ullm-logout">退出登录</button>' +
            '</div>' +
          '</div>' +
        '</div>';

      var logout = document.getElementById('ullm-logout');
      if (logout) {
        logout.addEventListener('click', function () { Layout.logout(); });
      }
    },

    renderSidebar: function () {
      var host = document.getElementById('app-sidebar');
      if (!host) { return; }
      var current = this.page();
      var html = '';
      for (var i = 0; i < NAV_ITEMS.length; i++) {
        var item = NAV_ITEMS[i];
        var active = item.page === current ? ' is-active' : '';
        var tag = item.tag ? ' <span class="ullm-badge ullm-badge-muted">' + item.tag + '</span>' : '';
        html += '<a class="ullm-nav-item' + active + '" href="' + item.href + '">' +
                  '<span>' + this.esc(item.label) + '</span>' + tag +
                '</a>';
      }
      host.innerHTML = html;
    },

    renderToastHost: function () {
      if (!document.getElementById('app-toast')) {
        var host = document.createElement('div');
        host.id = 'app-toast';
        document.body.appendChild(host);
      }
    },

    refreshHealth: function () {
      var self = this;
      // /health 是公开端点，无需 Token
      return API.get('/health').then(function (health) {
        self.health = health;
        self.renderBanner(health);
        self.updateStatus(health);
      }).catch(function () {
        self.health = null;
        self.renderBanner(null);
        self.updateStatus(null);
      });
    },

    updateStatus: function (health) {
      var dot = document.getElementById('ullm-status-dot');
      var text = document.getElementById('ullm-status-text');
      var wrap = document.getElementById('ullm-status');
      if (!dot || !text) { return; }
      dot.className = 'ullm-status-dot';
      if (!health) {
        text.textContent = '状态未知';
        if (wrap) { wrap.title = '无法获取 /health'; }
        return;
      }
      var backend = health.inference_backend || '未知';
      var real = health.inference_backend_is_real_model === true;
      dot.className = 'ullm-status-dot ' + (real ? 'is-success' : 'is-warning');
      text.textContent = (real ? '真实后端' : '占位后端') + ' (' + backend + ')';
      if (wrap) {
        var tip = 'backend: ' + backend;
        var api = '';
        if (window.Layout && Layout.health) { /* noop */ }
        tip += real ? ' · 真实模型' : ' · 占位输出，非真实模型';
        wrap.title = tip;
      }
    },

    /* 降级横幅：degraded=true 时常驻橙色、不可关闭 */
    renderBanner: function (health) {
      var host = document.getElementById('app-banner');
      if (!host) { return; }
      if (!health || health.degraded !== true) {
        host.innerHTML = '';
        return;
      }
      var backend = health.inference_backend || 'mock';
      host.innerHTML =
        '<div class="ullm-banner ullm-warning" role="alert">' +
          '<strong>⚠ 当前为占位后端，非真实模型。</strong>' +
          '<span>推理结果为确定性占位文本（backend：' + this.esc(backend) +
          '），不可作为模型能力结论。如需真实推理：请在 Linux + CUDA 环境执行 ' +
          'pip install -r requirements-gpu.txt。</span>' +
        '</div>';
    },

    logout: function () {
      API.clearToken();
      location.href = 'login.html';
    },

    /* ------------------------- 通用状态 ------------------------- */

    renderLoading: function (el, msg) {
      if (!el) { return; }
      el.innerHTML = '<div class="ullm-loading">' + this.esc(msg || '加载中…') + '</div>';
    },

    renderEmpty: function (el, opts) {
      if (!el) { return; }
      opts = opts || {};
      var icon = opts.icon || '📭';
      var title = opts.title || '暂无数据';
      var desc = opts.desc || '';
      el.innerHTML = '';
      var box = document.createElement('div');
      box.className = 'ullm-empty';
      box.innerHTML =
        '<div class="ullm-empty-icon">' + icon + '</div>' +
        '<div class="ullm-empty-title">' + this.esc(title) + '</div>' +
        (desc ? '<div class="ullm-empty-desc">' + this.esc(desc) + '</div>' : '');
      if (opts.actionLabel && typeof opts.onAction === 'function') {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'ullm-btn ullm-btn-primary';
        btn.textContent = opts.actionLabel;
        btn.addEventListener('click', opts.onAction);
        box.appendChild(btn);
      }
      el.appendChild(box);
    },

    /* 错误条：展示后端 detail 原文 + 重试入口，绝不吞错 */
    renderError: function (el, err, retryFn) {
      if (!el) { return; }
      var detail = (err && err.detail) ? err.detail : (err && err.message ? err.message : '未知错误');
      el.innerHTML = '';
      var bar = document.createElement('div');
      bar.className = 'ullm-errorbar';
      var msg = document.createElement('div');
      msg.className = 'ullm-errorbar-msg';
      msg.textContent = '✕ ' + detail;
      bar.appendChild(msg);
      if (typeof retryFn === 'function') {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'ullm-btn ullm-btn-sm';
        btn.textContent = '重试';
        btn.addEventListener('click', retryFn);
        bar.appendChild(btn);
      }
      el.appendChild(bar);
    },

    toast: function (msg, type) {
      this.renderToastHost();
      var host = document.getElementById('app-toast');
      var t = document.createElement('div');
      t.className = 'ullm-toast ' + (type === 'error' ? 'ullm-error' : type === 'success' ? 'ullm-success' : 'ullm-warning');
      t.textContent = msg;
      host.appendChild(t);
      setTimeout(function () {
        t.classList.add('ullm-toast-out');
        setTimeout(function () { if (t.parentNode) { t.parentNode.removeChild(t); } }, 320);
      }, 3400);
    },

    /* ------------------------- 弹层 ------------------------- */

    modal: function (opts) {
      opts = opts || {};
      var self = this;
      var mask = document.createElement('div');
      mask.className = 'ullm-modal-mask';
      var modal = document.createElement('div');
      modal.className = 'ullm-modal';

      var head = document.createElement('div');
      head.className = 'ullm-modal-head';
      var title = document.createElement('div');
      title.textContent = opts.title || '';
      var closeBtn = document.createElement('button');
      closeBtn.type = 'button';
      closeBtn.className = 'ullm-modal-close';
      closeBtn.setAttribute('aria-label', '关闭');
      closeBtn.textContent = '×';
      head.appendChild(title);
      head.appendChild(closeBtn);

      var body = document.createElement('div');
      body.className = 'ullm-modal-body';
      if (opts.bodyNode) { body.appendChild(opts.bodyNode); }
      else if (opts.bodyHTML) { body.innerHTML = opts.bodyHTML; }

      var foot = document.createElement('div');
      foot.className = 'ullm-modal-foot';

      function close() {
        if (mask.parentNode) { mask.parentNode.removeChild(mask); }
        document.removeEventListener('keydown', onKey);
      }
      function onKey(e) { if (e.key === 'Escape') { close(); } }

      var actions = opts.actions || [{ label: '关闭' }];
      for (var i = 0; i < actions.length; i++) {
        (function (action) {
          var btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'ullm-btn' + (action.primary ? ' ullm-btn-primary' : '') + (action.danger ? ' ullm-btn-danger' : '');
          btn.textContent = action.label;
          btn.addEventListener('click', function () {
            if (typeof action.onClick === 'function') {
              var res = action.onClick({ close: close, btn: btn });
              if (res === false) { return; }
            }
            if (action.keepOpen !== true) { close(); }
          });
          foot.appendChild(btn);
        })(actions[i]);
      }

      closeBtn.addEventListener('click', close);
      mask.addEventListener('click', function (e) { if (e.target === mask) { close(); } });
      document.addEventListener('keydown', onKey);

      modal.appendChild(head);
      modal.appendChild(body);
      if (foot.childNodes.length) { modal.appendChild(foot); }
      mask.appendChild(modal);
      document.body.appendChild(mask);

      return { close: close, body: body, mask: mask, foot: foot };
    },

    /* 设置按钮忙碌态（防重复提交） */
    setBusy: function (btn, busy, busyText) {
      if (!btn) { return; }
      if (busy) {
        if (!btn.getAttribute('data-label')) { btn.setAttribute('data-label', btn.textContent); }
        btn.disabled = true;
        btn.textContent = busyText || '处理中…';
      } else {
        btn.disabled = false;
        var label = btn.getAttribute('data-label');
        if (label) { btn.textContent = label; }
      }
    }
  };

  window.Layout = Layout;
})();
