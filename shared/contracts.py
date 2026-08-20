"""VANOVA Data Contracts — shared schemas between Cloud, Connector and Dashboard.

These are the canonical data structures. Every component consumes these shapes.
They are the contract between VANOVA Web, VANOVA Cloud and VANOVA Connector.

Data provenance modes:
- REAL   -> source is a connected, real business system (e.g. Shopify, ERP)
- MOCK   -> development sample data, clearly labelled
- EMPTY  -> source not connected; no data invented
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field

# ---------------------------------------------------------------
# Enums
# ---------------------------------------------------------------

# Data provenance
REAL = "real"
MOCK = "mock"
EMPTY = "empty"
DATA_MODES = (REAL, MOCK, EMPTY)

# Data source status
CONNECTED = "connected"
NOT_CONNECTED = "not_connected"
SYNCING = "syncing"
ERROR = "error"
NEEDS_CONFIGURATION = "needs_configuration"
SOURCE_STATUSES = (CONNECTED, NOT_CONNECTED, SYNCING, ERROR, NEEDS_CONFIGURATION)

# Agent status
AGENT_ACTIVE = "active"
AGENT_MONITORING = "monitoring"
AGENT_NEEDS_ATTENTION = "needs_attention"
AGENT_OFFLINE = "offline"
AGENT_STATUSES = (AGENT_ACTIVE, AGENT_MONITORING, AGENT_NEEDS_ATTENTION, AGENT_OFFLINE)

# Autonomy levels
AUTONOMY_AUTO = "auto"
AUTONOMY_APPROVAL = "approval"
AUTONOMY_HUMAN = "human"
AUTONOMY_LEVELS = (AUTONOMY_AUTO, AUTONOMY_APPROVAL, AUTONOMY_HUMAN)

# Activity status
ACTIVITY_RUNNING = "running"
ACTIVITY_COMPLETED = "completed"
ACTIVITY_NEEDS_ATTENTION = "needs_attention"
ACTIVITY_FAILED = "failed"
ACTIVITY_STATUSES = (ACTIVITY_RUNNING, ACTIVITY_COMPLETED, ACTIVITY_NEEDS_ATTENTION, ACTIVITY_FAILED)


# ---------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------
class DashboardOverview(BaseModel):
    revenue: float = 0
    revenueChange: str = "0%"
    revenueUp: bool = True
    orders: int = 0
    ordersChange: str = "0%"
    ordersUp: bool = True
    grossMargin: float = 0
    grossMarginChange: str = "0%"
    grossMarginUp: bool = True
    customers: int = 0
    customersChange: str = "0%"
    customersUp: bool = True
    inventoryValue: float = 0
    inventoryChange: str = "0%"
    inventoryUp: bool = True
    # provenance: which data mode each number came from
    dataMode: str = EMPTY
    fetchedAt: Optional[str] = None


class DashboardData(BaseModel):
    overview: DashboardOverview = Field(default_factory=DashboardOverview)
    priorities: list[dict] = Field(default_factory=list)     # AI Priority
    activity: list[dict] = Field(default_factory=list)       # AI Activity
    agents: list[dict] = Field(default_factory=list)         # Agent
    decisions: list[dict] = Field(default_factory=list)      # Decision
    automations: list[dict] = Field(default_factory=list)    # Automation
    dataMode: str = EMPTY
    sources: list[dict] = Field(default_factory=list)        # DataSource status
    fetchedAt: Optional[str] = None


# ---------------------------------------------------------------
# AI Insight / Priority
# ---------------------------------------------------------------
class AIInsight(BaseModel):
    id: str
    agent: str
    type: str                     # risk | opportunity | recommendation | anomaly | prediction
    priority: str                 # high | medium | low
    title: str
    description: str
    impact: str
    confidence: str
    recommendation: str
    status: str = "open"          # open | reviewed | approved | dismissed
    createdAt: Optional[str] = None


# ---------------------------------------------------------------
# AI Activity
# ---------------------------------------------------------------
class AIActivity(BaseModel):
    id: str
    agent: str
    action: str
    status: str = ACTIVITY_COMPLETED
    timestamp: Optional[str] = None
    result: Optional[str] = None


# ---------------------------------------------------------------
# Decision
# ---------------------------------------------------------------
class Decision(BaseModel):
    id: str
    title: str
    recommendation: str
    impact: str
    confidence: str
    autonomyLevel: str = AUTONOMY_APPROVAL
    status: str = "pending"       # pending | approved | rejected | investigating
    agent: Optional[str] = None


# ---------------------------------------------------------------
# Agent
# ---------------------------------------------------------------
class Agent(BaseModel):
    id: str
    name: str
    status: str = AGENT_ACTIVE
    lastActivity: Optional[str] = None
    currentTask: Optional[str] = None
    autonomyLevel: str = AUTONOMY_APPROVAL
    insightsGenerated: int = 0
    tasksCompleted: int = 0
    short: Optional[str] = None
    color: Optional[str] = None
    description: Optional[str] = None


# ---------------------------------------------------------------
# Automation (cronjob)
# ---------------------------------------------------------------
class Automation(BaseModel):
    id: str
    name: str
    schedule: str
    agent: str
    trigger: str = "schedule"
    status: str = ACTIVITY_COMPLETED
    lastExecution: Optional[str] = None
    nextExecution: Optional[str] = None
    lastResult: Optional[str] = None
    autonomyLevel: str = AUTONOMY_AUTO


# ---------------------------------------------------------------
# Data Source
# ---------------------------------------------------------------
class DataSource(BaseModel):
    id: str
    name: str
    status: str = NOT_CONNECTED
    source: str = ""
    lastSync: Optional[str] = None
    recordCount: int = 0
    error: Optional[str] = None
    permissions: str = "read"
    dataMode: str = EMPTY


# ---------------------------------------------------------------
# Connector / Device
# ---------------------------------------------------------------
class Device(BaseModel):
    id: str
    name: str
    status: str = "offline"       # online | offline
    lastHeartbeat: Optional[str] = None
    version: Optional[str] = None
    workspaceId: Optional[str] = None
    os: Optional[str] = None


# ---------------------------------------------------------------
# Hermes interaction result (no chain-of-thought)
# ---------------------------------------------------------------
class HermesResult(BaseModel):
    summary: str
    sourcesUsed: list[str] = Field(default_factory=list)
    agentsUsed: list[str] = Field(default_factory=list)
    dataUsed: list[str] = Field(default_factory=list)
    actionsTaken: list[str] = Field(default_factory=list)
    recommendation: Optional[str] = None
    status: str = ACTIVITY_COMPLETED
