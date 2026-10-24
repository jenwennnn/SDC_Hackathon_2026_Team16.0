"""
fx.py - motion and interaction effects for ShiftHappens

  render_dock(...)   floating glass dock at the bottom centre (replaces the top step bar)
  bridge(items)      installs, once per browser tab, a small script in the main page:
                       - command palette (Ctrl+K or Cmd+K), filters the menu, arrow keys + Enter
                       - frosted cards: soft light that follows the cursor, a brighter
                         border near the cursor, and a slight 3D tilt (max 4 degrees)
  roll(key, value)   a number that rolls from its previous value to the new one

How the script runs: st.html(..., unsafe_allow_javascript=True) runs it in the page.
It installs itself once per browser tab (window.__shFx) and only the menu list is
refreshed on each run. Nothing leaves the browser. If scripts are blocked, the app
still works without the effects.
"""
import html
import json
import re

import streamlit as st

DOCK_ICONS = [":material/badge:", ":material/fact_check:", ":material/donut_large:",
              ":material/work:", ":material/school:"]

DOCK_CSS = """
<style>
.block-container { padding-bottom: 140px !important; }
.st-key-dock {
  position: fixed !important; left: 50%; bottom: 22px; transform: translateX(-50%);
  z-index: 999; width: 330px !important; padding: 8px !important; border-radius: 26px;
  background: rgba(255, 255, 255, 0.55);
  -webkit-backdrop-filter: blur(22px) saturate(180%); backdrop-filter: blur(22px) saturate(180%);
  border: 1px solid rgba(255, 255, 255, 0.8);
  box-shadow: 0 14px 40px rgba(0, 0, 0, 0.14), 0 0 0 1px rgba(0, 0, 0, 0.05),
              inset 0 1px 0 rgba(255, 255, 255, 0.95);
  overflow: visible !important;
}
.st-key-dock [data-testid="stHorizontalBlock"] {
  gap: 0 !important; flex-wrap: nowrap !important; align-items: flex-end; overflow: visible !important;
}
.st-key-dock [data-testid="stColumn"] {
  position: relative; z-index: 1; min-width: 0 !important;
  transform-origin: 50% 100%;
  transition: transform 220ms cubic-bezier(0.2, 0.8, 0.2, 1);
}
/* hovered icon grows, its neighbours follow */
.st-key-dock [data-testid="stColumn"]:has(button:hover) { transform: scale(1.45) translateY(-6px); z-index: 3; }
.st-key-dock [data-testid="stColumn"]:has(button:hover) + [data-testid="stColumn"],
.st-key-dock [data-testid="stColumn"]:has(+ [data-testid="stColumn"] button:hover) {
  transform: scale(1.18) translateY(-2px); z-index: 2;
}
.st-key-dock button {
  background: transparent !important; border: none !important; box-shadow: none !important;
  -webkit-backdrop-filter: none !important; backdrop-filter: none !important;
  min-height: 46px !important; width: 100%; padding: 0 !important;
}
.st-key-dock button p { font-size: 0 !important; line-height: 0; }
.st-key-dock [data-testid="stBaseButton-secondary"]:hover:not(:disabled),
.st-key-dock [data-testid="stBaseButton-primary"]:hover:not(:disabled),
.st-key-dock [data-testid="stBaseButton-secondary"]:active,
.st-key-dock [data-testid="stBaseButton-primary"]:active {
  background: transparent !important; box-shadow: none !important; transform: none !important;
}
.st-key-dock button [data-testid="stIconMaterial"] { font-size: 24px !important; color: #171717 !important; }
.st-key-dock button:disabled [data-testid="stIconMaterial"] { color: #B5B5B5 !important; }
/* name above the icon on hover */
[class*="st-key-dock_"] { position: relative; }
[class*="st-key-dock_"]::before {
  position: absolute; left: 50%; bottom: calc(100% + 12px); transform: translateX(-50%);
  background: rgba(23, 23, 23, 0.86); color: #FFFFFF; font-size: 9px; font-weight: 500;
  padding: 3px 8px; border-radius: 999px; white-space: nowrap; pointer-events: none;
  opacity: 0; transition: opacity 150ms;
}
[class*="st-key-dock_"]:hover::before { opacity: 1; }
/* glass capsule under the current icon: the edge in front leads, the edge behind
   follows, so it stretches while moving and overshoots a little on arrival */
.st-key-dock::before {
  content: ""; position: absolute; top: 8px; bottom: 8px; z-index: 0; border-radius: 18px;
  left: calc(8px + (100% - 16px) * var(--nav-i) / var(--nav-n));
  right: calc(8px + (100% - 16px) * (var(--nav-n) - 1 - var(--nav-i)) / var(--nav-n));
  background: rgba(255, 255, 255, 0.7);
  -webkit-backdrop-filter: blur(16px) saturate(180%); backdrop-filter: blur(16px) saturate(180%);
  border: 1px solid rgba(255, 255, 255, 1);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.10), inset 0 0 0 0.5px rgba(255, 255, 255, 0.95),
              inset 0 1px 1px rgba(255, 255, 255, 1), 0 0 0 0.5px rgba(0, 0, 0, 0.06);
  transition:
    left var(--nav-left-dur) cubic-bezier(0.34, 1.56, 0.64, 1) var(--nav-left-delay),
    right var(--nav-right-dur) cubic-bezier(0.34, 1.56, 0.64, 1) var(--nav-right-delay);
}
.st-key-dock-hint { position: fixed; left: 50%; bottom: 6px; transform: translateX(-50%);
  font-size: 11px; color: #8F8F8F; z-index: 998; pointer-events: none; }
@media (prefers-reduced-motion: reduce) {
  .st-key-dock::before, .st-key-dock [data-testid="stColumn"] { transition: none !important; }
}
</style>
"""

# Runs in the main page (installed once per tab). Plain ES5, ASCII only.
PAGE_SCRIPT = r"""
(function () {
  if (window.__shFx) return;
  window.__shFx = true;
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var css = [
    ".shk-overlay{position:fixed;inset:0;z-index:100000;display:none;align-items:flex-start;justify-content:center;",
    "padding-top:18vh;background:rgba(10,10,10,.28);-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px);}",
    ".shk-overlay.show{display:flex;animation:shkFade .16s ease-out;}",
    "@keyframes shkFade{from{opacity:0}to{opacity:1}}",
    ".shk-box{width:min(560px,92vw);border-radius:18px;overflow:hidden;background:rgba(255,255,255,.72);",
    "-webkit-backdrop-filter:blur(24px) saturate(180%);backdrop-filter:blur(24px) saturate(180%);",
    "border:1px solid rgba(255,255,255,.9);box-shadow:0 24px 70px rgba(0,0,0,.25),0 0 0 1px rgba(0,0,0,.06);",
    "font-family:Geist,-apple-system,Segoe UI,sans-serif;animation:shkPop .18s cubic-bezier(.2,.8,.2,1);}",
    "@keyframes shkPop{from{transform:scale(.97);opacity:.6}to{transform:none;opacity:1}}",
    ".shk-in{width:100%;box-sizing:border-box;border:0;outline:0;background:transparent;font-size:17px;",
    "padding:18px 20px;border-bottom:1px solid rgba(0,0,0,.08);color:#171717;font-family:inherit;}",
    ".shk-list{list-style:none;margin:0;padding:6px;max-height:50vh;overflow:auto;}",
    ".shk-item{display:flex;align-items:center;gap:12px;padding:10px 12px;border-radius:10px;cursor:pointer;",
    "font-size:15px;color:#171717;}",
    ".shk-item.on{background:rgba(0,0,0,.06);}",
    ".shk-item.off{color:#A1A1A1;cursor:default;}",
    ".shk-item mark{background:rgba(0,112,243,.16);color:#0058C2;border-radius:3px;padding:0 1px;}",
    ".shk-num{width:24px;height:24px;border-radius:7px;background:rgba(0,0,0,.06);display:flex;",
    "align-items:center;justify-content:center;font-size:12px;font-weight:600;}",
    ".shk-tag{margin-left:auto;font-size:12px;color:#8F8F8F;}",
    ".shk-empty{padding:14px 12px;color:#8F8F8F;font-size:14px;}",
    ".shk-foot{padding:8px 14px;font-size:12px;color:#8F8F8F;border-top:1px solid rgba(0,0,0,.06);}"
  ].join("");
  var st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);

  // ---------- command palette ----------
  var overlay = null, input = null, list = null, sel = 0, shown = [];
  function items() { return window.__shItems || []; }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) {
    return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; }); }
  function mark(label, q) {
    if (!q) return esc(label);
    var i = label.toLowerCase().indexOf(q.toLowerCase());
    if (i < 0) return esc(label);
    return esc(label.slice(0, i)) + "<mark>" + esc(label.slice(i, i + q.length)) + "</mark>" +
           esc(label.slice(i + q.length));
  }
  function draw() {
    var q = input.value.trim();
    shown = items().filter(function (it) {
      return !q || it.label.toLowerCase().indexOf(q.toLowerCase()) >= 0; });
    if (sel >= shown.length) sel = Math.max(0, shown.length - 1);
    if (!shown.length) { list.innerHTML = '<li class="shk-empty">No matching page</li>'; return; }
    list.innerHTML = shown.map(function (it, i) {
      var tag = it.current ? "Current page" : (it.enabled ? "" : "Not available yet");
      return '<li class="shk-item' + (i === sel ? " on" : "") + (it.enabled ? "" : " off") +
             '" data-i="' + i + '" role="option" aria-selected="' + (i === sel) + '">' +
             '<span class="shk-num">' + it.n + '</span><span>' + mark(it.label, q) + '</span>' +
             (tag ? '<span class="shk-tag">' + tag + '</span>' : "") + '</li>';
    }).join("");
  }
  function build() {
    overlay = document.createElement("div"); overlay.className = "shk-overlay";
    overlay.innerHTML = '<div class="shk-box" role="dialog" aria-label="Go to page">' +
      '<input class="shk-in" placeholder="Go to page..." aria-label="Search pages">' +
      '<ul class="shk-list" role="listbox"></ul>' +
      '<div class="shk-foot">Up and down to choose, Enter to open, Esc to close</div></div>';
    document.body.appendChild(overlay);
    input = overlay.querySelector(".shk-in"); list = overlay.querySelector(".shk-list");
    input.addEventListener("input", function () { sel = 0; draw(); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { e.preventDefault(); sel = Math.min(sel + 1, shown.length - 1); draw(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); sel = Math.max(sel - 1, 0); draw(); }
      else if (e.key === "Enter") { e.preventDefault(); go(sel); }
      else if (e.key === "Escape") { e.preventDefault(); close(); }
    });
    list.addEventListener("mousemove", function (e) {
      var li = e.target.closest(".shk-item"); if (!li) return;
      var i = +li.getAttribute("data-i"); if (i !== sel) { sel = i; draw(); } });
    list.addEventListener("click", function (e) {
      var li = e.target.closest(".shk-item"); if (li) go(+li.getAttribute("data-i")); });
    overlay.addEventListener("mousedown", function (e) { if (e.target === overlay) close(); });
  }
  function open() {
    if (!overlay) build();
    input.value = ""; sel = 0;
    var cur = items().findIndex(function (it) { return it.current; });
    if (cur >= 0) sel = cur;
    draw(); overlay.classList.add("show");
    setTimeout(function () { input.focus(); }, 10);
  }
  function close() { if (overlay) overlay.classList.remove("show"); }
  function go(i) {
    var it = shown[i]; if (!it || !it.enabled) return;
    close();
    if (it.current) return;
    var b = document.querySelector(".st-key-" + it.key + " button");
    if (b && !b.disabled) b.click();
  }
  document.addEventListener("keydown", function (e) {
    if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) {
      e.preventDefault();
      if (overlay && overlay.classList.contains("show")) close(); else open();
    }
  });

  // ---------- frosted cards: cursor light, border glow, slight tilt ----------
  var lit = null;
  function reset(c) { c.classList.remove("sh-lit"); c.style.transform = ""; }
  document.addEventListener("mousemove", function (e) {
    var c = e.target && e.target.closest ? e.target.closest('[class*="st-key-card"]') : null;
    if (lit && lit !== c) reset(lit);
    lit = c;
    if (!c) return;
    var r = c.getBoundingClientRect();
    var x = e.clientX - r.left, y = e.clientY - r.top;
    c.style.setProperty("--mx", x + "px");
    c.style.setProperty("--my", y + "px");
    c.classList.add("sh-lit");
    if (reduce) return;
    var max = 4 * Math.min(1, 420 / Math.max(r.height, 420));   // tall cards tilt less
    var rx = (0.5 - y / r.height) * 2 * max;
    var ry = (x / r.width - 0.5) * 2 * max;
    c.style.transform = "perspective(1100px) rotateX(" + rx.toFixed(2) + "deg) rotateY(" + ry.toFixed(2) + "deg)";
  }, {passive: true});
  document.addEventListener("mouseleave", function () { if (lit) { reset(lit); lit = null; } });
})();
"""

BRIDGE_TEMPLATE = """<div class="sh-bridge" hidden></div><script>
(function () {
  try {
    window.__shItems = __ITEMS__;
    if (!window.__shFx) { (0, eval)(__SCRIPT__); }
  } catch (e) { if (window.console) console.warn("ShiftHappens effects off: " + e); }
})();
</script>"""


def _capsule_css(index, count, direction):
    lead, trail = ("380ms", "0ms"), ("520ms", "70ms")
    if direction > 0:
        right, left = lead, trail
    elif direction < 0:
        left, right = lead, trail
    else:
        left = right = lead
    return (f".st-key-dock{{--nav-i:{int(index)};--nav-n:{int(count)};"
            f"--nav-left-dur:{left[0]};--nav-left-delay:{left[1]};"
            f"--nav-right-dur:{right[0]};--nav-right-delay:{right[1]};}}")


def render_dock(steps, step, reachable, jump):
    """Bottom dock with one icon per step. Returns nothing."""
    prev = st.session_state.get("nav_prev_step", step)
    st.session_state["nav_prev_step"] = step
    names = "".join(f'.st-key-dock_{i}::before{{content:"{html.escape(n)}";}}'
                    for i, n in enumerate(steps, start=1))
    dot = (f".st-key-dock_{step}::after{{content:'';position:absolute;left:50%;bottom:-3px;"
           f"width:5px;height:5px;border-radius:50%;background:#171717;transform:translateX(-50%);}}")
    st.markdown(DOCK_CSS + "<style>" + _capsule_css(step - 1, len(steps), step - prev)
                + names + dot + "</style>", unsafe_allow_html=True)
    with st.container(key="dock"):
        cols = st.columns(len(steps), gap=None)
        for i, (col, name) in enumerate(zip(cols, steps), start=1):
            label = f"{i}. {name}"
            if i == step:
                col.button(label, key=f"dock_{i}", icon=DOCK_ICONS[i - 1], type="primary",
                           width="stretch", help=None)
            else:
                col.button(label, key=f"dock_{i}", icon=DOCK_ICONS[i - 1], width="stretch",
                           disabled=not reachable(i), on_click=jump, args=(i,))
    st.markdown('<div class="st-key-dock-hint">Press Ctrl+K to jump to a page</div>',
                unsafe_allow_html=True)


def _js_literal(value):
    """JSON for a <script> block. '<' and '>' are escaped because st.html skips a script
    whose text contains tag-like sequences such as '<li>'."""
    return (json.dumps(value, ensure_ascii=True)
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))


def bridge(items):
    """items: [{"n": 1, "label": "Your background", "key": "dock_1", "enabled": True, "current": False}]"""
    page = (BRIDGE_TEMPLATE.replace("__ITEMS__", _js_literal(items))
            .replace("__SCRIPT__", _js_literal(PAGE_SCRIPT)))
    with st.container(key="fxbridge"):
        st.html(page, unsafe_allow_javascript=True)


def roll(key, value, width=None):
    """HTML for a whole number that rolls from its last shown value to `value`."""
    value = int(round(value))
    store = st.session_state.setdefault("_roll_prev", {})
    prev = int(store.get(key, value))
    store[key] = value
    name = "shr_" + re.sub(r"[^A-Za-z0-9_]", "_", f"{key}_{prev}_{value}")
    style = f"--sh-n:{value};"
    if prev != value:
        style += f"animation:{name} 750ms cubic-bezier(0.2,0.8,0.2,1);"
    if width:
        style += f"min-width:{width};"
    return (f'<style>@keyframes {name}{{from{{--sh-n:{prev}}}to{{--sh-n:{value}}}}}</style>'
            f'<span class="v-roll" style="{style}"><span class="v-sr">{value}</span></span>')