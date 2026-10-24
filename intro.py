"""
intro.py - the opening screen of ShiftHappens

A full-window dark screen with an animated field of dots. Each dot is a "task":
the dots circle as one ring (one job), then split into three groups in the
basket colours (AI may take over / AI will assist you / stays mostly human),
then come back together. The animation is original canvas code, run in the page
with st.html(..., unsafe_allow_javascript=True).

The Start button is a real Streamlit button laid over the animation, so the
click reaches Python.

Used from app.py:
    if not intro.done():
        intro.render()
"""
import streamlit as st

TITLE = "ShiftHappens"
KICKER = "For office workers facing AI change"
SLOGAN = "AI changes tasks, not whole jobs. Find your next move."
NOTE = "No sign-up needed. Estimates to support your decision."

CSS = """
<style>
/* exists only on the opening screen, so the normal pages keep their layout */
.stApp { background: #0A0A0A !important; }
[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }
[data-testid="stMain"] { overflow: hidden; }
.block-container, [data-testid="stMainBlockContainer"] { padding: 0 !important; max-width: 100% !important; }
.sh-intro { position: fixed; inset: 0; z-index: 10; background: #0A0A0A; overflow: hidden;
            font-family: Geist, -apple-system, Segoe UI, sans-serif; }
.sh-intro canvas { position: absolute; inset: 0; width: 100%; height: 100%; }
.sh-intro .veil { position: absolute; inset: 0; pointer-events: none;
  background: radial-gradient(ellipse 46% 40% at 50% 46%, rgba(10,10,10,0.88), rgba(10,10,10,0) 70%); }
.sh-intro .text { position: absolute; left: 0; right: 0; top: 24%; text-align: center; color: #FFFFFF;
                  pointer-events: none; padding: 0 16px; }
.sh-intro .kicker { display: inline-block; font-size: 13px; color: rgba(255,255,255,0.72);
  border: 1px solid rgba(255,255,255,0.18); border-radius: 999px; padding: 5px 14px;
  background: rgba(255,255,255,0.04); }
.sh-intro .title { font-size: clamp(44px, 8vw, 88px); line-height: 1; letter-spacing: -0.05em;
                   margin: 18px 0 14px 0; font-weight: 700; color: #FFFFFF; }
.sh-intro .slogan { font-size: clamp(16px, 2vw, 20px); color: rgba(255,255,255,0.72); margin: 0; }
.sh-intro .note { position: absolute; left: 0; right: 0; bottom: 22px; text-align: center;
                  font-size: 12px; color: rgba(255,255,255,0.45); pointer-events: none; }
.sh-intro .legend { position: absolute; left: 0; right: 0; bottom: 48px; display: flex; gap: 18px;
                    justify-content: center; font-size: 12px; color: rgba(255,255,255,0.6); }
.sh-intro .legend span::before { content: ""; display: inline-block; width: 8px; height: 8px;
                                 border-radius: 50%; margin-right: 6px; background: var(--c); }
.st-key-intro_start {
  position: fixed !important; left: 50%; top: 58%; transform: translate(-50%, -50%);
  z-index: 20; width: auto !important;
}
.st-key-intro_start [data-testid="stBaseButton-primary"] {
  min-height: 54px; padding: 0 44px !important;
  background: rgba(255, 255, 255, 0.92) !important;
  border: 1px solid rgba(255, 255, 255, 0.6) !important;
  animation: introPulse 2.4s ease-in-out infinite;
}
.st-key-intro_start [data-testid="stBaseButton-primary"] p {
  color: #0A0A0A !important; font-size: 17px; font-weight: 600; letter-spacing: 0.02em;
}
.st-key-intro_start [data-testid="stBaseButton-primary"]:hover { background: #FFFFFF !important; }
@keyframes introPulse {
  0%, 100% { box-shadow: 0 0 0 6px rgba(255,255,255,0.08), 0 10px 40px rgba(255,255,255,0.18),
                         inset 0 1px 0 rgba(255,255,255,1); }
  50%      { box-shadow: 0 0 0 12px rgba(255,255,255,0.04), 0 10px 50px rgba(255,255,255,0.32),
                         inset 0 1px 0 rgba(255,255,255,1); }
}
@media (prefers-reduced-motion: reduce) {
  .st-key-intro_start [data-testid="stBaseButton-primary"] { animation: none; }
}
</style>
"""

SCENE = """
<div class="sh-intro">
  <canvas id="shIntroCanvas" aria-hidden="true"></canvas>
  <div class="veil"></div>
  <div class="text">
    <div class="kicker">__KICKER__</div>
    <div class="title" role="heading" aria-level="1">__TITLE__</div>
    <p class="slogan">__SLOGAN__</p>
  </div>
  <div class="legend">
    <span style="--c:#F5A623">AI may take over</span>
    <span style="--c:#0070F3">AI will assist you</span>
    <span style="--c:#45A557">Stays mostly human</span>
  </div>
  <div class="note">__NOTE__</div>
</div>
<script>
(function () {
  var canvas = document.getElementById("shIntroCanvas");
  if (!canvas || canvas.__running) return;
  canvas.__running = true;
  var ctx = canvas.getContext("2d");
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var W = 0, H = 0, DPR = Math.min(window.devicePixelRatio || 1, 2);
  var COLORS = [[245, 166, 35], [0, 112, 243], [69, 165, 87]];
  var N = 240, dots = [];

  function resize() {
    W = canvas.clientWidth; H = canvas.clientHeight;
    canvas.width = W * DPR; canvas.height = H * DPR;
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  }
  window.addEventListener("resize", resize);
  resize();

  for (var i = 0; i < N; i++) {
    dots.push({ a: (i / N) * Math.PI * 2, g: i % 3,
                jx: Math.random() - 0.5, jy: Math.random() - 0.5,
                r: 1.2 + Math.random() * 1.6, ph: Math.random() * Math.PI * 2, x: 0, y: 0 });
  }
  function ease(t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }
  var CYCLE = 9000;
  function mix(t) {
    var p = (t % CYCLE) / CYCLE;
    if (p < 0.30) return 0;
    if (p < 0.45) return ease((p - 0.30) / 0.15);
    if (p < 0.80) return 1;
    if (p < 0.95) return 1 - ease((p - 0.80) / 0.15);
    return 0;
  }
  function frame(now) {
    if (!canvas.isConnected) { window.removeEventListener("resize", resize); return; }
    if (!W || !H) resize();
    var t = reduce ? 0 : now, m = reduce ? 0 : mix(t);
    var cx = W / 2, cy = H * 0.46, R = Math.min(W, H) * 0.40, spin = t * 0.00006;
    var gcs = [[cx - W * 0.35, cy - H * 0.10], [cx + W * 0.35, cy - H * 0.06], [cx, cy + H * 0.34]];
    ctx.clearRect(0, 0, W, H);
    for (var i = 0; i < N; i++) {
      var d = dots[i], wob = Math.sin(t * 0.001 + d.ph) * 6;
      var ax = cx + Math.cos(d.a + spin) * (R + wob * 2) * 1.35;
      var ay = cy + Math.sin(d.a + spin) * (R + wob * 2) * 0.62;
      var gc = gcs[d.g], spread = Math.min(W, H) * 0.11;
      var bx = gc[0] + d.jx * spread * 2 + Math.cos(t * 0.0007 + d.ph) * 8;
      var by = gc[1] + d.jy * spread * 1.4 + Math.sin(t * 0.0009 + d.ph) * 8;
      d.x = ax + (bx - ax) * m; d.y = ay + (by - ay) * m;
    }
    ctx.lineWidth = 0.6;
    for (var a = 0; a < N; a++) {
      for (var b = a + 1; b < N; b += 3) {
        var dx = dots[a].x - dots[b].x, dy = dots[a].y - dots[b].y, d2 = dx * dx + dy * dy;
        if (d2 < 2600) {
          ctx.strokeStyle = "rgba(255,255,255," + ((1 - d2 / 2600) * 0.22).toFixed(3) + ")";
          ctx.beginPath(); ctx.moveTo(dots[a].x, dots[a].y); ctx.lineTo(dots[b].x, dots[b].y); ctx.stroke();
        }
      }
    }
    for (var k = 0; k < N; k++) {
      var e = dots[k], c = COLORS[e.g];
      var rr = Math.round(255 + (c[0] - 255) * m), gg = Math.round(255 + (c[1] - 255) * m),
          bb = Math.round(255 + (c[2] - 255) * m);
      var glow = 0.55 + 0.45 * Math.sin(t * 0.002 + e.ph);
      ctx.fillStyle = "rgba(" + rr + "," + gg + "," + bb + "," + (0.5 + 0.5 * glow).toFixed(3) + ")";
      ctx.beginPath(); ctx.arc(e.x, e.y, e.r + m * 0.6, 0, Math.PI * 2); ctx.fill();
    }
    if (!reduce) requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();
</script>
"""


def done():
    return bool(st.session_state.get("intro_done"))


def _start():
    st.session_state["intro_done"] = True
    st.session_state["step"] = 1


def render():
    st.markdown(CSS, unsafe_allow_html=True)
    st.html(SCENE.replace("__TITLE__", TITLE).replace("__KICKER__", KICKER)
            .replace("__SLOGAN__", SLOGAN).replace("__NOTE__", NOTE),
            unsafe_allow_javascript=True)
    with st.container(key="intro_start"):
        st.button("Start", key="intro_start_btn", type="primary", on_click=_start)