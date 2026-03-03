"""
Módulo de geração de insights do sistema solar.
Centraliza a lógica usada tanto pela API web quanto pelo scheduler de emails.
"""
from datetime import date, timedelta, datetime
from calendar import monthrange
from pathlib import Path
import yaml
from ..database.repository import Repository

# Constantes do sistema
CO2_FACTOR   = 0.5     # kg CO2 evitado por kWh
INSTALLED_KW = 15.95   # kWp instalado

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "config.yaml"


def _load_tariff() -> float:
    """Lê a tarifa R$/kWh do config.yaml; retorna 0.80 como fallback."""
    try:
        with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f)
        return float(cfg.get('system', {}).get('tariff_brl', 0.80))
    except Exception:
        return 0.80

MONTH_NAMES = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']


# ── Helpers privados ─────────────────────────────────────────────────────────

def _daily_kwh_from_gen_data(rows, start: date, end: date) -> dict:
    """Extrai kWh diário dos dados de geração.

    Filtra panel_id IS NULL, pega MAX(energy_kwh_daily) por dia.
    Retorna 0.0 para dias sem dados dentro do intervalo [start, end].
    """
    daily_max = {}
    cur = start
    while cur <= end:
        daily_max[cur] = 0.0
        cur += timedelta(days=1)

    for row in rows:
        if row.panel_id is not None:
            continue
        if row.energy_kwh_daily is None:
            continue
        d = row.timestamp.date()
        if start <= d <= end:
            v = float(row.energy_kwh_daily)
            if v > daily_max.get(d, 0.0):
                daily_max[d] = v

    return daily_max


def _hourly_kwh_from_gen_data(rows, start: date, end: date) -> dict:
    """Extrai kWh por hora dos dados de geração (panel_id == 'hourly').

    Retorna: {date: {hour(int): kwh(float)}}
    """
    result = {}
    for row in rows:
        if row.panel_id != 'hourly':
            continue
        if row.energy_kwh_daily is None:
            continue
        d = row.timestamp.date()
        if start <= d <= end:
            h = row.timestamp.hour
            result.setdefault(d, {})
            result[d][h] = result[d].get(h, 0.0) + float(row.energy_kwh_daily)
    return result


def _minutes(t: str) -> int:
    """Converte 'HH:MM' em minutos totais."""
    h, m = map(int, t.split(':'))
    return h * 60 + m


# ── Função principal ─────────────────────────────────────────────────────────

def generate_insights(repository=None, target_date=None) -> dict:
    """
    Gera todos os insights do sistema solar.

    Args:
        repository:  instância de Repository (cria uma nova se None)
        target_date: data alvo (date); se None, usa hoje

    Returns:
        Dict com todas as chaves de insights (retrocompatível — nenhuma chave removida)
    """
    if repository is None:
        repository = Repository()

    today       = date.today()
    target_date = target_date or today
    is_today    = (target_date == today)
    yesterday   = target_date - timedelta(days=1)

    # ── 0. HISTÓRICO 6 MESES (query única reutilizada por todas as features) ─
    six_m_month = target_date.month - 6
    six_m_year  = target_date.year
    if six_m_month <= 0:
        six_m_month += 12
        six_m_year  -= 1
    six_m_start  = date(six_m_year, six_m_month, 1)
    history_data = repository.get_generation_data_for_period(six_m_start, target_date)

    # ── 1. ENERGY TOTALS ────────────────────────────────────────────────────
    if is_today:
        summaries = repository.get_all_inverter_summaries()
    else:
        summaries = repository.get_all_inverter_summaries_for_date(target_date)

    month_kwh = 0.0
    year_kwh  = 0.0
    today_kwh = 0.0
    for rec in (summaries or []):
        for ch in (rec.channels or {}).values():
            month_kwh += float(ch.get('month') or 0)
            year_kwh  += float(ch.get('year')  or 0)
            today_kwh += float(ch.get('today') or 0)

    # Para datas históricas sem summaries com dados de mês, calcular do histórico
    if not is_today and month_kwh == 0.0:
        month_start_hist = date(target_date.year, target_date.month, 1)
        computed = sum(
            _daily_kwh_from_gen_data(history_data, month_start_hist, target_date).values()
        )
        if computed > 0:
            month_kwh = computed

    data_today = repository.get_generation_data_for_period(target_date, target_date)
    aggregate  = next(
        (d for d in reversed(data_today)
         if d.panel_id is None and d.energy_kwh_total is not None),
        None
    )
    lifetime_kwh = float(aggregate.energy_kwh_total) if aggregate else 0.0

    tariff_brl         = _load_tariff()
    financial_savings  = round(lifetime_kwh * tariff_brl, 2)
    co2_avoided_kg     = round(lifetime_kwh * CO2_FACTOR, 1)
    co2_avoided_tonnes = round(co2_avoided_kg / 1000, 2)

    # ── 2. TODAY vs YESTERDAY ────────────────────────────────────────────────
    yesterday_summaries = repository.get_all_inverter_summaries_for_date(yesterday)
    yesterday_kwh = 0.0
    for rec in (yesterday_summaries or []):
        for ch in (rec.channels or {}).values():
            yesterday_kwh += float(ch.get('today') or 0)

    # Fallback: se banco não tem dados de ontem, buscar da API (daily energy)
    if yesterday_kwh == 0.0:
        try:
            from ..api.apsystems_openapi_client import APSystemsOpenAPIClient
            import os
            _cred_path = Path(__file__).parent.parent.parent / "config" / "credentials.yaml"
            try:
                with open(_cred_path, 'r', encoding='utf-8') as _f:
                    _creds = yaml.safe_load(_f) or {}
            except FileNotFoundError:
                _creds = {}
            _ap = _creds.get('apsystems', {})
            _app_id = os.environ.get('APSYSTEMS_APP_ID') or _ap.get('app_id') or ''
            _app_secret = os.environ.get('APSYSTEMS_APP_SECRET') or _ap.get('app_secret') or ''
            _sid = os.environ.get('APSYSTEMS_SID') or _ap.get('sid') or ''

            if _app_id and _app_secret and _sid:
                client = APSystemsOpenAPIClient(_app_id, _app_secret, _sid)
                # get_system_energy('daily', 'YYYY-MM') retorna lista de kWh por dia
                month_str = yesterday.strftime('%Y-%m')
                daily_list = client.get_system_energy('daily', month_str)
                if daily_list and len(daily_list) >= yesterday.day:
                    yesterday_kwh = float(daily_list[yesterday.day - 1] or 0)
        except Exception as _e:
            from ..utils.logger import logger
            logger.warning(f"Fallback API para yesterday_kwh falhou: {_e}")

    day_change_pct = None
    if yesterday_kwh > 0:
        day_change_pct = round(((today_kwh - yesterday_kwh) / yesterday_kwh) * 100, 1)

    # ── 3. GENERATION PROFILE (ECU telemetry minutely) ──────────────────────
    telemetry = repository.get_latest_ecu_telemetry_for_date(target_date)
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

            # ── Feature 6: Janela Eficiente ─────────────────────────────────
            threshold = max_power * 0.50
            eff_idx   = [i for i, p in enumerate(powers) if p >= threshold]
            if eff_idx and start_time and end_time:
                eff_start = times[eff_idx[0]]  if eff_idx[0]  < len(times) else None
                eff_end   = times[eff_idx[-1]] if eff_idx[-1] < len(times) else None
                if eff_start and eff_end:
                    eff_dur = _minutes(eff_end) - _minutes(eff_start)
                    profile['efficient_window'] = {
                        'start_time':       eff_start,
                        'end_time':         eff_end,
                        'duration_minutes': eff_dur,
                        'label': (
                            f'{eff_start} – {eff_end} '
                            f'({eff_dur // 60}h{eff_dur % 60:02d}min)'
                        ),
                    }

    # ── 4. INVERTER PERFORMANCE ──────────────────────────────────────────────
    batch = repository.get_latest_inverter_batch_for_date(target_date)
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

        active_chs    = {k: v for k, v in ch_today.items() if v > 0}
        asymmetry_pct = None
        if len(active_chs) >= 2:
            mn, mx = min(active_chs.values()), max(active_chs.values())
            if mx > 0:
                asymmetry_pct = round(((mx - mn) / mx) * 100, 1)

        zero_channels = sum(1 for v in ch_today.values() if v == 0)
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
            'zero_channels': zero_channels,
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

    # ── 5. ALERTS ────────────────────────────────────────────────────────────
    if is_today:
        todays_alerts = repository.get_todays_alerts(unresolved_only=False)
    else:
        all_recent    = repository.get_recent_alerts(limit=500, unresolved_only=False)
        todays_alerts = [a for a in all_recent if a.timestamp.date() == target_date]

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

    # ── Feature 1: Health Score ───────────────────────────────────────────────
    cap_factor_val = profile.get('capacity_factor_pct', 0) if profile else 0
    total_inv      = len(inverters_sorted)
    good_inv_count = sum(1 for inv in inverters_sorted if inv.get('pct_of_best', 0) >= 85)
    worst_asym     = max(
        (inv['asymmetry_pct'] for inv in inverters_sorted if inv.get('asymmetry_pct') is not None),
        default=0
    )

    score_capacity  = min(cap_factor_val / 100, 1.0) * 40
    score_inverters = (good_inv_count / total_inv * 30) if total_inv > 0 else 0
    score_alerts    = 20 if unresolved_count == 0 else 0
    score_asym      = max(0.0, 1.0 - worst_asym / 25.0) * 10
    health_score    = round(score_capacity + score_inverters + score_alerts + score_asym, 1)

    if health_score >= 85:
        health_grade, health_color = 'Excelente', 'success'
    elif health_score >= 70:
        health_grade, health_color = 'Bom', 'info'
    elif health_score >= 50:
        health_grade, health_color = 'Regular', 'warning'
    else:
        health_grade, health_color = 'Crítico', 'danger'

    health = {
        'score': health_score,
        'grade': health_grade,
        'color': health_color,
        'components': {
            'capacity':  round(score_capacity, 1),
            'inverters': round(score_inverters, 1),
            'alerts':    score_alerts,
            'asymmetry': round(score_asym, 1),
        },
    }

    # ── Feature 2: Histórico 7 Dias ───────────────────────────────────────────
    h7_start  = target_date - timedelta(days=6)
    daily_map = _daily_kwh_from_gen_data(history_data, h7_start, target_date)
    history_7d = [
        {'date': str(d), 'kwh': round(v, 2)}
        for d, v in sorted(daily_map.items())
    ]

    # ── Feature 3: Projeção do Mês ────────────────────────────────────────────
    days_in_month = monthrange(target_date.year, target_date.month)[1]
    elapsed_days  = target_date.day
    month_so_far  = month_kwh  # já corrigido acima para ambos os casos

    if elapsed_days > 0 and month_so_far > 0:
        daily_avg = month_so_far / elapsed_days
        projected = round(daily_avg * days_in_month, 2)
        prog_pct  = round((month_so_far / projected) * 100, 1) if projected > 0 else 0.0
    else:
        daily_avg = 0.0
        projected = 0.0
        prog_pct  = 0.0

    month_projection = {
        'actual_kwh':    round(month_so_far, 2),
        'projected_kwh': projected,
        'progress_pct':  prog_pct,
        'elapsed_days':  elapsed_days,
        'days_in_month': days_in_month,
        'daily_avg_kwh': round(daily_avg, 2),
    }

    # ── Feature 5: Comparativo Mensal ─────────────────────────────────────────
    pm_month = target_date.month - 1
    pm_year  = target_date.year
    if pm_month == 0:
        pm_month = 12
        pm_year -= 1
    pm_start = date(pm_year, pm_month, 1)
    pm_end   = date(pm_year, pm_month, monthrange(pm_year, pm_month)[1])
    pm_kwh   = round(sum(_daily_kwh_from_gen_data(history_data, pm_start, pm_end).values()), 2)
    cur_kwh  = round(month_so_far, 2)

    if pm_kwh > 0:
        change_pct = round(((cur_kwh - pm_kwh) / pm_kwh) * 100, 1)
    else:
        change_pct = None

    monthly_comparison = {
        'current_month_kwh': cur_kwh,
        'prev_month_kwh':    pm_kwh,
        'change_pct':        change_pct,
        'current_label':     f"{MONTH_NAMES[target_date.month - 1]}/{target_date.year}",
        'prev_label':        f"{MONTH_NAMES[pm_month - 1]}/{pm_year}",
    }

    # ── Feature 4: Inversores em Atenção ─────────────────────────────────────
    inverters_attention = [
        {
            'uid':           inv['uid'],
            'series':        inv['series'],
            'pct_of_best':   inv.get('pct_of_best', 0),
            'today_kwh':     inv['today_kwh'],
            'zero_channels': inv['zero_channels'],
            'rank_overall':  inv['rank_overall'],
        }
        for inv in inverters_sorted
        if inv.get('pct_of_best', 100) < 75
    ]

    # ── Feature 8: Contribuição por Inversor ──────────────────────────────────
    total_today = sum(inv['today_kwh'] for inv in inverters_sorted)
    inverter_contribution = [
        {
            'uid':       inv['uid'],
            'series':    inv['series'],
            'today_kwh': inv['today_kwh'],
            'pct_total': round((inv['today_kwh'] / total_today) * 100, 1) if total_today > 0 else 0.0,
        }
        for inv in inverters_sorted[:15]
    ]

    # ── Feature 9: Comparativo Horário 14 Dias ────────────────────────────────
    h14_start  = target_date - timedelta(days=14)
    h14_end    = target_date - timedelta(days=1)
    hourly_14d = _hourly_kwh_from_gen_data(history_data, h14_start, h14_end)

    hour_sums  = {h: 0.0 for h in range(24)}
    hour_count = {h: 0   for h in range(24)}
    for day_data in hourly_14d.values():
        for h, kwh in day_data.items():
            if kwh > 0:
                hour_sums[h]  += kwh
                hour_count[h] += 1
    hour_avg = {
        h: round(hour_sums[h] / hour_count[h], 3) if hour_count[h] > 0 else 0.0
        for h in range(24)
    }

    today_hourly_data = _hourly_kwh_from_gen_data(data_today, target_date, target_date)
    today_hours = today_hourly_data.get(target_date, {})

    HOUR_RANGE = list(range(5, 22))
    hourly_comparison = {
        'labels':  [f'{h:02d}:00' for h in HOUR_RANGE],
        'avg_14d': [hour_avg[h] for h in HOUR_RANGE],
        'today':   [round(today_hours.get(h, 0.0), 3) for h in HOUR_RANGE],
    }

    # ── Feature 10: Economia 6 Meses ──────────────────────────────────────────
    savings_history_6m = []
    for i in range(5, -1, -1):
        m_month = target_date.month - i
        m_year  = target_date.year
        while m_month <= 0:
            m_month += 12
            m_year  -= 1
        m_start = date(m_year, m_month, 1)
        m_end   = date(m_year, m_month, monthrange(m_year, m_month)[1])
        m_kwh   = round(sum(_daily_kwh_from_gen_data(history_data, m_start, m_end).values()), 2)
        savings_history_6m.append({
            'label': f"{MONTH_NAMES[m_month - 1]}/{m_year}",
            'kwh':   m_kwh,
            'brl':   round(m_kwh * tariff_brl, 2),
        })

    # ── RETORNO ───────────────────────────────────────────────────────────────
    return {
        'status':       'success',
        'generated_at': datetime.now().isoformat(),
        'target_date':  str(target_date),
        'is_today':     is_today,
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
            'tariff_brl':            tariff_brl,
        },
        'profile':               profile,
        'inverters':             inverters_sorted,
        'alerts':                alerts_summary,
        'alerts_unresolved':     unresolved_count,
        'health':                health,
        'history_7d':            history_7d,
        'month_projection':      month_projection,
        'inverters_attention':   inverters_attention,
        'monthly_comparison':    monthly_comparison,
        'inverter_contribution': inverter_contribution,
        'hourly_comparison':     hourly_comparison,
        'savings_history_6m':    savings_history_6m,
    }
