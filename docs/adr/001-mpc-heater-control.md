# ADR-001: Port MPC Heater Control from Kalico

**Date:** 2026-04-03

**Status:** Accepted

## Context

The stock Klipper PID heater control algorithm, while functional, has known limitations: it requires manual tuning per-heater, responds poorly to environmental changes (fan speed, filament cooling), and can overshoot during initial heatup. MPC (Model Predictive Control) is a physics-based alternative that models the thermal system and predicts heat requirements, producing smoother temperature control with better disturbance rejection.

The Kalico Klipper fork (https://github.com/KalicoCrew/kalico) implements a mature MPC heater control system. Rather than rewriting this safety-critical code, we ported it directly from Kalico to minimize the risk of introducing bugs in code that controls heating elements at dangerous temperatures.

**Source:** Kalico fork at `/home/bickus/projects/kalico` (commit at time of port)

## Decision

Port MPC heater control from Kalico by directly copying the implementation with minimal, targeted modifications. The approach prioritizes correctness and safety over code elegance.

**Key design decisions:**
- **Direct copy of `control_mpc.py`** — the core MPC algorithm file is byte-for-byte identical to Kalico's version. No modifications were made to the algorithm.
- **Full ProfileManager port** — Kalico's profile management system was ported in full (excluding non-MPC control types) to support runtime profile switching and `PID_PROFILE` GCode commands.
- **`danger_options` stubbed out** — Kalico's `danger_options.py` module (which allows overriding safety limits via config) was NOT ported. Instead, the two MPC virtual sensor files have the `danger_options` import removed and limits are always enforced. This is the safest approach.
- **`MAX_HEAT_TIME` preserved at 5.0** — Kalico uses `MAX_HEAT_TIME = 3.0`; we preserved klipper-my's upstream value of `5.0` to match the firmware's expected watchdog timeout. This has zero effect on the MPC algorithm (see proof below).
- **LCD menu entries skipped** — Kalico's `display/menu.cfg` entries for MPC calibration dialogs were not ported. `MPC_CALIBRATE` is available as a GCode command.

## Files Modified/Created

| File | Action |
|------|--------|
| `klippy/gcode.py` | Added `_interrupt_counter`, `get_interrupt_counter()`, `increment_interrupt_counter()`, `HEATER_INTERRUPT` command |
| `klippy/klippy.py` | Added `WaitInterruption` exception class, `wait_while()` method on Printer |
| `klippy/extras/control_mpc.py` | **New** — verbatim copy from Kalico (MPC algorithm + calibration) |
| `klippy/extras/heaters.py` | Major rebuild from Kalico base with targeted exclusions |
| `klippy/extras/mpc_ambient_temperature.py` | **New** — MPC ambient temperature virtual sensor (danger_options stubbed) |
| `klippy/extras/mpc_block_temperature.py` | **New** — MPC block temperature virtual sensor (danger_options stubbed) |
| `klippy/extras/temperature_sensors.cfg` | Added MPC sensor type registrations |
| `klippy/extras/pid_calibrate.py` | Updated `set_control()` calls for new signature, added ControlAutoTune stubs |

## Fully Migrated Features

- **MPC control algorithm** (`control_mpc.py`) — complete thermal model with block temperature simulation, sensor lag compensation, adaptive ambient estimation, fan modulation, and filament feed-forward
- **MPC calibration** — `MPC_CALIBRATE` GCode command with multi-phase heatup and steady-state transfer measurement
- **MPC runtime tuning** — `MPC_SET` GCode command for adjusting filament parameters at runtime
- **ProfileManager** — heater profile management supporting named profiles with `PID_PROFILE LOAD/SAVE/REMOVE` commands
- **`printer.wait_while()` infrastructure** — interrupt counter mechanism, `HEATER_INTERRUPT` GCode command, `WaitInterruption` exception class for cancellable blocking operations
- **MPC virtual sensors** — `mpc_ambient_temperature` and `mpc_block_temperature` sensor types exposing MPC's internal model state for monitoring
- **`verify_mainthread_time` safety watchdog** — replaces the simpler `is_shutdown` boolean flag with a time-based watchdog that forces heater off if the main thread stops responding within 5 seconds
- **`set_control(keep_target=True)` signature** — control algorithm swap now optionally preserves target temperature (needed for MPC calibration phase transitions)
- **ControlPID/ControlBangBang profile-based constructors** — control classes now accept a profile dict instead of reading config directly, enabling runtime profile switching
- **New GCode commands**: `SET_HEATER_PID`, `SET_SMOOTH_TIME`, `COLD_EXTRUDE`, `PID_PROFILE`, `HEATER_INTERRUPT`

## Partially Migrated Features

- **ProfileManager `PID_PROFILE` command** — `LOAD` and `REMOVE` subcommands work for all control types (PID, watermark, MPC). However, `SAVE`, `GET_VALUES`, and `SET_VALUES` only work with PID profiles — they access PID-specific keys (`pid_kp`, `pid_ki`, `pid_kd`, `pid_tolerance`) that MPC profiles don't have, causing `KeyError`. MPC profiles are saved via `MPC_CALIBRATE` + `SAVE_CONFIG` instead.
- **Timing constants** — `QUELL_STALE_TIME` (7.0) and `MAX_MAINTHREAD_TIME` (5.0) were copied from Kalico, but `MAX_HEAT_TIME` (5.0) and the `next_pwm_time` formula were preserved from klipper-my to match firmware expectations.

## Omitted Features (Intentionally NOT Ported)

- **`ControlVelocityPID`** — Kalico's alternative PID algorithm (`control: pid_v`). Not needed; standard PID is sufficient.
- **`ControlDualLoopPID` / `ControlInnerPID`** — Kalico's dual-sensor PID control (`control: dual_loop_pid`). Requires `DualSensorHeater` class and secondary sensor infrastructure.
- **`DualSensorHeater`** — secondary sensor heater wrapper, only used by dual_loop_pid.
- **`danger_options.py` module** — Kalico-specific safety override infrastructure. Stubbed out; thermal limits are always enforced in our port.
- **LCD menu entries** — `display/menu.cfg` dialogs for `MPC_CALIBRATE`. Command-line `MPC_CALIBRATE` remains fully functional.
- **Kalico's `pid_calibrate.py` rewrite** — Kalico's version (499 lines) includes tolerance-based convergence and secondary calibration for dual_loop_pid. We kept klipper-my's simpler version (146 lines) with minimal compatibility updates (added `keep_target=False` to `set_control()` calls and interface stubs to `ControlAutoTune`).
- **Cosmetic formatting changes** — Kalico reformatted `heater_bed.py`, `heater_generic.py`, `verify_heater.py`, `homing_heaters.py` with double quotes and Black-style formatting. These files were not touched.

## Known Limitations

1. **`PID_PROFILE SAVE/GET_VALUES/SET_VALUES` crash with `KeyError` when MPC is active** — pre-existing Kalico limitation. Use `MPC_CALIBRATE` + `SAVE_CONFIG` for MPC profiles.
2. **`gcode.respond_error()` bug fixed during port** — Kalico's MPC sensor files call `gcode.respond_error()` which doesn't exist (only private `_respond_error`). Fixed by replacing with `gcode.respond_info()`.
3. **`HEATER_INTERRUPT` help text** — Added for discoverability; not present in Kalico's source.
4. **`TuningControl` lacks `update_smooth_time()`** — If `SET_SMOOTH_TIME` is issued during MPC calibration, it would fail. Pre-existing Kalico limitation, extremely unlikely scenario.
5. **Pre-existing Kalico edge cases in `control_mpc.py`** (copied verbatim, not introduced by port):
   - `process_first_pass()` crashes with `TypeError` if heater never reaches threshold temperature during calibration (e.g., faulty wiring)
   - `measure_power()` may divide by zero if measurement samples are empty
   - `process_second_pass()` may divide by zero if ambient temperature equals target temperature

## MAX_HEAT_TIME Safety Proof

`MAX_HEAT_TIME` was changed from Kalico's 3.0 to klipper-my's 5.0. This has **zero effect on the MPC algorithm**:

- `control_mpc.py` does not reference `MAX_HEAT_TIME` or `next_pwm_time` — verified by exhaustive search
- MPC's timing comes from sensor callbacks (~300ms for ADC thermistors), independent of `MAX_HEAT_TIME`
- `MAX_HEAT_TIME` only affects: (1) MCU firmware watchdog timeout, (2) PWM update suppression window for redundant values
- The `next_pwm_time` formula (`0.75 * MAX_HEAT_TIME = 3.75s`) keeps forced updates well within the 5.0s firmware watchdog
- `MAX_HEAT_TIME = 5.0` is the upstream Klipper default

## Consequences

- New `control: mpc` option available for `[extruder]` and `[heater_bed]` config sections
- Existing `control: pid` and `control: watermark` configs continue to work without changes
- Control class constructors changed from `(heater, config)` to `(profile, heater, load_clean)` — affects any third-party code that instantiates control classes directly
- New GCode commands available: `MPC_CALIBRATE`, `MPC_SET`, `HEATER_INTERRUPT`, `PID_PROFILE`, `SET_HEATER_PID`, `SET_SMOOTH_TIME`, `COLD_EXTRUDE`
- **Next steps:** Test on actual hardware with `MPC_CALIBRATE HEATER=extruder TARGET=200`, verify temperature stability, compare with PID performance
