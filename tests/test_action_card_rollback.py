"""An action card never names a rollback that the target's own service card forbids.

S1 rehearsal: `container.start` declared `rollback: container.stop` while the cache's service card says
`never: [container.stop]`. The judge flagged the clash in every verdict, and the approver was shown a way back the
service forbids."""
from __future__ import annotations

from argus.actions.catalog import ACTION_CATALOGUE
from argus.actions.cards import load_action_cards
from argus.adapters.outbound.config_adapters import YamlInventory
from test_core import ROOT


def test_no_rollback_is_an_action_the_service_card_forbids():
    cards = load_action_cards(ROOT / "config" / "actions")
    inventory = YamlInventory((ROOT / "config" / "inventory.yaml").read_text(encoding="utf-8"))
    clashes = []
    for info in inventory.targets():
        service = info.service_card()
        if service is None:
            continue
        for action in service.safe_actions:
            card = cards.get(action)
            if card is not None and card.rollback in ACTION_CATALOGUE and card.rollback in service.never:
                clashes.append((str(info.ref), action, card.rollback))
    assert clashes == []


def test_start_has_no_automatic_rollback_and_says_why():
    from argus.application.approval_view import _reversible
    card = load_action_cards(ROOT / "config" / "actions")["container.start"]
    assert card.rollback.startswith("none:") and "unavailable service" in card.rollback
    assert _reversible(card.rollback) is False            # the approver sees "Reversible: no"
