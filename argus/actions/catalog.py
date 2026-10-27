"""Closed action catalogue and safety boundaries (ACR-0019 §3.3).

The model never writes commands; it selects from typed actions in this closed catalogue.
Actions in NEVER_OFFERED_ACTIONS can never be registered or executed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argus.actions.cards import ServiceCard


@dataclass(frozen=True)
class ActionSpec:
    name: str
    model_name: str
    intent: str
    description: str


NEVER_OFFERED_ACTIONS: frozenset[str] = frozenset({
    "container.exec",
    "docker.restart_daemon",
    "container.delete_volume",
    "host.flush_firewall",
    "host.change_clock",
    "argus.restart",
    "database.free_sql",
    "host.install_package",
    "host.create_user",
})


ACTION_CATALOGUE: dict[str, ActionSpec] = {
    "container.start": ActionSpec(
        name="container.start",
        model_name="start_container",
        intent="start",
        description="Start a stopped or exited container",
    ),
    "container.restart": ActionSpec(
        name="container.restart",
        model_name="restart_container",
        intent="start",
        description="Restart a running or looping container",
    ),
    "container.stop": ActionSpec(
        name="container.stop",
        model_name="stop_container",
        intent="stop",
        description="Gracefully stop a container",
    ),
    "container.pause": ActionSpec(
        name="container.pause",
        model_name="pause_container",
        intent="stop",
        description="Pause container execution processes",
    ),
    "container.unpause": ActionSpec(
        name="container.unpause",
        model_name="unpause_container",
        intent="start",
        description="Unpause a paused container",
    ),
    "container.update_resources": ActionSpec(
        name="container.update_resources",
        model_name="update_container_resources",
        intent="limit",
        description="Update resource bounds (memory, CPU shares) on a container",
    ),
    "container.signal": ActionSpec(
        name="container.signal",
        model_name="signal_container",
        intent="stop",
        description="Send an OS signal (e.g. SIGHUP, SIGTERM) to a container",
    ),
    "network.restore": ActionSpec(
        name="network.restore",
        model_name="restore_network",
        intent="network",
        description="Connect a lab container to its declared network, then leave the undeclared one (ACR-0035)",
    ),
    "deployment.rollback": ActionSpec(
        name="deployment.rollback",
        model_name="rollback_deployment",
        intent="rollback",
        description="Roll back a service to its previous stable image/configuration",
    ),
    "docker.prune_images": ActionSpec(
        name="docker.prune_images",
        model_name="prune_docker_images",
        intent="free_disk",
        description="Prune dangling, unreferenced container images to reclaim disk space",
    ),
    "docker.prune_build_cache": ActionSpec(
        name="docker.prune_build_cache",
        model_name="prune_docker_build_cache",
        intent="free_disk",
        description="Prune builder cache to reclaim disk space",
    ),
}

# Each released card must name the exact gateway route reviewed for that capability.
ACTION_ROUTES = {
    "container.start": "/containers/{name}/start",
    "container.restart": "/containers/{name}/restart",
    "container.stop": "/containers/{name}/stop",
    "network.restore": "/containers/{name}/network-restore",  # one worker call; the gateway does connect, then disconnect
}


def get_action_spec(name: str) -> ActionSpec:
    if name not in ACTION_CATALOGUE:
        raise KeyError(f"Unknown action '{name}'. Must be defined in ACTION_CATALOGUE.")
    return ACTION_CATALOGUE[name]


def is_action_permitted_on_service(action: str, service: ServiceCard) -> bool:
    """Verifies that an action is allowed by the target's ServiceCard."""
    if action not in ACTION_CATALOGUE or action in NEVER_OFFERED_ACTIONS:
        return False
    if action in service.never:
        return False
    return action in service.safe_actions
