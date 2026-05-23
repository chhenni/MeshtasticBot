# USB Device Aliases (udev)

By default, Linux assigns USB serial devices to `/dev/ttyUSB0`, `/dev/ttyACM0`, etc. — and the numbering can change depending on which order devices are plugged in.

This guide sets up stable **udev symlinks** so the paths in `docker-compose.yml` and `config.yaml` always point to the right device, regardless of plug order.

---

## 1. Find the USB IDs for your devices

Plug in each device one at a time and run:

```bash
udevadm info -a /dev/ttyUSB0 | grep -E 'idVendor|idProduct|serial'
udevadm info -a /dev/ttyACM0 | grep -E 'idVendor|idProduct|serial'
```

Note the `idVendor` and `idProduct` values for each device.

Common values:

| Device | idVendor | idProduct |
|---|---|---|
| Meshtastic node (CP210x) | `10c4` | `ea60` |
| Flipper Zero | `0483` | `5740` |

> If two devices share the same vendor/product ID (e.g. cheap CP210x clones),
> use `ATTRS{serial}=="..."` to distinguish them by their USB serial number.

---

## 2. Create the udev rules file

```bash
sudo nano /etc/udev/rules.d/99-meshtastic.rules
```

Paste (adjusting IDs if needed):

```
# Meshtastic node
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", SYMLINK+="meshtastic"

# Flipper Zero
SUBSYSTEM=="tty", ATTRS{idVendor}=="0483", ATTRS{idProduct}=="5740", SYMLINK+="flipper"
```

---

## 3. Reload and verify

```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
ls -la /dev/meshtastic /dev/flipper
```

You should see symlinks pointing to the actual `ttyUSB*` / `ttyACM*` device:

```
lrwxrwxrwx 1 root root 7 May 23 15:00 /dev/flipper -> ttyACM0
lrwxrwxrwx 1 root root 7 May 23 15:00 /dev/meshtastic -> ttyUSB1
```

---

## 4. Restart the bot

```bash
docker-compose up -d
```

The `docker-compose.yml` already references `/dev/meshtastic` and `/dev/flipper`, so no further changes are needed.
