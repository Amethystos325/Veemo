# Veemo Service Management

## Start

```bash
sudo systemctl start veemo.service
```

## Stop

```bash
sudo systemctl stop veemo.service
```

## Restart

```bash
sudo systemctl restart veemo.service
```

## Status

```bash
sudo systemctl status veemo.service --no-pager -l
```

## Logs

```bash
journalctl -u veemo.service -f
```

## Enable At Boot

```bash
sudo systemctl enable veemo.service
```

## Disable At Boot

```bash
sudo systemctl disable veemo.service
```

## Uninstall Service

Stop the service and disable auto-start:

```bash
sudo systemctl stop veemo.service
sudo systemctl disable veemo.service
```

Remove the service unit and reload `systemd`:

```bash
sudo rm /etc/systemd/system/veemo.service
sudo systemctl daemon-reload
sudo systemctl reset-failed
```

If you also want to remove the deployed project directory:

```bash
rm -rf ~/veemo
```

## Note

If `veemo.service` is running, manual commands such as `veemo once` or
`veemo doctor` can fail with `GPIO busy` because the display hardware is already
owned by the service. Stop the service first if you need exclusive access.
