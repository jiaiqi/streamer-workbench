/* ============================================================
 * 歌单海报生成器 · 共享交互脚本
 * 亮/暗切换（持久化 + 平滑过渡）、lucide 图标、入场编排、
 * 数字滚动、折叠面板、分段选择器、开关、Toast
 * ============================================================ */
(function () {
  "use strict";

  /* ---------- 主题 ---------- */
  const THEME_KEY = "gp-theme";

  function currentTheme() {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === "dark" || saved === "light") return saved;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function applyTheme(theme, animate, persist) {
    const html = document.documentElement;
    if (animate) {
      html.classList.add("gp-anim");
      setTimeout(() => html.classList.remove("gp-anim"), 450);
    }
    html.classList.toggle("dark", theme === "dark");
    if (persist) localStorage.setItem(THEME_KEY, theme);
    document.querySelectorAll("[data-theme-icon]").forEach((el) => {
      el.innerHTML =
        theme === "dark"
          ? '<i data-lucide="sun" class="h-full w-full"></i>'
          : '<i data-lucide="moon" class="h-full w-full"></i>';
    });
    if (window.lucide) lucide.createIcons();
  }

  function toggleTheme() {
    applyTheme(currentTheme() === "dark" ? "light" : "dark", true, true);
  }

  /* ---------- 入场编排：为 .gp-stagger 子元素写入级联延迟 ---------- */
  function setupStagger() {
    document.querySelectorAll(".gp-stagger, .gp-stagger-scale").forEach((wrap) => {
      const step = parseFloat(wrap.dataset.staggerStep || "55");
      const base = parseFloat(wrap.dataset.staggerBase || "0");
      Array.from(wrap.children).forEach((child, i) => {
        child.style.animationDelay = base + i * step + "ms";
      });
    });
  }

  /* ---------- 数字滚动 ---------- */
  function animateCount(el) {
    const target = parseFloat(el.dataset.count);
    const duration = parseFloat(el.dataset.countDuration || "1100");
    const start = performance.now();
    function tick(now) {
      const p = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      el.textContent = Math.round(target * eased);
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  function setupCounters() {
    const els = document.querySelectorAll("[data-count]");
    if (!("IntersectionObserver" in window)) {
      els.forEach(animateCount);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            animateCount(e.target);
            io.unobserve(e.target);
          }
        });
      },
      { threshold: 0.4 }
    );
    els.forEach((el) => io.observe(el));
  }

  /* ---------- 折叠面板 ---------- */
  function setupCollapse() {
    document.querySelectorAll("[data-collapse-trigger]").forEach((trigger) => {
      trigger.addEventListener("click", () => {
        const panel = document.querySelector(trigger.dataset.collapseTrigger);
        if (!panel) return;
        const open = panel.classList.toggle("open");
        trigger.setAttribute("aria-expanded", open ? "true" : "false");
      });
    });
  }

  /* ---------- 分段选择器（滑块跟随） ---------- */
  function setupSegments() {
    document.querySelectorAll(".gp-segment").forEach((seg) => {
      const thumb = document.createElement("span");
      thumb.className = "gp-segment-thumb";
      seg.prepend(thumb);
      const buttons = Array.from(seg.querySelectorAll("button"));

      function move(btn) {
        buttons.forEach((b) => b.classList.toggle("active", b === btn));
        thumb.style.left = btn.offsetLeft + "px";
        thumb.style.width = btn.offsetWidth + "px";
        seg.dispatchEvent(new CustomEvent("gp:segment", { detail: { value: btn.dataset.value } }));
      }
      buttons.forEach((btn) =>
        btn.addEventListener("click", () => {
          if (seg.dataset.role === "theme-mode") {
            const v = btn.dataset.value;
            if (v === "system") {
              localStorage.removeItem(THEME_KEY);
              applyTheme(
                window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light",
                true,
                false
              );
            } else applyTheme(v, true, true);
          }
          move(btn);
        })
      );
      let initial = buttons.find((b) => b.classList.contains("active")) || buttons[0];
      if (seg.dataset.role === "theme-mode") {
        const saved = localStorage.getItem(THEME_KEY);
        initial = buttons.find((b) => b.dataset.value === (saved || "system")) || initial;
      }
      requestAnimationFrame(() => move(initial));
      window.addEventListener("resize", () => move(seg.querySelector("button.active") || buttons[0]));
    });
  }

  /* ---------- 开关 ---------- */
  function setupSwitches() {
    document.querySelectorAll(".gp-switch").forEach((sw) => {
      sw.setAttribute("role", "switch");
      sw.setAttribute("aria-checked", sw.classList.contains("on") ? "true" : "false");
      sw.addEventListener("click", () => {
        const on = sw.classList.toggle("on");
        sw.setAttribute("aria-checked", on ? "true" : "false");
        sw.dispatchEvent(new CustomEvent("gp:switch", { detail: { on } }));
      });
    });
  }

  /* ---------- Toast ---------- */
  let toastWrap = null;
  function toast(message, icon) {
    if (!toastWrap) {
      toastWrap = document.createElement("div");
      toastWrap.className = "gp-toast-wrap";
      document.body.appendChild(toastWrap);
    }
    const el = document.createElement("div");
    el.className = "gp-toast";
    el.innerHTML =
      '<span class="gp-icon h-4 w-4 text-primary"><i data-lucide="' +
      (icon || "check-circle-2") +
      '"></i></span><span></span>';
    el.lastElementChild.textContent = message;
    toastWrap.appendChild(el);
    if (window.lucide) lucide.createIcons();
    setTimeout(() => {
      el.classList.add("leaving");
      setTimeout(() => el.remove(), 320);
    }, 2400);
  }

  /* ---------- 初始化 ---------- */
  document.addEventListener("DOMContentLoaded", () => {
    applyTheme(currentTheme(), false, false);
    setupStagger();
    setupCounters();
    setupCollapse();
    setupSegments();
    setupSwitches();
    document.querySelectorAll("[data-theme-toggle]").forEach((btn) =>
      btn.addEventListener("click", toggleTheme)
    );
    if (window.lucide) lucide.createIcons();
  });

  window.gp = { toast, applyTheme, toggleTheme, currentTheme };
})();
