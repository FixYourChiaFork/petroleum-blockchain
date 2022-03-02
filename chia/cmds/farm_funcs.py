from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, List, Optional

import aiohttp

from chia.cmds.units import units
from chia.consensus.block_record import BlockRecord
from chia.consensus.coinbase import create_puzzlehash_for_pk
from chia.rpc.farmer_rpc_client import FarmerRpcClient
from chia.rpc.full_node_rpc_client import FullNodeRpcClient
from chia.rpc.wallet_rpc_client import WalletRpcClient
from chia.types.blockchain_format.sized_bytes import bytes32
from chia.util.bech32m import encode_puzzle_hash
from chia.util.byte_types import hexstr_to_bytes
from chia.util.config import load_config, save_config, config_path_for_filename
from chia.util.default_root import DEFAULT_ROOT_PATH
from chia.util.ints import uint16, uint64
from chia.util.misc import format_bytes, format_minutes
from chia.util.network import is_localhost
from chia.util.keychain import Keychain
from chia.wallet.derive_keys import master_sk_to_farmer_sk

SECONDS_PER_BLOCK = (24 * 3600) / 4608


async def get_harvesters(farmer_rpc_port: Optional[int]) -> Optional[Dict[str, Any]]:
    try:
        config = load_config(DEFAULT_ROOT_PATH, "config.yaml")
        self_hostname = config["self_hostname"]
        if farmer_rpc_port is None:
            farmer_rpc_port = config["farmer"]["rpc_port"]
        farmer_client = await FarmerRpcClient.create(self_hostname, uint16(farmer_rpc_port), DEFAULT_ROOT_PATH, config)
        plots = await farmer_client.get_harvesters()
    except Exception as e:
        if isinstance(e, aiohttp.ClientConnectorError):
            print(f"Connection error. Check if farmer is running at {farmer_rpc_port}")
        else:
            print(f"Exception from 'harvester' {e}")
        return None
    farmer_client.close()
    await farmer_client.await_closed()
    return plots


async def get_blockchain_state(rpc_port: Optional[int]) -> Optional[Dict[str, Any]]:
    blockchain_state = None
    try:
        config = load_config(DEFAULT_ROOT_PATH, "config.yaml")
        self_hostname = config["self_hostname"]
        if rpc_port is None:
            rpc_port = config["full_node"]["rpc_port"]
        client = await FullNodeRpcClient.create(self_hostname, uint16(rpc_port), DEFAULT_ROOT_PATH, config)
        blockchain_state = await client.get_blockchain_state()
    except Exception as e:
        if isinstance(e, aiohttp.ClientConnectorError):
            print(f"Connection error. Check if full node is running at {rpc_port}")
        else:
            print(f"Exception from 'full node' {e}")

    client.close()
    await client.await_closed()
    return blockchain_state

async def get_ph_balance(rpc_port: Optional[int], puzzle_hash: bytes32) -> Optional[uint64]:
    coins = None
    try:
        config = load_config(DEFAULT_ROOT_PATH, "config.yaml")
        self_hostname = config["self_hostname"]
        if rpc_port is None:
            rpc_port = config["full_node"]["rpc_port"]
        client = await FullNodeRpcClient.create(self_hostname, uint16(rpc_port), DEFAULT_ROOT_PATH, config)
        coins = await client.get_coin_records_by_puzzle_hash(puzzle_hash, False)
    except Exception as e:
        if isinstance(e, aiohttp.ClientConnectorError):
            print(f"Connection error. Check if full node is running at {rpc_port}")
        else:
            print(f"Exception from 'full node' {e}")

    client.close()
    await client.await_closed()
    return sum(coin.coin.amount for coin in coins)


async def get_average_block_time(rpc_port: Optional[int]) -> float:
    try:
        blocks_to_compare = 500
        config = load_config(DEFAULT_ROOT_PATH, "config.yaml")
        self_hostname = config["self_hostname"]
        if rpc_port is None:
            rpc_port = config["full_node"]["rpc_port"]
        client = await FullNodeRpcClient.create(self_hostname, uint16(rpc_port), DEFAULT_ROOT_PATH, config)
        blockchain_state = await client.get_blockchain_state()
        curr: Optional[BlockRecord] = blockchain_state["peak"]
        if curr is None or curr.height < (blocks_to_compare + 100):
            client.close()
            await client.await_closed()
            return SECONDS_PER_BLOCK
        while curr is not None and curr.height > 0 and not curr.is_transaction_block:
            curr = await client.get_block_record(curr.prev_hash)
        if curr is None:
            client.close()
            await client.await_closed()
            return SECONDS_PER_BLOCK

        past_curr = await client.get_block_record_by_height(curr.height - blocks_to_compare)
        while past_curr is not None and past_curr.height > 0 and not past_curr.is_transaction_block:
            past_curr = await client.get_block_record(past_curr.prev_hash)
        if past_curr is None:
            client.close()
            await client.await_closed()
            return SECONDS_PER_BLOCK

        client.close()
        await client.await_closed()
        return (curr.timestamp - past_curr.timestamp) / (curr.height - past_curr.height)

    except Exception as e:
        if isinstance(e, aiohttp.ClientConnectorError):
            print(f"Connection error. Check if full node is running at {rpc_port}")
        else:
            print(f"Exception from 'full node' {e}")

    client.close()
    await client.await_closed()
    return SECONDS_PER_BLOCK


async def get_wallets_stats(wallet_rpc_port: Optional[int]) -> Optional[Dict[str, Any]]:
    amounts = None
    try:
        config = load_config(DEFAULT_ROOT_PATH, "config.yaml")
        self_hostname = config["self_hostname"]
        if wallet_rpc_port is None:
            wallet_rpc_port = config["wallet"]["rpc_port"]
        wallet_client = await WalletRpcClient.create(self_hostname, uint16(wallet_rpc_port), DEFAULT_ROOT_PATH, config)
        amounts = await wallet_client.get_farmed_amount()
    #
    # Don't catch any exceptions, the caller will handle it
    #
    finally:
        wallet_client.close()
        await wallet_client.await_closed()

    return amounts


async def is_farmer_running(farmer_rpc_port: Optional[int]) -> bool:
    is_running = False
    try:
        config = load_config(DEFAULT_ROOT_PATH, "config.yaml")
        self_hostname = config["self_hostname"]
        if farmer_rpc_port is None:
            farmer_rpc_port = config["farmer"]["rpc_port"]
        farmer_client = await FarmerRpcClient.create(self_hostname, uint16(farmer_rpc_port), DEFAULT_ROOT_PATH, config)
        await farmer_client.get_connections()
        is_running = True
    except Exception as e:
        if isinstance(e, aiohttp.ClientConnectorError):
            print(f"Connection error. Check if farmer is running at {farmer_rpc_port}")
        else:
            print(f"Exception from 'farmer' {e}")

    farmer_client.close()
    await farmer_client.await_closed()
    return is_running


async def get_challenges(farmer_rpc_port: Optional[int]) -> Optional[List[Dict[str, Any]]]:
    signage_points = None
    try:
        config = load_config(DEFAULT_ROOT_PATH, "config.yaml")
        self_hostname = config["self_hostname"]
        if farmer_rpc_port is None:
            farmer_rpc_port = config["farmer"]["rpc_port"]
        farmer_client = await FarmerRpcClient.create(self_hostname, uint16(farmer_rpc_port), DEFAULT_ROOT_PATH, config)
        signage_points = await farmer_client.get_signage_points()
    except Exception as e:
        if isinstance(e, aiohttp.ClientConnectorError):
            print(f"Connection error. Check if farmer is running at {farmer_rpc_port}")
        else:
            print(f"Exception from 'farmer' {e}")

    farmer_client.close()
    await farmer_client.await_closed()
    return signage_points


async def challenges(farmer_rpc_port: Optional[int], limit: int) -> None:
    signage_points = await get_challenges(farmer_rpc_port)
    if signage_points is None:
        return None

    signage_points.reverse()
    if limit != 0:
        signage_points = signage_points[:limit]

    for signage_point in signage_points:
        print(
            (
                f"Hash: {signage_point['signage_point']['challenge_hash']} "
                f"Index: {signage_point['signage_point']['signage_point_index']}"
            )
        )


async def summary(
    rpc_port: Optional[int],
    wallet_rpc_port: Optional[int],
    harvester_rpc_port: Optional[int],
    farmer_rpc_port: Optional[int],
    fetch_staking_addresses: Optional[str],
    show_staking_balance: Optional[bool],
) -> None:
    config = load_config(DEFAULT_ROOT_PATH, "config.yaml")
    all_harvesters = await get_harvesters(farmer_rpc_port)
    blockchain_state = await get_blockchain_state(rpc_port)
    farmer_running = await is_farmer_running(farmer_rpc_port)

    wallet_not_ready: bool = False
    wallet_not_running: bool = False
    amounts = None
    try:
        amounts = await get_wallets_stats(wallet_rpc_port)
    except Exception as e:
        if isinstance(e, aiohttp.ClientConnectorError):
            wallet_not_running = True
        else:
            wallet_not_ready = True

    print("Farming status: ", end="")
    if blockchain_state is None:
        print("Not available")
    elif blockchain_state["sync"]["sync_mode"]:
        print("Syncing")
    elif not blockchain_state["sync"]["synced"]:
        print("Not synced or not connected to peers")
    elif not farmer_running:
        print("Not running")
    else:
        print("Farming")

    if amounts is not None:
        print(f"Total silicoin farmed: {amounts['farmed_amount'] / units['chia']}")
        print(f"User transaction fees: {amounts['fee_amount'] / units['chia']}")
        print(f"Block rewards: {(amounts['farmer_reward_amount'] + amounts['pool_reward_amount']) / units['chia']}")
        print(f"Last height farmed: {amounts['last_height_farmed']}")

    class PlotStats:
        total_plot_size = 0
        total_plots = 0
        staking_addresses = defaultdict(int)
        fingerprints = defaultdict(int)

    total_staking_balance = 0
    if all_harvesters is not None:
        harvesters_local: dict = {}
        harvesters_remote: dict = {}
        for harvester in all_harvesters["harvesters"]:
            ip = harvester["connection"]["host"]
            if is_localhost(ip):
                harvesters_local[harvester["connection"]["node_id"]] = harvester
            else:
                if ip not in harvesters_remote:
                    harvesters_remote[ip] = {}
                harvesters_remote[ip][harvester["connection"]["node_id"]] = harvester

        def process_harvesters(harvester_peers_in: dict):
            if get_staking_addresses_from_keys:
                keychain = Keychain()
                private_keys = keychain.get_all_private_keys()

                for sk, seed in private_keys:
                    ph = create_puzzlehash_for_pk(hexstr_to_bytes(str(master_sk_to_farmer_sk(sk).get_g1())))

                    PlotStats.staking_addresses[ph] += 0
                    PlotStats.fingerprints[str(ph)] = sk.get_g1().get_fingerprint()

            for harvester_peer_id, plots in harvester_peers_in.items():
                total_plot_size_harvester = sum(map(lambda x: x["file_size"], plots["plots"]))
                PlotStats.total_plot_size += total_plot_size_harvester
                PlotStats.total_plots += len(plots["plots"])
                if get_staking_addresses_from_plots:
                    for plot in plots["plots"]:
                        ph = create_puzzlehash_for_pk(hexstr_to_bytes(plot["farmer_public_key"]))
                        PlotStats.staking_addresses[ph] += 1
                print(f"   {len(plots['plots'])} plots of size: {format_bytes(total_plot_size_harvester)}")

        STAKING_INFO_CACHE_FILE = 'staking_info_cache.yaml'
        staking_info_cache_path = config_path_for_filename(DEFAULT_ROOT_PATH, STAKING_INFO_CACHE_FILE)

        get_staking_addresses_from_keys = False
        get_staking_addresses_from_plots = False
        invalid_sa_option = False

        if fetch_staking_addresses == 'k':
            get_staking_addresses_from_keys = True
        elif fetch_staking_addresses == 'p':
            get_staking_addresses_from_plots = True
        elif fetch_staking_addresses == 'a':
            get_staking_addresses_from_keys = True
            get_staking_addresses_from_plots = True
        elif fetch_staking_addresses == 'n':
            if staking_info_cache_path.exists():
                staking_info_cache_path.unlink()
        elif fetch_staking_addresses != None:
            invalid_sa_option = True

        if len(harvesters_local) > 0:
            print(f"Local Harvester{'s' if len(harvesters_local) > 1 else ''}")
            process_harvesters(harvesters_local)
        for harvester_ip, harvester_peers in harvesters_remote.items():
            print(f"Remote Harvester{'s' if len(harvester_peers) > 1 else ''} for IP: {harvester_ip}")
            process_harvesters(harvester_peers)

        print(f"Plot count for all harvesters: {PlotStats.total_plots}")

        print("Total size of plots: ", end="")
        print(format_bytes(PlotStats.total_plot_size))

        staking_info = None

        if get_staking_addresses_from_keys or get_staking_addresses_from_plots:
            staking_info = {}

            for ph, plots in PlotStats.staking_addresses.items():
                ph = str(ph)
                staking_info[ph] = {}

                if get_staking_addresses_from_keys:
                    staking_info[ph]["fingerprint"] = PlotStats.fingerprints[ph]

                if get_staking_addresses_from_plots:
                    staking_info[ph]["plots"] = plots

            save_config(DEFAULT_ROOT_PATH, STAKING_INFO_CACHE_FILE, staking_info)
        elif staking_info_cache_path.exists():
            staking_info = load_config(DEFAULT_ROOT_PATH, STAKING_INFO_CACHE_FILE)

        if invalid_sa_option:
            print(f"   Invalid argument for -sa/--staking-addresses: {fetch_staking_addresses}")

        if staking_info == None:
            if show_staking_balance:
                print("   No staking addresses cached. See 'sit farm summary -h' for more info.")
        else:
            print("Staking addresses:")
            address_prefix = config["network_overrides"]["config"][config["selected_network"]]["address_prefix"]
            for ph, entry in staking_info.items():
                ph = hexstr_to_bytes(ph)
                print(f"  {encode_puzzle_hash(ph, address_prefix)}")

                if "fingerprint" in entry:
                    print(f"    Fingerprint: {entry['fingerprint']}")
                if "plots" in entry:
                    print(f"    Plots: {entry['plots']}")
                if show_staking_balance:
                    # query balance
                    balance = await get_ph_balance(rpc_port, ph)
                    balance /= Decimal(10 ** 12)
                    print(f"    Balance: {balance}")
    else:
        print("Plot count: Unknown")
        print("Total size of plots: Unknown")

    if blockchain_state is not None:
        print("Estimated network space: ", end="")
        print(format_bytes(blockchain_state["space"]))
    else:
        print("Estimated network space: Unknown")

    sf = await get_est_staking_factor(PlotStats.total_plot_size, total_staking_balance)
    print(f"Estimated staking factor: {sf}")

    minutes = -1
    if blockchain_state is not None and all_harvesters is not None:
        est_plot_size = PlotStats.total_plot_size / float(sf)
        proportion = est_plot_size / blockchain_state["space"] if blockchain_state["space"] else -1
        minutes = int((await get_average_block_time(rpc_port) / 60) / proportion) if proportion else -1

    if all_harvesters is not None and PlotStats.total_plots == 0:
        print("Expected time to win: Never (no plots)")
    else:
        print("Expected time to win: " + format_minutes(minutes))

    if amounts is None:
        if wallet_not_running:
            print(
                "For details on farmed rewards and fees you should run 'sit start wallet' and 'sit wallet show'"
            )
        elif wallet_not_ready:
            print("For details on farmed rewards and fees you should run 'sit wallet show'")
    else:
        print("Note: log into your key using 'sit wallet show' to see rewards for each key")


async def get_est_staking_factor(total_plot_size, total_staking_balance) -> Decimal:

    sf = 0
    if total_plot_size == 0:
        return Decimal(1)

    # convert farmer space from byte to T unit
    converted_plot_size = total_plot_size / 1000000000000

    if total_staking_balance >= converted_plot_size:
        sf = Decimal("0.5") + Decimal(1) / (Decimal(total_staking_balance) / Decimal(converted_plot_size) + Decimal(1))
    else:
        sf = Decimal("0.05") + Decimal(1) / (Decimal(total_staking_balance) / Decimal(converted_plot_size) + Decimal("0.05"))

    return round(sf, 2)

