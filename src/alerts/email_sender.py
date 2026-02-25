import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict
import yaml
from pathlib import Path
from ..utils.logger import logger


class EmailSender:
    """Gerenciador de envio de emails."""

    def __init__(self):
        # Carregar credenciais
        cred_path = Path(__file__).parent.parent.parent / "config" / "credentials.yaml"
        with open(cred_path, 'r', encoding='utf-8') as f:
            credentials = yaml.safe_load(f)

        self.email_config = credentials['email']
        self.smtp_host = self.email_config['smtp_host']
        self.smtp_port = self.email_config['smtp_port']
        self.sender_email = self.email_config['sender_email']
        self.sender_password = self.email_config['sender_password']
        self.recipient_email = self.email_config['recipient_email']

    def _get_recipients(self, alerts_only: bool = False, reports_only: bool = False) -> list:
        """Retorna lista de emails dos destinatários ativos no banco.
        Fallback para recipient_email do credentials.yaml se banco vazio."""
        try:
            from ..database.repository import Repository
            repo = Repository()
            records = repo.get_active_recipients(alerts_only=alerts_only, reports_only=reports_only)
            if records:
                return [r.email for r in records]
        except Exception as e:
            logger.warning(f"Erro ao buscar destinatários do banco: {e}")
        # Fallback: destinatário do credentials.yaml
        if self.recipient_email and self.recipient_email != 'email_destino@gmail.com':
            return [self.recipient_email]
        return []

    def send_email(self, subject: str, body: str, html: bool = True,
                   recipients: list = None) -> bool:
        """Envia email para a lista de destinatários informada ou para todos os ativos no banco."""
        if recipients is None:
            recipients = self._get_recipients()

        if not recipients:
            logger.warning("Nenhum destinatário configurado — email não enviado")
            return False

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)

                for to_email in recipients:
                    msg = MIMEMultipart('alternative')
                    msg['Subject'] = subject
                    msg['From'] = self.sender_email
                    msg['To'] = to_email
                    msg.attach(MIMEText(body, 'html' if html else 'plain'))
                    server.send_message(msg)
                    logger.info(f"Email enviado para {to_email}: {subject}")

            return True

        except Exception as e:
            logger.error(f"Erro ao enviar email: {e}")
            return False

    def send_alert_email(self, alert: Dict) -> bool:
        """
        Envia email de alerta.

        Args:
            alert: Dicionário com dados do alerta

        Returns:
            True se enviado com sucesso
        """
        alert_type = alert.get('alert_type', 'unknown')
        severity = alert.get('severity', 'info')
        message = alert.get('message', 'Sem descrição')
        details = alert.get('details', {})

        # Definir emoji de severidade
        severity_emoji = {
            'info': 'ℹ️',
            'warning': '⚠️',
            'critical': '🚨'
        }
        emoji = severity_emoji.get(severity, '📋')

        # Criar assunto
        subject = f"{emoji} Alerta Solar - {severity.upper()}: {alert_type}"

        # Criar corpo HTML
        body = self._create_alert_html(alert_type, severity, message, details)

        recipients = self._get_recipients(alerts_only=True)
        return self.send_email(subject, body, html=True, recipients=recipients)

    def send_daily_report_email(self, stats: Dict, alerts: list = None,
                                insights: dict = None) -> bool:
        """
        Envia email com relatório diário, incluindo alertas e insights se disponíveis.

        Args:
            stats:    Dicionário com estatísticas do dia
            alerts:   Lista de dicionários de alerta (opcional)
            insights: Dict gerado por generate_insights() (opcional)

        Returns:
            True se enviado com sucesso
        """
        subject = f"📊 Relatório Solar Diário - {stats['date']}"
        if alerts:
            subject += f" ⚠️ {len(alerts)} alerta(s)"
        body = self._create_daily_report_html(stats, alerts or [], insights)
        recipients = self._get_recipients(reports_only=True)
        return self.send_email(subject, body, html=True, recipients=recipients)

    def _create_alert_html(self, alert_type: str, severity: str, message: str, details: Dict) -> str:
        """
        Cria HTML para email de alerta.

        Args:
            alert_type: Tipo do alerta
            severity: Severidade
            message: Mensagem do alerta
            details: Detalhes adicionais

        Returns:
            HTML do email
        """
        severity_colors = {
            'info': '#17a2b8',
            'warning': '#ffc107',
            'critical': '#dc3545'
        }
        color = severity_colors.get(severity, '#6c757d')

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: {color}; color: white; padding: 20px; border-radius: 5px 5px 0 0; }}
                .content {{ background-color: #f8f9fa; padding: 20px; border-radius: 0 0 5px 5px; }}
                .detail-item {{ margin: 10px 0; padding: 10px; background-color: white; border-left: 3px solid {color}; }}
                .footer {{ margin-top: 20px; padding-top: 20px; border-top: 1px solid #dee2e6; font-size: 12px; color: #6c757d; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>Alerta do Sistema Solar</h2>
                    <p><strong>Tipo:</strong> {alert_type.upper()}</p>
                    <p><strong>Severidade:</strong> {severity.upper()}</p>
                </div>
                <div class="content">
                    <h3>Mensagem:</h3>
                    <p>{message}</p>

                    <h3>Detalhes:</h3>
        """

        for key, value in details.items():
            html += f'<div class="detail-item"><strong>{key}:</strong> {value}</div>'

        html += f"""
                    <div class="footer">
                        <p>Gerado automaticamente em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                        <p>Sistema de Monitoramento Solar</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """

        return html

    def send_evening_summary_email(self, data: Dict, alerts: list = None,
                                   insights: dict = None) -> bool:
        """Envia resumo do dia às 17:00, incluindo alertas e insights se disponíveis."""
        subject = f"☀️ Resumo Solar — {data['date']}"
        if alerts:
            subject += f" ⚠️ {len(alerts)} alerta(s)"
        body = self._create_evening_summary_html(data, alerts or [], insights)
        recipients = self._get_recipients(reports_only=True)
        return self.send_email(subject, body, html=True, recipients=recipients)

    def _build_insights_html_block(self, insights: dict) -> str:
        """Cria bloco HTML com as seções de insights para incluir nos emails programados."""
        if not insights or insights.get('status') != 'success':
            return ''

        energy  = insights.get('energy', {})
        profile = insights.get('profile', {})
        invs    = insights.get('inverters', [])

        sections = []

        # ── Perfil de Geração ─────────────────────────────────────────────────
        if profile:
            dur = profile.get('duration_minutes')
            dur_txt = f"{dur // 60}h{dur % 60:02d}min" if dur else '—'
            sections.append(f"""
      <div style="margin-top:20px;border-top:2px solid #f39c12;padding-top:16px">
        <p style="margin:0 0 10px;font-weight:bold;color:#f39c12">☀️ Perfil de Geração do Dia</p>
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <tbody>
            <tr>
              <td style="padding:5px 10px;border-bottom:1px solid #dee2e6;color:#6c757d;width:50%">Início da geração</td>
              <td style="padding:5px 10px;border-bottom:1px solid #dee2e6;font-weight:600">{profile.get('start_time','—')}</td>
              <td style="padding:5px 10px;border-bottom:1px solid #dee2e6;color:#6c757d;width:50%">Fim da geração</td>
              <td style="padding:5px 10px;border-bottom:1px solid #dee2e6;font-weight:600">{profile.get('end_time','—')}</td>
            </tr>
            <tr>
              <td style="padding:5px 10px;border-bottom:1px solid #dee2e6;color:#6c757d">Horário do pico</td>
              <td style="padding:5px 10px;border-bottom:1px solid #dee2e6;font-weight:600">{profile.get('peak_time','—')}</td>
              <td style="padding:5px 10px;border-bottom:1px solid #dee2e6;color:#6c757d">Pico de potência</td>
              <td style="padding:5px 10px;border-bottom:1px solid #dee2e6;font-weight:600">{profile.get('peak_power_w',0):,} W ({profile.get('peak_power_pct',0):.1f}% da cap.)</td>
            </tr>
            <tr>
              <td style="padding:5px 10px;border-bottom:1px solid #dee2e6;color:#6c757d">Duração solar</td>
              <td style="padding:5px 10px;border-bottom:1px solid #dee2e6;font-weight:600">{dur_txt}</td>
              <td style="padding:5px 10px;border-bottom:1px solid #dee2e6;color:#6c757d">Fator de capacidade</td>
              <td style="padding:5px 10px;border-bottom:1px solid #dee2e6;font-weight:600">{profile.get('capacity_factor_pct',0):.1f}%</td>
            </tr>
            <tr>
              <td style="padding:5px 10px;color:#6c757d">Potência média ativa</td>
              <td style="padding:5px 10px;font-weight:600">{profile.get('avg_active_power_w',0):,} W</td>
              <td style="padding:5px 10px;color:#6c757d">Pontos de dados</td>
              <td style="padding:5px 10px;font-weight:600">{profile.get('data_points',0)}</td>
            </tr>
          </tbody>
        </table>
      </div>""")

        # ── Impacto Ambiental e Financeiro ─────────────────────────────────────
        if energy.get('lifetime_kwh', 0) > 0:
            day_change = energy.get('day_change_pct')
            if day_change is not None:
                arrow = '▲' if day_change >= 0 else '▼'
                chg_color = '#198754' if day_change >= 0 else '#dc3545'
                sign = '+' if day_change >= 0 else ''
                day_change_html = (
                    f'<span style="color:{chg_color};font-weight:600">'
                    f'{arrow} {sign}{day_change:.1f}% vs ontem</span>'
                )
            else:
                day_change_html = '<span style="color:#6c757d">—</span>'

            sections.append(f"""
      <div style="margin-top:20px;border-top:2px solid #20c997;padding-top:16px">
        <p style="margin:0 0 10px;font-weight:bold;color:#20c997">🌱 Impacto Ambiental e Financeiro</p>
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <tbody>
            <tr>
              <td style="padding:5px 10px;border-bottom:1px solid #dee2e6;color:#6c757d;width:50%">Economia acumulada</td>
              <td style="padding:5px 10px;border-bottom:1px solid #dee2e6;font-weight:600">R$ {energy.get('financial_savings_brl',0):,.2f}</td>
              <td style="padding:5px 10px;border-bottom:1px solid #dee2e6;color:#6c757d;width:50%">CO₂ evitado</td>
              <td style="padding:5px 10px;border-bottom:1px solid #dee2e6;font-weight:600">{energy.get('co2_avoided_tonnes',0):.2f} t</td>
            </tr>
            <tr>
              <td style="padding:5px 10px;color:#6c757d">Geração acumulada (lifetime)</td>
              <td style="padding:5px 10px;font-weight:600">{energy.get('lifetime_kwh',0):,.2f} kWh</td>
              <td style="padding:5px 10px;color:#6c757d">Variação vs ontem</td>
              <td style="padding:5px 10px">{day_change_html}</td>
            </tr>
          </tbody>
        </table>
      </div>""")

        # ── Performance dos Inversores ─────────────────────────────────────────
        if invs:
            # Mostrar até top-5 e bottom-3 se houver muitos
            show_top = invs[:5]
            show_bot = [i for i in invs[-3:] if i not in show_top] if len(invs) > 5 else []
            all_show = show_top + show_bot

            rows = ''
            for idx, inv in enumerate(all_show):
                is_separator = (idx == len(show_top) and show_bot)
                if is_separator:
                    rows += '<tr><td colspan="5" style="padding:4px 10px;font-size:11px;color:#6c757d;background:#f8f9fa;text-align:center">⋯ demais inversores ⋯</td></tr>'
                asym = inv.get('asymmetry_pct')
                asym_txt = f"{asym:.1f}%" if asym is not None else '—'
                bar_pct = inv.get('pct_of_best', 0)
                bar_color = '#198754' if bar_pct >= 90 else ('#ffc107' if bar_pct >= 70 else '#dc3545')
                rows += f"""<tr>
              <td style="padding:5px 10px;border-bottom:1px solid #dee2e6;font-family:monospace;font-size:12px">{inv['uid']}</td>
              <td style="padding:5px 10px;border-bottom:1px solid #dee2e6;text-align:right">{inv['today_kwh']:.3f} kWh</td>
              <td style="padding:5px 10px;border-bottom:1px solid #dee2e6;text-align:right">{inv['month_kwh']:.2f} kWh</td>
              <td style="padding:5px 10px;border-bottom:1px solid #dee2e6;text-align:right">{asym_txt}</td>
              <td style="padding:5px 10px;border-bottom:1px solid #dee2e6">
                <div style="background:#e9ecef;border-radius:4px;height:10px;width:100%;min-width:60px">
                  <div style="background:{bar_color};width:{bar_pct}%;height:10px;border-radius:4px"></div>
                </div>
                <span style="font-size:11px;color:#6c757d">{bar_pct:.0f}%</span>
              </td>
            </tr>"""

            sections.append(f"""
      <div style="margin-top:20px;border-top:2px solid #17a2b8;padding-top:16px">
        <p style="margin:0 0 10px;font-weight:bold;color:#17a2b8">⚡ Performance dos Inversores (Hoje)</p>
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead>
            <tr style="background:#f8f9fa">
              <th style="padding:6px 10px;text-align:left;border-bottom:2px solid #dee2e6">Inversor</th>
              <th style="padding:6px 10px;text-align:right;border-bottom:2px solid #dee2e6">Hoje</th>
              <th style="padding:6px 10px;text-align:right;border-bottom:2px solid #dee2e6">Mês</th>
              <th style="padding:6px 10px;text-align:right;border-bottom:2px solid #dee2e6">Assim.</th>
              <th style="padding:6px 10px;text-align:left;border-bottom:2px solid #dee2e6">% do melhor</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>""")

        return '\n'.join(sections)

    def _build_alerts_html_block(self, alerts: list) -> str:
        """Cria bloco HTML com tabela de alertas para incluir nos emails programados."""
        if not alerts:
            return ''
        severity_colors = {'critical': '#dc3545', 'warning': '#ffc107', 'info': '#17a2b8'}
        severity_labels = {'critical': '🚨 Crítico', 'warning': '⚠️ Atenção', 'info': 'ℹ️ Info'}
        type_labels = {
            'inverter_fault': 'Falha Inversor', 'ecu_alarm': 'Alarme ECU',
            'offline': 'Offline', 'low_generation': 'Baixa Geração',
            'peak': 'Pico', 'alarm': 'Alarme'
        }
        rows = ''
        for a in alerts:
            color = severity_colors.get(a.get('severity', 'info'), '#6c757d')
            sev_label = severity_labels.get(a.get('severity', 'info'), a.get('severity', ''))
            type_label = type_labels.get(a.get('alert_type', ''), a.get('alert_type', ''))
            ts = a.get('timestamp', '')
            if ts:
                try:
                    from datetime import datetime as _dt
                    ts = _dt.fromisoformat(ts).strftime('%H:%M')
                except Exception:
                    pass
            rows += f"""<tr>
              <td style="padding:6px 10px;border-bottom:1px solid #dee2e6">
                <span style="color:{color};font-weight:bold">{sev_label}</span>
              </td>
              <td style="padding:6px 10px;border-bottom:1px solid #dee2e6">{ts}</td>
              <td style="padding:6px 10px;border-bottom:1px solid #dee2e6">{type_label}</td>
              <td style="padding:6px 10px;border-bottom:1px solid #dee2e6;font-size:13px">{a.get('message','')}</td>
            </tr>"""
        return f"""
      <div style="margin-top:20px;border-top:2px solid #dc3545;padding-top:16px">
        <p style="margin:0 0 10px;font-weight:bold;color:#dc3545">⚠️ Alertas do Dia ({len(alerts)})</p>
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead>
            <tr style="background:#f8f9fa">
              <th style="padding:6px 10px;text-align:left;border-bottom:2px solid #dee2e6">Severidade</th>
              <th style="padding:6px 10px;text-align:left;border-bottom:2px solid #dee2e6">Hora</th>
              <th style="padding:6px 10px;text-align:left;border-bottom:2px solid #dee2e6">Tipo</th>
              <th style="padding:6px 10px;text-align:left;border-bottom:2px solid #dee2e6">Mensagem</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>"""

    def _create_evening_summary_html(self, data: Dict, alerts: list = None,
                                     insights: dict = None) -> str:
        """Cria HTML do resumo vespertino."""
        lifetime = data.get('lifetime_kwh', 0)
        lifetime_row = f"""
      <div class="stat-box" style="border-color:#6c757d">
        <p style="margin:0 0 4px;color:#6c757d">Total Acumulado (Lifetime)</p>
        <p class="stat-value" style="color:#6c757d">{lifetime:,.2f} kWh</p>
      </div>""" if lifetime else ''
        alerts_block   = self._build_alerts_html_block(alerts or [])
        insights_block = self._build_insights_html_block(insights) if insights else ''

        return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body{{font-family:Arial,sans-serif;line-height:1.6;color:#333;background:#f0f0f0;margin:0;padding:20px}}
    .container{{max-width:600px;margin:0 auto;background:white;border-radius:10px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.1)}}
    .header{{background:linear-gradient(135deg,#f39c12,#e67e22);color:white;padding:28px 24px}}
    .header h2{{margin:0 0 4px;font-size:22px}}
    .header p{{margin:0;opacity:.9}}
    .content{{padding:24px}}
    .grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px}}
    .stat-box{{padding:14px 18px;background:#f8f9fa;border-left:4px solid #f39c12;border-radius:0 6px 6px 0}}
    .stat-value{{font-size:26px;font-weight:bold;color:#f39c12;margin:0}}
    .stat-box.green{{border-color:#28a745}}.stat-box.green .stat-value{{color:#28a745}}
    .stat-box.blue{{border-color:#17a2b8}}.stat-box.blue .stat-value{{color:#17a2b8}}
    .footer{{margin-top:24px;padding-top:16px;border-top:1px solid #dee2e6;font-size:12px;color:#6c757d}}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h2>☀️ Resumo do Dia</h2>
      <p>{data['date']} — Encerramento de geração</p>
    </div>
    <div class="content">
      <div class="grid">
        <div class="stat-box">
          <p style="margin:0 0 4px;color:#6c757d">Geração do Dia</p>
          <p class="stat-value">{data['total_generation_kwh']:.2f} kWh</p>
        </div>
        <div class="stat-box">
          <p style="margin:0 0 4px;color:#6c757d">Pico de Potência</p>
          <p class="stat-value">{data['peak_power_watts']:.0f} W</p>
        </div>
      </div>
      <div class="grid">
        <div class="stat-box green">
          <p style="margin:0 0 4px;color:#6c757d">Geração no Mês</p>
          <p class="stat-value">{data.get('month_kwh', 0):.2f} kWh</p>
        </div>
        <div class="stat-box blue">
          <p style="margin:0 0 4px;color:#6c757d">Geração no Ano</p>
          <p class="stat-value">{data.get('year_kwh', 0):.2f} kWh</p>
        </div>
      </div>
      {lifetime_row}
      {insights_block}
      {alerts_block}
      <div class="footer">
        <p>Enviado automaticamente às 17:00 — Sistema de Monitoramento Solar APSystems</p>
      </div>
    </div>
  </div>
</body>
</html>"""

    def _create_daily_report_html(self, stats: Dict, alerts: list = None,
                                   insights: dict = None) -> str:
        """Cria HTML para relatório diário."""
        month_kwh      = stats.get('month_kwh', 0)
        year_kwh       = stats.get('year_kwh', 0)
        alerts_block   = self._build_alerts_html_block(alerts or [])
        insights_block = self._build_insights_html_block(insights) if insights else ''

        month_row = f"""
            <div class="stat-box">
                <p style="margin:0 0 4px;color:#6c757d">Geração no Mês</p>
                <p class="stat-value">{month_kwh:.2f} kWh</p>
            </div>
            <div class="stat-box">
                <p style="margin:0 0 4px;color:#6c757d">Geração no Ano</p>
                <p class="stat-value">{year_kwh:.2f} kWh</p>
            </div>""" if month_kwh else ''

        html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body{{font-family:Arial,sans-serif;line-height:1.6;color:#333;background:#f0f0f0;margin:0;padding:20px}}
    .container{{max-width:600px;margin:0 auto;background:white;border-radius:10px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.1)}}
    .header{{background:linear-gradient(135deg,#28a745,#20c997);color:white;padding:28px 24px}}
    .header h2{{margin:0 0 4px;font-size:22px}}
    .header p{{margin:0;opacity:.9}}
    .content{{padding:24px}}
    .stat-box{{margin:10px 0;padding:14px 18px;background:#f8f9fa;border-left:4px solid #28a745;border-radius:0 6px 6px 0}}
    .stat-value{{font-size:26px;font-weight:bold;color:#28a745;margin:0}}
    .footer{{margin-top:24px;padding-top:16px;border-top:1px solid #dee2e6;font-size:12px;color:#6c757d}}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h2>☀️ Relatório Solar Diário</h2>
      <p>Data: {stats['date']}</p>
    </div>
    <div class="content">
      <div class="stat-box">
        <p style="margin:0 0 4px;color:#6c757d">Geração do Dia</p>
        <p class="stat-value">{stats['total_generation_kwh']:.2f} kWh</p>
      </div>
      <div class="stat-box">
        <p style="margin:0 0 4px;color:#6c757d">Pico de Potência</p>
        <p class="stat-value">{stats['peak_power_watts']:.0f} W</p>
      </div>
      <div class="stat-box">
        <p style="margin:0 0 4px;color:#6c757d">Média de Potência</p>
        <p class="stat-value">{stats['average_power_watts']:.0f} W</p>
      </div>
      {month_row}
      {insights_block}
      {alerts_block}
      <div class="footer">
        <p>Gerado automaticamente em {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}</p>
        <p>Sistema de Monitoramento Solar APSystems</p>
      </div>
    </div>
  </div>
</body>
</html>"""
        return html
