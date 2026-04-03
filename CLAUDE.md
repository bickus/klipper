# klipper-my

Custom Klipper fork with additional features ported from other forks and community contributions.

## Architecture Decision Records

ADRs documenting significant changes are in [`docs/adr/`](docs/adr/).

## Key Custom Modifications

- **MPC Heater Control** — Model Predictive Control heater algorithm ported from Kalico (see ADR-001)
- **Temperature Fan Curve Control** — `control: curve` option with percent-of-target support (in `klippy/plugins/temperature_fan.py`)
- **Plugin System** — `klippy/plugins/` directory searched before `klippy/extras/` for module overrides

## Build & Run

Standard Klipper build process. See upstream Klipper documentation.
