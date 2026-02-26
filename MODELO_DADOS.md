# Modelo de Dados — Sistema de Monitoramento Solar

Banco: `data/solar_monitoring.db` (SQLite)

---

## Diagrama ER

```mermaid
erDiagram

    %% ── GERAÇÃO ────────────────────────────────────────────────────────────

    generation_data {
        INTEGER  id              PK
        DATETIME timestamp       "NOT NULL, INDEX"
        STRING   ecu_id          "NOT NULL, INDEX"
        STRING   panel_id        "INDEX (null = total ECU; 'hourly' = agregado hora)"
        FLOAT    power_watts     "NOT NULL"
        FLOAT    energy_kwh_daily
        FLOAT    energy_kwh_total
        DATETIME created_at
    }

    ecu_telemetry {
        INTEGER  id              PK
        DATE     date            "NOT NULL, INDEX"
        STRING   ecu_id          "NOT NULL, INDEX"
        JSON     time_series     "{time, power, energy, today}"
        DATETIME updated_at
    }

    inverter_batch_data {
        INTEGER  id              PK
        DATE     date            "NOT NULL, INDEX"
        STRING   ecu_id          "NOT NULL, INDEX"
        JSON     power_data      "{time, power: {uid-ch: [W]}}"
        JSON     energy_data     "{energy: [uid-ch-kwh]}"
        DATETIME updated_at
    }

    inverter_summary {
        INTEGER  id              PK
        DATETIME timestamp       "NOT NULL, INDEX"
        STRING   inverter_uid    "NOT NULL, INDEX"
        JSON     channels        "{ch: {today, month, year, lifetime}}"
        DATETIME created_at
    }

    statistics {
        INTEGER  id              PK
        DATE     date            "NOT NULL, INDEX"
        ENUM     period_type     "daily | monthly | yearly"
        FLOAT    total_generation_kwh  "NOT NULL"
        FLOAT    peak_power_watts      "NOT NULL"
        FLOAT    average_power_watts   "NOT NULL"
        JSON     panel_stats
    }

    %% ── MEDIDOR ─────────────────────────────────────────────────────────────

    meter_data {
        INTEGER  id              PK
        DATETIME timestamp       "NOT NULL, INDEX"
        STRING   meter_id        "NOT NULL, INDEX"
        JSON     today           "{consumed, exported, imported, produced}"
        JSON     month
        JSON     year
        JSON     lifetime
        DATETIME created_at
    }

    %% ── SISTEMA ─────────────────────────────────────────────────────────────

    system_status {
        INTEGER  id                  PK
        DATETIME timestamp           "NOT NULL, INDEX"
        STRING   ecu_id              "NOT NULL, INDEX"
        ENUM     status              "online | offline | error"
        DATETIME last_communication  "NOT NULL"
        INTEGER  alarm_count
    }

    alerts {
        INTEGER  id           PK
        DATETIME timestamp    "NOT NULL, INDEX"
        ENUM     alert_type   "peak | low_generation | offline | alarm | inverter_fault | ecu_alarm"
        ENUM     severity     "info | warning | critical"
        TEXT     message      "NOT NULL"
        JSON     details
        BOOLEAN  resolved
        DATETIME resolved_at
    }

    %% ── EMAIL ───────────────────────────────────────────────────────────────

    alert_recipients {
        INTEGER  id               PK
        STRING   name             "NOT NULL"
        STRING   email            "NOT NULL, UNIQUE"
        BOOLEAN  active
        BOOLEAN  receive_alerts
        BOOLEAN  receive_reports
        DATETIME created_at
    }

    email_log {
        INTEGER  id               PK
        DATETIME sent_at          "NOT NULL, INDEX"
        STRING   email_type       "alert | daily_report | evening_summary | test"
        STRING   subject          "NOT NULL"
        JSON     recipients       "[email, ...]"
        INTEGER  recipient_count
        BOOLEAN  success          "NOT NULL"
        TEXT     error_message
    }

    %% ── RELACIONAMENTOS LÓGICOS ─────────────────────────────────────────────
    %% (sem FK explícitas no SQLite — vínculos por ecu_id / inverter_uid)

    generation_data    }o--o{ ecu_telemetry       : "ecu_id"
    generation_data    }o--o{ inverter_batch_data  : "ecu_id"
    generation_data    }o--o{ system_status        : "ecu_id"
    ecu_telemetry      }o--o{ inverter_batch_data  : "ecu_id (mesmo dia)"
    statistics         }o--o{ generation_data      : "date (agregação)"
    alerts             }o--o{ email_log            : "email_type = alert"
    alert_recipients   }o--o{ email_log            : "recipients[]"
```

---

## Descrição das Tabelas

### Grupo: Geração

#### `generation_data`
Série temporal bruta coletada a cada ciclo do scheduler.

| Campo | Tipo | Descrição |
|---|---|---|
| `timestamp` | DateTime | Momento da leitura |
| `ecu_id` | String | ID da ECU (ex: `E19H368434753865`) |
| `panel_id` | String | `null` = leitura total da ECU; `'hourly'` = registro horário agregado; UID do painel = leitura individual |
| `power_watts` | Float | Potência instantânea em Watts |
| `energy_kwh_daily` | Float | Energia acumulada no dia (kWh) |
| `energy_kwh_total` | Float | Energia total lifetime (kWh) |

#### `ecu_telemetry`
Série minutely da ECU — uma linha por ECU por dia, atualizada a cada coleta.

| Campo | Tipo | Descrição |
|---|---|---|
| `date` | Date | Data da série |
| `ecu_id` | String | ID da ECU |
| `time_series` | JSON | `{time: ["HH:mm",...], power: [W,...], energy: [kWh,...], today: kWh}` |

**Chave lógica única:** `(date, ecu_id)` — upsert a cada coleta.

#### `inverter_batch_data`
Power telemetry e energia diária de todos os inversores de uma ECU — uma linha por ECU por dia.

| Campo | Tipo | Descrição |
|---|---|---|
| `date` | Date | Data |
| `ecu_id` | String | ID da ECU |
| `power_data` | JSON | `{time: ["HH:mm",...], power: {"uid-ch": [W,...]}}` |
| `energy_data` | JSON | `{energy: ["uid-ch-kwh",...]}` — energia do dia por canal |

**Chave lógica única:** `(date, ecu_id)` — upsert a cada coleta.

#### `inverter_summary`
Snapshot de energia acumulada por inversor e canal (hoje/mês/ano/lifetime).

| Campo | Tipo | Descrição |
|---|---|---|
| `inverter_uid` | String | UID do inversor |
| `channels` | JSON | `{1: {today, month, year, lifetime}, 2: {...}}` — energia em kWh |

#### `statistics`
Estatísticas agregadas calculadas pelo sistema.

| Campo | Tipo | Descrição |
|---|---|---|
| `date` | Date | Data de referência |
| `period_type` | Enum | `daily` / `monthly` / `yearly` |
| `total_generation_kwh` | Float | Total gerado no período |
| `peak_power_watts` | Float | Pico de potência |
| `average_power_watts` | Float | Média de potência |
| `panel_stats` | JSON | Detalhamento por painel/inversor |

---

### Grupo: Medidor

#### `meter_data`
Dados do medidor de energia — balanço consumo vs geração vs rede.

| Campo | Tipo | Descrição |
|---|---|---|
| `meter_id` | String | ID do medidor |
| `today` | JSON | `{consumed, exported, imported, produced}` em kWh |
| `month` | JSON | Mesma estrutura, acumulado no mês |
| `year` | JSON | Acumulado no ano |
| `lifetime` | JSON | Acumulado total |

---

### Grupo: Sistema

#### `system_status`
Histórico de status de comunicação da ECU.

| Campo | Tipo | Descrição |
|---|---|---|
| `ecu_id` | String | ID da ECU |
| `status` | Enum | `online` / `offline` / `error` |
| `last_communication` | DateTime | Último contato bem-sucedido |
| `alarm_count` | Integer | Quantidade de alarmes ativos |

#### `alerts`
Alertas gerados pelo sistema de monitoramento.

| Campo | Tipo | Descrição |
|---|---|---|
| `alert_type` | Enum | `peak` / `low_generation` / `offline` / `alarm` / `inverter_fault` / `ecu_alarm` |
| `severity` | Enum | `info` / `warning` / `critical` |
| `message` | Text | Descrição legível do alerta |
| `details` | JSON | Dados adicionais do contexto |
| `resolved` | Boolean | Se foi marcado como resolvido |
| `resolved_at` | DateTime | Momento da resolução |

---

### Grupo: Email

#### `alert_recipients`
Cadastro de destinatários de alertas e relatórios.

| Campo | Tipo | Descrição |
|---|---|---|
| `email` | String | Endereço único |
| `active` | Boolean | Se recebe emails |
| `receive_alerts` | Boolean | Recebe alertas |
| `receive_reports` | Boolean | Recebe relatórios diários |

#### `email_log`
Histórico completo de todos os emails enviados.

| Campo | Tipo | Descrição |
|---|---|---|
| `email_type` | String | `alert` / `daily_report` / `evening_summary` / `test` |
| `subject` | String | Assunto do email |
| `recipients` | JSON | Lista de endereços destinatários |
| `success` | Boolean | Se o envio foi bem-sucedido |
| `error_message` | Text | Mensagem de erro (se houver) |

---

## Enums

| Enum | Valores |
|---|---|
| `PeriodType` | `daily`, `monthly`, `yearly` |
| `AlertType` | `peak`, `low_generation`, `offline`, `alarm`, `inverter_fault`, `ecu_alarm` |
| `Severity` | `info`, `warning`, `critical` |
| `SystemStatus` | `online`, `offline`, `error` |

---

## Observações de Design

- **Sem foreign keys explícitas** — SQLite permite isso; os vínculos são mantidos por convenção de código (ex: `ecu_id` presente em múltiplas tabelas).
- **Campos JSON** — usados para séries temporais e estruturas variáveis; evitam tabelas filhas para dados de alta frequência.
- **Upsert por chave lógica** — `ecu_telemetry` e `inverter_batch_data` usam `(date, ecu_id)` como chave lógica única, atualizando o registro existente a cada coleta do dia.
- **`generation_data`** — tabela mais volumosa; cresce a cada ciclo de coleta (~a cada 5 minutos durante o dia).
