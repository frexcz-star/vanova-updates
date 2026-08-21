"""AI Business Architect — recommends agents based on company profile."""
from __future__ import annotations

from typing import Any

from .company_profile import CompanyProfile


AGENT_CATALOG: list[dict[str, Any]] = [
    {
        "id": "marketing-agent",
        "name": "Agente de Marketing",
        "description": "Planea campañas, vigila el rendimiento y sugiere mejoras para vender más.",
        "responsibilities": ["Planificación de campañas", "Análisis de canales", "Seguimiento del retorno"],
        "tools": ["analytics", "content_calendar"],
        "integrations": ["instagram", "shopify"],
        "triggers": ["schedule", "manual"],
        "schedules": ["Daily 18:00"],
        "permissions": ["read_analytics", "suggest_actions"],
        "matchChannels": ["instagram", "facebook", "tiktok"],
        "matchGoals": ["marketing"],
    },
    {
        "id": "sales-analyst",
        "name": "Analista de Ventas",
        "description": "Detecta oportunidades y tendencias de venta, y anticipa los ingresos.",
        "responsibilities": ["Informe de ventas", "Análisis de tendencias", "Previsión de ingresos"],
        "tools": ["shopify_admin", "reports"],
        "integrations": ["shopify"],
        "triggers": ["schedule", "event"],
        "schedules": ["Daily 08:00"],
        "permissions": ["read_orders", "read_products"],
        "matchChannels": ["shopify", "amazon"],
        "matchGoals": ["sales"],
    },
    {
        "id": "content-agent",
        "name": "Agente de Contenido",
        "description": "Genera ideas de contenido, redacta publicaciones y prepara los materiales.",
        "responsibilities": ["Ideas de contenido", "Redacción de borradores", "Preparación de publicaciones"],
        "tools": ["llm", "creatomate"],
        "integrations": ["instagram"],
        "triggers": ["schedule", "manual"],
        "schedules": ["Weekly Monday 09:00"],
        "permissions": ["generate_content", "queue_review"],
        "matchChannels": ["instagram", "tiktok"],
        "matchGoals": ["content", "marketing"],
    },
    {
        "id": "inventory-agent",
        "name": "Agente de Stock",
        "description": "Vigila el inventario, avisa de roturas de stock y sugiere reposiciones.",
        "responsibilities": ["Control de stock", "Avisos de reposición", "Previsión de demanda"],
        "tools": ["shopify_admin", "erp"],
        "integrations": ["shopify"],
        "triggers": ["schedule", "event"],
        "schedules": ["Daily 07:00"],
        "permissions": ["read_inventory"],
        "matchChannels": ["shopify"],
        "matchGoals": ["inventory"],
    },
    {
        "id": "support-agent",
        "name": "Agente de Atención al Cliente",
        "description": "Redacta respuestas, clasifica consultas y escala los casos complejos.",
        "responsibilities": ["Clasificación de consultas", "Redacción de respuestas", "Escalado de casos"],
        "tools": ["email", "crm"],
        "integrations": ["shopify", "email"],
        "triggers": ["event", "manual"],
        "schedules": [],
        "permissions": ["read_tickets", "draft_responses"],
        "matchChannels": ["email", "shopify"],
        "matchGoals": ["customer support"],
    },
    {
        "id": "ceo-copilot",
        "name": "Copiloto de Dirección",
        "description": "Resumen ejecutivo, seguimiento de indicadores clave y recomendaciones estratégicas.",
        "responsibilities": ["Informe ejecutivo", "Seguimiento de indicadores", "Apoyo a la decisión"],
        "tools": ["analytics", "reports"],
        "integrations": ["shopify", "instagram"],
        "triggers": ["schedule", "manual"],
        "schedules": ["Weekly Monday 08:00"],
        "permissions": ["read_all"],
        "matchChannels": [],
        "matchGoals": ["marketing", "sales", "content", "inventory"],
    },
]


def recommend(profile: CompanyProfile) -> list[dict[str, Any]]:
    channels = {c.lower() for c in profile.channels}
    goals = {g.lower() for g in profile.goals}
    recommendations = []

    for agent in AGENT_CATALOG:
        channel_match = bool(channels & set(agent.get("matchChannels", [])))
        goal_match = bool(goals & set(agent.get("matchGoals", [])))
        score = 0
        reasons = []

        if channel_match:
            score += 2
            matched = channels & set(agent.get("matchChannels", []))
            reasons.append(f"Usas {', '.join(m.title() for m in matched)}.")
        if goal_match:
            score += 2
            matched = goals & set(agent.get("matchGoals", []))
            reasons.append(f"Alineado con tus objetivos de {', '.join(m.title() for m in matched)}.")
        if agent["id"] == "ceo-copilot" and profile.identity.get("name"):
            score += 1
            reasons.append("Te da una visión general de tu negocio.")

        if score >= 2:
            recommendations.append({
                **{k: v for k, v in agent.items() if not k.startswith("match")},
                "recommended": True,
                "score": score,
                "reason": " ".join(reasons) or agent["description"],
                "selected": score >= 3,
            })
        elif score == 1:
            recommendations.append({
                **{k: v for k, v in agent.items() if not k.startswith("match")},
                "recommended": False,
                "score": score,
                "reason": "Opcional por ahora.",
                "selected": False,
            })

    recommendations.sort(key=lambda x: x["score"], reverse=True)
    if not recommendations:
        # Default minimum set
        for agent in AGENT_CATALOG[:2]:
            recommendations.append({
                **{k: v for k, v in agent.items() if not k.startswith("match")},
                "recommended": True,
                "score": 1,
                "reason": "Recomendado como punto de partida.",
                "selected": True,
            })
    return recommendations
