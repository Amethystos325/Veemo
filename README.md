# Veemo

Veemo is a Raspberry Pi InkSight-compatible client for the Waveshare 4.2 inch
e-Paper Module (V2). It fetches rendered BMP images from an InkSight backend and
shows them on the connected display without porting the ESP32 firmware stack.

## Features

- Runs as a foreground CLI or a `systemd` service
- Uses the existing InkSight device APIs for token, render, and heartbeat
- Supports fast refresh with periodic full refresh to reduce ghosting
- Skips unchanged frames by default
- Keeps the backend integration abstract so the same client can target the
  official hosted backend or a self-hosted InkSight deployment

## Requirements

- Raspberry Pi with SPI enabled
- Waveshare 4.2inch e-Paper Module (V2) wired as documented in
  [platforms/raspberry3b+/PIN.md](/Users/cat/Desktop/code/Veemo/platforms/raspberry3b+/PIN.md)
- Python 3.11+
- Waveshare runtime dependencies:
  - `Pillow`
  - `spidev`
  - `gpiozero`
  - `RPi.GPIO`

Install the Veemo package and dependencies:

```bash
python3 -m pip install -e '.[dev]'
python3 -m pip install spidev gpiozero RPi.GPIO
```

## Configuration

Copy the sample config and adjust it for your environment:

```bash
cp veemo.toml.example veemo.toml
```

Environment overrides:

- `VEEMO_BACKEND_BASE_URL`
- `VEEMO_LOG_LEVEL`
- `VEEMO_CONFIG`

## Usage

Run once:

```bash
veemo once
```

Run continuously:

```bash
veemo run
```

Run diagnostics:

```bash
veemo doctor
```

## systemd

An example unit file is provided at
[systemd/veemo.service](/Users/cat/Desktop/code/Veemo/systemd/veemo.service).
The sample unit runs Veemo directly from `/home/cat/veemo`; adjust `User`,
`WorkingDirectory`, `PYTHONPATH`, and the config path if your deployment uses a
different location.

Recommended installation:

```bash
sudo cp systemd/veemo.service /etc/systemd/system/veemo.service
sudo systemctl daemon-reload
sudo systemctl enable --now veemo.service
```

## Notes

- Veemo loads the Waveshare Python driver from the repository's
  `platforms/raspberry3b+/examples/python/lib` directory.
- The client only supports 400x300 monochrome BMP payloads in v1.
- On restart Veemo requests the device token again; InkSight will reuse the
  existing token for the same MAC if one already exists.
