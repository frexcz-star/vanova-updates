"""Update state machine — explicit states and transitions."""
from __future__ import annotations

from enum import Enum
from typing import Optional


class UpdateState(str, Enum):
    IDLE = "idle"
    CHECKING = "checking"
    AVAILABLE = "available"
    UP_TO_DATE = "up_to_date"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    VERIFYING = "verifying"
    READY_TO_INSTALL = "ready_to_install"
    BACKING_UP = "backing_up"
    INSTALLING = "installing"
    RESTARTING = "restarting"
    VERIFYING_INSTALL = "verifying_install"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLBACK = "rollback"
    OFFLINE = "offline"


TERMINAL = frozenset({
    UpdateState.IDLE,
    UpdateState.UP_TO_DATE,
    UpdateState.COMPLETED,
    UpdateState.FAILED,
    UpdateState.CANCELLED,
    UpdateState.OFFLINE,
})


def can_transition(current: UpdateState, target: UpdateState) -> bool:
    allowed = {
        UpdateState.IDLE: {UpdateState.CHECKING, UpdateState.OFFLINE},
        UpdateState.CHECKING: {UpdateState.AVAILABLE, UpdateState.UP_TO_DATE, UpdateState.OFFLINE, UpdateState.FAILED},
        UpdateState.AVAILABLE: {UpdateState.DOWNLOADING, UpdateState.IDLE, UpdateState.CANCELLED},
        UpdateState.UP_TO_DATE: {UpdateState.IDLE, UpdateState.CHECKING},
        UpdateState.DOWNLOADING: {UpdateState.DOWNLOADED, UpdateState.FAILED, UpdateState.CANCELLED},
        UpdateState.DOWNLOADED: {UpdateState.VERIFYING, UpdateState.FAILED},
        UpdateState.VERIFYING: {UpdateState.READY_TO_INSTALL, UpdateState.FAILED},
        UpdateState.READY_TO_INSTALL: {UpdateState.BACKING_UP, UpdateState.INSTALLING, UpdateState.CANCELLED},
        UpdateState.BACKING_UP: {UpdateState.INSTALLING, UpdateState.FAILED},
        UpdateState.INSTALLING: {UpdateState.RESTARTING, UpdateState.FAILED, UpdateState.ROLLBACK},
        UpdateState.RESTARTING: {UpdateState.VERIFYING_INSTALL, UpdateState.FAILED, UpdateState.ROLLBACK},
        UpdateState.VERIFYING_INSTALL: {UpdateState.COMPLETED, UpdateState.ROLLBACK, UpdateState.FAILED},
        UpdateState.FAILED: {UpdateState.IDLE, UpdateState.ROLLBACK},
        UpdateState.ROLLBACK: {UpdateState.IDLE, UpdateState.FAILED},
        UpdateState.CANCELLED: {UpdateState.IDLE},
        UpdateState.COMPLETED: {UpdateState.IDLE},
        UpdateState.OFFLINE: {UpdateState.IDLE, UpdateState.CHECKING},
    }
    return target in allowed.get(current, set())


def transition(current: UpdateState, target: UpdateState) -> UpdateState:
    if not can_transition(current, target):
        raise ValueError(f"Invalid transition {current.value} → {target.value}")
    return target
