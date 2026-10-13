"""Readable report. No server or JavaScript dependency."""
import html
import json
from pathlib import Path


def save_report(result: dict, destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    (destination / 'trace.json').write_text(encoded + '\n', encoding='utf-8')
    events = ''.join(
        '<details><summary>' + html.escape(f"{e['seq']:02d} · {e['agent']} · {e['kind']}") +
        '</summary><pre>' + html.escape(json.dumps(e['data'], ensure_ascii=False, indent=2)) +
        '</pre></details>' for e in result['trace'])
    sessions = (result.get('plan') or {}).get('sessions')
    if not isinstance(sessions, list):
        sessions = []
    rows = ''.join('<tr>' + ''.join('<td>' + html.escape(str(s.get(k, ''))) + '</td>'
                    for k in ['day', 'topic', 'minutes', 'source_id']) + '</tr>'
                   for s in sessions if isinstance(s, dict))
    document = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Study assistant trace</title>
<style>body{font:18px/1.5 system-ui;max-width:1040px;margin:40px auto;padding:0 24px;color:#14273b;background:#f5f7fb}
h1{font-size:38px}header,section{background:white;border-radius:16px;padding:24px;margin-bottom:18px}
.mode{background:#ffefbf;padding:12px;border-radius:8px}table{border-collapse:collapse;width:100%}
td,th{text-align:left;border-bottom:1px solid #dce4ed;padding:10px}details{padding:12px;border-bottom:1px solid #dce4ed}
summary{cursor:pointer;font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px}
</style><header><h1>Study assistant</h1><p class="mode">''' + html.escape(result['mode']) + '''</p>
<p>Status: <strong>''' + html.escape(result['status']) + '''</strong> · Revisions: ''' + str(result['revisions']) + '''</p>
</header><section><h2>Study schedule</h2><table><tr><th>Day</th><th>Topic</th><th>Minutes</th><th>Source</th></tr>''' + rows + '''</table>
<p>''' + html.escape(result.get('message', '')) + '''</p></section><section><h2>Prompts, tool calls and results</h2>''' + events + '</section></html>'
    (destination / 'report.html').write_text(document, encoding='utf-8')
