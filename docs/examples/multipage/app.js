/* アンケン帳 共有スクリプト。3ページすべてが読み込む(修正前後で変更しない) */
(function () {
  'use strict';

  // タブ: [data-tab="名前"] のボタンと [data-tab-panel="名前"] のパネル
  document.querySelectorAll('[data-tabs]').forEach(function (group) {
    var tabs = group.querySelectorAll('[data-tab]');
    tabs.forEach(function (tab) {
      tab.addEventListener('click', function () {
        tabs.forEach(function (t) {
          var on = t === tab;
          t.classList.toggle('is-active', on);
          t.setAttribute('aria-selected', on ? 'true' : 'false');
        });
        document.querySelectorAll('[data-tab-panel]').forEach(function (p) {
          p.classList.toggle('is-active', p.getAttribute('data-tab-panel') === tab.getAttribute('data-tab'));
        });
      });
    });
  });

  // モーダル: [data-modal-open="id"] で開き、[data-modal-close]・背景・Esc で閉じる
  var lastFocus = null;
  function closeModals() {
    document.querySelectorAll('.modal-backdrop.is-open').forEach(function (m) { m.classList.remove('is-open'); });
    if (lastFocus) { lastFocus.focus(); lastFocus = null; }
  }
  document.addEventListener('click', function (e) {
    var opener = e.target.closest('[data-modal-open]');
    if (opener) {
      var m = document.getElementById(opener.getAttribute('data-modal-open'));
      if (m) {
        lastFocus = opener;
        m.classList.add('is-open');
        var first = m.querySelector('input, select, textarea, button');
        if (first) first.focus();
      }
      return;
    }
    if (e.target.closest('[data-modal-close]') || e.target.classList.contains('modal-backdrop')) closeModals();
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeModals(); });

  // お知らせ(トースト)
  var toast = document.getElementById('toast');
  var toastTimer;
  function showToast(text) {
    if (!toast) return;
    toast.textContent = text;
    toast.classList.add('is-shown');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toast.classList.remove('is-shown'); }, 2400);
  }

  // 一覧: 状態と検索語で絞り込む
  var filter = document.getElementById('statusFilter');
  var keyword = document.getElementById('keyword');
  var rows = document.querySelectorAll('#projectRows tr');
  var empty = document.getElementById('emptyState');
  var counter = document.getElementById('resultCount');
  function applyFilter() {
    var status = filter ? filter.value : 'all';
    var q = keyword ? keyword.value.trim().toLowerCase() : '';
    var shown = 0;
    rows.forEach(function (r) {
      var ok = (status === 'all' || r.getAttribute('data-status') === status) &&
               (!q || r.textContent.toLowerCase().indexOf(q) !== -1);
      r.style.display = ok ? '' : 'none';
      if (ok) shown++;
    });
    if (empty) empty.classList.toggle('is-shown', shown === 0);
    if (counter) counter.textContent = shown + '件';
  }
  if (filter) filter.addEventListener('change', applyFilter);
  if (keyword) keyword.addEventListener('input', applyFilter);
  if (rows.length) applyFilter();

  // フォーム: [data-validate] のフォームは必須項目を確かめ、通ればトーストを出す(送信はしない)
  document.querySelectorAll('form[data-validate]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var ok = true;
      form.querySelectorAll('[required]').forEach(function (input) {
        var bad = !input.value.trim() || (input.type === 'email' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(input.value.trim()));
        input.classList.toggle('is-invalid', bad);
        input.setAttribute('aria-invalid', bad ? 'true' : 'false');
        var err = document.getElementById(input.id + 'Error');
        if (err) err.hidden = !bad;
        if (bad) ok = false;
      });
      if (!ok) {
        var first = form.querySelector('.is-invalid');
        if (first) first.focus();
        return;
      }
      showToast(form.getAttribute('data-success') || '保存しました');
      if (form.closest('.modal-backdrop')) closeModals();
    });
  });
})();
