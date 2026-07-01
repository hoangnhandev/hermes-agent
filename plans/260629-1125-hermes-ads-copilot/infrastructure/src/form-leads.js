// GET /api/form-leads — CRM list of form submissions from the
// mua-vinfast.com landing page (vinfast_leads table).
//
// Privacy: this endpoint is served to the authenticated dashboard. We expose
// only the columns the CRM view needs by SELECTing an explicit whitelist —
// `ip`, `user_agent`, and any future `idempotency_key` are structurally never
// returned (defense-in-depth, not just deletion after the fact).
//
// Response shape (mirrors leads.js conventions):
//   {
//     leads:    [ { id, created_at, ho_ten, sdt, dong_xe, loi_nhan,
//                    source, gclid, fbclid, utm_source, utm_medium,
//                    utm_campaign, status } ],
//     total:    <number>,           // count of returned (filtered) leads
//     by_status:{ new, contacted, closed, spam }  // across ALL rows
//   }
//
// Query params:
//   ?status=new|contacted|closed|spam  (optional filter on returned leads)

const ALLOWED_STATUSES = ['new', 'contacted', 'closed', 'spam'];

// Columns returned to the client. Anything NOT in this list stays private.
const SELECT_COLUMNS = `
  id,
  ho_ten,
  sdt,
  dong_xe,
  loi_nhan,
  source,
  gclid,
  fbclid,
  utm_source,
  utm_medium,
  utm_campaign,
  status,
  created_at
`;

export async function handleFormLeads(request, env) {
  try {
    const url = new URL(request.url);
    const statusFilter = url.searchParams.get('status');

    // Validate optional ?status against a whitelist — never interpolate raw
    // user input. Binds below are still parameterised; this just gives a
    // clean 400 instead of an empty result for junk values.
    if (statusFilter != null && !ALLOWED_STATUSES.includes(statusFilter)) {
      return new Response(
        JSON.stringify({
          error: 'Invalid status. Must be one of: ' + ALLOWED_STATUSES.join(', '),
        }),
        { status: 400, headers: { 'Content-Type': 'application/json' } }
      );
    }

    // --- Returned leads (LIMIT 100, newest first) ---
    let query = 'SELECT ' + SELECT_COLUMNS + ' FROM vinfast_leads';
    const params = [];
    if (statusFilter) {
      query += ' WHERE status = ?';
      params.push(statusFilter);
    }
    query += ' ORDER BY created_at DESC LIMIT 100';

    const leadsResult = await env.DB.prepare(query).bind(...params).all();
    const leads = leadsResult.results || [];

    // --- Status totals across ALL rows (unfiltered, for KPI row) ---
    // GROUP BY is cheaper than 4 separate COUNT(*) queries and keeps the
    // totals consistent regardless of the ?status filter above.
    const statusRows = await env.DB.prepare(
      "SELECT status, COUNT(*) AS n FROM vinfast_leads GROUP BY status"
    ).all();
    const by_status = { new: 0, contacted: 0, closed: 0, spam: 0 };
    (statusRows.results || []).forEach((row) => {
      if (ALLOWED_STATUSES.includes(row.status)) {
        by_status[row.status] = row.n;
      }
    });
    const totalAll =
      by_status.new + by_status.contacted + by_status.closed + by_status.spam;

    return new Response(
      JSON.stringify({
        leads,
        total: statusFilter ? leads.length : totalAll,
        by_status,
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } }
    );
  } catch (error) {
    console.error('Form-leads error:', error);
    return new Response(
      JSON.stringify({ error: 'Internal Server Error' }),
      { status: 500, headers: { 'Content-Type': 'application/json' } }
    );
  }
}
