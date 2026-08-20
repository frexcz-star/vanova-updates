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
    {"id": "trend", "name": "Trend Hunter", "short": "TH", "color": "#0ea5e9", "description": "Detects emerging stationery and licensing trends.", "autonomyLevel": "auto", "status": "active"},
    {"id": "licensing", "name": "Licensing Intelligence", "short": "LI", "color": "#8b5cf6", "description": "Analyzes performance and risk of each license.", "autonomyLevel": "approval", "status": "active"},
    {"id": "product", "name": "Product Designer AI", "short": "PD", "color": "#f43f5e", "description": "Proposes product designs and concepts.", "autonomyLevel": "auto", "status": "monitoring"},
    {"id": "pricing", "name": "Pricing AI", "short": "PR", "color": "#f59e0b", "description": "Recommends optimal pricing and promotions.", "autonomyLevel": "approval", "status": "active"},
    {"id": "sales", "name": "Sales Copilot", "short": "SC", "color": "#22c55e", "description": "Assists in sales and opportunity detection.", "autonomyLevel": "auto", "status": "active"},
    {"id": "forecast", "name": "Forecast AI", "short": "FC", "color": "#3b82f6", "description": "Predicts demand and detects stockouts.", "autonomyLevel": "auto", "status": "active"},
    {"id": "factory", "name": "Factory Optimizer", "short": "FO", "color": "#14b8a6", "description": "Maximizes production line efficiency.", "autonomyLevel": "auto", "status": "monitoring"},
    {"id": "procurement", "name": "Procurement AI", "short": "PU", "color": "#a855f7", "description": "Manages purchasing and supplier risk.", "autonomyLevel": "approval", "status": "needs_attention"},
    {"id": "marketing", "name": "Marketing Studio AI", "short": "MK", "color": "#ec4899", "description": "Creates campaigns and marketing content.", "autonomyLevel": "approval", "status": "active"},
    {"id": "customer", "name": "Customer Success AI", "short": "CS", "color": "#6366f1", "description": "Prevents churn and improves retention.", "autonomyLevel": "auto", "status": "active"},
    {"id": "finance", "name": "Financial Intelligence", "short": "FI", "color": "#10b981", "description": "Financial analysis and anomaly detection.", "autonomyLevel": "approval", "status": "active"},
    {"id": "ceo", "name": "CEO Copilot", "short": "CC", "color": "#dc2626", "description": "Executive synthesis for leadership.", "autonomyLevel": "human", "status": "active"},
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
        {"id": "p1", "agent": "Forecast AI", "type": "risk", "priority": "high",
         "title": "Possible stockout detected for Mooving Planner A5",
         "description": "Forecast indicates current stock does not cover projected demand for back-to-school.",
         "impact": "€12,400", "confidence": "94%",
         "recommendation": "Increase order by 500 units.", "status": "open"},
        {"id": "p2", "agent": "Trend Hunter", "type": "opportunity", "priority": "medium",
         "title": "Pastel metallic stationery trending +34%",
         "description": "Trend detected across monitored channels (social, marketplaces, study forums).",
         "impact": "€8,100", "confidence": "89%",
         "recommendation": "Launch a pilot line and validate.", "status": "open"},
    ],
    "activity": [
        {"id": "a1", "agent": "Forecast AI", "action": "Updated demand forecast for 24 products.", "status": "completed", "result": "3 products flagged low stock"},
        {"id": "a2", "agent": "Marketing Studio AI", "action": "Generated 6 campaign concepts for back-to-school.", "status": "completed"},
        {"id": "a3", "agent": "Procurement AI", "action": "Detected supplier risk.", "status": "needs_attention", "result": "InkCorp delays 12%"},
        {"id": "a4", "agent": "Trend Hunter", "action": "Detected emerging stationery trend.", "status": "completed"},
        {"id": "a5", "agent": "Hermes", "action": "Completed daily business analysis.", "status": "completed"},
    ],
    "agents": [
        {**a, "insightsGenerated": (142 - i * 9), "tasksCompleted": (389 - i * 20),
         "lastActivity": "Hace 12 min", "currentTask": "Monitoring sources"}
        for i, a in enumerate(MAIOS_AGENTS)
    ],
    "decisions": [
        {"id": "d1", "title": "Increase order quantity for Mooving Planner A5?",
         "recommendation": "+500 units", "impact": "+€12,400 revenue", "confidence": "91%",
         "autonomyLevel": "approval", "status": "pending", "agent": "Forecast AI"},
        {"id": "d2", "title": "Reevaluate pricing for the Escolar family?",
         "recommendation": "+4% margin", "impact": "+€19,300", "confidence": "88%",
         "autonomyLevel": "approval", "status": "pending", "agent": "Financial Intelligence"},
    ],
    "automations": [
        {"id": "au1", "name": "Daily Executive Brief", "schedule": "Every day — 07:30", "agent": "CEO Copilot", "trigger": "schedule", "status": "active"},
        {"id": "au2", "name": "Demand Forecast", "schedule": "Every day — 06:30", "agent": "Forecast AI", "trigger": "schedule", "status": "active"},
        {"id": "au3", "name": "Trend Monitoring", "schedule": "Every 6 hours", "agent": "Trend Hunter", "trigger": "schedule", "status": "active"},
        {"id": "au4", "name": "Financial Analysis", "schedule": "Every day — 07:00", "agent": "Financial Intelligence", "trigger": "schedule", "status": "active"},
        {"id": "au5", "name": "Marketing Content Generation", "schedule": "Every Monday", "agent": "Marketing Studio AI", "trigger": "schedule", "status": "active"},
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
