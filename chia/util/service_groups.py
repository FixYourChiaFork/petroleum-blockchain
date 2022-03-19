from typing import Generator, KeysView

SERVICES_FOR_GROUP = {
    "all": "petroleum_harvester petroleum_timelord_launcher petroleum_timelord petroleum_farmer petroleum_full_node petroleum_wallet".split(),
    "node": "petroleum_full_node".split(),
    "harvester": "petroleum_harvester".split(),
    "farmer": "petroleum_harvester petroleum_farmer petroleum_full_node petroleum_wallet".split(),
    "farmer-no-wallet": "petroleum_harvester petroleum_farmer petroleum_full_node".split(),
    "farmer-only": "petroleum_farmer".split(),
    "timelord": "petroleum_timelord_launcher petroleum_timelord petroleum_full_node".split(),
    "timelord-only": "petroleum_timelord".split(),
    "timelord-launcher-only": "petroleum_timelord_launcher".split(),
    "wallet": "petroleum_wallet petroleum_full_node".split(),
    "wallet-only": "petroleum_wallet".split(),
    "introducer": "petroleum_introducer".split(),
    "simulator": "petroleum_full_node_simulator".split(),
}


def all_groups() -> KeysView[str]:
    return SERVICES_FOR_GROUP.keys()


def services_for_groups(groups) -> Generator[str, None, None]:
    for group in groups:
        for service in SERVICES_FOR_GROUP[group]:
            yield service


def validate_service(service: str) -> bool:
    return any(service in _ for _ in SERVICES_FOR_GROUP.values())
