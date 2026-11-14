/*
 * design-polish 切り替えスニペット(開発環境に貼る版)
 *
 * 共通層のCSSを、同じ画面の上でオン・オフする。ページを再読み込みしないので、
 * モーダルを開いたまま、タブを切り替えたまま、エラーを出したまま前後を比べられる。
 *
 * 使い方(どちらか):
 *   <script src="toggle-snippet.js" data-polish-href="polish.css"></script>
 *   <script src="toggle-snippet.js" data-polish-css="body{background:#fafaf8}"></script>
 * src で読めない環境では、この中身を <script> に貼り、下の CONFIG を書き換える。
 *
 * 任意の属性:
 *   data-polish-default="off"   初回の状態(既定は on)
 *   data-polish-key="名前"      状態を保存するキー(既定は dp-polish)
 *
 * 操作: 右下のボタン、または Alt + P
 * 外部への通信はしない。確認が済んだら本番のコードから外すこと。
 */
(function () {
  'use strict';

  var CONFIG = {
    href: '',        // 共通層のCSSファイルへのパス
    css: '',         // またはCSSの文字列
    initial: 'on',   // 初回の状態: 'on' か 'off'
    key: 'dp-polish' // 状態を保存するキー
  };

  var script = document.currentScript;
  if (script) {
    CONFIG.href = script.getAttribute('data-polish-href') || CONFIG.href;
    CONFIG.css = script.getAttribute('data-polish-css') || CONFIG.css;
    CONFIG.initial = script.getAttribute('data-polish-default') || CONFIG.initial;
    CONFIG.key = script.getAttribute('data-polish-key') || CONFIG.key;
  }

  // 二重に読み込まれたら、切り替えだけ行う
  if (window.__dpPolish) { window.__dpPolish.toggle(); return; }
  if (!CONFIG.href && !CONFIG.css) {
    console.warn('[design-polish] data-polish-href か data-polish-css を指定してください');
    return;
  }

  function load() {
    try { return window.localStorage.getItem(CONFIG.key); } catch (e) { return null; }
  }
  function save(v) {
    try { window.localStorage.setItem(CONFIG.key, v); } catch (e) { /* 保存できなくても動かす */ }
  }

  var saved = load();
  var on = saved ? saved === 'on' : CONFIG.initial !== 'off';

  // 共通層のCSSを差し込む。media を切り替えて有効・無効にする
  var sheet;
  if (CONFIG.href) {
    sheet = document.createElement('link');
    sheet.rel = 'stylesheet';
    sheet.href = CONFIG.href;
  } else {
    sheet = document.createElement('style');
    sheet.textContent = CONFIG.css;
  }
  sheet.id = 'dp-polish-sheet';
  document.head.appendChild(sheet);

  // ボタンは Shadow DOM の中に描き、対象ページのCSSの影響を受けないようにする
  var host = document.createElement('div');
  host.id = 'dp-polish-toggle';
  host.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:2147483647;';
  var root = host.attachShadow ? host.attachShadow({ mode: 'open' }) : host;
  root.innerHTML =
    '<style>' +
    'button{all:initial;display:inline-flex;align-items:center;gap:10px;box-sizing:border-box;' +
    'min-height:44px;padding:0 16px 0 12px;border-radius:22px;cursor:pointer;' +
    'font:600 13px/1 system-ui,-apple-system,"Hiragino Sans","Yu Gothic UI",sans-serif;' +
    'background:#1d1c1a;color:#f3f1ec;box-shadow:0 2px 10px rgba(0,0,0,.28);}' +
    'button:focus-visible{outline:3px solid #f3f1ec;outline-offset:2px;box-shadow:0 0 0 5px #1d1c1a;}' +
    '.track{position:relative;width:34px;height:20px;border-radius:10px;background:#6d6a63;flex:none;}' +
    '.knob{position:absolute;top:2px;left:2px;width:16px;height:16px;border-radius:50%;background:#f3f1ec;}' +
    'button[aria-pressed="true"] .track{background:#3f8f6b;}' +
    'button[aria-pressed="true"] .knob{left:16px;}' +
    'small{font:400 11px/1 system-ui,sans-serif;color:#b5b1a8;}' +
    '@media (prefers-reduced-motion:no-preference){.knob{transition:left .15s}}' +
    '</style>' +
    '<button type="button" title="Alt + P で切り替え">' +
    '<span class="track"><span class="knob"></span></span>' +
    '<span class="label"></span><small>Alt+P</small></button>';
  var button = root.querySelector('button');
  var label = root.querySelector('.label');

  function render() {
    sheet.media = on ? 'all' : 'not all';
    button.setAttribute('aria-pressed', on ? 'true' : 'false');
    label.textContent = on ? '修正後(共通層CSS オン)' : '修正前(共通層CSS オフ)';
    document.documentElement.setAttribute('data-dp-polish', on ? 'on' : 'off');
  }
  function set(next) { on = !!next; save(on ? 'on' : 'off'); render(); }
  function toggle() { set(!on); }

  button.addEventListener('click', toggle);
  document.addEventListener('keydown', function (e) {
    if (e.altKey && !e.ctrlKey && !e.metaKey && e.code === 'KeyP') { e.preventDefault(); toggle(); }
  });

  function mount() { document.body.appendChild(host); render(); }
  if (document.body) mount(); else document.addEventListener('DOMContentLoaded', mount);

  window.__dpPolish = { toggle: toggle, set: set, isOn: function () { return on; } };
})();
