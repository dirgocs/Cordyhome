"""Leitura das mensagens de descoberta do Home Assistant (`homeassistant/.../config`).

Cada aparelho publica, num tópico retido, a descrição das suas entidades: o relé (`switch`),
a luz (`light`) e os sensores (`sensor`) de potência, tensão e corrente. Aqui essas
descrições viram `Entity` e são agrupadas por aparelho físico para a tela de adicionar.

Formatos aceitos:
- por entidade: `<prefixo>/<componente>/[<nó>/]<objeto>/config`;
- por aparelho: `<prefixo>/device/<objeto>/config`, com as entidades em `cmps`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from typing import Any

from ..base import BRIGHTNESS, ENERGY, POWER

CONTROL_COMPONENTS = ("switch", "light")
SENSOR_CLASSES = ("power", "voltage", "current")

# Abreviações do Home Assistant usadas pelas entidades que entendemos.
ABBREVIATIONS = {
    "avty": "availability",
    "avty_mode": "availability_mode",
    "avty_t": "availability_topic",
    "avty_tpl": "availability_template",
    "bri_cmd_t": "brightness_command_topic",
    "bri_scl": "brightness_scale",
    "bri_stat_t": "brightness_state_topic",
    "bri_val_tpl": "brightness_value_template",
    "cmd_t": "command_topic",
    "cmd_tpl": "command_template",
    "cmps": "components",
    "dev": "device",
    "dev_cla": "device_class",
    "name": "name",
    "obj_id": "object_id",
    "p": "platform",
    "pl_avail": "payload_available",
    "pl_not_avail": "payload_not_available",
    "pl_off": "payload_off",
    "pl_on": "payload_on",
    "stat_off": "state_off",
    "stat_on": "state_on",
    "stat_t": "state_topic",
    "stat_val_tpl": "state_value_template",
    "t": "topic",
    "uniq_id": "unique_id",
    "unit_of_meas": "unit_of_measurement",
    "val_tpl": "value_template",
}
DEVICE_ABBREVIATIONS = {
    "cns": "connections",
    "ids": "identifiers",
    "mdl": "model",
    "mdl_id": "model_id",
    "mf": "manufacturer",
    "sw": "sw_version",
}
# Opções do aparelho que valem para todas as entidades no formato por aparelho.
SHARED_OPTIONS = ("availability", "availability_topic", "availability_mode", "state_topic", "qos")


@dataclass
class Availability:
    topic: str
    payload_available: str = "online"
    payload_not_available: str = "offline"
    value_template: str | None = None


@dataclass
class Entity:
    key: str
    component: str  # switch | light | sensor
    name: str | None = None
    device_key: str = ""
    device_name: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    state_topic: str | None = None
    command_topic: str | None = None
    value_template: str | None = None
    command_template: str | None = None
    payload_on: str = "ON"
    payload_off: str = "OFF"
    state_on: str | None = None
    state_off: str | None = None
    # Luzes: "default" usa tópicos separados para brilho; "json" manda tudo num JSON.
    schema: str = "default"
    brightness: bool = False
    brightness_command_topic: str | None = None
    brightness_state_topic: str | None = None
    brightness_value_template: str | None = None
    brightness_scale: int = 255
    device_class: str | None = None
    unit: str | None = None
    availability: list[Availability] = field(default_factory=list)
    availability_mode: str = "latest"
    qos: int = 0

    @property
    def capabilities(self) -> list[str]:
        if self.component == "sensor":
            return [ENERGY] if self.device_class == "power" else []
        caps = [POWER]
        if self.component == "light" and (
            self.brightness_command_topic or (self.schema == "json" and self.brightness)
        ):
            caps.append(BRIGHTNESS)
        return caps

    @property
    def topics(self) -> set[str]:
        """Tópicos de onde vem o estado desta entidade."""
        out = {a.topic for a in self.availability}
        out |= {t for t in (self.state_topic, self.brightness_state_topic) if t}
        return out

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Entity:
        known = {f.name for f in fields(cls)}
        values = {k: v for k, v in data.items() if k in known}
        values["availability"] = [Availability(**a) for a in data.get("availability") or []]
        return cls(**values)


def _expand(data: dict[str, Any], table: dict[str, str]) -> dict[str, Any]:
    return {table.get(k, k): v for k, v in data.items()}


def _base_topic(config: dict[str, Any]) -> None:
    """Troca o `~` dos tópicos pelo tópico base, como faz o Home Assistant."""
    base = config.pop("~", None)
    if not isinstance(base, str):
        return

    def fix(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        if value.startswith("~"):
            return base + value[1:]
        if value.endswith("~"):
            return value[:-1] + base
        return value

    for key, value in list(config.items()):
        if key.endswith("topic") or key == "topic":
            config[key] = fix(value)
    for item in config.get("availability") or []:
        if isinstance(item, dict):
            item["topic"] = fix(item.get("topic"))


def _text(value: Any, default: str | None = None) -> str | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _device_key(device: dict[str, Any]) -> str | None:
    ids = device.get("identifiers")
    if isinstance(ids, list) and ids:
        return str(ids[0])
    if isinstance(ids, str) and ids:
        return ids
    connections = device.get("connections")
    if isinstance(connections, list) and connections and isinstance(connections[0], list):
        return ":".join(str(c) for c in connections[0])
    return None


def _availability(config: dict[str, Any]) -> list[Availability]:
    items: list[Availability] = []
    default_on = _text(config.get("payload_available"), "online")
    default_off = _text(config.get("payload_not_available"), "offline")
    if isinstance(config.get("availability_topic"), str):
        items.append(
            Availability(
                topic=config["availability_topic"],
                payload_available=default_on,
                payload_not_available=default_off,
                value_template=config.get("availability_template"),
            )
        )
    for raw in config.get("availability") or []:
        if not isinstance(raw, dict):
            continue
        item = _expand(raw, ABBREVIATIONS)
        if isinstance(item.get("topic"), str):
            items.append(
                Availability(
                    topic=item["topic"],
                    payload_available=_text(item.get("payload_available"), default_on),
                    payload_not_available=_text(item.get("payload_not_available"), default_off),
                    value_template=item.get("value_template"),
                )
            )
    return items


def parse_entity(component: str, key: str, config: dict[str, Any]) -> Entity | None:
    """Monta a entidade a partir da configuração já expandida. None se não nos interessa."""
    if component not in (*CONTROL_COMPONENTS, "sensor"):
        return None
    if component == "sensor" and config.get("device_class") not in SENSOR_CLASSES:
        return None
    if component in CONTROL_COMPONENTS and not isinstance(config.get("command_topic"), str):
        return None
    if component == "sensor" and not isinstance(config.get("state_topic"), str):
        return None
    device = _expand(config.get("device") or {}, DEVICE_ABBREVIATIONS)
    schema = config.get("schema") or "default"
    if schema not in ("default", "basic", "json"):
        return None  # luz por template: rara e fora do que entendemos
    unique = config.get("unique_id")
    entity_key = str(unique) if unique else key
    payload_on = _text(config.get("payload_on"), "ON")
    payload_off = _text(config.get("payload_off"), "OFF")
    try:
        scale = int(config.get("brightness_scale") or 255)
        qos = int(config.get("qos") or 0)
    except (TypeError, ValueError):
        return None
    return Entity(
        key=entity_key,
        component=component,
        name=_text(config.get("name")),
        device_key=_device_key(device) or entity_key,
        device_name=_text(device.get("name")),
        manufacturer=_text(device.get("manufacturer")),
        model=_text(device.get("model") or device.get("model_id")),
        state_topic=config.get("state_topic"),
        command_topic=config.get("command_topic"),
        value_template=config.get("state_value_template") or config.get("value_template"),
        command_template=config.get("command_template"),
        payload_on=payload_on,
        payload_off=payload_off,
        state_on=_text(config.get("state_on"), payload_on),
        state_off=_text(config.get("state_off"), payload_off),
        schema="json" if schema == "json" else "default",
        brightness=bool(config.get("brightness")),
        brightness_command_topic=config.get("brightness_command_topic"),
        brightness_state_topic=config.get("brightness_state_topic"),
        brightness_value_template=config.get("brightness_value_template"),
        brightness_scale=max(1, scale),
        device_class=config.get("device_class"),
        unit=_text(config.get("unit_of_measurement")),
        availability=_availability(config),
        availability_mode=config.get("availability_mode") or "latest",
        qos=qos if qos in (0, 1, 2) else 0,
    )


def parse_discovery(prefix: str, topic: str, payload: bytes) -> tuple[list[str], list[Entity]]:
    """Lê uma mensagem de descoberta.

    Devolve as chaves que este tópico anuncia (para remoções futuras) e as entidades
    válidas. Mensagem vazia significa que o aparelho retirou as entidades.
    """
    parts = topic.split("/")
    prefix_parts = prefix.strip("/").split("/")
    if parts[: len(prefix_parts)] != prefix_parts or parts[-1] != "config":
        return [], []
    rest = parts[len(prefix_parts) : -1]
    if len(rest) not in (2, 3):
        return [], []
    component, ids = rest[0], rest[1:]
    if not payload.strip():
        return [], []
    try:
        config = json.loads(payload)
    except ValueError:
        return [], []
    if not isinstance(config, dict):
        return [], []
    config = _expand(config, ABBREVIATIONS)
    if component == "device":
        return _parse_device(config, "/".join(ids))
    _base_topic(config)
    entity = parse_entity(component, "/".join([component, *ids]), config)
    return ([entity.key], [entity]) if entity else ([], [])


def _parse_device(config: dict[str, Any], object_id: str) -> tuple[list[str], list[Entity]]:
    components = config.get("components")
    if not isinstance(components, dict):
        return [], []
    shared = {k: config[k] for k in SHARED_OPTIONS if k in config}
    entities: list[Entity] = []
    for cmp_id, raw in components.items():
        if not isinstance(raw, dict):
            continue
        cmp = _expand(raw, ABBREVIATIONS)
        merged = {**shared, **cmp, "device": config.get("device") or {}}
        if "~" in config and "~" not in merged:
            merged["~"] = config["~"]
        _base_topic(merged)
        component = str(cmp.get("platform") or "")
        entity = parse_entity(component, f"{object_id}/{cmp_id}", merged)
        if entity:
            entities.append(entity)
    return [e.key for e in entities], entities


@dataclass
class Candidate:
    """Um aparelho que pode ser adicionado: um controle e/ou os sensores dele."""

    key: str
    name: str
    kind: str
    control: Entity | None
    sensors: list[Entity]
    manufacturer: str | None = None
    model: str | None = None

    @property
    def capabilities(self) -> list[str]:
        caps = list(self.control.capabilities) if self.control else []
        if any(s.device_class == "power" for s in self.sensors):
            caps.append(ENERGY)
        return caps

    @property
    def product_name(self) -> str | None:
        parts = [p for p in (self.manufacturer, self.model) if p]
        return " ".join(parts) or None


def _guess_kind(entity: Entity) -> str:
    if entity.component == "light":
        return "light"
    text = " ".join(filter(None, (entity.name, entity.device_name, entity.model))).lower()
    if any(word in text for word in ("plug", "socket", "tomada", "outlet")):
        return "plug"
    return "relay"


def group_candidates(entities: list[Entity]) -> list[Candidate]:
    """Agrupa as entidades por aparelho físico.

    Um aparelho com um só relé vira um item, com os sensores juntos. Com vários relés (um
    interruptor de duas teclas, por exemplo), cada relé vira um item; os sensores ficam de
    fora porque não dá para saber de qual relé são. Um medidor sem relé vira um item só de
    medição.
    """
    by_device: dict[str, list[Entity]] = {}
    for entity in entities:
        by_device.setdefault(entity.device_key, []).append(entity)
    out: list[Candidate] = []
    for device_key, group in by_device.items():
        controls = [e for e in group if e.component in CONTROL_COMPONENTS]
        sensors = [e for e in group if e.component == "sensor"]
        first = group[0]
        device_name = first.device_name or first.name or device_key
        if len(controls) == 1:
            control = controls[0]
            out.append(
                Candidate(
                    key=control.key,
                    name=device_name,
                    kind=_guess_kind(control),
                    control=control,
                    sensors=sensors,
                    manufacturer=first.manufacturer,
                    model=first.model,
                )
            )
        elif controls:
            for control in controls:
                out.append(
                    Candidate(
                        key=control.key,
                        name=f"{device_name} {control.name}" if control.name else device_name,
                        kind=_guess_kind(control),
                        control=control,
                        sensors=[],
                        manufacturer=first.manufacturer,
                        model=first.model,
                    )
                )
        elif any(s.device_class == "power" for s in sensors):
            out.append(
                Candidate(
                    key=f"meter:{device_key}",
                    name=device_name,
                    kind="other",
                    control=None,
                    sensors=sensors,
                    manufacturer=first.manufacturer,
                    model=first.model,
                )
            )
    return sorted(out, key=lambda c: c.name.lower())
