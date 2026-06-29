/* ============================================================
   app.js — shell interactions: theme toggle, sidebar collapse,
   mobile off-canvas drawer, manual refresh. Decoupled from data
   layer via custom events ('ads:refresh', 'themechange').
   Depends on icons.js (icon()). Run after DOMContentLoaded.
   ============================================================ */

(function () {
  const THEME_KEY = 'ads-theme';
  const SIDEBAR_KEY = 'ads-sidebar';
  const MQ_MOBILE = window.matchMedia('(max-width: 768px)');

  const shell = () => document.getElementById('appShell');

  /* ---------- Theme ---------- */
  function currentTheme() {
    return document.documentElement.getAttribute('data-theme') || 'dark';
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(THEME_KEY, theme);
    const btn = document.getElementById('themeToggle');
    if (btn) {
      btn.setAttribute('aria-label', theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme');
      btn.setAttribute('aria-pressed', String(theme === 'light'));
    }
    // Fill only the icon span so the visible "Theme" label is preserved.
    const iconSlot = document.getElementById('themeToggleIcon');
    if (iconSlot) iconSlot.innerHTML = icon(theme === 'dark' ? 'sun' : 'moon', { size: 20 });
    // Notify charts/renderers to re-pull CSS-variable colors and re-render.
    window.dispatchEvent(new CustomEvent('themechange', { detail: { theme } }));
  }

  function initTheme() {
    let theme = localStorage.getItem(THEME_KEY);
    if (!theme) {
      theme = window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
    }
    applyTheme(theme);
    const btn = document.getElementById('themeToggle');
    if (btn) btn.addEventListener('click', () => applyTheme(currentTheme() === 'dark' ? 'light' : 'dark'));
  }

  /* ---------- Sidebar (collapse on desktop / drawer on mobile) ---------- */
  function isCollapsed() {
    return shell()?.classList.contains('sidebar-collapsed');
  }

  function setCollapsed(collapsed, { persist = true } = {}) {
    const s = shell();
    if (!s) return;
    s.classList.toggle('sidebar-collapsed', collapsed);
    if (persist && !MQ_MOBILE.matches) {
      localStorage.setItem(SIDEBAR_KEY, collapsed ? 'collapsed' : 'expanded');
    }
  }

  function initSidebar() {
    // Desktop: honor stored preference (default expanded).
    // Mobile: always start with drawer closed to avoid an open overlay on load.
    if (MQ_MOBILE.matches) {
      setCollapsed(true, { persist: false });
    } else {
      setCollapsed(localStorage.getItem(SIDEBAR_KEY) === 'collapsed', { persist: false });
    }

    const toggle = document.getElementById('sidebarToggle');
    if (toggle) toggle.addEventListener('click', () => setCollapsed(!isCollapsed()));

    const overlay = document.getElementById('sidebarOverlay');
    if (overlay) overlay.addEventListener('click', () => setCollapsed(true));

    // Close drawer after navigating on mobile (only real nav items,
    // not theme/logout toggles which share the .nav-item class).
    document.addEventListener('click', (e) => {
      const item = e.target.closest('.nav-item[data-tab]');
      if (item && MQ_MOBILE.matches) setCollapsed(true);
    });

    // If the viewport shrinks to mobile, snap the drawer closed.
    MQ_MOBILE.addEventListener('change', (e) => {
      if (e.matches) setCollapsed(true, { persist: false });
    });
  }

  /* ---------- Refresh ---------- */
  function initRefresh() {
    const btn = document.getElementById('refreshBtn');
    if (!btn) return;
    btn.addEventListener('click', () => {
      btn.setAttribute('aria-busy', 'true');
      // dashboard.js listens and re-fetches; reset busy after it resolves.
      window.dispatchEvent(new CustomEvent('ads:refresh', {
        detail: { done: () => btn.removeAttribute('aria-busy') },
      }));
      // Safety reset in case no listener resets busy.
      window.setTimeout(() => btn.removeAttribute('aria-busy'), 4000);
    });
  }

  /* ---------- Logout ---------- */
  // Clears the HttpOnly session via the backend (must exist: POST /api/auth/logout).
  // Redirects to login regardless of the response so the UI never dead-ends.
  function initLogout() {
    const btn = document.getElementById('logoutBtn');
    if (!btn) return;
    btn.addEventListener('click', async () => {
      btn.setAttribute('aria-busy', 'true');
      try {
        await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });
      } catch (e) {
        /* network/endpoint missing — still leave the dashboard */
      }
      window.location.href = 'index.html';
    });
  }

  /* ---------- Boot ---------- */
  function init() {
    initTheme();
    initSidebar();
    initRefresh();
    initLogout();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
