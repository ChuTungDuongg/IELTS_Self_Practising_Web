"""Small private local-file review artifact. No server, CDN, telemetry or editing framework."""

import base64
import hashlib
from html import escape
from urllib.parse import quote

from app.evaluation.speaking.replay_cache import private_write

SCRIPT = """
const tracks = [...document.querySelectorAll('audio')];
for (const track of tracks) {
  track.addEventListener('play', () => tracks.forEach(other => { if (other !== track) other.pause(); }));
  track.addEventListener('timeupdate', () => {
    const end = Number(track.dataset.stop);
    if (track.dataset.stop && track.currentTime >= end) { track.pause(); delete track.dataset.stop; }
  });
}
for (const button of document.querySelectorAll('button[data-audio]')) {
  button.addEventListener('click', () => {
    const track = document.getElementById(button.dataset.audio);
    tracks.forEach(other => other.pause());
    track.dataset.stop = button.dataset.end;
    track.currentTime = Number(button.dataset.start);
    track.play().catch(() => { document.getElementById('status').textContent = 'Use the local audio controls to play.'; });
  });
}
"""


def write_local_review(root, results, proposal, *, part_boundaries=None):
    script_hash = base64.b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()
    csp = (
        "default-src 'none'; connect-src 'none'; media-src 'self' file:; "
        f"script-src 'sha256-{script_hash}'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
    )
    sections, source_ids = [], {}
    for index, result in enumerate(results):
        audio_id = f"audio-{index}"
        source_ids[result.source] = audio_id
        rows = []
        for speaker in sorted({t.speaker_id for t in result.regular}):
            role = proposal.roles[result.source][speaker]
            confirmed = role.get("candidate_confirmed", False)
            color = (
                "candidate"
                if confirmed
                else "suggested"
                if role["suggested_role"] == "candidate"
                else "other"
            )
            bars = "".join(
                f'<span class="turn {color}" style="left:{t.start_ms * 100 / result.duration_ms:.4f}%;'
                f'width:{(t.end_ms - t.start_ms) * 100 / result.duration_ms:.4f}%" '
                f'title="{t.start_ms}..{t.end_ms}ms"></span>'
                for t in result.regular
                if t.speaker_id == speaker
            )
            markers = "".join(
                f'<span class="part-marker" style="left:{boundary * 100 / result.duration_ms:.4f}%">P{index + 2}</span>'
                for index, boundary in enumerate((part_boundaries or {}).get(result.source, ()))
            )
            rows.append(
                f"<div><strong>{escape(speaker)}</strong> — suggested {escape(role['suggested_role'])}"
                f"; candidate identity confirmed: {confirmed}"
                f'<div class="timeline" aria-label="Speaker timeline">{bars}{markers}</div></div>'
            )
        sections.append(
            f"<section><h2>Source {index + 1} · {result.duration_ms / 1000:.1f}s</h2>"
            f"<p>Model: {escape(str(result.identity.get('model', 'unknown')))}; "
            f"revision: {escape(str(result.identity.get('revision', 'unknown')))}. Speaker hypotheses need review.</p>"
            f'<audio id="{audio_id}" controls preload="none" src="{escape(quote(result.source), quote=True)}"></audio>'
            + "".join(rows)
            + "</section>"
        )
    rows = []
    for item in proposal.segments:
        label = "Selected proposal" if item.selected else "Excluded / other speaker"
        blocked = "OTHER_SPEAKER_OVERLAP" in item.flags
        rows.append(
            f'<tr class="{"blocked" if blocked else ""}"><td>{escape(item.id)}<br>{escape(item.speaker_id)}</td>'
            f'<td>{item.start_ms}–{item.end_ms} ms<br><button type="button" data-audio="{source_ids[item.source]}" '
            f'data-start="{item.start_ms / 1000:.3f}" data-end="{item.end_ms / 1000:.3f}">Listen to window</button></td>'
            f"<td>{label}<br>Part: {item.part_number or 'unknown'}</td>"
            f"<td>{escape(item.prompt_text) if item.prompt_text else 'Question unknown'}"
            f"<br>Question verified: {item.prompt_verified}</td><td>{escape(', '.join(item.flags))}</td></tr>"
        )
    document = f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{escape(csp, quote=True)}">
<title>Private speaking segment review</title>
<style>
body {{font: 16px/1.5 system-ui,sans-serif;max-width:1200px;margin:2rem auto;padding:0 1rem;color:#172033;background:#f8fafc}}
section {{background:white;border:1px solid #cbd5e1;padding:1rem;margin:1rem 0;border-radius:.5rem}}
audio {{width:100%;margin-bottom:1rem}} .timeline {{height:1rem;background:#e2e8f0;position:relative;margin:.3rem 0 1rem}}
.turn {{position:absolute;height:100%;background:#2563eb}} table {{width:100%;border-collapse:collapse;background:white}}
.turn.candidate {{background:#15803d}} .turn.suggested {{background:#b45309}}
.part-marker {{position:absolute;top:-.3rem;border-left:2px dashed #172033;height:1.6rem;font-size:.65rem}}
th,td {{padding:.75rem;border:1px solid #cbd5e1;text-align:left;vertical-align:top;overflow-wrap:anywhere}}
.blocked {{background:#fff1f2}} button {{font:inherit;padding:.35rem .7rem;cursor:pointer}}
button:focus-visible {{outline:3px solid #2563eb;outline-offset:2px}}
.scroll {{overflow:auto}} @media(max-width:600px) {{table {{min-width:760px}}}}
</style><h1>Private speaking segment review</h1>
<p>Local files only. No uploads or external connections. Speaker roles are suggestions.
Role verification: <strong>{proposal.role_verification}</strong>; boundaries and candidate-only content still require final approval.</p>
<p id="status" role="status">Use each speaker track and answer window to check identities, overlap, preparation and boundaries.
Red rows contain known other-speaker overlap and cannot be approved unchanged.</p>
<p>Green: confirmed candidate identity. Amber: heuristic candidate suggestion. Blue: other/unknown.
Confirmation does not prove every interval is clean. Part markers appear only after operator confirmation.</p>
{"".join(sections)}<h2>Response proposals</h2><div class="scroll"><table>
<thead><tr><th>Segment / speaker</th><th>Source window</th><th>Selection / Part</th><th>Question context</th><th>Review flags</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>
<p>Make corrections with the replay CLI. Confirm the candidate, two Part transitions and real questions,
then explicitly run --approve-segments. This report does not approve or grade audio.</p>
<script>{SCRIPT}</script></html>'''
    private_write(root / "review.local.html", document)
