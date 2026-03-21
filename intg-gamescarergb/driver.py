"""
Games Care RGB Switch integration driver for Unfolded Circle Remote 3.

Exposes a media_player entity for switching between named inputs on a
Games Care RGB Switch. Supports up to 4 boards (32 ports) via extension boards.

API: GET http://{host}/ports?force={port_number}
     Port 0 = Auto mode, Port 1-N = select that input.
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

import aiohttp
import ucapi
from ucapi.media_player import Attributes as MediaAttr
from ucapi.media_player import Features as MediaFeatures
from ucapi.media_player import States as MediaStates

_LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_PORT_SELECT = "/ports"
CONFIG_FILE = "gamescarergb_config.json"
PORTS_PER_BOARD = 8
AUTO_PORT = 0

# ---------------------------------------------------------------------------
# ucapi setup
# ---------------------------------------------------------------------------

loop = asyncio.new_event_loop()
api = ucapi.IntegrationAPI(loop)

_devices: list[dict] = []
_session: aiohttp.ClientSession | None = None
_current_ports: dict[str, int] = {}


# ---------------------------------------------------------------------------
# Config persistence
# ---------------------------------------------------------------------------

def _config_path() -> Path:
    config_home = os.environ.get("UC_CONFIG_HOME", str(Path.home()))
    return Path(config_home) / CONFIG_FILE


def _load_config() -> list[dict]:
    path = _config_path()
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            _LOGGER.error("Failed to load config: %s", e)
    return []


def _save_config(devices: list[dict]) -> None:
    path = _config_path()
    try:
        with open(path, "w") as f:
            json.dump(devices, f, indent=2)
        _LOGGER.debug("Config saved to %s", path)
    except Exception as e:
        _LOGGER.error("Failed to save config: %s", e)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _device_id(host: str) -> str:
    return f"gamescarergb_{host.replace('.', '_').replace('-', '_')}"


def _default_port_names(total_ports: int) -> list[str]:
    """port_names[0] = Auto, port_names[1..N] = Port 1..N"""
    return ["Auto"] + [f"Port {i}" for i in range(1, total_ports + 1)]


async def _send_port_command(host: str, port: int) -> bool:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    url = f"http://{host}{API_PORT_SELECT}"
    try:
        async with asyncio.timeout(5):
            resp = await _session.get(url, params={"force": port})
            if resp.status == 200:
                _LOGGER.debug("Switched %s to port %d", host, port)
                return True
            _LOGGER.error("Unexpected response from %s: %s", host, resp.status)
            return False
    except Exception as e:
        _LOGGER.error("Failed to send port command to %s: %s", host, e)
        return False


async def _test_connection(host: str) -> bool:
    return await _send_port_command(host, AUTO_PORT)


# ---------------------------------------------------------------------------
# Entity management
# ---------------------------------------------------------------------------

async def _cmd_handler(
    entity: ucapi.media_player.MediaPlayer,
    cmd_id: str,
    params: dict[str, Any] | None,
    websocket: Any,
) -> ucapi.StatusCodes:
    """Handle media player commands from the remote."""
    device = next((d for d in _devices if _device_id(d["host"]) == entity.id), None)
    if device is None:
        _LOGGER.error("Command received for unknown entity: %s", entity.id)
        return ucapi.StatusCodes.NOT_FOUND

    host = device["host"]
    entity_id = entity.id
    port_names: list[str] = device["port_names"]
    source_list = port_names[1:]
    current_port = _current_ports.get(entity_id, AUTO_PORT)

    if cmd_id == "on":
        target = current_port if current_port > AUTO_PORT else 1
        return await _apply_port(entity_id, host, target, port_names)

    if cmd_id == "off":
        return await _apply_port(entity_id, host, AUTO_PORT, port_names)

    if cmd_id == "toggle":
        target = AUTO_PORT if current_port > AUTO_PORT else 1
        return await _apply_port(entity_id, host, target, port_names)

    if cmd_id == "select_source":
        source = params.get("source") if params else None
        if source is None or source not in source_list:
            _LOGGER.warning("Unknown source: %s", source)
            return ucapi.StatusCodes.BAD_REQUEST
        port = source_list.index(source) + 1
        return await _apply_port(entity_id, host, port, port_names)

    _LOGGER.warning("Unknown command: %s", cmd_id)
    return ucapi.StatusCodes.BAD_REQUEST


async def _apply_port(
    entity_id: str, host: str, port: int, port_names: list[str]
) -> ucapi.StatusCodes:
    success = await _send_port_command(host, port)
    if not success:
        return ucapi.StatusCodes.SERVER_ERROR

    _current_ports[entity_id] = port
    source_list = port_names[1:]
    current_source = port_names[port] if port > AUTO_PORT else ""
    state = MediaStates.OFF if port == AUTO_PORT else MediaStates.ON

    api.configured_entities.update_attributes(
        entity_id,
        {
            MediaAttr.STATE: state,
            MediaAttr.SOURCE: current_source,
            MediaAttr.SOURCE_LIST: source_list,
        },
    )
    return ucapi.StatusCodes.OK


def _create_entity(device: dict) -> ucapi.media_player.MediaPlayer:
    entity_id = _device_id(device["host"])
    port_names: list[str] = device["port_names"]
    source_list = port_names[1:]
    current_port = _current_ports.get(entity_id, AUTO_PORT)
    state = MediaStates.OFF if current_port == AUTO_PORT else MediaStates.ON
    current_source = port_names[current_port] if current_port > AUTO_PORT else ""

    return ucapi.media_player.MediaPlayer(
        entity_id,
        {"en": device["name"]},
        [
            MediaFeatures.ON_OFF,
            MediaFeatures.TOGGLE,
            MediaFeatures.SELECT_SOURCE,
        ],
        {
            MediaAttr.STATE: state,
            MediaAttr.SOURCE: current_source,
            MediaAttr.SOURCE_LIST: source_list,
        },
        cmd_handler=_cmd_handler,
    )


def _register_entities() -> None:
    for device in _devices:
        entity = _create_entity(device)
        if not api.available_entities.contains(entity.id):
            api.available_entities.add(entity)
            _LOGGER.info("Registered entity: %s (%s)", entity.id, device["name"])


# ---------------------------------------------------------------------------
# UCR3 event handlers
# ---------------------------------------------------------------------------

@api.listens_to(ucapi.Events.CONNECT)
async def on_connect():
    _LOGGER.info("Remote connected")
    await api.set_device_state(ucapi.DeviceStates.CONNECTED)


@api.listens_to(ucapi.Events.DISCONNECT)
async def on_disconnect():
    _LOGGER.info("Remote disconnected")


@api.listens_to(ucapi.Events.ENTER_STANDBY)
async def on_enter_standby():
    _LOGGER.debug("Remote entering standby")


@api.listens_to(ucapi.Events.EXIT_STANDBY)
async def on_exit_standby():
    _LOGGER.debug("Remote exiting standby")


@api.listens_to(ucapi.Events.SUBSCRIBE_ENTITIES)
async def on_subscribe_entities(entity_ids: list[str]):
    _LOGGER.info("Subscribe entities: %s", entity_ids)
    for entity_id in entity_ids:
        device = next((d for d in _devices if _device_id(d["host"]) == entity_id), None)
        if device is None:
            continue
        port_names = device["port_names"]
        source_list = port_names[1:]
        current_port = _current_ports.get(entity_id, AUTO_PORT)
        state = MediaStates.OFF if current_port == AUTO_PORT else MediaStates.ON
        current_source = port_names[current_port] if current_port > AUTO_PORT else ""
        api.configured_entities.update_attributes(
            entity_id,
            {
                MediaAttr.STATE: state,
                MediaAttr.SOURCE: current_source,
                MediaAttr.SOURCE_LIST: source_list,
            },
        )


@api.listens_to(ucapi.Events.UNSUBSCRIBE_ENTITIES)
async def on_unsubscribe_entities(entity_ids: list[str]):
    _LOGGER.info("Unsubscribe entities: %s", entity_ids)


# ---------------------------------------------------------------------------
# Setup flow
# ---------------------------------------------------------------------------

async def driver_setup_handler(msg: ucapi.SetupDriver) -> ucapi.SetupAction:
    if isinstance(msg, ucapi.DriverSetupRequest):
        return await _handle_setup_request(msg)
    if isinstance(msg, ucapi.UserDataResponse):
        return await _handle_user_data(msg)
    return ucapi.SetupError()


async def _handle_setup_request(msg: ucapi.DriverSetupRequest) -> ucapi.SetupAction:
    host = msg.setup_data.get("host", "").strip()
    host = host.removeprefix("https://").removeprefix("http://").strip("/")
    name = msg.setup_data.get("name", "GC RGB Switch").strip() or "GC RGB Switch"

    try:
        extensions = int(msg.setup_data.get("extensions", "0").strip())
        extensions = max(0, min(3, extensions))
    except ValueError:
        extensions = 0

    if not host:
        return ucapi.SetupError(ucapi.IntegrationSetupError.NOT_FOUND)

    if not await _test_connection(host):
        _LOGGER.error("Setup: could not connect to %s", host)
        return ucapi.SetupError(ucapi.IntegrationSetupError.CONNECTION_REFUSED)

    total_ports = PORTS_PER_BOARD * (extensions + 1)

    device_id = _device_id(host)
    existing = next((d for d in _devices if d["id"] == device_id), None)
    existing_names = existing["port_names"] if existing else _default_port_names(total_ports)

    while len(existing_names) < total_ports + 1:
        existing_names.append(f"Port {len(existing_names)}")
    existing_names = existing_names[:total_ports + 1]

    fields = [
        {
            "id": "_host",
            "label": {"en": "Host (do not change)"},
            "field": {"text": {"value": host}},
        },
        {
            "id": "_name",
            "label": {"en": "Device name (do not change)"},
            "field": {"text": {"value": name}},
        },
        {
            "id": "_extensions",
            "label": {"en": "Extension boards (do not change)"},
            "field": {"text": {"value": str(extensions)}},
        },
        {
            "id": "port_0",
            "label": {"en": "Auto / Off label"},
            "field": {"text": {"value": existing_names[0]}},
        },
    ]

    for i in range(1, total_ports + 1):
        fields.append({
            "id": f"port_{i}",
            "label": {"en": f"Port {i} name"},
            "field": {"text": {"value": existing_names[i]}},
        })

    return ucapi.RequestUserInput(
        {"en": f"Name your inputs ({total_ports} ports)"},
        fields,
    )


async def _handle_user_data(msg: ucapi.UserDataResponse) -> ucapi.SetupAction:
    input_values = msg.input_values

    host = input_values.get("_host", "").strip()
    name = input_values.get("_name", "GC RGB Switch").strip() or "GC RGB Switch"
    try:
        extensions = int(input_values.get("_extensions", "0").strip())
    except ValueError:
        extensions = 0

    total_ports = PORTS_PER_BOARD * (extensions + 1)

    port_names = []
    for i in range(total_ports + 1):
        key = f"port_{i}"
        default = "Auto" if i == 0 else f"Port {i}"
        port_names.append(input_values.get(key, default).strip() or default)

    device_id = _device_id(host)
    device = {
        "id": device_id,
        "host": host,
        "name": name,
        "extensions": extensions,
        "port_names": port_names,
    }

    global _devices
    _devices = [d for d in _devices if d["id"] != device_id]
    _devices.append(device)
    _save_config(_devices)

    _current_ports[device_id] = AUTO_PORT

    entity = _create_entity(device)
    if api.available_entities.contains(entity.id):
        api.available_entities.remove(entity.id)
    api.available_entities.add(entity)

    _LOGGER.info("Setup complete for %s (%s) with %d ports", host, name, total_ports)
    return ucapi.SetupComplete()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    global _devices
    _devices = _load_config()
    _LOGGER.info("Loaded %d configured device(s)", len(_devices))

    for device in _devices:
        _current_ports[_device_id(device["host"])] = AUTO_PORT

    _register_entities()
    await api.init("driver.json", driver_setup_handler)


if __name__ == "__main__":
    loop.run_until_complete(main())
    loop.run_forever()
