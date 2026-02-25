from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
from ..database.repository import Repository
from ..utils.logger import logger


class StatisticsCalculator:
    """Calculador de estatísticas de geração solar."""

    def __init__(self):
        self.repository = Repository()

    def calculate_daily_stats(self, target_date: date) -> Dict:
        """
        Calcula estatísticas diárias.

        Args:
            target_date: Data alvo

        Returns:
            Dicionário com estatísticas
        """
        logger.info(f"Calculando estatísticas diárias para {target_date}")

        try:
            # Buscar dados do dia
            data = self.repository.get_generation_data_for_period(target_date, target_date)

            if not data:
                logger.warning(f"Sem dados para {target_date}")
                return None

            # Total de geração vem do registro agregado (panel_id=None com energy_kwh_daily preenchido)
            aggregate_records = [d for d in data if d.panel_id is None and d.energy_kwh_daily]
            total_generation = max((d.energy_kwh_daily for d in aggregate_records), default=0)

            # Potência vem dos registros horários (panel_id='hourly')
            hourly_records = [d for d in data if d.panel_id == 'hourly']
            power_values = [d.power_watts for d in hourly_records] if hourly_records else [0]

            stats = {
                'date': target_date,
                'period_type': 'daily',
                'total_generation_kwh': total_generation,
                'peak_power_watts': max(power_values),
                'average_power_watts': sum(power_values) / len(power_values),
                'panel_stats': self._calculate_panel_stats(data)
            }

            # Salvar no banco
            self.repository.save_statistics(stats)
            logger.info(f"Estatísticas diárias salvas: {stats['total_generation_kwh']:.2f} kWh")

            return stats

        except Exception as e:
            logger.error(f"Erro ao calcular estatísticas diárias: {e}")
            return None

    def calculate_monthly_stats(self, year: int, month: int) -> Dict:
        """
        Calcula estatísticas mensais.

        Args:
            year: Ano
            month: Mês

        Returns:
            Dicionário com estatísticas
        """
        logger.info(f"Calculando estatísticas mensais para {year}-{month:02d}")

        try:
            # Buscar dados do mês
            start_date = date(year, month, 1)
            if month == 12:
                end_date = date(year + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = date(year, month + 1, 1) - timedelta(days=1)

            data = self.repository.get_generation_data_for_period(start_date, end_date)

            if not data:
                logger.warning(f"Sem dados para {year}-{month:02d}")
                return None

            # Calcular estatísticas
            power_values = [d.power_watts for d in data]

            # Para total mensal, somar os totais diários únicos
            daily_totals = {}
            for d in data:
                day = d.timestamp.date()
                if d.energy_kwh_daily:
                    if day not in daily_totals:
                        daily_totals[day] = d.energy_kwh_daily
                    else:
                        daily_totals[day] = max(daily_totals[day], d.energy_kwh_daily)

            total_generation = sum(daily_totals.values())

            stats = {
                'date': start_date,
                'period_type': 'monthly',
                'total_generation_kwh': total_generation,
                'peak_power_watts': max(power_values),
                'average_power_watts': sum(power_values) / len(power_values),
                'panel_stats': self._calculate_panel_stats(data)
            }

            # Salvar no banco
            self.repository.save_statistics(stats)
            logger.info(f"Estatísticas mensais salvas: {stats['total_generation_kwh']:.2f} kWh")

            return stats

        except Exception as e:
            logger.error(f"Erro ao calcular estatísticas mensais: {e}")
            return None

    def calculate_yearly_stats(self, year: int) -> Dict:
        """
        Calcula estatísticas anuais.

        Args:
            year: Ano

        Returns:
            Dicionário com estatísticas
        """
        logger.info(f"Calculando estatísticas anuais para {year}")

        try:
            # Buscar dados do ano
            start_date = date(year, 1, 1)
            end_date = date(year, 12, 31)

            data = self.repository.get_generation_data_for_period(start_date, end_date)

            if not data:
                logger.warning(f"Sem dados para {year}")
                return None

            # Calcular estatísticas
            power_values = [d.power_watts for d in data]

            # Para total anual, somar os totais diários únicos
            daily_totals = {}
            for d in data:
                day = d.timestamp.date()
                if d.energy_kwh_daily:
                    if day not in daily_totals:
                        daily_totals[day] = d.energy_kwh_daily
                    else:
                        daily_totals[day] = max(daily_totals[day], d.energy_kwh_daily)

            total_generation = sum(daily_totals.values())

            stats = {
                'date': start_date,
                'period_type': 'yearly',
                'total_generation_kwh': total_generation,
                'peak_power_watts': max(power_values),
                'average_power_watts': sum(power_values) / len(power_values),
                'panel_stats': self._calculate_panel_stats(data)
            }

            # Salvar no banco
            self.repository.save_statistics(stats)
            logger.info(f"Estatísticas anuais salvas: {stats['total_generation_kwh']:.2f} kWh")

            return stats

        except Exception as e:
            logger.error(f"Erro ao calcular estatísticas anuais: {e}")
            return None

    def _calculate_panel_stats(self, data: List) -> Dict:
        """
        Calcula estatísticas por painel.

        Args:
            data: Lista de dados de geração

        Returns:
            Dicionário com estatísticas por painel
        """
        panel_stats = {}

        try:
            for record in data:
                if not record.panel_id:
                    continue

                if record.panel_id not in panel_stats:
                    panel_stats[record.panel_id] = {
                        'power_values': [],
                        'energy_values': []
                    }

                panel_stats[record.panel_id]['power_values'].append(record.power_watts)
                if record.energy_kwh_daily:
                    panel_stats[record.panel_id]['energy_values'].append(record.energy_kwh_daily)

            # Calcular médias
            result = {}
            for panel_id, values in panel_stats.items():
                power_vals = values['power_values']
                energy_vals = values['energy_values']

                result[panel_id] = {
                    'average_power': sum(power_vals) / len(power_vals) if power_vals else 0,
                    'peak_power': max(power_vals) if power_vals else 0,
                    'total_energy': max(energy_vals) if energy_vals else 0
                }

            return result

        except Exception as e:
            logger.error(f"Erro ao calcular estatísticas de painéis: {e}")
            return {}

    def calculate_panel_efficiency(self, panel_id: str, start_date: date, end_date: date) -> Dict:
        """
        Calcula eficiência de um painel específico.

        Args:
            panel_id: ID do painel
            start_date: Data inicial
            end_date: Data final

        Returns:
            Dicionário com eficiência do painel
        """
        logger.info(f"Calculando eficiência do painel {panel_id}")

        try:
            data = self.repository.get_panel_performance(panel_id, start_date, end_date)

            if not data:
                return None

            power_values = [d.power_watts for d in data]
            energy_values = [d.energy_kwh_daily for d in data if d.energy_kwh_daily]

            return {
                'panel_id': panel_id,
                'period_start': start_date,
                'period_end': end_date,
                'average_power': sum(power_values) / len(power_values),
                'peak_power': max(power_values),
                'total_energy': sum(energy_values),
                'readings_count': len(data)
            }

        except Exception as e:
            logger.error(f"Erro ao calcular eficiência do painel: {e}")
            return None

    def generate_comparison_report(self, period1_start: date, period1_end: date,
                                   period2_start: date, period2_end: date) -> Dict:
        """
        Gera relatório comparativo entre dois períodos.

        Args:
            period1_start: Data inicial período 1
            period1_end: Data final período 1
            period2_start: Data inicial período 2
            period2_end: Data final período 2

        Returns:
            Dicionário com comparação
        """
        logger.info(f"Gerando relatório comparativo")

        try:
            # Dados período 1
            data1 = self.repository.get_generation_data_for_period(period1_start, period1_end)
            # Dados período 2
            data2 = self.repository.get_generation_data_for_period(period2_start, period2_end)

            if not data1 or not data2:
                logger.warning("Dados insuficientes para comparação")
                return None

            # Calcular totais
            def calc_totals(data):
                daily_totals = {}
                for d in data:
                    day = d.timestamp.date()
                    if d.energy_kwh_daily:
                        if day not in daily_totals:
                            daily_totals[day] = d.energy_kwh_daily
                        else:
                            daily_totals[day] = max(daily_totals[day], d.energy_kwh_daily)
                return sum(daily_totals.values())

            total1 = calc_totals(data1)
            total2 = calc_totals(data2)

            difference = total2 - total1
            if total1 > 0:
                percentage_change = (difference / total1) * 100
            else:
                percentage_change = 0

            return {
                'period1': {
                    'start': period1_start,
                    'end': period1_end,
                    'total_kwh': total1
                },
                'period2': {
                    'start': period2_start,
                    'end': period2_end,
                    'total_kwh': total2
                },
                'difference_kwh': difference,
                'percentage_change': percentage_change
            }

        except Exception as e:
            logger.error(f"Erro ao gerar relatório comparativo: {e}")
            return None
