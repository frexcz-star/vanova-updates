"""VANOVA Mock Data — DEVELOPMENT SAMPLE DATA.

This module returns clearly-labelled sample data. Every payload carries
`dataMode: "mock"` so the UI can distinguish it from real data.

It is used ONLY when DATA_MODE=mock (default during development) or as
fallback when a source is disconnected. It is NEVER presented as real
MOOVING PAPER data.
"""
from __future__ import annotations

from datetime import datetime, timezone

# The 12 VANOVA specialist agents
MAIOS_AGENTS = [
    {"id": "trend", "name": "Cazador de Tendencias", "short": "TH", "color": "#0ea5e9", "description": "Detecta las tendencias emergentes de tu sector.", "autonomyLevel": "auto", "status": "active"},
    {"id": "licensing", "name": "Inteligencia de Licencias", "short": "LI", "color": "#8b5cf6", "description": "Analiza el rendimiento y el riesgo de cada licencia.", "autonomyLevel": "approval", "status": "active"},
    {"id": "product", "name": "Diseñador de Producto IA", "short": "PD", "color": "#f43f5e", "description": "Propone diseños y conceptos de producto.", "autonomyLevel": "auto", "status": "monitoring"},
    {"id": "pricing", "name": "IA de Precios", "short": "PR", "color": "#f59e0b", "description": "Recomienda precios y promociones óptimos.", "autonomyLevel": "approval", "status": "active"},
    {"id": "sales", "name": "Copiloto de Ventas", "short": "SC", "color": "#22c55e", "description": "Ayuda en las ventas y a detectar oportunidades.", "autonomyLevel": "auto", "status": "active"},
    {"id": "forecast", "name": "IA de Previsión", "short": "FC", "color": "#3b82f6", "description": "Predice la demanda y detecta roturas de stock.", "autonomyLevel": "auto", "status": "active"},
    {"id": "factory", "name": "Optimizador de Producción", "short": "FO", "color": "#14b8a6", "description": "Maximiza la eficiencia de la línea de producción.", "autonomyLevel": "auto", "status": "monitoring"},
    {"id": "procurement", "name": "IA de Compras", "short": "PU", "color": "#a855f7", "description": "Gestiona las compras y el riesgo de proveedores.", "autonomyLevel": "approval", "status": "needs_attention"},
    {"id": "marketing", "name": "Estudio de Marketing IA", "short": "MK", "color": "#ec4899", "description": "Crea campañas y contenido de marketing.", "autonomyLevel": "approval", "status": "active"},
    {"id": "customer", "name": "IA de Fidelización", "short": "CS", "color": "#6366f1", "description": "Previene la pérdida de clientes y mejora la retención.", "autonomyLevel": "auto", "status": "active"},
    {"id": "finance", "name": "Inteligencia Financiera", "short": "FI", "color": "#10b981", "description": "Análisis financiero y detección de anomalías.", "autonomyLevel": "approval", "status": "active"},
    {"id": "ceo", "name": "Copiloto de Dirección", "short": "CC", "color": "#dc2626", "description": "Síntesis ejecutiva para la dirección.", "autonomyLevel": "human", "status": "active"},
]

MOCK_DASHBOARD = {
    "overview": {
        "revenue": 284312.0, "revenueChange": "+12.4%", "revenueUp": True,
        "orders": 1247, "ordersChange": "+8.1%", "ordersUp": True,
        "grossMargin": 21.3, "grossMarginChange": "-0.8%", "grossMarginUp": False,
        "customers": 8942, "customersChange": "+4.2%", "customersUp": True,
        "inventoryValue": 1203450.0, "inventoryChange": "-2.1%", "inventoryUp": False,
        "dataMode": "mock",
    },
    "priorities": [
        {"id": "p1", "agent": "IA de Previsión", "type": "risk", "priority": "high",
         "title": "Possible stockout detected for Mooving Planner A5",
         "description": "Forecast indicates current stock does not cover projected demand for back-to-school.",
         "impact": "€12,400", "confidence": "94%",
         "recommendation": "Increase order by 500 units.", "status": "open"},
        {"id": "p2", "agent": "Cazador de Tendencias", "type": "opportunity", "priority": "medium",
         "title": "Pastel metallic stationery trending +34%",
         "description": "Trend detected across monitored channels (social, marketplaces, study forums).",
         "impact": "€8,100", "confidence": "89%",
         "recommendation": "Launch a pilot line and validate.", "status": "open"},
    ],
    "activity": [
        {"id": "a1", "agent": "IA de Previsión", "action": "Actualizada la previsión de demanda de 24 productos.", "status": "completed", "result": "3 productos marcados con stock bajo"},
        {"id": "a2", "agent": "Estudio de Marketing IA", "action": "Generados 6 conceptos de campaña para la vuelta al cole.", "status": "completed"},
        {"id": "a3", "agent": "IA de Compras", "action": "Riesgo de proveedor detectado.", "status": "needs_attention", "result": "InkCorp retrasos del 12%"},
        {"id": "a4", "agent": "Cazador de Tendencias", "action": "Detectada una tendencia emergente del sector.", "status": "completed"},
        {"id": "a5", "agent": "Hermes", "action": "Análisis de negocio diario completado.", "status": "completed"},
    ],
    "agents": [
        {**a, "insightsGenerated": (142 - i * 9), "tasksCompleted": (389 - i * 20),
         "lastActivity": "Hace 12 min", "currentTask": "Monitoring sources"}
        for i, a in enumerate(MAIOS_AGENTS)
    ],
    "decisions": [
        {"id": "d1", "title": "Increase order quantity for Mooving Planner A5?",
         "recommendation": "+500 units", "impact": "+€12,400 revenue", "confidence": "91%",
         "autonomyLevel": "approval", "status": "pending", "agent": "IA de Previsión"},
        {"id": "d2", "title": "Reevaluate pricing for the Escolar family?",
         "recommendation": "+4% margin", "impact": "+€19,300", "confidence": "88%",
         "autonomyLevel": "approval", "status": "pending", "agent": "Inteligencia Financiera"},
    ],
    "automations": [
        {"id": "au1", "name": "Informe ejecutivo diario", "schedule": "Todos los días — 07:30", "agent": "Copiloto de Dirección", "trigger": "schedule", "status": "active"},
        {"id": "au2", "name": "Previsión de demanda", "schedule": "Todos los días — 06:30", "agent": "IA de Previsión", "trigger": "schedule", "status": "active"},
        {"id": "au3", "name": "Seguimiento de tendencias", "schedule": "Cada 6 horas", "agent": "Cazador de Tendencias", "trigger": "schedule", "status": "active"},
        {"id": "au4", "name": "Análisis financiero", "schedule": "Todos los días — 07:00", "agent": "Inteligencia Financiera", "trigger": "schedule", "status": "active"},
        {"id": "au5", "name": "Generación de contenido de marketing", "schedule": "Cada lunes", "agent": "Estudio de Marketing IA", "trigger": "schedule", "status": "active"},
    ],
    "sources": [
        {"id": "sales", "name": "Sales", "status": "connected", "source": "Shopify", "recordCount": 1247, "dataMode": "mock"},
        {"id": "products", "name": "Products", "status": "connected", "source": "Shopify", "recordCount": 320, "dataMode": "mock"},
        {"id": "inventory", "name": "Inventory", "status": "connected", "source": "Shopify", "recordCount": 210, "dataMode": "mock"},
        {"id": "customers", "name": "Customers", "status": "connected", "source": "Shopify", "recordCount": 8942, "dataMode": "mock"},
        {"id": "production", "name": "Production", "status": "needs_configuration", "source": "", "recordCount": 0, "dataMode": "empty"},
        {"id": "logistics", "name": "Logistics", "status": "needs_configuration", "source": "", "recordCount": 0, "dataMode": "empty"},
        {"id": "finance", "name": "Finance", "status": "needs_configuration", "source": "", "recordCount": 0, "dataMode": "empty"},
        {"id": "marketing", "name": "Marketing", "status": "connected", "source": "Instagram", "recordCount": 86, "dataMode": "mock"},
        {"id": "licensing", "name": "Licensing", "status": "needs_configuration", "source": "", "recordCount": 0, "dataMode": "empty"},
    ],
    "dataMode": "mock",
}


def get_mock_dashboard():
    data = json_deepcopy(MOCK_DASHBOARD)
    data["fetchedAt"] = datetime.now(timezone.utc).isoformat()
    return data


def json_deepcopy(obj):
    import json
    return json.loads(json.dumps(obj))
