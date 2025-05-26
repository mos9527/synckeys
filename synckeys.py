#!/usr/bin/env python

import configparser
import argparse
import os
import shutil
import codecs
import re
from datetime import datetime
from tempfile import TemporaryDirectory
import subprocess
import sys

# From https://github.com/x2es/bt-dualboot/blob/master/bt_dualboot/bt_windows/devices.py
WINDOWS10_REGISTRY_PATH = os.path.join("Windows", "System32", "config", "SYSTEM")
WINDOWS_BT_REGISTER_PATH = r"ControlSet001\Services\BTHPORT\Parameters\Keys"


def export_registery(windows_root, reg_key):
    """Exports given registry key as text
    Args:
        reg_key (str): key for export
            NOTE:   key should be relative to Hive file. For example, "ControlSet001" placed in root of "SYSTEM" file.
                    @see chntpw and reged manuals for details

    Returns:
        (str): content of registry
    """
    with TemporaryDirectory() as temp_dir_name:
        exported_reg_filename = os.path.join(temp_dir_name, "exported.reg")
        # SAMPLE: reged -x ./Windows/System32/config/SYSTEM PREFIX "ControlSet001\Services\...." out.reg
        export_cmd = [
            "reged",
            "-x",
            os.path.join(windows_root, WINDOWS10_REGISTRY_PATH),
            "HKEY_LOCAL_MACHINE\\SYSTEM",
            reg_key,
            exported_reg_filename,
        ]
        subprocess.run(export_cmd)

        with open(exported_reg_filename, "r") as f:
            # skip first line "Windows Registry Editor Version 5.00" for ConfigParser compability
            exported_text = f.read()
    return exported_text


# General global variables
_prev_adapter_mac = None


def format_hex(hex_string):
    return hex_string.replace("hex:", "").replace(",", "").upper()


def format_hex_b(hex_string):
    hex_parts = hex_string.replace("hex(b):", "").split(",")
    hex_parts.reverse()
    hex = "".join(hex_parts)
    return hex


def format_dword(dword_string):
    dword = dword_string.replace("dword:", "")
    return dword


def format_mac_address(mac_string):
    address = mac_string.upper()
    address_parts = [address[i : i + 2] for i in range(0, len(address), 2)]
    return ":".join(address_parts)


def load_keys(contents):
    # Load full file contents and clean up into a config parseable format
    contents = contents.replace('"', "").replace("=", " = ")
    contents = (
        re.sub(
            r"HKEY_LOCAL_MACHINE\\SYSTEM\\.*?\\Services\\BTHPORT\\Parameters\\Keys\\",
            "",
            contents,
        )
        .replace("\r\n", "\n")
        .split("\n")
    )

    del contents[0:4]
    config_contents = "\n".join(contents)

    # Parse the contents into a configuration structure
    parsed_config = configparser.ConfigParser()
    parsed_config.read_string(config_contents)
    return parsed_config


def get_device_path(adapter_mac, device_mac):
    return f"/var/lib/bluetooth/{adapter_mac}/{device_mac}"


def backup_device_info_file(adapter_mac, device_mac):
    device_path = get_device_path(adapter_mac, device_mac)
    now = datetime.now()
    current_datetime = now.strftime("%Y%m%d%H%M%S")
    shutil.copyfile(f"{device_path}/info", f"{device_path}/info-{current_datetime}")


def get_device_pairing_info(adapter_mac, device_mac):
    device_path = get_device_path(adapter_mac, device_mac)
    info_file = f"{device_path}/info"

    if not os.path.isfile(info_file):
        return None

    # Read info data into a config structure
    pairing_config = configparser.ConfigParser()
    pairing_config.optionxform = str
    pairing_config.read(info_file)
    return pairing_config


def update_system_pairing(adapter_mac, device_mac, config):
    backup_device_info_file(adapter_mac, device_mac)
    # Write config structure back to info file
    device_path = get_device_path(adapter_mac, device_mac)
    info_file = open(f"{device_path}/info", "w")
    config.write(info_file)
    info_file.close()


def print_device_info(device_config, device_mac):
    if not device_config:
        print(f"  {device_mac} (# not paired #)")
        return

    # Get paired device name
    device_name = device_config["General"]["Name"]
    device_alias = device_config["General"].get("Alias", device_name)
    print(f"\n  {device_mac} ({device_name} / {device_alias})")


def print_update_values(name, current_value, new_value):
    change_required = False

    if current_value == new_value:
        print(f"    | {name}: {current_value} > No change required.")
    else:
        print(f"    | {name}: {current_value} > Update to: {new_value}")
        change_required = True

    return change_required


def process_basic_pairing(adapter_config, adapter_mac):
    # Iterate through each device and pairing key from the dumped registry config
    for device, pairing_key in adapter_config.items():
        if device == "masterirk":
            continue

        device_mac = format_mac_address(device)
        pairing_key = format_hex(pairing_key)

        # Check this adapter's paired devices in the current Linux system
        paired_config = get_device_pairing_info(adapter_mac, device_mac)
        print_device_info(paired_config, device_mac)

        if not paired_config:
            continue

        current_key = paired_config["LinkKey"]["Key"]
        # preemptively replace system key
        paired_config["LinkKey"]["Key"] = pairing_key

        if not print_update_values("LinkKey", current_key, pairing_key):
            continue

        action = input(f"    > Update keys for device? (y/N): ")
        if action.lower() == "y":
            update_system_pairing(adapter_mac, device_mac, paired_config)
            print(f"    > OK!")


def process_advanced_pairing(adapter_config, adapter_mac, device_mac):
    # Check this adapter's paired devices in the current Linux system
    paired_config = get_device_pairing_info(adapter_mac, device_mac)
    print_device_info(paired_config, device_mac)
    require_update = False

    if not paired_config:
        return

    if "IRK" in adapter_config:
        irk = format_hex(adapter_config["IRK"])
        current_irk = paired_config["IdentityResolvingKey"]["Key"]
        # preemptively setting the final value in the config, but not persisting
        paired_config["IdentityResolvingKey"]["Key"] = irk
        require_update |= print_update_values("IdentityResolvingKey", current_irk, irk)

    if "CSRK" in adapter_config:
        csrk = format_hex(adapter_config["CSRK"])
        current_csrk = paired_config["LocalSignatureKey"]["Key"]
        # preemptively setting the final value in the config, but not persisting
        paired_config["LocalSignatureKey"]["Key"] = csrk
        require_update |= print_update_values("LocalSignatureKey", current_csrk, csrk)

    if "LTK" in adapter_config:
        ltk = format_hex(adapter_config["LTK"])
        if "LongTermKey" in paired_config:
            current_ltk = paired_config["LongTermKey"]["Key"]
            # preemptively setting the final value in the config, but not persisting
            paired_config["LongTermKey"]["Key"] = ltk
            require_update |= print_update_values("LongTermKey", ltk, current_ltk)
        if "SlaveLongTermKey" in paired_config:
            current_ltk = paired_config["SlaveLongTermKey"]["Key"]
            # preemptively setting the final value in the config, but not persisting
            paired_config["SlaveLongTermKey"]["Key"] = ltk
            require_update |= print_update_values("SlaveLongTermKey", ltk, current_ltk)
        if "PeripheralLongTermKey" in paired_config:
            current_ltk = paired_config["PeripheralLongTermKey"]["Key"]
            # preemptively setting the final value in the config, but not persisting
            paired_config["PeripheralLongTermKey"]["Key"] = ltk
            require_update |= print_update_values(
                "PeripheralLongTermKey", ltk, current_ltk
            )

    if "KeyLength" in adapter_config:
        ltk_key_length = str(int(format_dword(adapter_config["KeyLength"]), 16))
        if "LongTermKey" in paired_config:
            current_ltk_key_length = paired_config["LongTermKey"]["EncSize"]
            # preemptively setting the final value in the config, but not persisting
            paired_config["LongTermKey"]["EncSize"] = ltk_key_length
            require_update |= print_update_values(
                "  EncSize", ltk_key_length, current_ltk_key_length
            )
        if "SlaveLongTermKey" in paired_config:
            current_ltk_key_length = paired_config["SlaveLongTermKey"]["EncSize"]
            # preemptively setting the final value in the config, but not persisting
            paired_config["SlaveLongTermKey"]["EncSize"] = ltk_key_length
            require_update |= print_update_values(
                "  EncSize", ltk_key_length, current_ltk_key_length
            )
        if "PeripheralLongTermKey" in paired_config:
            current_ltk_key_length = paired_config["PeripheralLongTermKey"]["EncSize"]
            # preemptively setting the final value in the config, but not persisting
            paired_config["PeripheralLongTermKey"]["EncSize"] = ltk_key_length
            require_update |= print_update_values(
                "  EncSize", ltk_key_length, current_ltk_key_length
            )

    if "EDIV" in adapter_config:
        ltk_ediv = str(int(format_dword(adapter_config["EDIV"]), 16))
        if "LongTermKey" in paired_config:
            current_ltk_ediv = paired_config["LongTermKey"]["EDiv"]
            # preemptively setting the final value in the config, but not persisting
            paired_config["LongTermKey"]["EDiv"] = ltk_ediv
            require_update |= print_update_values("  EDiv", ltk_ediv, current_ltk_ediv)
        if "SlaveLongTermKey" in paired_config:
            current_ltk_ediv = paired_config["SlaveLongTermKey"]["EDiv"]
            # preemptively setting the final value in the config, but not persisting
            paired_config["SlaveLongTermKey"]["EDiv"] = ltk_ediv
            require_update |= print_update_values("  EDiv", ltk_ediv, current_ltk_ediv)
        if "PeripheralLongTermKey" in paired_config:
            current_ltk_ediv = paired_config["PeripheralLongTermKey"]["EDiv"]
            # preemptively setting the final value in the config, but not persisting
            paired_config["PeripheralLongTermKey"]["EDiv"] = ltk_ediv
            require_update |= print_update_values("  EDiv", ltk_ediv, current_ltk_ediv)

    if "ERand" in adapter_config:
        ltk_erand = str(int(format_hex_b(adapter_config["ERand"]), 16))
        if "LongTermKey" in paired_config:
            current_ltk_erand = paired_config["LongTermKey"]["Rand"]
            # preemptively setting the final value in the config, but not persisting
            paired_config["LongTermKey"]["Rand"] = ltk_erand
            require_update |= print_update_values(
                "  Rand", ltk_erand, current_ltk_erand
            )
        if "SlaveLongTermKey" in paired_config:
            current_ltk_erand = paired_config["SlaveLongTermKey"]["Rand"]
            # preemptively setting the final value in the config, but not persisting
            paired_config["SlaveLongTermKey"]["Rand"] = ltk_erand
            require_update |= print_update_values(
                "  Rand", ltk_erand, current_ltk_erand
            )
        if "PeripheralLongTermKey" in paired_config:
            current_ltk_erand = paired_config["PeripheralLongTermKey"]["Rand"]
            # preemptively setting the final value in the config, but not persisting
            paired_config["PeripheralLongTermKey"]["Rand"] = ltk_erand
            require_update |= print_update_values(
                "  Rand", ltk_erand, current_ltk_erand
            )

    if not require_update:
        return

    action = input(f"    > Update keys for device? (y/N): ")
    if action.lower() != "y":
        update_system_pairing(adapter_mac, device_mac, paired_config)
        print(f"    > OK!")


def print_adapter_mac(current_adapter_mac):
    global _prev_adapter_mac
    # Only print the adapter mac information if we are starting for the first time or when we change adapter group of devices.
    # Will work only if we sort device and adapter\device pairs first such that they are grouped together.
    if _prev_adapter_mac != current_adapter_mac:
        if _prev_adapter_mac != None:
            print()
        print(f"Bluetooth Adapter - {current_adapter_mac}")
    _prev_adapter_mac = current_adapter_mac


def process_devices(config):
    # Sort the list of adapters and adapter\device pairs to make sequential grouping by adapter and parsing easier
    adapter_devices = sorted(config.sections())
    for device in adapter_devices:
        if not "\\" in device:
            adapter_mac = format_mac_address(device)
            print_adapter_mac(adapter_mac)
            # Launch basic pairing extraction and update
            process_basic_pairing(config[device], adapter_mac)
        else:
            mac_addresses = device.split("\\")
            adapter_mac = format_mac_address(mac_addresses[0])
            device_mac = format_mac_address(mac_addresses[1])
            print_adapter_mac(adapter_mac)
            # Launch advanced pairing extraction and update
            process_advanced_pairing(config[device], adapter_mac, device_mac)


def parse_args():
    parser = argparse.ArgumentParser(
        description="SyncKeys - Update Linux Bluetooth keys from Windows-paired devices"
    )
    parser.add_argument(
        "-w",
        "--windows-dir",
        help="Path to the root of your mounted Windows drive",
    )
    parser.add_argument(
        "-r",
        "--registery-file",
        help="Path to the dumped Registery file. This options supercedes `-r` (`--windows-dir`)",
    )
    return parser.parse_args()


def __main__():
    if not os.geteuid() == 0:
        print("ERROR: You need to be root to be able to run this script.")
        return 1
    args = parse_args()
    if not args.registery_file and args.windows_dir:
        print(f"Using Windows root {args.windows_dir}")
        content = export_registery(args.windows_dir, WINDOWS_BT_REGISTER_PATH)
    elif args.registery_file:
        print(f"Reading from Registery file {args.registery_file}")
        with codecs.open(args.registery_file, "r", "utf-16-le") as f:
            content = f.read()
    else:
        print(
            "ERROR: You must specify either a Windows directory (-w) or a Registery file (-r)"
        )
        return 1
    config = load_keys(content)
    process_devices(config)
    return 0


if __name__ == "__main__":
    sys.exit(__main__())
