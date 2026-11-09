// Readable Telegram HTML for a Komodo alert. Upstream dumps the alert's data as JSON under
// parse_mode=Markdown, which Telegram rejects whenever a field holds an unpaired "_" or "*".
const LEVEL = { CRITICAL: '🔴', ERROR: '🚨', WARNING: '⚠️', INFO: 'ℹ️', OK: '✅' };
const LIMIT = 3900; // sendMessage caps at 4096 characters

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const num = (n) => (Number.isInteger(n) ? String(n) : n.toFixed(1));

function value(v) {
  if (typeof v === 'number') return num(v);
  if (Array.isArray(v)) return v.map(value).join(', ');
  if (v && typeof v === 'object') return v.error ? [v.error, ...(v.trace || [])].join(' | ') : JSON.stringify(v);
  return String(v);
}

function details(data) {
  const lines = [];
  const rest = { ...data };
  if (rest.from !== undefined && rest.to !== undefined) {
    lines.push(`状态: ${rest.from} → ${rest.to}`);
    delete rest.from;
    delete rest.to;
  }
  if (typeof rest.used_gb === 'number' && typeof rest.total_gb === 'number') {
    lines.push(`用量: ${num(rest.used_gb)} / ${num(rest.total_gb)} GB (${Math.round((rest.used_gb / rest.total_gb) * 100)}%)`);
    delete rest.used_gb;
    delete rest.total_gb;
  }
  for (const [k, v] of Object.entries(rest)) {
    // ids mean nothing in a chat; the resource names are already there
    if (k === 'id' || k === 'name' || k.endsWith('_id') || v === null || v === undefined || v === '') continue;
    lines.push(`${k}: ${value(v)}`);
  }
  return lines;
}

export function formatAlert(alert) {
  const level = String(alert.level || 'Unknown').toUpperCase();
  const type = alert.data?.type || 'Unknown';
  const data = alert.data?.data || {};
  const target = alert.target?.type || '';
  const when = alert.ts
    ? new Date(alert.ts).toLocaleString('zh-CN', { hour12: false, timeZone: process.env.TZ || 'Asia/Shanghai' })
    : '';
  // `resolved` alone means "closed", not "fixed": one-shot events (ProcedureFailed, StackStateChange, Test...) are
  // filed closed from the start, with resolved_ts = ts. Only a closed stateful alert has a later resolved_ts.
  const recovered = alert.resolved && level === 'OK' && alert.resolved_ts > alert.ts;
  const head = `${LEVEL[level] || 'ℹ️'} <b>${esc(level)} · ${esc(type)}</b>${recovered ? '  ✅ 已恢复' : ''}`;
  const who = `<b>${esc(data.name || 'Unnamed')}</b>${target ? ` (${esc(target)})` : ''}`;
  const body = esc([...details(data), when].filter(Boolean).join('\n'));
  const text = `${head}\n${who}\n${body}`;
  // cut only inside the escaped body so a tag is never left open; half an entity or half a surrogate pair
  // would make Telegram reject the whole message
  return text.length > LIMIT ? `${text.slice(0, LIMIT).replace(/[\uD800-\uDBFF]$/, '').replace(/&[a-z]*$/, '')}…` : text;
}
