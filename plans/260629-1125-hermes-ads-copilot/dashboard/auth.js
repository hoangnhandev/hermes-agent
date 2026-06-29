// Client-side auth helpers.
//
// The dashboard session cookie (jwt_token) is HttpOnly + Secure, so it is NOT
// readable via document.cookie by design (see infra/src/auth.js). Authentication
// therefore MUST be verified by asking the server, never by reading the cookie
// in JS. Reading document.cookie here silently returns null and logs the user
// out immediately after login.

// Ask the server whether the current HttpOnly session cookie is valid.
async function checkAuth() {
    try {
        const response = await fetch('/api/auth/verify', {
            method: 'GET',
            credentials: 'include'
        });
        return response.ok;
    } catch (error) {
        return false;
    }
}

// Attempt a token refresh. Returns true on success (page reloads), false when the
// session cannot be refreshed (caller redirects to login). The boolean return is
// required by fetchWithAuth (utils.js) to decide whether to retry the request.
async function refreshAndRedirect() {
    try {
        const response = await fetch('/api/auth/refresh', {
            method: 'POST',
            credentials: 'include'
        });

        if (response.ok) {
            window.location.reload();
            return true;
        }

        window.location.href = 'index.html';
        return false;
    } catch (error) {
        window.location.href = 'index.html';
        return false;
    }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { checkAuth, refreshAndRedirect };
}
