// JWT authentication using Web Crypto API (no external dependencies)
const JWT_HEADER = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
const TOKEN_EXPIRY_MS = 24 * 60 * 60 * 1000; // 24 hours

// Create JWT using Web Crypto API
async function createJWT(payload, secret) {
  const encoder = new TextEncoder();
  const keyData = encoder.encode(secret);

  const key = await crypto.subtle.importKey(
    'raw',
    keyData,
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );

  const header = JWT_HEADER;
  const payloadStr = btoa(JSON.stringify(payload));
  const message = encoder.encode(`${header}.${payloadStr}`);

  const signature = await crypto.subtle.sign('HMAC', key, message);
  const signatureStr = btoa(String.fromCharCode(...new Uint8Array(signature)));

  return `${header}.${payloadStr}.${signatureStr}`;
}

// Verify JWT using Web Crypto API
async function verifyJWT(token, secret) {
  try {
    const [header, payload, signature] = token.split('.');

    const encoder = new TextEncoder();
    const keyData = encoder.encode(secret);

    const key = await crypto.subtle.importKey(
      'raw',
      keyData,
      { name: 'HMAC', hash: 'SHA-256' },
      false,
      ['verify']
    );

    const message = encoder.encode(`${header}.${payload}`);
    const signatureData = Uint8Array.from(atob(signature), c => c.charCodeAt(0));

    const isValid = await crypto.subtle.verify('HMAC', key, signatureData, message);

    if (!isValid) {
      return null;
    }

    const payloadObj = JSON.parse(atob(payload));

    // Check expiration
    if (payloadObj.exp && payloadObj.exp * 1000 < Date.now()) {
      return null;
    }

    return payloadObj;
  } catch (error) {
    console.error('JWT verification error:', error);
    return null;
  }
}

// Middleware to verify authentication
export async function verifyAuth(request, env) {
  const cookieHeader = request.headers.get('cookie') || '';
  const cookies = cookieHeader.split(';').reduce((acc, cookie) => {
    // Split on the FIRST '=' only: JWT values are base64 and may contain
    // '=' padding (and '+'/'/'), which split('=') would truncate.
    const eqIdx = cookie.indexOf('=');
    if (eqIdx === -1) return acc;
    const key = cookie.slice(0, eqIdx).trim();
    acc[key] = cookie.slice(eqIdx + 1).trim();
    return acc;
  }, {});

  const jwtToken = cookies.jwt_token;

  if (!jwtToken) {
    return { authenticated: false };
  }

  const payload = await verifyJWT(jwtToken, env.JWT_SECRET);

  if (!payload) {
    return { authenticated: false };
  }

  return { authenticated: true, user: payload };
}

// Login handler
export async function handleLogin(request, env) {
  try {
    const { password } = await request.json();

    if (!password || password !== env.DASHBOARD_PASSWORD) {
      return new Response(JSON.stringify({ error: 'Invalid credentials' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' }
      });
    }

    const payload = {
      sub: 'dashboard-user',
      iat: Math.floor(Date.now() / 1000),
      exp: Math.floor((Date.now() + TOKEN_EXPIRY_MS) / 1000)
    };

    const token = await createJWT(payload, env.JWT_SECRET);

    return new Response(JSON.stringify({ success: true }), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Set-Cookie': `jwt_token=${token}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=${TOKEN_EXPIRY_MS / 1000}`
      }
    });
  } catch (error) {
    console.error('Login error:', error);
    return new Response(JSON.stringify({ error: 'Internal Server Error' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

// Refresh token handler
export async function handleRefresh(request, env) {
  const authResult = await verifyAuth(request, env);

  if (!authResult.authenticated) {
    return new Response(JSON.stringify({ error: 'Unauthorized' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' }
    });
  }

  const payload = {
    sub: 'dashboard-user',
    iat: Math.floor(Date.now() / 1000),
    exp: Math.floor((Date.now() + TOKEN_EXPIRY_MS) / 1000)
  };

  const token = await createJWT(payload, env.JWT_SECRET);

  return new Response(JSON.stringify({ success: true }), {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      'Set-Cookie': `jwt_token=${token}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=${TOKEN_EXPIRY_MS / 1000}`
    }
  });
}

// Logout handler — clears the HttpOnly session cookie.
// Client JS cannot delete an HttpOnly cookie, so the server MUST issue an
// expired Set-Cookie. Idempotent: succeeds whether or not a cookie exists.
export async function handleLogout() {
  return new Response(JSON.stringify({ success: true }), {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      // Max-Age=0 + past Expires → browser deletes the cookie immediately.
      'Set-Cookie': 'jwt_token=; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT'
    }
  });
}