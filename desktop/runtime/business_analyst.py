"""AI Business Architect — recommends agents based on company profile."""
from __future__ import annotations

from typing import Any

from .company_profile import CompanyProfile


AGENT_CATALOG: list[dict[str, Any]] = [
    {
        "id": "marketing-agent",
        "name": "Marketing Agent",
        "description": "Plans campaigns, monitors performance, and suggests optimizations.",
        "responsibilities": ["Campaign planning", "Channel analysis", "ROI tracking"],
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
        "name": "Sales Analyst",
        "description": "Analyzes sales trends, identifies opportunities, and forecasts revenue.",
        "responsibilities": ["Sales reporting", "Trend analysis", "Forecasting"],
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
        "name": "Content Agent",
        "description": "Generates content ideas, drafts posts, and prepares media briefs.",
        "responsibilities": ["Content ideation", "Draft creation", "Publishing prep"],
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
        "name": "Inventory Agent",
        "description": "Monitors stock levels, alerts on low inventory, and suggests reorders.",
        "responsibilities": ["Stock monitoring", "Reorder alerts", "Demand forecasting"],
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
        "name": "Customer Support Agent",
        "description": "Drafts responses, categorizes tickets, and escalates complex issues.",
        "responsibilities": ["Ticket triage", "Response drafting", "Escalation"],
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
        "name": "CEO Copilot",
        "description": "Executive summary, KPI monitoring, and strategic recommendations.",
        "responsibilities": ["Executive briefing", "KPI monitoring", "Decision support"],
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
            reasons.append(f"You use {', '.join(m.title() for m in matched)}.")
        if goal_match:
            score += 2
            matched = goals & set(agent.get("matchGoals", []))
            reasons.append(f"Aligned with your {', '.join(m.title() for m in matched)} goals.")
        if agent["id"] == "ceo-copilot" and profile.identity.get("name"):
            score += 1
            reasons.append("Provides executive overview for your business.")

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
                "reason": "Optional for now.",
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
                "reason": "Recommended as a starting point.",
                "selected": True,
            })
    return recommendations
