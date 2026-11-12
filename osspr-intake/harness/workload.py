"""Shared large-bridge workload for intake harnesses.

A whole-home HomeKit bridge: lights, sensors, thermostats, switches, fans,
outlets, window coverings and locks. 620 accessories is a large but real
Home Assistant style bridge (the upstream benchmark calls 250 "heavy").
"""

from __future__ import annotations

from typing import Any

from pyhap.accessory import Accessory, Bridge
from pyhap.const import (
    CATEGORY_DOOR_LOCK,
    CATEGORY_FAN,
    CATEGORY_LIGHTBULB,
    CATEGORY_OUTLET,
    CATEGORY_SENSOR,
    CATEGORY_SWITCH,
    CATEGORY_THERMOSTAT,
    CATEGORY_WINDOW_COVERING,
)

ACCESSORY_COUNT = 620

# (category, service name, optional characteristics a typical device exposes)
DEVICE_PLANS: tuple[tuple[int, str, tuple[str, ...]], ...] = (
    (
        CATEGORY_LIGHTBULB,
        "Lightbulb",
        ("Brightness", "Hue", "Saturation", "ColorTemperature", "Name"),
    ),
    (
        CATEGORY_SENSOR,
        "TemperatureSensor",
        ("Name", "StatusActive", "StatusLowBattery", "StatusFault"),
    ),
    (
        CATEGORY_SENSOR,
        "HumiditySensor",
        ("Name", "StatusActive", "StatusFault"),
    ),
    (
        CATEGORY_SENSOR,
        "MotionSensor",
        ("StatusActive", "StatusFault"),
    ),
    (
        CATEGORY_SENSOR,
        "ContactSensor",
        ("StatusActive", "StatusLowBattery", "StatusTampered"),
    ),
    (
        CATEGORY_THERMOSTAT,
        "Thermostat",
        (
            "Name",
            "CurrentRelativeHumidity",
            "CoolingThresholdTemperature",
            "HeatingThresholdTemperature",
        ),
    ),
    (CATEGORY_SWITCH, "Switch", ("Name",)),
    (CATEGORY_FAN, "Fan", ("RotationSpeed", "RotationDirection", "Name")),
    (CATEGORY_OUTLET, "Outlet", ("Name", "OutletInUse")),
    (
        CATEGORY_WINDOW_COVERING,
        "WindowCovering",
        ("Name", "CurrentPosition", "TargetPosition", "PositionState"),
    ),
    (CATEGORY_DOOR_LOCK, "LockMechanism", ("Name",)),
)


class _LoaderDriver:
    """Enough of a driver for Accessory to load services. No sockets."""

    def __init__(self, loader: Any) -> None:
        self.loader = loader

    def publish(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def build_bridge(driver: Any, count: int = ACCESSORY_COUNT) -> Bridge:
    """Build ``count`` bridged accessories on ``driver``."""
    bridge = Bridge(driver, "Whole Home")
    for index in range(count):
        category, service_name, extra = DEVICE_PLANS[index % len(DEVICE_PLANS)]
        accessory = Accessory(driver, f"Device {index + 1}", aid=index + 2)
        accessory.category = category
        accessory.add_preload_service(service_name, chars=extra)
        info = accessory.get_service("AccessoryInformation")
        assert info is not None
        info.configure_char("Manufacturer", value="Northwind")
        info.configure_char("Model", value=service_name)
        info.configure_char("FirmwareRevision", value="2.4.1")
        info.configure_char("SerialNumber", value=f"NW-{index:05d}")
        bridge.add_accessory(accessory)
    return bridge
