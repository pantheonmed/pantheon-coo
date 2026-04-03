"""
tools/email.py — Email tool (Phase 3)

Backends:
  smtp   → works with Gmail, Outlook, any SMTP server
  resend → modern transactional email via resend.com API

Configure in .env:
  EMAIL_BACKEND=smtp | resend
  EMAIL_FROM=coo@pantheon.ai
  SMTP_HOST=smtp.gmail.com
  SMTP_PORT=587
  SMTP_USER=you@gmail.com
  SMTP_PASSWORD=your-app-password
  SMTP_FROM=verified-sender@yourdomain.com
  RESEND_API_KEY=re_...

Production send order (async :func:`send_email`):
  1. Gmail-compatible SMTP when ``smtp_user`` and ``smtp_password`` are set
  2. Resend API when ``resend_api_key`` is set
  3. Save message to file under workspace

Supported actions:
  send        → send a plain or HTML email
  send_report → send a formatted COO execution report
"""
import asyncio
import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Any, Optional

import httpx


async def execute(action: str, params: dict[str, Any]) -> Any:
    dispatch = {
        "send":        _send,
        "send_report": _send_report,
        "send_email_real": send_email_real,
    }
    fn = dispatch.get(action)
    if fn is None:
        raise ValueError(f"Unknown email action: '{action}'. Available: {list(dispatch)}")
    return await fn(params)


async def send_email(
    to: str,
    subject: str,
    body: str,
    from_name: str = "Pantheon COO",
) -> dict[str, Any]:
    """
    Try SMTP (Gmail-compatible STARTTLS) → Resend → save to disk.
    """
    from config import settings

    smtp_from = (
        (getattr(settings, "smtp_from", None) or "").strip()
        or (getattr(settings, "email_from", None) or "coo@pantheon.ai").strip()
    )

    user = (getattr(settings, "smtp_user", None) or "").strip()
    password = (getattr(settings, "smtp_password", None) or "").strip()

    if user and password:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{from_name} <{smtp_from}>"
            msg["To"] = to
            msg.attach(MIMEText(body, "plain"))
            html_body = body.replace("\n", "<br>")
            msg.attach(MIMEText(f"<html><body>{html_body}</body></html>", "html"))

            host = getattr(settings, "smtp_host", "smtp.gmail.com")
            port = int(getattr(settings, "smtp_port", 587) or 587)

            def _send_sync() -> None:
                with smtplib.SMTP(host, port) as server:
                    server.ehlo()
                    server.starttls()
                    server.login(user, password)
                    server.send_message(msg)

            await asyncio.get_event_loop().run_in_executor(None, _send_sync)
            return {
                "sent": True,
                "method": "smtp",
                "backend": "smtp",
                "to": to,
                "subject": subject,
            }
        except Exception as e:
            print(f"SMTP failed: {e}")

    api_key = (getattr(settings, "resend_api_key", None) or "").strip()
    if api_key:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "from": f"{from_name} <{smtp_from}>",
                        "to": [to],
                        "subject": subject,
                        "text": body,
                        "html": f"<html><body>{body.replace(chr(10), '<br>')}</body></html>",
                    },
                )
            if 200 <= r.status_code < 300:
                return {
                    "sent": True,
                    "method": "resend",
                    "backend": "resend",
                    "to": to,
                    "subject": subject,
                    "id": r.json().get("id"),
                }
        except Exception as e:
            print(f"Resend failed: {e}")

    base = Path(getattr(settings, "workspace_dir", "/tmp/pantheon_v2") or "/tmp/pantheon_v2") / "emails"
    base.mkdir(parents=True, exist_ok=True)
    filename = base / f"email_{int(time.time())}.txt"
    content = f"TO: {to}\nSUBJECT: {subject}\n\n{body}"
    filename.write_text(content, encoding="utf-8")
    return {
        "sent": False,
        "method": "file_saved",
        "backend": "file_saved",
        "file": str(filename),
        "note": "Email saved (no SMTP / Resend delivery)",
        "to": to,
        "subject": subject,
    }


async def send_email_real(to: str, subject: str, body: str) -> dict:
    """Alias for production pipeline (:func:`send_email`)."""
    return await send_email(to, subject, body, from_name="Pantheon COO")


async def _send(p: dict) -> dict:
    """
    params: { to, subject, body, html? (optional), from? (optional) }
    """
    from config import settings
    cfg = settings

    to: str | list = p["to"]
    subject: str = p["subject"]
    body: str = p.get("body", "")
    html: Optional[str] = p.get("html")
    from_addr: str = p.get("from", getattr(cfg, "email_from", "coo@pantheon.ai"))
    backend: str = getattr(cfg, "email_backend", "smtp")

    if backend == "resend":
        return await _resend(to, subject, body, html, from_addr)
    return await _smtp(to, subject, body, html, from_addr)


async def _send_report(p: dict) -> dict:
    """
    params: { to, task_id, goal, summary, results (list of step results) }
    """
    to = p["to"]
    goal = p.get("goal", "")
    summary = p.get("summary", "")
    task_id = p.get("task_id", "")
    results = p.get("results", [])
    score = p.get("eval_score")

    score_bar = ""
    if score is not None:
        filled = int(score * 20)
        score_bar = f"{'█' * filled}{'░' * (20 - filled)} {score:.2f}"

    rows_html = "".join(
        f"<tr><td style='padding:6px 12px'>{r.get('step_id','')}</td>"
        f"<td style='padding:6px 12px'>{'✅' if r.get('status')=='success' else '❌'} {r.get('status','')}</td>"
        f"<td style='padding:6px 12px;color:#666'>{str(r.get('error') or r.get('result',''))[:80]}</td></tr>"
        for r in results
    )

    html = f"""<html><body style="font-family:sans-serif;max-width:600px;margin:40px auto;color:#1a1a2e">
  <h2 style="color:#7c6ff7">Pantheon COO OS — Execution Report</h2>
  <table style="width:100%;border-collapse:collapse;margin-bottom:20px">
    <tr><td style="padding:6px 0;color:#666">Task ID</td><td>{task_id}</td></tr>
    <tr><td style="padding:6px 0;color:#666">Goal</td><td><b>{goal}</b></td></tr>
    <tr><td style="padding:6px 0;color:#666">Summary</td><td>{summary}</td></tr>
    {'<tr><td style="padding:6px 0;color:#666">Score</td><td><code style="font-family:monospace">' + score_bar + '</code></td></tr>' if score_bar else ''}
  </table>
  <table border="1" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;border:1px solid #e0e0e0">
    <tr style="background:#f0f0ff;font-weight:600">
      <td style="padding:8px 12px">Step</td>
      <td style="padding:8px 12px">Status</td>
      <td style="padding:8px 12px">Output</td>
    </tr>
    {rows_html}
  </table>
  <p style="color:#999;font-size:12px;margin-top:24px">Pantheon COO OS · Autonomous Execution · {task_id[:8]}</p>
</body></html>"""

    return await _send({
        "to": to,
        "subject": f"COO Report: {goal[:60]}",
        "body": summary,
        "html": html,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Backends
# ─────────────────────────────────────────────────────────────────────────────

async def _smtp(to, subject, body, html, from_addr) -> dict:
    from config import settings
    cfg = settings

    host = getattr(cfg, "smtp_host", "smtp.gmail.com")
    port = getattr(cfg, "smtp_port", 587)
    user = getattr(cfg, "smtp_user", "")
    password = getattr(cfg, "smtp_password", "")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to if isinstance(to, str) else ", ".join(to)
    msg.attach(MIMEText(body, "plain"))
    if html:
        msg.attach(MIMEText(html, "html"))

    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _smtp_send_sync, host, port, user, password,
                               from_addr, to, msg)
    return {"sent": True, "to": to, "subject": subject, "backend": "smtp"}


def _smtp_send_sync(host, port, user, password, from_addr, to, msg):
    with smtplib.SMTP(host, port) as server:
        server.ehlo()
        server.starttls()
        if user and password:
            server.login(user, password)
        recipients = [to] if isinstance(to, str) else to
        server.sendmail(from_addr, recipients, msg.as_string())


async def _resend(to, subject, body, html, from_addr) -> dict:
    from config import settings
    api_key = getattr(settings, "resend_api_key", "")
    if not api_key:
        raise ValueError("RESEND_API_KEY not set in .env")

    payload: dict = {
        "from": from_addr,
        "to": [to] if isinstance(to, str) else to,
        "subject": subject,
        "text": body,
    }
    if html:
        payload["html"] = html

    async with httpx.AsyncClient() as c:
        r = await c.post(
            "https://api.resend.com/emails",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        r.raise_for_status()
        return {"sent": True, "to": to, "subject": subject,
                "backend": "resend", "id": r.json().get("id")}
