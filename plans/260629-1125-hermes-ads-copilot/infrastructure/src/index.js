// Router for all API endpoints
import { verifyAuth } from './auth.js';
import { handleSync } from './sync.js';
import { handleMetrics } from './metrics.js';
import { handleLeads } from './leads.js';
import { handleFormLeads } from './form-leads.js';
import { handleKeywords } from './keywords.js';
import { handleBudget } from './budget.js';
import { handleAnomalies } from './anomalies.js';

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const { pathname } = url;

    // Routes that don't require authentication
    if (pathname === '/api/auth/login' && request.method === 'POST') {
      const { handleLogin } = await import('./auth.js');
      return handleLogin(request, env);
    }

    if (pathname === '/api/auth/refresh' && request.method === 'POST') {
      const { handleRefresh } = await import('./auth.js');
      return handleRefresh(request, env);
    }

    // Logout: clear the HttpOnly session cookie. Public route (idempotent).
    if (pathname === '/api/auth/logout' && request.method === 'POST') {
      const { handleLogout } = await import('./auth.js');
      return handleLogout(request, env);
    }

    // Cookie verification for the SPA auth gate.
    // The dashboard cookie (jwt_token) is HttpOnly, so the browser cannot read
    // it from JS — the client must ask the server whether it is authenticated.
    if (pathname === '/api/auth/verify' && request.method === 'GET') {
      const result = await verifyAuth(request, env);
      return new Response(
        JSON.stringify({ authenticated: result.authenticated }),
        {
          status: result.authenticated ? 200 : 401,
          headers: { 'Content-Type': 'application/json' }
        }
      );
    }

    // Machine-to-machine sync: authenticates via X-Hermes-Secret header
    // (checked inside handleSync), NOT the dashboard cookie. MUST bypass
    // verifyAuth — otherwise every sync gets 401'd at the cookie gate before
    // the secret is ever read, and the monitor→D1 pipeline never works.
    if (pathname === '/api/sync' && request.method === 'POST') {
      return handleSync(request, env);
    }

    // Apply auth middleware to all other routes
    const authResult = await verifyAuth(request, env);
    if (!authResult.authenticated) {
      return new Response(JSON.stringify({ error: 'Unauthorized' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' }
      });
    }

    // Route authenticated requests
    try {
      switch (pathname) {
        case '/api/sync':
          if (request.method === 'POST') {
            return handleSync(request, env);
          }
          break;

        case '/api/metrics':
          if (request.method === 'GET') {
            return handleMetrics(request, env);
          }
          break;

        case '/api/leads':
          if (request.method === 'GET') {
            return handleLeads(request, env);
          }
          break;

        // CRM list of form submissions (vinfast_leads). Same auth model as
        // /api/leads — behind verifyAuth because it exposes PII (phone/name)
        // to an authenticated dashboard only.
        case '/api/form-leads':
          if (request.method === 'GET') {
            return handleFormLeads(request, env);
          }
          break;

        case '/api/keywords':
          if (request.method === 'GET') {
            return handleKeywords(request, env);
          }
          break;

        case '/api/budget':
          if (request.method === 'GET') {
            return handleBudget(request, env);
          }
          break;

        // Anomaly feed for the dashboard panel (wire 5). Behind verifyAuth like
        // the other dashboard reads — anomalies expose no PII but aren't public.
        case '/api/anomalies':
          if (request.method === 'GET') {
            return handleAnomalies(request, env);
          }
          break;

        default:
          return new Response(JSON.stringify({ error: 'Not Found' }), {
            status: 404,
            headers: { 'Content-Type': 'application/json' }
          });
      }
    } catch (error) {
      console.error('API Error:', error);
      return new Response(JSON.stringify({ error: 'Internal Server Error' }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' }
      });
    }

    return new Response(JSON.stringify({ error: 'Method Not Allowed' }), {
      status: 405,
      headers: { 'Content-Type': 'application/json' }
    });
  }
};