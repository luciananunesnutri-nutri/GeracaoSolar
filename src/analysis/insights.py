"""
Módulo de geração de insights do sistema solar.
Centraliza a lógica usada tanto pela API web quanto pelo scheduler de emails.
"""
from datetime import date, timedelta, datetime
from ..database.repository import Repository

# Constantes do sistema
TARIFF_BRL   = 0.80    # R$/kWh (média Brasil)
CO2_FACTOR   = 0.5     # kg CO2 evitado por kWh
INSTALLED_KW = 15.95   # kWp instalado


def generate_insights(repository=None) -> dict:
    """
    Gera todos os insights do sistema solar.

    Args:
        repository: instância de Repository (cria uma nova se None)

    Returns:
        Dict com as chaves: status, generated_at, energy, profile,
        inverters, alerts, alerts_unresolved
    """
    if repository is None:
        repository = Repository()

    today     = date.today()
    yesterday = today - timedelta(days=1)

    # ── 1. ENERGY TOTALS ────────────────────────────────────────────────────
    summaries  = repository.get_all_inverter_summaries()
    month_kwh  = 0.0
    year_kwh   = 0.0
    today_kwh  = 0.0
    for rec in (summaries or []):
        for ch in (rec.channels or {}).values():
            month_kwh += float(ch.get('month')   or 0)
            year_kwh  += float(ch.get('year')    or 0)
            today_kwh += float(ch.get('today')   or 0)

    data_today = repository.get_generation_data_for_period(today, today)
    aggregate  = next(
        (d for d in reversed(data_today)
         if d.panel_id is None and d.energy_kwh_total is not None),
        None
    )
    lifetime_kwh = float(aggregate.energy_kwh_total) if aggregate else 0.0

    financial_savings  = round(lifetime_kwh * TARIFF_BRL, 2)
    co2_avoided_kg     = round(lifetime_kwh * CO2_FACTOR, 1)
    co2_avoided_tonnes = round(co2_avoided_kg / 1000, 2)

    # ── 2. TODAY vs YESTERDAY ────────────────────────────────────────────────
    yesterday_summaries = repository.get_all_inverter_summaries_for_date(yesterday)
    yesterday_kwh = 0.0
    for rec in (yesterday_summaries or []):
        for ch in (rec.channels or {}).values():
            yesterday_kwh += float(ch.get('today') or 0)
    day_change_pct = None
    if yesterday_kwh > 0:
        day_change_pct = round(((today_kwh - yesterday_kwh) / yesterday_kwh) * 100, 1)

    # ── 3. GENERATION PROFILE (ECU telemetry minutely) ──────────────────────
    telemetry = repository.get_latest_ecu_telemetry_for_date(today)
    profile   = {}
    if telemetry and telemetry.time_series:
        ts     = telemetry.time_series
        times  = ts.get('time', [])
        powers = [float(p) if p else 0 for p in ts.get('power', [])]

        if times and powers:
            max_power = max(powers)
            peak_idx  = powers.index(max_power)
            peak_time = times[peak_idx] if peak_idx < len(times) else None

            start_time = next(
                (times[i] for i, p in enumerate(powers) if p > 0 and i < len(times)), None
            )
            end_time = next(
                (times[i] for i in range(len(powers)-1, -1, -1)
                 if powers[i] > 0 and i < len(times)), None
            )

            active_points = [p for p in powers if p > 0]
            avg_active    = sum(active_points) / len(active_points) if active_points else 0
            cap_factor    = round((avg_active / (INSTALLED_KW * 1000)) * 100, 1) if avg_active > 0 else 0
            peak_pct      = round((max_power / (INSTALLED_KW * 1000)) * 100, 1)

            duration_min = None
            if start_time and end_time:
                def _minutes(t):
                    h, m = map(int, t.split(':'))
                    return h * 60 + m
                duration_min = _minutes(end_time) - _minutes(start_time)

            profile = {
                'start_time':          start_time,
                'peak_time':           peak_time,
                'peak_power_w':        round(max_power),
                'peak_power_pct':      peak_pct,
                'end_time':            end_time,
                'avg_active_power_w':  round(avg_active),
                'capacity_factor_pct': cap_factor,
                'duration_minutes':    duration_min,
                'data_points':         len(times),
            }

    # ── 4. INVERTER PERFORMANCE ──────────────────────────────────────────────
    batch = repository.get_latest_inverter_batch_for_date(today)
    inv_avg_power = {}
    if batch and batch.power_data:
        uid_pts = {}
        for ch_key, values in batch.power_data.get('power', {}).items():
            uid = ch_key.rsplit('-', 1)[0]
            uid_pts.setdefault(uid, []).extend(
                float(v) for v in values if v is not None and float(v) > 0
            )
        for uid, pts in uid_pts.items():
            inv_avg_power[uid] = round(sum(pts) / len(pts), 1) if pts else 0

    inverters_analysis = []
    for rec in sorted(summaries or [], key=lambda r: r.inverter_uid):
        uid      = rec.inverter_uid
        channels = rec.channels or {}

        today_inv = sum(float(ch.get('today')    or 0) for ch in channels.values())
        month_inv = sum(float(ch.get('month')    or 0) for ch in channels.values())
        year_inv  = sum(float(ch.get('year')     or 0) for ch in channels.values())
        life_inv  = sum(float(ch.get('lifetime') or 0) for ch in channels.values())

        ch_today = {int(k): float(v.get('today') or 0) for k, v in channels.items()}

        active_chs   = {k: v for k, v in ch_today.items() if v > 0}
        asymmetry_pct = None
        if len(active_chs) >= 2:
            mn, mx = min(active_chs.values()), max(active_chs.values())
            if mx > 0:
                asymmetry_pct = round(((mx - mn) / mx) * 100, 1)

        series = uid[:3] if uid else 'N/A'
        inverters_analysis.append({
            'uid':           uid,
            'series':        series,
            'today_kwh':     round(today_inv, 3),
            'month_kwh':     round(month_inv, 2),
            'year_kwh':      round(year_inv, 2),
            'lifetime_kwh':  round(life_inv, 2),
            'avg_power_w':   inv_avg_power.get(uid, 0),
            'channels':      ch_today,
            'asymmetry_pct': asymmetry_pct,
        })

    # Ranking por série
    by_series = {}
    for inv in inverters_analysis:
        by_series.setdefault(inv['series'], []).append(inv)
    for series_list in by_series.values():
        ranked   = sorted(series_list, key=lambda x: x['today_kwh'], reverse=True)
        best_kwh = ranked[0]['today_kwh'] if ranked else 1.0
        for i, inv in enumerate(ranked):
            inv['rank_in_series'] = i + 1
            inv['pct_of_best']    = round((inv['today_kwh'] / best_kwh) * 100, 1) if best_kwh > 0 else 0

    # Ranking geral
    inverters_sorted = sorted(inverters_analysis, key=lambda x: x['today_kwh'], reverse=True)
    for i, inv in enumerate(inverters_sorted):
        inv['rank_overall'] = i + 1

    # ── 5. ALERTS TODAY ──────────────────────────────────────────────────────
    todays_alerts = repository.get_todays_alerts(unresolved_only=False)
    alerts_summary = [
        {
            'id':       a.id,
            'type':     a.alert_type.value,
            'severity': a.severity.value,
            'message':  a.message,
            'resolved': a.resolved,
            'time':     a.timestamp.strftime('%H:%M'),
        }
        for a in todays_alerts
    ]
    unresolved_count = sum(1 for a in alerts_summary if not a['resolved'])

    return {
        'status':            'success',
        'generated_at':      datetime.now().isoformat(),
        'energy': {
            'today_kwh':             round(today_kwh, 2),
            'yesterday_kwh':         round(yesterday_kwh, 2),
            'day_change_pct':        day_change_pct,
            'month_kwh':             round(month_kwh, 2),
            'year_kwh':              round(year_kwh, 2),
            'lifetime_kwh':          round(lifetime_kwh, 2),
            'financial_savings_brl': financial_savings,
            'co2_avoided_kg':        co2_avoided_kg,
            'co2_avoided_tonnes':    co2_avoided_tonnes,
            'installed_kw':          INSTALLED_KW,
        },
        'profile':           profile,
        'inverters':         inverters_sorted,
        'alerts':            alerts_summary,
        'alerts_unresolved': unresolved_count,
    }
