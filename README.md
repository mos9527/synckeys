synckeys
---
Python script to sync Bluetooth pairing keys from Windows to your Linux installations.

## Credits
- https://wiki.archlinux.org/title/Bluetooth#Dual_boot_pairing
- https://github.com/x2es/bt-dualboot for the original implementation.
- https://github.com/ademlabs/synckeys for properly handling BT5.1 and BLE devices
- https://github.com/wochap/synckeys for handling devices without LTK (Long Term Key)

## Warning / Disclaimer
> The code and instructions within this project accesses and modifies system files on your Windows and Linux installations. Although care has been taken to ensure that nothing harmful happens, there could be a risk of damage to your software and hardware. Your usage of the program and instructions herein constitutes acceptance of those risks and the author cannot be held liable for any claims whatsoever.

## Prerequisites 
* Python 3.6+
* **sudo** / **root** access.

## Usage
For either of the methods to work, **you need to have the Bluetooth devices paired with both your Linux and Windows systems beforehand**. This is necessary to create the required initial pairing configurations.

Do note, however, that **it's not necessary to have the devices connected to your system at the time of the procedures.**
But it **is** necessary to have the device **working on Windows** prior to running the script, as it will read the pairing keys from the Windows registry.

### Additional Prerequisites for BLE devices
If you are trying to sync a BLE device since modern BLE devices alter their MAC address with each new pairing. Hence, your script won't find the in OS1 paired device in OS2. 

In order to resolve this problem, just copy the setup in OS2 (Linux) to a folder with the MAC address as used in windows helps:
```
sudo cp -r /var/lib/bluetooth/<adapter>/<in-linux-paired-MAC> /var/lib/bluetooth/<adapter>/<in-windows-paired-MAC>
```
>**NOTE:** To get `<adapter>` MAC address, just type on a terminal `bluetoothctl` and then type `list` and for `<in-linux-paired-MAC>` inside `bluetoothctl` >type devices and search for the desired MAC address of the device. Finally, for `<in-windows-paired-MAC>` search in the `keydump.reg` file the same (except >for one digit) MAC address. After changing those address, run the command.


### Method A. Dump and sync keys from within Linux
#### Additional Prerequisites
* `chntpw` 
  - Arch: `sudo pacman -S chntpw`
  - Debian/Ubuntu: `sudo apt install chntpw`

This method requires at least read-only access to your Windows drive in Linux.
- Run the `synckeys.py` Python 3 script with **root** or **sudo**:
```
sudo ./synckeys.py -w /path/to/windows/drive/root
```
The root path should be the root of your Windows drive, i.e. there's a `Windows` folder in it.
- Follow the prompts.
- Once the keys are updated, you can restart the bluetooth service with the following (or the equivalent on your system):
```
sudo systemctl restart bluetooth
```
- Enjoy :D
### Method B. Dump keys from Windows and sync to Linux
#### Additional Prequisites

On Windows you need the following:
1. [PSExec](http://live.sysinternals.com/psexec.exe) downloaded and accessible via the command line. E.g. downloaded to the root of your C:\ drive.
2. **Administrator** access.

### Steps
- Reboot into your Windows system and pair the same devices again. We will use the keys generated from this OS.
- Open a command prompt in **Administrator** mode and navigate to the directory where you downloaded [PSExec](http://live.sysinternals.com/psexec.exe) into. Run the following command to dump the keys:
```
psexec -s -i regedit /e c:\keydump.reg HKEY_LOCAL_MACHINE\SYSTEM\ControlSet001\Services\BTHPORT\Parameters\Keys
```
- Copy the file from `c:\keydump.reg` into a removeable storage or a location which is accessible by your Linux system.
- Reboot into your Linux system.
- Copy the `keydump.reg` file to an accessible location in your Linux filesystem and reboot your PC again to linux.
- Open a terminal and navigate to the location where `synckeys.py` is located.
- Run the `synckeys.py` Python 3 script with **root** or **sudo**:
```
sudo ./synckeys.py -r /path/to/keydump.reg
```
- The adapters and devices from the key dump will be compared to the pairing in Linux and if a difference is detected, it will prompt you to update the keys. You can choose Yes or No (default). If you choose `Yes`, a timestamped backup file is created in the `/var/lib/bluetooth/{ADAPTER_MAC}/{DEVICE_MAC}` directory before the update is performed.
```
Bluetooth Adapter - 7C:B2:7D:57:EA:D5
  DC:0C:2D:ED:01:65 (# not paired #)
  04:00:00:00:6A:8B (# not paired #)

  0C:E0:E4:C8:27:5D (PLT_BBTSENSE / PLT_BBTSENSE)
    | LinkKey: 63C1F72FB8E5F474AED058019A834FDA > No change required.

  F3:46:AD:D7:53:3C (Orochi V2 / Orochi V2)
    | IdentityResolvingKey: BB123FA60524A22A5AF33EE83514FF0B > Update to: AA764EA60524A76A5AF50EE49463ED0C
    | LongTermKey: 28513DB654511A7346BDA3F676CAE7F8 > Update to: 85140DC915611A7346ECD3F676CFF7E9
    |   EncSize: 16 > No change required.
    |   EDiv: 43465 > Update to: 74325
    |   Rand: 5734307009814747306 > Update to: 9876302985738291827
    > Update keys for device? (y/N): y
    > OK!
```
- Once the keys are updated, you can restart the bluetooth service with the following (or the equivalent on your system):
```
sudo systemctl restart bluetooth
```
- Enjoy :D