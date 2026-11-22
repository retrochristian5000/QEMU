#!/usr/bin/env python3
"""Read-only QMP PCI inventory smoke test for WHP-Drivers research targets.

This checks generic controller enumeration, not guest driver operation or
emulation of the physical hardware under investigation.
"""

import argparse
import json
import pathlib
import socket
import subprocess
import sys
import tempfile
import time

# (QEMU qdev ID, emulated QEMU device model, PCI class/subclass).
CONTROLLERS = (
    ("whp-ahci", "ich9-ahci", 0x0106),
    ("whp-hda", "intel-hda", 0x0403),
    ("whp-ehci", "usb-ehci", 0x0C03),
)


def pci_devices(buses):
    """Flatten QMP query-pci buses, including bridges, without guessing IDs."""
    if not isinstance(buses, list):
        raise ValueError("query-pci did not return a bus list")
    for bus in buses:
        if not isinstance(bus, dict) or not isinstance(bus.get("devices"), list):
            raise ValueError("malformed PCI bus in query-pci")
        for device in bus["devices"]:
            if not isinstance(device, dict):
                raise ValueError("malformed PCI device in query-pci")
            yield device
            bridge = device.get("pci_bridge")
            if bridge is not None:
                if not isinstance(bridge, dict) or "bus" not in bridge:
                    raise ValueError("malformed PCI bridge in query-pci")
                yield from pci_devices([bridge["bus"]])


def validate_inventory(buses):
    """Require the intended qdev instances and controller class codes."""
    indexed = {}
    for device in pci_devices(buses):
        ident = device.get("qdev_id")
        if isinstance(ident, str) and ident:
            if ident in indexed:
                raise ValueError(f"duplicate QMP qdev ID: {ident}")
            indexed[ident] = device

    verified = []
    for ident, model, expected_class in CONTROLLERS:
        device = indexed.get(ident)
        if device is None:
            raise ValueError(f"QEMU did not expose {ident} ({model}) on PCI")
        class_info = device.get("class_info")
        actual_class = (class_info.get("class")
                        if isinstance(class_info, dict) else None)
        if actual_class != expected_class:
            raise ValueError(
                f"{ident}: PCI class/subclass {actual_class!r}; "
                f"expected 0x{expected_class:04x}"
            )
        pci_id = device.get("id", {})
        if not isinstance(pci_id, dict):
            raise ValueError(f"{ident}: malformed PCI vendor/device identity")
        vendor, product = pci_id.get("vendor"), pci_id.get("device")
        if not isinstance(vendor, int) or not isinstance(product, int):
            raise ValueError(f"{ident}: missing PCI vendor/device identity")
        verified.append({
            "model": model,
            "qdev_id": ident,
            "class_code": f"{expected_class:04x}",
            "pci_id": f"{vendor:04x}:{product:04x}",
        })
    return verified


def qmp_receive(reader):
    while True:
        line = reader.readline()
        if not line:
            raise RuntimeError("QMP connection closed unexpectedly")
        message = json.loads(line)
        if "event" not in message:
            return message


def qmp_execute(connection, reader, command):
    connection.sendall((json.dumps({"execute": command}) + "\r\n").encode("utf-8"))
    reply = qmp_receive(reader)
    if "error" in reply:
        raise RuntimeError(f"QMP {command}: {reply['error']}")
    if "return" not in reply:
        raise RuntimeError(f"QMP {command}: missing return value")
    return reply["return"]


def connect_qmp(path, process, seconds=10):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            details = process.stderr.read().decode("utf-8", "replace")
            raise RuntimeError(f"QEMU exited during startup: {details.strip()}")
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(3)
        try:
            connection.connect(str(path))
            return connection
        except (FileNotFoundError, ConnectionRefusedError):
            connection.close()
            time.sleep(0.05)
        except BaseException:
            connection.close()
            raise
    raise TimeoutError("QEMU QMP socket was not ready within 10 seconds")


def run_probe(qemu):
    if not qemu.is_file():
        raise ValueError(f"QEMU binary not found: {qemu}")
    with tempfile.TemporaryDirectory(prefix="whp-qmp-") as temporary:
        qmp_path = pathlib.Path(temporary) / "qmp.sock"
        arguments = [
            str(qemu), "-machine", "pc,accel=tcg", "-m", "64", "-S",
            "-nodefaults", "-no-user-config", "-nic", "none",
            "-display", "none", "-serial", "none", "-monitor", "none",
            "-qmp", f"unix:{qmp_path},server=on,wait=off",
        ]
        for ident, model, _ in CONTROLLERS:
            arguments.extend(("-device", f"{model},id={ident}"))
        process = subprocess.Popen(
            arguments, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        try:
            with connect_qmp(qmp_path, process) as connection:
                with connection.makefile("r", encoding="utf-8") as reader:
                    hello = qmp_receive(reader)
                    if "QMP" not in hello:
                        raise RuntimeError("expected QMP greeting")
                    qmp_execute(connection, reader, "qmp_capabilities")
                    buses = qmp_execute(connection, reader, "query-pci")
                    return validate_inventory(buses)
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=pathlib.Path, required=True,
                        help="path to the QEMU fork's built qemu-system-i386")
    arguments = parser.parse_args()
    try:
        controllers = run_probe(arguments.qemu.resolve())
    except (OSError, ValueError, RuntimeError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"WHP QMP smoke test failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "generic-controller-enumeration-only",
                      "controllers": controllers}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
