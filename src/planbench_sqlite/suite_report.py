"""Script-free suite ledger with per-case evidence embedded in one document."""
from .report import CSS, _e, _track, difference_section
from .suite import suite_status


def render_suite_html(report):
    cases = report.get('cases', [])
    state = suite_status(cases)
    headings = {'equivalent': 'Every comparison matches.', 'different': 'A regression needs attention.', 'inconclusive': 'The suite needs a closer look.'}
    ledger, cards = [], []
    for index, item in enumerate(cases):
        anchor = 'case-' + str(index)
        ledger.append('<tr><td><a href="#' + anchor + '">' + _e(item.get('id')) + '</a></td><td>' + _e(item.get('case')) + '</td><td>' + _e(item.get('status')) + '</td><td>' + _e(item.get('execution')) + '</td></tr>')
        detail = '<p class="error">' + _e(item['error']) + '</p>' if item.get('error') else ''
        single = item.get('report')
        if single:
            detail += '<p class="muted">' + _e(single.get('equality', {}).get('reason')) + '</p>'
            detail += difference_section(single)
            detail += '<div class="tracks">' + _track('Baseline', single.get('baseline', {})) + _track('Candidate', single.get('candidate', {})) + '</div>'
            detail += '<p class="muted">Effective per-phase time budget: ' + _e(single.get('limits', {}).get('timeout_seconds')) + ' seconds. Snapshot: ' + _e(single.get('source', {}).get('database')) + '.</p>'
        cards.append('<details class="case-detail" id="' + anchor + '"><summary>' + _e(item.get('id')) + ' — ' + _e(item.get('status')) + '</summary>' + detail + '</details>')
    counts = {key: sum(item.get('status') == key for item in cases) for key in ('equivalent', 'different', 'inconclusive')}
    summary = ' · '.join(_e(value) + ' ' + key for key, value in counts.items())
    notes = ''.join('<li>' + _e(note) + '</li>' for note in report.get('notes', []))
    return '<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'"><title>' + _e(report.get('title')) + ' · PlanBench suite</title><style>' + CSS + '</style></head><body><a class="skip" href="#main">Skip to results</a><header><a href="#main">PLANBENCH / Suite</a><span>INDEPENDENT SNAPSHOTS / COMPLETE CASE LEDGER</span></header><main id="main"><div class="eyebrow">' + _e(report.get('title')) + '</div><h1>' + headings[state] + '</h1><span class="status ' + state + '">' + state + '</span><p>' + summary + '</p><p class="muted">Every case has a result — including invalid, timed-out and unrun cases. Each case owns its own snapshot; the suite is not one common database snapshot.</p><h2>Case ledger</h2><div class="table-scroll"><table class="suite-ledger"><thead><tr><th scope="col">Case</th><th scope="col">Input</th><th scope="col">Outcome</th><th scope="col">Execution</th></tr></thead><tbody>' + ''.join(ledger) + '</tbody></table></div><h2 style="margin-top:32px">Inspect the evidence</h2>' + ''.join(cards) + '<section class="evidence"><h2>Scope and limits</h2><p class="muted">Run budget: ' + _e(report.get('timeout_seconds')) + ' seconds, cooperative. SQLite ' + _e(report.get('environment', {}).get('sqlite')) + '. PlanBench ' + _e(report.get('environment', {}).get('tool_version')) + '.</p><ul class="muted">' + notes + '</ul></section></main><footer>Offline evidence only. Values and bound parameters omitted; SQL literals and identifiers remain visible.</footer></body></html>\n'
