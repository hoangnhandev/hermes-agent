// /api/anomalies — recent anomalies for the dashboard panel (wire 5).
// Returns newest-first rows from the D1 `anomalies` table (synced from the
// local anomaly_log via sync_to_d1). Read-only; same auth model as /api/metrics.
export async function handleAnomalies(request, env) {
  try {
    const url = new URL(request.url);
    const limit = Math.min(parseInt(url.searchParams.get('limit') || '50', 10), 200);

    const result = await env.DB.prepare(`
      SELECT detected_at, anomaly_type, entity_id, entity_name,
             metric_name, current_value, baseline_value, change_pct
      FROM anomalies
      ORDER BY detected_at DESC
      LIMIT ?
    `).bind(limit).all();

    return new Response(JSON.stringify({ anomalies: result.results || [] }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    });

  } catch (error) {
    console.error('Anomalies error:', error);
    return new Response(JSON.stringify({ error: 'Internal Server Error' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}
