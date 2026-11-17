"""Pure, escaped, offline HTML reports. No JavaScript or external resources."""

from html import escape
import math

CSS = """
:root{color-scheme:light;--ink:#152e4b;--muted:#56677b;--paper:#f0f3f8;--line:#ced8e4;--green:#22634e;--red:#9f3941;--amber:#805515}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.6 'Segoe UI',system-ui,sans-serif}
a{color:inherit}a:focus-visible,summary:focus-visible{outline:3px solid #316bc5;outline-offset:5px}.skip{position:absolute;top:-80px;padding:12px;background:white}.skip:focus{top:8px;z-index:5}
header{border-bottom:1px solid var(--line);padding:19px 5vw;background:#fff;display:flex;gap:20px;justify-content:space-between;align-items:center}header a{text-decoration:none;font-weight:650;letter-spacing:.025em}.brand-mark{display:inline-block;width:22px;height:22px;border:3px solid var(--ink);border-left-width:8px;vertical-align:-4px;margin-right:10px}header span{font-size:12px;color:var(--muted)}
main{max-width:1240px;margin:auto;padding:50px 36px 64px}.eyebrow{text-transform:uppercase;font-size:11px;letter-spacing:.15em;font-weight:700;color:var(--muted)}h1,h2,h3{font-family:'Bahnschrift','Segoe UI',sans-serif;font-weight:600;line-height:1.15}h1{font-size:clamp(32px,4.5vw,60px);letter-spacing:-.035em;margin:16px 0 20px;max-width:900px}h2{font-size:25px;margin:0 0 14px}h3{font-size:18px;margin:0}.intro{max-width:810px}.intro p{color:var(--muted);margin:8px 0 20px}.status{display:inline-flex;align-items:center;gap:9px;border:1px solid currentColor;padding:4px 10px;border-radius:3px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.07em}.status:before{content:'';width:7px;height:7px;border-radius:50%;background:currentColor}.equivalent{color:var(--green)}.different{color:var(--red)}.inconclusive{color:var(--amber)}
.context{display:flex;flex-wrap:wrap;gap:10px 26px;margin:28px 0 36px;font-size:13px;color:var(--muted)}.context strong{color:var(--ink);font-weight:600}.tracks{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:24px}.track{background:#fff;border:1px solid var(--line);border-radius:7px;overflow:hidden;min-width:0}.track-head{background:var(--ink);color:#fff;padding:18px 24px;display:flex;justify-content:space-between;align-items:center;gap:12px}.track-head small{font:12px ui-monospace,Consolas,monospace;color:#d4e1ef}.track-body{padding:24px}.stage{position:relative;padding:0 0 22px 23px;border-left:1px solid var(--line)}.stage:last-child{padding-bottom:0;border-left-color:transparent}.stage:before{content:'';position:absolute;width:9px;height:9px;left:-5px;top:5px;background:var(--ink);border:2px solid #fff;outline:1px solid var(--line)}.stage-label{font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;margin:0 0 9px;color:var(--muted)}
pre,code{font-family:ui-monospace,'Cascadia Code',Consolas,monospace;font-size:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f7fb;border:1px solid #e1e7ef;border-radius:4px;padding:14px;margin:0;line-height:1.7}.plan{list-style:none;padding:0;margin:0}.plan li{padding:9px 10px;margin:6px 0;background:#f4f7fb;border-left:3px solid #6990b5;overflow-wrap:anywhere}.plan small{display:block;font-size:10px;color:var(--muted)}.plan code{font-weight:600}.metrics{display:grid;grid-template-columns:1fr 1fr;gap:17px}.metric{min-width:0}.metric strong{font-family:'Bahnschrift','Segoe UI',sans-serif;font-size:28px;font-weight:500;font-variant-numeric:tabular-nums}.metric span{display:block;font-size:11px;color:var(--muted)}.muted{color:var(--muted);font-size:13px}.error{background:#fff1eb;color:#822e28;border-left:3px solid #ad5540;padding:12px;overflow-wrap:anywhere;font-size:13px}.hash{overflow-wrap:anywhere;font-size:11px;color:var(--muted)}details{margin-top:14px}summary{cursor:pointer;color:var(--muted);font-size:12px;padding:5px 0}details pre{margin-top:8px}
.verdict{display:grid;grid-template-columns:1fr 2fr;gap:35px;border-top:2px solid var(--ink);border-bottom:1px solid var(--line);padding:28px 0;margin:34px 0}.verdict p{margin:0;color:var(--muted);font-size:14px}.verdict strong{display:block;font-size:18px;color:var(--ink);margin-bottom:8px}.footgrid{display:grid;grid-template-columns:1fr 1.3fr;gap:50px}.footgrid h2{font-size:20px}.footgrid p,.footgrid li{font-size:13px;color:var(--muted)}.footgrid ul{padding-left:18px;margin:0}.footgrid li{margin-bottom:9px}dl{font-size:12px;margin:0}dl div{display:flex;gap:16px;justify-content:space-between;border-bottom:1px solid var(--line);padding:9px 0}dt{color:var(--muted);overflow-wrap:anywhere}dd{margin:0;font-family:ui-monospace,Consolas,monospace}footer{max-width:1240px;padding:24px 36px;margin:auto;border-top:1px solid var(--line);font-size:12px;color:var(--muted)}
@media(max-width:760px){header{padding:16px 20px}header span{display:none}main{padding:30px 20px}.tracks,.verdict,.footgrid{grid-template-columns:1fr}.track-head,.track-body{padding:18px}.context{gap:7px 17px}.verdict{gap:12px}.footgrid{gap:28px}.metrics{gap:13px}footer{padding:20px}.stage{padding-left:17px}}
@media print{body{background:white}header{padding:8px 0}main{padding:20px 0}.track{break-inside:avoid}.track-head{background:#eee;color:#152e4b}.track-head small{color:#152e4b}.footgrid{gap:25px}footer{padding:10px 0}details{display:block}.skip{display:none}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
"""


def _e(value):
    return escape('Not available' if value is None else str(value), quote=True)


def _number(value, decimal=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        return 'Not available'
    return f'{value:,.4f}' if decimal else f'{value:,}'


def _plan(nodes):
    if not nodes:
        return '<p class="muted">No plan captured.</p>'
    parents = {node.get('id'): node.get('parent') for node in nodes}
    items = []
    for node in nodes:
        seen, depth = {node.get('id')}, 0
        parent = node.get('parent')
        while parent in parents and parent not in seen and depth < 8:
            seen.add(parent)
            depth += 1
            parent = parents[parent]
        items.append('<li style="margin-left:' + str(depth * 10) + 'px"><code>' + _e(node.get('detail')) + '</code><small>node ' + _e(node.get('id')) + ' / parent ' + _e(node.get('parent')) + ' / auxiliary ' + _e(node.get('auxiliary')) + '</small></li>')
    return '<ol class="plan">' + ''.join(items) + '</ol>'


def _track(name, arm):
    error = '<p class="error">' + _e(arm['error']) + '</p>' if arm.get('error') else ''
    definitions = arm.get('index_definitions') or []
    indexes = '<details><summary>Candidate index definitions</summary><pre>' + _e('\n'.join(definitions)) + '</pre></details>' if definitions else '<p class="muted">No additional indexes.</p>'
    metrics = [('Returned rows', arm.get('row_count'), False), ('Progress callbacks', arm.get('progress_calls'), False),
               ('Encoded bytes', arm.get('result_bytes'), False), ('Instrumented seconds', arm.get('elapsed_seconds'), True)]
    boxes = ''.join('<div class="metric"><strong>' + _e(_number(value, decimal)) + '</strong><span>' + label + '</span></div>' for label, value, decimal in metrics)
    partial = '<p class="muted">Incomplete run: counters below may be partial; no equality evidence.</p>' if arm.get('status') != 'complete' else ''
    return '<section class="track" aria-label="' + name + '"><div class="track-head"><h2 style="margin:0;font-size:21px">' + name + '</h2><small>' + _e(arm.get('status')) + '</small></div><div class="track-body">' + error + '<div class="stage"><p class="stage-label">Query input</p><pre>' + _e(arm.get('sql')) + '</pre>' + indexes + '</div><div class="stage"><p class="stage-label">SQLite execution plan</p>' + _plan(arm.get('plan', [])) + '</div><div class="stage"><p class="stage-label">Observed output</p>' + partial + '<div class="metrics">' + boxes + '</div><details><summary>Result schema and fingerprint</summary><p class="muted">Columns: ' + _e(', '.join(arm.get('columns', []))) + '</p><p class="hash">SHA-256: ' + _e(arm.get('result_sha256')) + '</p><p class="muted">The fingerprint is diagnostic. Equality uses exact typed rows, not hashes.</p></details></div></div></section>'


def render_html(report: dict) -> str:
    """Render the public report dict as one offline, script-free document."""
    equality = report.get('equality', {})
    completed = all(report.get(key, {}).get('status') == 'complete' for key in ('baseline', 'candidate'))
    state = 'inconclusive'
    if completed and equality.get('comparable') is True:
        if report.get('status') == 'equivalent' and equality.get('equivalent') is True:
            state = 'equivalent'
        elif report.get('status') == 'different' and equality.get('equivalent') is False:
            state = 'different'
    headings = {'equivalent': 'Same rows. Different route.', 'different': 'The results differ.', 'inconclusive': 'Comparison not established.'}
    reasons = equality.get('reason') or 'No conclusion was established. Inspect the evidence below.'
    if state == 'inconclusive' and report.get('status') != 'inconclusive':
        reasons = 'The report state is inconsistent; no conclusion can be established.'
    mode = report.get('comparison', 'unknown')
    description = 'Exact typed row sequence, including duplicates and column names.' if mode == 'ordered' else 'Exact typed row multiplicities and column names; row order is ignored.'
    ratio = equality.get('progress_ratio') if state == 'equivalent' else None
    ratio_text = ('Candidate / baseline callbacks: ' + _number(ratio, True)) if ratio is not None else 'No comparable callback ratio.'
    limits = ''.join('<div><dt>' + _e(k.replace('_', ' ')) + '</dt><dd>' + _e(v) + '</dd></div>' for k, v in report.get('limits', {}).items())
    notes = ''.join('<li>' + _e(note) + '</li>' for note in report.get('notes', []))
    env, source = report.get('environment', {}), report.get('source', {})
    return '<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'"><title>' + _e(report.get('title', 'PlanBench experiment')) + ' · PlanBench SQLite</title><style>' + CSS + '</style></head><body><a class="skip" href="#main">Skip to results</a><header><a href="#main"><span class="brand-mark" aria-hidden="true"></span>PLANBENCH <small> / SQLite</small></a><span>LOCAL EXPERIMENT / OFFLINE EVIDENCE</span></header><main id="main"><div class="intro"><div class="eyebrow">' + _e(report.get('title')) + '</div><h1>' + headings[state] + '</h1><span class="status ' + state + '">' + state + '</span><p>' + _e(reasons) + '</p></div><div class="context"><span>Database <strong>' + _e(source.get('database')) + '</strong></span><span>SQLite <strong>' + _e(env.get('sqlite')) + '</strong></span><span>Python <strong>' + _e(env.get('python')) + '</strong></span><span>Comparison <strong>' + _e(mode) + '</strong></span><span>Snapshot <strong>' + _e(_number(source.get('snapshot_bytes'))) + ' B</strong></span></div><div class="tracks">' + _track('Baseline', report.get('baseline', {})) + _track('Candidate', report.get('candidate', {})) + '</div><section class="verdict"><h2>What this establishes</h2><div><strong>' + _e(description) + '</strong><p>Only for this database snapshot and these parameters. This is not a proof of SQL equivalence for all data.</p><p style="margin-top:12px">' + _e(ratio_text) + ' <b>Not a speedup.</b> Progress callbacks are instrumented observations, not exact VM instructions. Timings include that instrumentation.</p></div></section><div class="footgrid"><section><h2>Experiment limits</h2><dl>' + limits + '</dl><p>Limits are cooperative, not hard process isolation. A native SQLite operation can delay cancellation.</p></section><section><h2>Read before sharing</h2><ul>' + notes + '</ul></section></div></main><footer>PlanBench SQLite · No network requests. No result rows or parameter values embedded. SQL literals and identifiers remain visible.</footer></body></html>\n'
