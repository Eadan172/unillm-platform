/* UniLLM 控制台 · 唯一出网出口
 * - 自动携带 Token
 * - 统一处理 401 / 403
 * - 统一把后端错误体解析为 ApiError(status, error_code, detail, hint)
 * 页面只允许通过 API.* 访问后端，禁止裸 fetch。
 */
(function () {
  'use strict';

  var TOKEN_KEY = 'unillm_token';

  function ApiError(status, error_code, detail, hint) {
    var msg = detail || ('HTTP ' + status);
    var err = new Error(msg);
    err.name = 'ApiError';
    err.status = status;
    err.error_code = error_code;
    err.detail = detail;
    err.hint = hint;
    return err;
  }

  function isLoginPage() {
    return /\/login\.html$/.test(location.pathname);
  }

  function toLogin(nextPath) {
    var next = nextPath || (location.pathname.replace(/^.*\/console\//, '') + location.search);
    location.href = 'login.html?next=' + encodeURIComponent(next || 'index.html');
  }

  var API = {
    getToken: function () {
      try { return localStorage.getItem(TOKEN_KEY) || ''; } catch (e) { return ''; }
    },
    setToken: function (t) {
      try { localStorage.setItem(TOKEN_KEY, t || ''); } catch (e) { /* 忽略隐私模式等 */ }
    },
    clearToken: function () {
      try { localStorage.removeItem(TOKEN_KEY); } catch (e) { /* 忽略 */ }
    },

    _authHeaders: function (extra) {
      var headers = extra || {};
      var token = this.getToken();
      if (token) { headers['Authorization'] = 'Bearer ' + token; }
      return headers;
    },

    request: function (path, opts) {
      var self = this;
      opts = opts || {};
      var method = opts.method || 'GET';
      var body = opts.body === undefined ? null : opts.body;
      var isForm = !!opts.isForm;
      var headers = this._authHeaders(opts.headers ? Object.assign({}, opts.headers) : {});

      var payload = null;
      if (body !== null) {
        if (isForm) {
          payload = body; // FormData：Content-Type 交给浏览器
        } else {
          headers['Content-Type'] = 'application/json';
          payload = JSON.stringify(body);
        }
      }

      return fetch(path, { method: method, headers: headers, body: payload }).then(function (response) {
        if (response.status === 401) {
          self.clearToken();
          if (!isLoginPage()) {
            if (window.Layout && Layout.toast) { Layout.toast('登录已失效，请重新登录', 'error'); }
            toLogin();
          }
          return response.text().then(function () {
            throw ApiError(401, 'UNAUTHORIZED', '登录已失效，请重新登录', null);
          });
        }
        if (response.status === 403) {
          if (window.Layout && Layout.toast) { Layout.toast('Token 无权访问该操作', 'error'); }
        }
        return response.text().then(function (text) {
          var data = null;
          if (text) {
            try { data = JSON.parse(text); } catch (e) { data = text; }
          }
          if (!response.ok) {
            var detail = (data && data.detail) ? data.detail : ('请求失败（HTTP ' + response.status + '）');
            throw ApiError(
              response.status,
              (data && data.error_code) ? data.error_code : null,
              detail,
              (data && data.hint) ? data.hint : null
            );
          }
          return data;
        });
      }).catch(function (err) {
        if (err && err.name === 'ApiError') { throw err; }
        throw ApiError(0, 'NETWORK_ERROR', '无法连接服务，请确认服务已启动', null);
      });
    },

    get: function (path) { return this.request(path, { method: 'GET' }); },
    post: function (path, body, isForm) {
      return this.request(path, { method: 'POST', body: body === undefined ? null : body, isForm: !!isForm });
    },
    del: function (path) { return this.request(path, { method: 'DELETE' }); },

    /* 登录探针：只返回布尔值，不产生跳转副作用，供 layout.guard() 使用 */
    verify: function () {
      var headers = this._authHeaders({});
      var self = this;
      return fetch('/api/auth/verify', { method: 'GET', headers: headers }).then(function (response) {
        if (response.status === 401) { self.clearToken(); return false; }
        if (!response.ok) { return false; }
        return response.json().then(function (data) { return !!(data && data.valid); })
          .catch(function () { return false; });
      }).catch(function () { return false; });
    },

    /* 带 Token 下载：必须用 fetch + Blob + a[download]，否则带不上 Authorization 头 */
    download: function (path, filename) {
      var self = this;
      var headers = this._authHeaders({});
      return fetch(path, { method: 'GET', headers: headers }).then(function (response) {
        if (response.status === 401) {
          self.clearToken();
          if (!isLoginPage()) { toLogin(); }
          throw ApiError(401, 'UNAUTHORIZED', '登录已失效，请重新登录', null);
        }
        if (!response.ok) {
          return response.text().then(function (text) {
            var detail = '下载失败（HTTP ' + response.status + '）';
            try { var d = JSON.parse(text); if (d && d.detail) { detail = d.detail; } } catch (e) { /* 非 JSON */ }
            throw ApiError(response.status, null, detail, null);
          });
        }
        return response.blob().then(function (blob) {
          var url = URL.createObjectURL(blob);
          var a = document.createElement('a');
          a.href = url;
          a.download = filename || 'download.jsonl';
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
        });
      }).catch(function (err) {
        if (err && err.name === 'ApiError') { throw err; }
        throw ApiError(0, 'NETWORK_ERROR', '无法连接服务，请确认服务已启动', null);
      });
    }
  };

  window.API = API;
  window.ApiError = ApiError;
})();
