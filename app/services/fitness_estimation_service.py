"""Servicio para la configuración de estimaciones físicas (kcal / kg de grasa).

Envuelve la query/mutations GraphQL ``fitnessEstimationSettings`` /
``saveFitnessEstimationConfig`` / ``setClassTypeMet``, que controlan el número que las
campañas de reactivación le dicen al socio ("dejaste de quemar N kcal").

La pantalla mezcla tres cosas distintas a propósito: la política editable, la intensidad por
actividad, y —sólo de lectura— el horario que el sistema deduce de ``class_templates``. Ver
los tres juntos es lo que permite entender de dónde sale el número: si está mal porque falta
configurar algo o porque el gimnasio todavía no tiene horario cargado.
"""
from typing import Any, Dict, List, Optional

from ..core.logging import get_logger

logger = get_logger(__name__)


_CONFIG_FIELDS = """
    id
    referenceWeightKg
    horizonWeeks
    defaultSessionsPerWeek
    minBookingsForHistory
    cadenceLookbackDays
    defaultMet
    defaultDurationMin
    defaultOpenDaysPerWeek
    netOfResting
    kcalPerKgFat
    metabolicAdaptation
    kgHalfLifeDays
    kgPer100KcalPerDay
    realizationFactor
"""

_SETTINGS_FIELDS = f"""
    config {{ {_CONFIG_FIELDS} }}
    classTypes {{ id code name metValue effectiveMet isDefault }}
    schedule {{ openDaysPerWeek openWeekdays meanDurationMin activeTemplates }}
    preview {{
        daysInactive weeksCounted horizonReached sessionsPerWeek sessionsMissed
        met durationMin kcalPerSession kcalPerDay kcal kgSteadyState kgFat
        kcalText kgFatText windowLabel
    }}
"""


def _map_config(node: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not node:
        return None
    return {
        "id": node.get("id"),
        "reference_weight_kg": float(node.get("referenceWeightKg") or 70),
        "horizon_weeks": int(node.get("horizonWeeks") or 104),
        "default_sessions_per_week": float(node.get("defaultSessionsPerWeek") or 2.5),
        "min_bookings_for_history": int(node.get("minBookingsForHistory") or 4),
        "cadence_lookback_days": int(node.get("cadenceLookbackDays") or 180),
        "default_met": float(node.get("defaultMet") or 6.0),
        "default_duration_min": int(node.get("defaultDurationMin") or 60),
        "default_open_days_per_week": int(node.get("defaultOpenDaysPerWeek") or 5),
        "net_of_resting": bool(node.get("netOfResting")),
        "kcal_per_kg_fat": int(node.get("kcalPerKgFat") or 7700),
        "metabolic_adaptation": bool(node.get("metabolicAdaptation")),
        "kg_half_life_days": int(node.get("kgHalfLifeDays") or 365),
        "kg_per_100_kcal_per_day": float(node.get("kgPer100KcalPerDay") or 4.5),
        "realization_factor": float(node.get("realizationFactor") or 1.0),
    }


def _map_class_types(nodes: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    return [
        {
            "id": n.get("id"),
            "code": n.get("code") or "",
            "name": n.get("name") or "",
            "met_value": n.get("metValue"),
            "effective_met": float(n.get("effectiveMet") or 0),
            "is_default": bool(n.get("isDefault")),
        }
        for n in (nodes or [])
    ]


def _map_schedule(node: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    node = node or {}
    return {
        "open_days_per_week": int(node.get("openDaysPerWeek") or 0),
        "open_weekdays": list(node.get("openWeekdays") or []),
        "mean_duration_min": node.get("meanDurationMin"),
        "active_templates": int(node.get("activeTemplates") or 0),
    }


def _map_preview(node: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not node:
        return None
    return {
        "days_inactive": int(node.get("daysInactive") or 0),
        "weeks_counted": float(node.get("weeksCounted") or 0),
        "horizon_reached": bool(node.get("horizonReached")),
        "sessions_per_week": float(node.get("sessionsPerWeek") or 0),
        "sessions_missed": float(node.get("sessionsMissed") or 0),
        "met": float(node.get("met") or 0),
        "duration_min": int(node.get("durationMin") or 0),
        "kcal_per_session": float(node.get("kcalPerSession") or 0),
        "kcal_per_day": float(node.get("kcalPerDay") or 0),
        "kcal": int(node.get("kcal") or 0),
        "kg_steady_state": float(node.get("kgSteadyState") or 0),
        "kg_fat": float(node.get("kgFat") or 0),
        "kcal_text": node.get("kcalText") or "",
        "kg_fat_text": node.get("kgFatText") or "",
        "window_label": node.get("windowLabel") or "",
    }


def _map_settings(node: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not node:
        return None
    return {
        "config": _map_config(node.get("config")),
        "class_types": _map_class_types(node.get("classTypes")),
        "schedule": _map_schedule(node.get("schedule")),
        "preview": _map_preview(node.get("preview")),
    }


class FitnessEstimationService:
    """Servicio para leer/guardar la configuración de estimaciones."""

    def __init__(self, graphql_client):
        self.client = graphql_client

    async def get_settings(self) -> Optional[Dict[str, Any]]:
        query = f"""
            query FitnessEstimationSettings {{
                fitnessEstimationSettings {{
                    {_SETTINGS_FIELDS}
                }}
            }}
        """
        result = await self.client.execute(query)
        if result and result.get("fitnessEstimationSettings") is not None:
            return _map_settings(result["fitnessEstimationSettings"])
        return None

    async def save_config(self, **fields) -> Dict[str, Any]:
        mutation = f"""
            mutation SaveFitnessEstimationConfig($input: SaveFitnessEstimationConfigInput!) {{
                saveFitnessEstimationConfig(input: $input) {{
                    success
                    error
                    settings {{ {_SETTINGS_FIELDS} }}
                }}
            }}
        """
        variables = {
            "input": {
                "referenceWeightKg": fields.get("reference_weight_kg"),
                "horizonWeeks": fields.get("horizon_weeks"),
                "defaultSessionsPerWeek": fields.get("default_sessions_per_week"),
                "minBookingsForHistory": fields.get("min_bookings_for_history"),
                "cadenceLookbackDays": fields.get("cadence_lookback_days"),
                "defaultMet": fields.get("default_met"),
                "defaultDurationMin": fields.get("default_duration_min"),
                "defaultOpenDaysPerWeek": fields.get("default_open_days_per_week"),
                "netOfResting": fields.get("net_of_resting"),
                "kcalPerKgFat": fields.get("kcal_per_kg_fat"),
                "metabolicAdaptation": fields.get("metabolic_adaptation"),
                "kgHalfLifeDays": fields.get("kg_half_life_days"),
                "kgPer100KcalPerDay": fields.get("kg_per_100_kcal_per_day"),
                "realizationFactor": fields.get("realization_factor"),
            }
        }
        return self._settings_result(
            await self.client.execute(mutation, variables), "saveFitnessEstimationConfig"
        )

    async def set_class_type_met(
        self, class_type_id: int, met_value: Optional[float]
    ) -> Dict[str, Any]:
        """``met_value=None`` borra el override y devuelve la actividad a su default."""
        mutation = f"""
            mutation SetClassTypeMet($input: SetClassTypeMetInput!) {{
                setClassTypeMet(input: $input) {{
                    success
                    error
                    settings {{ {_SETTINGS_FIELDS} }}
                }}
            }}
        """
        variables = {"input": {"classTypeId": class_type_id, "metValue": met_value}}
        return self._settings_result(
            await self.client.execute(mutation, variables), "setClassTypeMet"
        )

    @staticmethod
    def _settings_result(result: Optional[Dict[str, Any]], key: str) -> Dict[str, Any]:
        payload = (result or {}).get(key)
        if not payload:
            return {"success": False, "error": "Sin respuesta del servidor", "settings": None}
        return {
            "success": bool(payload.get("success")),
            "error": payload.get("error"),
            "settings": _map_settings(payload.get("settings")),
        }
