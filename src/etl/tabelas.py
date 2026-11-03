"""Catálogo do que entra no projeto: quais arquivos e quais colunas de cada um.

Funciona como lista de permissão. O que não está aqui nunca é carregado, o que
exclui por construção amigos, perfil, ECG, GPS e campos de texto livre.

O VO2 e a velocidade do relógio também ficam de fora de propósito, porque não
são confiáveis nos treinos de esteira inclinada.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Tabela:
    arquivo: str
    colunas: tuple[str, ...]


_PERIODO = ("start_time", "end_time", "time_offset")

TABELAS: dict[str, Tabela] = {
    "exercicio": Tabela(
        "com.samsung.shealth.exercise",
        ("datauuid", *_PERIODO, "exercise_type", "duration", "mean_heart_rate", "max_heart_rate",
         "min_heart_rate", "count", "mean_cadence", "location_data"),
    ),
    "sono": Tabela(
        "com.samsung.shealth.sleep",
        ("datauuid", *_PERIODO, "sleep_duration", "efficiency", "sleep_latency", "total_rem_duration",
         "total_light_duration", "movement_awakening", "sleep_type", "sleep_score"),
    ),
    "estagios_sono": Tabela(
        "com.samsung.health.sleep_stage",
        ("datauuid", *_PERIODO, "sleep_id", "stage"),
    ),
    "vfc": Tabela(
        "com.samsung.health.hrv",
        ("datauuid", *_PERIODO, "binning_data"),
    ),
    "fc_continua": Tabela(
        "com.samsung.shealth.tracker.heart_rate",
        ("datauuid", *_PERIODO, "heart_rate", "min", "max", "binning_data"),
    ),
    "recuperacao_fc": Tabela(
        "com.samsung.shealth.exercise.recovery_heart_rate",
        ("datauuid", *_PERIODO, "exercise_id", "heart_rate"),
    ),
    "temperatura_pele": Tabela(
        "com.samsung.health.skin_temperature",
        ("datauuid", *_PERIODO, "temperature", "min", "max"),
    ),
    "respiracao": Tabela(
        "com.samsung.health.respiratory_rate",
        ("datauuid", *_PERIODO, "average", "is_outlier"),
    ),
    "spo2": Tabela(
        "com.samsung.shealth.tracker.oxygen_saturation",
        ("datauuid", *_PERIODO, "spo2", "min", "max"),
    ),
    "vitalidade": Tabela(
        "com.samsung.shealth.vitality_score",
        ("datauuid", "day_time", "sleep_duration", "sleep_score", "shr_value", "shrv_value",
         "shr_score", "shrv_score", "activity_score", "total_score"),
    ),
    "passos_minuto": Tabela(
        "com.samsung.shealth.tracker.pedometer_step_count",
        ("datauuid", *_PERIODO, "count", "walk_step", "run_step", "deviceuuid"),
    ),
    "passos_dia": Tabela(
        "com.samsung.shealth.step_daily_trend",
        ("datauuid", "day_time", "source_type", "count", "binning_data"),
    ),
}
