/* ============================================================
   login.js — password login + show/hide toggle.
   If a valid session already exists, skip straight to dashboard.
   ============================================================ */

const form = document.getElementById('loginForm');
const errorDiv = document.getElementById('errorMessage');
const loginBtn = document.getElementById('loginBtn');
const passwordInput = document.getElementById('password');
const passwordToggle = document.getElementById('passwordToggle');

// Skip the login screen entirely if the session cookie is still valid.
(async () => {
  try {
    const res = await fetch('/api/auth/verify', { credentials: 'include' });
    if (res.ok) window.location.href = 'dashboard.html';
  } catch (e) {
    /* offline / verify unavailable — stay on login */
  }
})();

// Show / hide password.
passwordToggle.addEventListener('click', () => {
  const show = passwordInput.type === 'password';
  passwordInput.type = show ? 'text' : 'password';
  passwordToggle.setAttribute('aria-pressed', String(show));
  passwordToggle.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
  const slot = passwordToggle.querySelector('[data-icon]');
  if (slot) {
    slot.setAttribute('data-icon', show ? 'eye-off' : 'eye');
    slot.innerHTML = icon(show ? 'eye-off' : 'eye', { size: 20 });
  }
});

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const password = form.password.value;

  errorDiv.textContent = '';
  loginBtn.setAttribute('aria-busy', 'true');

  try {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ password }),
    });

    if (response.ok) {
      window.location.href = 'dashboard.html';
    } else {
      const error = await response.json().catch(() => ({}));
      errorDiv.textContent = error.message || 'Login failed. Please try again.';
    }
  } catch (error) {
    errorDiv.textContent = 'Connection error. Please try again.';
  } finally {
    loginBtn.removeAttribute('aria-busy');
  }
});
