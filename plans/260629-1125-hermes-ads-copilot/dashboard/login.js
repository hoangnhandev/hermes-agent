document.getElementById('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const form = e.target;
    const password = form.password.value;
    const errorDiv = document.getElementById('errorMessage');

    errorDiv.textContent = '';
    errorDiv.classList.remove('show');

    try {
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'include',
            body: JSON.stringify({ password }),
        });

        if (response.ok) {
            window.location.href = 'dashboard.html';
        } else {
            const error = await response.json();
            errorDiv.textContent = error.message || 'Login failed';
            errorDiv.classList.add('show');
        }
    } catch (error) {
        errorDiv.textContent = 'Connection error. Please try again.';
        errorDiv.classList.add('show');
    }
});