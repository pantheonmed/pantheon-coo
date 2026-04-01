"""
security/self_protector.py
──────────────────────────
SelfProtector — continuous security monitoring + automated response.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import memory.store as store
from config import settings


class SelfProtector:
    """COO monitors and protects itself."""

    def __init__(self) -> None:
        self.threat_threshold = 10
        self.monitoring_active = True

    async def monitor_continuously(self) -> None:
        """Run forever — check every 60 seconds."""
        while self.monitoring_active:
            try:
                await self.check_threats()
            except Exception:
                pass
            await asyncio.sleep(60)

    async def check_threats(self) -> None:
        threats: list[dict] = []

        failed_logins = await store.count_security_events("FAILED_LOGIN", minutes=10)
        if failed_logins > 20:
            threats.append({"type": "BRUTE_FORCE", "severity": "high", "action": "block_suspicious_ips"})

        api_calls = await store.count_api_calls(minutes=5)
        if api_calls > 500:
            threats.append({"type": "DDOS_ATTEMPT", "severity": "critical", "action": "enable_strict_mode"})

        injection_attempts = await store.count_security_events("INJECTION_BLOCKED", minutes=5)
        if injection_attempts > 5:
            threats.append({"type": "INJECTION_ATTACK", "severity": "high", "action": "block_attacker_ip"})

        api_cost_estimate = await self.estimate_api_cost_usd()
        if api_cost_estimate > float(getattr(settings, "daily_cost_limit_usd", 50.0) or 50.0):
            threats.append({"type": "COST_ANOMALY", "severity": "high", "action": "pause_execution"})

        for t in threats:
            await self.handle_threat(t)

    async def estimate_api_cost_usd(self) -> float:
        # Conservative placeholder: real cost tracking would require per-call token accounting.
        return 0.0

    async def handle_threat(self, threat: dict) -> None:
        action = threat.get("action", "")
        severity = threat.get("severity", "medium")

        await store.log_security_event(threat.get("type", "THREAT"), "system", str(threat), severity=severity)

        if action == "block_suspicious_ips":
            ips = await store.get_suspicious_ips()
            for ip in ips:
                await store.add_blocked_ip(ip, hours=24, reason="BRUTE_FORCE")

        elif action == "enable_strict_mode":
            settings.strict_mode = True
            await self.notify_admin("🚨 DDoS detected! Strict mode ON")

        elif action == "block_attacker_ip":
            attacker_ip = await store.get_top_attacker_ip()
            if attacker_ip:
                await store.add_blocked_ip(attacker_ip, hours=48, reason="INJECTION_ATTACK")

        elif action == "pause_execution":
            settings.execution_paused = True
            await self.notify_admin("⚠️ Execution paused! Cost anomaly detected")

        if severity == "critical":
            await self.emergency_alert(threat)

    async def notify_admin(self, message: str) -> None:
        try:
            from whatsapp import send as wa_send

            if (settings.admin_whatsapp_number or "").strip():
                await wa_send(
                    settings.admin_whatsapp_number,
                    f"🔐 Security Alert\n{message}\nTime: {datetime.utcnow().isoformat()}",
                )
        except Exception:
            pass

    async def emergency_alert(self, threat: dict) -> None:
        await self.notify_admin(f"🚨🚨 CRITICAL THREAT!\n{threat}")
        # Email channel optional; do not hard-fail if not configured.
        try:
            from notifications import send_email

            if (settings.admin_email or "").strip():
                await send_email(
                    settings.admin_email,
                    "CRITICAL: Pantheon COO Security Alert",
                    str(threat),
                )
        except Exception:
            pass

