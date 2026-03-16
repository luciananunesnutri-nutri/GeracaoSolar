#!/usr/bin/env python3
"""
Cliente OpenAPI APSystems - Conforme documentação oficial
"""

import requests
import hashlib
import base64
import uuid
import time
from datetime import datetime
from typing import Dict, List, Optional
from ..utils.logger import logger


class APSystemsOpenAPIClient:
    """Cliente para OpenAPI APSystems com autenticação por assinatura."""

    def __init__(self, app_id: str, app_secret: str, system_id: str):
        self.base_url = "https://api.apsystemsema.com:9282"
        self.app_id = app_id or ''
        self.app_secret = app_secret or ''
        self.system_id = system_id or ''
        self.signature_method = "HmacSHA256"

    def _calculate_signature(self, timestamp: str, nonce: str, request_path: str, http_method: str) -> str:
        last_segment = request_path.rstrip('/').split('/')[-1]
        string_to_sign = f"{timestamp}/{nonce}/{self.app_id}/{last_segment}/{http_method}/{self.signature_method}"
        logger.debug(f"String to sign: {string_to_sign}")

        import hmac
        signature_bytes = hmac.new(
            self.app_secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            hashlib.sha256
        ).digest()
        return base64.b64encode(signature_bytes).decode('utf-8')

    def _make_request(self, endpoint: str, method: str = "GET", **kwargs) -> Dict:
        url = f"{self.base_url}{endpoint}"
        timestamp = str(int(time.time() * 1000))
        nonce = uuid.uuid4().hex

        signature = self._calculate_signature(timestamp, nonce, endpoint, method)
        headers = {
            'X-CA-AppId': self.app_id,
            'X-CA-Timestamp': timestamp,
            'X-CA-Nonce': nonce,
            'X-CA-Signature-Method': self.signature_method,
            'X-CA-Signature': signature,
            'Content-Type': 'application/json'
        }

        if 'headers' in kwargs:
            headers.update(kwargs['headers'])
        kwargs['headers'] = headers

        if 'timeout' not in kwargs:
            kwargs['timeout'] = 30

        max_retries = 3
        # Erros temporários que vale retry (NÃO incluir 2005 = rate limit)
        retry_codes = {5000, 6000, 7000}
        # Erros de rate limit — não fazer retry, só piora
        no_retry_codes = {2005, 7001, 7002}

        for attempt in range(1, max_retries + 1):
            try:
                # Recalcular assinatura a cada tentativa (timestamp muda)
                if attempt > 1:
                    timestamp = str(int(time.time() * 1000))
                    nonce = uuid.uuid4().hex
                    signature = self._calculate_signature(timestamp, nonce, endpoint, method)
                    kwargs['headers'].update({
                        'X-CA-Timestamp': timestamp,
                        'X-CA-Nonce': nonce,
                        'X-CA-Signature': signature,
                    })

                logger.info(f"Requisição {method} {url} (tentativa {attempt}/{max_retries})")
                response = requests.request(method, url, **kwargs)
                response.raise_for_status()
                data = response.json()

                if data.get('code') == 0:
                    logger.info(f"Requisição bem-sucedida: {endpoint}")
                    return data
                else:
                    api_code = data.get('code')
                    error_msg = f"Erro na API (code={api_code}): {data.get('message', 'Unknown error')}"

                    # Rate limit — falhar imediatamente sem retry
                    if api_code in no_retry_codes:
                        logger.error(f"{error_msg} (rate limit — sem retry)")
                        raise Exception(error_msg)

                    if api_code in retry_codes and attempt < max_retries:
                        wait = 2 ** attempt  # 2s, 4s
                        logger.warning(f"{error_msg} — retry em {wait}s...")
                        time.sleep(wait)
                        continue

                    logger.error(error_msg)
                    raise Exception(error_msg)

            except requests.exceptions.RequestException as e:
                if attempt < max_retries:
                    wait = 2 ** attempt
                    logger.warning(f"Erro na requisição {method} {url}: {e} — retry em {wait}s...")
                    time.sleep(wait)
                    continue
                logger.error(f"Erro na requisição {method} {url}: {e}")
                raise

    # ── Endpoints existentes ──────────────────────────────────────────────────

    def get_system_details(self) -> Dict:
        endpoint = f"/user/api/v2/systems/details/{self.system_id}"
        return self._make_request(endpoint).get('data', {})

    def get_system_inverters(self) -> List:
        endpoint = f"/user/api/v2/systems/inverters/{self.system_id}"
        return self._make_request(endpoint).get('data', [])

    def get_system_summary(self) -> Dict:
        endpoint = f"/user/api/v2/systems/summary/{self.system_id}"
        return self._make_request(endpoint).get('data', {})

    def get_system_energy(self, energy_level: str, date_range: Optional[str] = None) -> list:
        endpoint = f"/user/api/v2/systems/energy/{self.system_id}"
        params = {'energy_level': energy_level}
        if date_range:
            params['date_range'] = date_range
        return self._make_request(endpoint, params=params).get('data', [])

    def get_ecu_summary(self, ecu_id: str) -> Dict:
        endpoint = f"/user/api/v2/systems/{self.system_id}/devices/ecu/summary/{ecu_id}"
        return self._make_request(endpoint).get('data', {})

    # ── Novos endpoints ───────────────────────────────────────────────────────

    def get_system_meters(self) -> List:
        """Retorna lista de IDs dos medidores do sistema."""
        endpoint = f"/user/api/v2/systems/meters/{self.system_id}"
        return self._make_request(endpoint).get('data', [])

    def get_ecu_energy(self, ecu_id: str, energy_level: str, date_range: Optional[str] = None) -> Dict:
        """
        Energia por período de uma ECU.
        energy_level: 'minutely' | 'hourly' | 'daily' | 'monthly' | 'yearly'
        Retorno minutely: {time:[HH:mm,...], power:[W,...], energy:[kWh,...], today:kWh}
        Retorno outros: lista de kWh
        """
        endpoint = f"/user/api/v2/systems/{self.system_id}/devices/ecu/energy/{ecu_id}"
        params = {'energy_level': energy_level}
        if date_range:
            params['date_range'] = date_range
        return self._make_request(endpoint, params=params).get('data', {})

    def get_meter_summary(self, meter_id: str) -> Dict:
        """
        Resumo de energia do medidor.
        Retorna: {today:{consumed,exported,imported,produced}, month:{...}, year:{...}, lifetime:{...}}
        """
        endpoint = f"/user/api/v2/systems/{self.system_id}/devices/meter/summary/{meter_id}"
        return self._make_request(endpoint).get('data', {})

    def get_meter_energy(self, meter_id: str, energy_level: str, date_range: Optional[str] = None) -> Dict:
        """
        Energia do medidor por período.
        energy_level: 'minutely' | 'hourly' | 'daily' | 'monthly' | 'yearly'
        """
        endpoint = f"/user/api/v2/systems/{self.system_id}/devices/meter/period/{meter_id}"
        params = {'energy_level': energy_level}
        if date_range:
            params['date_range'] = date_range
        return self._make_request(endpoint, params=params).get('data', {})

    def get_inverter_summary(self, uid: str) -> Dict:
        """
        Resumo de energia de um inversor por canal.
        Retorna: {d1, m1, y1, t1, d2, m2, y2, t2, ...} (até 4 canais)
        d=today, m=month, y=year, t=lifetime
        """
        endpoint = f"/user/api/v2/systems/{self.system_id}/devices/inverter/summary/{uid}"
        return self._make_request(endpoint).get('data', {})

    def get_inverter_energy(self, uid: str, energy_level: str, date_range: Optional[str] = None) -> Dict:
        """
        Energia de um inversor por período.
        energy_level: 'minutely' | 'hourly' | 'daily' | 'monthly' | 'yearly'
        Retorno minutely: {t:[HH:mm,...], dc_p1:[W,...], dc_i1:[A,...], dc_v1:[V,...],
                           dc_e1:[kWh,...], ac_p:[W,...], ac_v1:[V,...], ac_t:[°C,...], ac_f:[Hz,...]}
        """
        endpoint = f"/user/api/v2/systems/{self.system_id}/devices/inverter/energy/{uid}"
        params = {'energy_level': energy_level}
        if date_range:
            params['date_range'] = date_range
        return self._make_request(endpoint, params=params).get('data', {})

    def get_inverter_batch_energy(self, ecu_id: str, energy_level: str, date_range: str) -> Dict:
        """
        Energia de todos os inversores de uma ECU em uma única chamada.
        energy_level: 'power' | 'energy'
        Retorno power: {time:[HH:mm,...], power:{'uid-ch':[W,...]}}
        Retorno energy: {energy:['uid-ch-kwh',...]}
        """
        endpoint = f"/user/api/v2/systems/{self.system_id}/devices/inverter/batch/energy/{ecu_id}"
        params = {'energy_level': energy_level, 'date_range': date_range}
        return self._make_request(endpoint, params=params).get('data', {})

    # ── Coleta completa ───────────────────────────────────────────────────────

    def collect_all_data(self) -> Dict:
        """Coleta todos os dados disponíveis do sistema."""
        logger.info(f"Coletando todos os dados do sistema {self.system_id}")

        today_str = datetime.now().strftime('%Y-%m-%d')

        data = {
            'timestamp': datetime.now(),
            'system_id': self.system_id,
            'details': None,
            'inverters': None,
            'summary': None,
            'energy_today': None,
            'meters': [],
            'ecu_telemetry': {},    # {ecu_id: {time, power, energy, today}}
            'meter_summaries': {},  # {meter_id: {today, month, year, lifetime}}
            'inverter_batch_power': {},   # {ecu_id: {time, power}}
            'inverter_batch_energy': {},  # {ecu_id: {energy}}
            'inverter_summaries': {},     # {uid: {d1,m1,y1,t1,...}}
        }

        # ── Dados básicos (críticos) ──────────────────────────────────────────
        try:
            data['details'] = self.get_system_details()
            logger.info(f"Detalhes obtidos: capacidade={data['details'].get('capacity')} kW")
        except Exception as e:
            logger.warning(f"Erro ao obter detalhes: {e}")

        try:
            data['inverters'] = self.get_system_inverters()
            logger.info(f"Inversores obtidos: {len(data['inverters'])} ECU(s)")
        except Exception as e:
            logger.warning(f"Erro ao obter inversores: {e}")

        try:
            data['summary'] = self.get_system_summary()
            logger.info(f"Resumo: Hoje={data['summary'].get('today')} kWh | "
                        f"Mês={data['summary'].get('month')} kWh | "
                        f"Ano={data['summary'].get('year')} kWh | "
                        f"Total={data['summary'].get('lifetime')} kWh")
        except Exception as e:
            logger.warning(f"Erro ao obter resumo: {e}")
            # Continuar sem summary — dados parciais ainda são úteis

        try:
            data['energy_today'] = self.get_system_energy('hourly', today_str)
            logger.info(f"Energia horária de hoje: {len(data['energy_today'])} horas")
        except Exception as e:
            logger.warning(f"Erro ao obter energia horária: {e}")

        # ── Medidores ─────────────────────────────────────────────────────────
        try:
            data['meters'] = self.get_system_meters()
            logger.info(f"Medidores encontrados: {data['meters']}")
            for meter_id in data['meters']:
                try:
                    data['meter_summaries'][meter_id] = self.get_meter_summary(meter_id)
                    logger.info(f"Medidor {meter_id}: {data['meter_summaries'][meter_id].get('today')}")
                except Exception as e:
                    logger.warning(f"Erro ao obter dados do medidor {meter_id}: {e}")
        except Exception as e:
            logger.warning(f"Erro ao obter lista de medidores: {e}")

        # ── Dados por ECU e inversores ────────────────────────────────────────
        ecu_list = data['inverters'] or []
        for ecu in ecu_list:
            ecu_id = ecu.get('eid')
            if not ecu_id:
                continue

            # Telemetria minutely da ECU
            try:
                telemetry = self.get_ecu_energy(ecu_id, 'minutely', today_str)
                if telemetry:
                    data['ecu_telemetry'][ecu_id] = telemetry
                    points = len(telemetry.get('time', []))
                    logger.info(f"ECU {ecu_id}: telemetria minutely com {points} pontos")
            except Exception as e:
                logger.warning(f"ECU {ecu_id}: erro na telemetria minutely: {e}")

            # Batch power de todos os inversores da ECU
            try:
                batch_power = self.get_inverter_batch_energy(ecu_id, 'power', today_str)
                if batch_power:
                    data['inverter_batch_power'][ecu_id] = batch_power
                    logger.info(f"ECU {ecu_id}: batch power obtido")
            except Exception as e:
                logger.warning(f"ECU {ecu_id}: erro no batch power: {e}")

            # Batch energy (energia diária por canal)
            try:
                batch_energy = self.get_inverter_batch_energy(ecu_id, 'energy', today_str)
                if batch_energy:
                    data['inverter_batch_energy'][ecu_id] = batch_energy
                    logger.info(f"ECU {ecu_id}: batch energy obtido")
            except Exception as e:
                logger.warning(f"ECU {ecu_id}: erro no batch energy: {e}")

            # Resumo por inversor individual
            for inv in ecu.get('inverter', []):
                uid = inv.get('uid')
                if not uid:
                    continue
                try:
                    summary = self.get_inverter_summary(uid)
                    if summary:
                        data['inverter_summaries'][uid] = summary
                        logger.info(f"Inversor {uid}: resumo obtido (hoje={summary.get('d1')} kWh)")
                except Exception as e:
                    logger.warning(f"Inversor {uid}: erro no resumo: {e}")

        return data
