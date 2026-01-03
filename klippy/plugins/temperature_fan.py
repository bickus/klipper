
# Support fans that are enabled when temperature exceeds a set threshold
#
# Copyright (C) 2016-2020  Kevin O'Connor <kevin@koconnor.net>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import statistics

from . import fan

KELVIN_TO_CELSIUS = -273.15
MAX_FAN_TIME = 5.0
AMBIENT_TEMP = 25.
PID_PARAM_BASE = 255.

class TemperatureFan:
    def __init__(self, config):
        self.name = config.get_name().split()[1]
        self.printer = config.get_printer()
        self.fan = fan.Fan(config, default_shutdown_speed=1.)
        self.min_temp = config.getfloat('min_temp', minval=KELVIN_TO_CELSIUS)
        self.max_temp = config.getfloat('max_temp', above=self.min_temp)
        pheaters = self.printer.load_object(config, 'heaters')
        self.sensor = pheaters.setup_sensor(config)
        self.sensor.setup_minmax(self.min_temp, self.max_temp)
        self.sensor.setup_callback(self.temperature_callback)
        pheaters.register_sensor(config, self)
        self.speed_delay = self.sensor.get_report_time_delta()
        self.max_speed_conf = config.getfloat(
            'max_speed', 1., above=0., maxval=1.)
        self.max_speed = self.max_speed_conf
        self.min_speed_conf = config.getfloat(
            'min_speed', 0.3, minval=0., maxval=1.)
        self.min_speed = self.min_speed_conf
        self.last_temp = 0.
        self.last_temp_time = 0.
        self.target_temp_conf = config.getfloat(
            'target_temp', 40. if self.max_temp > 40. else self.max_temp,
            minval=self.min_temp, maxval=self.max_temp)
        self.target_temp = self.target_temp_conf

        # >>> VORON MOD START: expose a flag to interpret curve points as percent of target
        # New optional boolean. If true (default), "points" are interpreted as (percent_of_target, speed).
        # If false, legacy absolute-temperature points are used.
        self.points_are_percent = config.getboolean('points_are_percent', False)
        # <<< VORON MOD END

        algos = {'watermark': ControlBangBang, 'pid': ControlPID, "curve": ControlCurve}
        algo = config.getchoice('control', algos)
        self.control = algo(self, config)
        self.next_speed_time = 0.
        self.last_speed_value = 0.
        gcode = self.printer.lookup_object('gcode')
        gcode.register_mux_command(
            "SET_TEMPERATURE_FAN_TARGET", "TEMPERATURE_FAN", self.name,
            self.cmd_SET_TEMPERATURE_FAN_TARGET,
            desc=self.cmd_SET_TEMPERATURE_FAN_TARGET_help)

    def set_tf_speed(self, read_time, value):
        if value <= 0.:
            value = 0.
        elif value < self.min_speed:
            value = self.min_speed
        if self.target_temp <= 0.:
            value = 0.
        if ((read_time < self.next_speed_time or not self.last_speed_value)
                and abs(value - self.last_speed_value) < 0.05):
            # No significant change in value - can suppress update
            return
        speed_time = read_time + self.speed_delay
        self.next_speed_time = speed_time + 0.75 * MAX_FAN_TIME
        self.last_speed_value = value
        self.fan.set_speed(value, speed_time)
    def temperature_callback(self, read_time, temp):
        self.last_temp = temp
        self.control.temperature_callback(read_time, temp)
    def get_temp(self, eventtime):
        return self.last_temp, self.target_temp
    def get_min_speed(self):
        return self.min_speed
    def get_max_speed(self):
        return self.max_speed
    def get_status(self, eventtime):
        status = self.fan.get_status(eventtime)
        status["temperature"] = round(self.last_temp, 2)
        status["target"] = self.target_temp
        status["control"] = self.control.get_type()
        return status
    cmd_SET_TEMPERATURE_FAN_TARGET_help = \
        "Sets a temperature fan target and fan speed limits"
    def cmd_SET_TEMPERATURE_FAN_TARGET(self, gcmd):
        temp = gcmd.get_float("TARGET", None)
        # >>> VORON MOD START: allow setting TARGET even when using control=curve
        # (Removed original restriction that raised an error when in curve mode.)
        # <<< VORON MOD END
        min_speed = gcmd.get_float('MIN_SPEED', self.min_speed)
        max_speed = gcmd.get_float('MAX_SPEED', self.max_speed)
        if min_speed > max_speed:
            raise self.printer.command_error(
                "Requested min speed (%.1f) is greater than max speed (%.1f)"
                % (min_speed, max_speed))
        self.set_min_speed(min_speed)
        self.set_max_speed(max_speed)
        self.set_temp(self.target_temp_conf if temp is None else temp)

    def set_temp(self, degrees):
        if degrees and (degrees < self.min_temp or degrees > self.max_temp):
            raise self.printer.command_error(
                "Requested temperature (%.1f) out of range (%.1f:%.1f)"
                % (degrees, self.min_temp, self.max_temp))
        self.target_temp = degrees
        # >>> VORON MOD START: notify curve controller that target changed
        if self.control.get_type() == "curve":
            self.control.on_target_changed()
        # <<< VORON MOD END

    def set_min_speed(self, speed):
        if speed and (speed < 0. or speed > 1.):
            raise self.printer.command_error(
                "Requested min speed (%.1f) out of range (0.0 : 1.0)"
                % (speed))
        self.min_speed = speed

    def set_max_speed(self, speed):
        if speed and (speed < 0. or speed > 1.):
            raise self.printer.command_error(
                "Requested max speed (%.1f) out of range (0.0 : 1.0)"
                % (speed))
        self.max_speed = speed

######################################################################
# Bang-bang control algo
######################################################################

class ControlBangBang:
    def __init__(self, temperature_fan, config):
        self.temperature_fan = temperature_fan
        self.max_delta = config.getfloat('max_delta', 2.0, above=0.)
        self.heating = False
    def temperature_callback(self, read_time, temp):
        current_temp, target_temp = self.temperature_fan.get_temp(read_time)
        if (self.heating
            and temp >= target_temp+self.max_delta):
            self.heating = False
        elif (not self.heating
              and temp <= target_temp-self.max_delta):
            self.heating = True
        if self.heating:
            self.temperature_fan.set_tf_speed(read_time, 0.)
        else:
            self.temperature_fan.set_tf_speed(
                read_time, self.temperature_fan.get_max_speed())
    def get_type(self):
        return "watermark"

######################################################################
# Proportional Integral Derivative (PID) control algo
######################################################################

PID_SETTLE_DELTA = 1.
PID_SETTLE_SLOPE = .1

class ControlPID:
    def __init__(self, temperature_fan, config):
        self.temperature_fan = temperature_fan
        self.Kp = config.getfloat('pid_Kp') / PID_PARAM_BASE
        self.Ki = config.getfloat('pid_Ki') / PID_PARAM_BASE
        self.Kd = config.getfloat('pid_Kd') / PID_PARAM_BASE
        self.min_deriv_time = config.getfloat('pid_deriv_time', 2., above=0.)
        self.temp_integ_max = 0.
        if self.Ki:
            self.temp_integ_max = self.temperature_fan.get_max_speed() / self.Ki
        self.prev_temp = AMBIENT_TEMP
        self.prev_temp_time = 0.
        self.prev_temp_deriv = 0.
        self.prev_temp_integ = 0.
    def temperature_callback(self, read_time, temp):
        current_temp, target_temp = self.temperature_fan.get_temp(read_time)
        time_diff = read_time - self.prev_temp_time
        # Calculate change of temperature
        temp_diff = temp - self.prev_temp
        if time_diff >= self.min_deriv_time:
            temp_deriv = temp_diff / time_diff
        else:
            temp_deriv = (self.prev_temp_deriv * (self.min_deriv_time-time_diff)
                          + temp_diff) / self.min_deriv_time
        # Calculate accumulated temperature "error"
        temp_err = target_temp - temp
        temp_integ = self.prev_temp_integ + temp_err * time_diff
        temp_integ = max(0., min(self.temp_integ_max, temp_integ))
        # Calculate output
        co = self.Kp*temp_err + self.Ki*temp_integ - self.Kd*temp_deriv
        bounded_co = max(0., min(self.temperature_fan.get_max_speed(), co))
        self.temperature_fan.set_tf_speed(
            read_time, max(self.temperature_fan.get_min_speed(),
                           self.temperature_fan.get_max_speed() - bounded_co))
        # Store state for next measurement
        self.prev_temp = temp
        self.prev_temp_time = read_time
        self.prev_temp_deriv = temp_deriv
        if co == bounded_co:
            self.prev_temp_integ = temp_integ

    def get_type(self):
        return "pid"
    
######################################################################
# Curve Control algo
######################################################################

class ControlCurve:
    def __init__(self, temperature_fan, config, controlled_fan=None):
        self.temperature_fan = temperature_fan
        self.controlled_fan = (
            temperature_fan if controlled_fan is None else controlled_fan
        )

        # >>> VORON MOD START: interpret curve "points" as (percent_of_target, speed)
        # Example:
        # [temperature_fan my_fan]
        # control: curve
        # points_are_percent: True
        # points:
        #   40, 0.0
        #   60, 0.2
        #   80, 0.5
        # (100% is implicit and always set to max_speed)
        self.use_percent = self.temperature_fan.points_are_percent
        self.percent_points = []
        if self.use_percent:
            raw_points = config.getlists("points", seps=(",", "\n"), parser=float, count=2)
            for pct, pwm in raw_points:
                if pct is None or pwm is None:
                    continue
                if pct < 0 or pct > 100:
                    raise temperature_fan.printer.config_error(
                        "Percent in point must be between 0 and 100."
                    )
                if pwm < temperature_fan.get_min_speed() or pwm > temperature_fan.get_max_speed():
                    raise temperature_fan.printer.config_error(
                        "Speed in point must be within min_speed and max_speed."
                    )
                self.percent_points.append([pct, pwm])
            # Ensure we have at least one point below 100 and add implicit 100% endpoint
            self.percent_points.append([100.0, temperature_fan.get_max_speed()])  # 100% -> max
            if len(self.percent_points) < 2:
                raise temperature_fan.printer.config_error(
                    "At least two points (including the implicit 100%) are required for curve."
                )
            self.percent_points.sort(key=lambda p: p[0])
            last = [0.0, temperature_fan.get_min_speed()]
            for p in self.percent_points:
                if p[1] < last[1]:
                    raise temperature_fan.printer.config_error(
                        "Points with higher percent must have higher or equal speed."
                    )
                last = p
        else:
            # Legacy absolute-temperature points (unchanged behavior)
            self.points = []
            points = config.getlists(
                "points", seps=(",", "\n"), parser=float, count=2
            )
            for temp, pwm in points:
                current_point = [temp, pwm]
                if current_point is None:
                    continue
                if len(current_point) != 2:
                    raise temperature_fan.printer.config_error(
                        "Point needs to have exactly one temperature and one speed "
                        "value."
                    )
                if current_point[0] > temperature_fan.target_temp:
                    raise temperature_fan.printer.config_error(
                        "Temperature in point can not exceed target temperature."
                    )
                if current_point[0] < temperature_fan.min_temp:
                    raise temperature_fan.printer.config_error(
                        "Temperature in point can not fall below min_temp."
                    )
                if current_point[1] > temperature_fan.get_max_speed():
                    raise temperature_fan.printer.config_error(
                        "Speed in point can not exceed max_speed."
                    )
                if current_point[1] < temperature_fan.get_min_speed():
                    raise temperature_fan.printer.config_error(
                        "Speed in point can not fall below min_speed."
                    )
                self.points.append(current_point)
            self.points.append(
                [temperature_fan.target_temp, temperature_fan.get_max_speed()]
            )
            if len(self.points) < 2:
                raise temperature_fan.printer.config_error(
                    "At least two points need to be defined for curve in "
                    "temperature_fan."
                )
            self.points.sort(key=lambda p: p[0])
            last_point = [temperature_fan.min_temp, temperature_fan.get_min_speed()]
            for point in self.points:
                if point[1] < last_point[1]:
                    raise temperature_fan.printer.config_error(
                        "Points with higher temperatures have to have higher or "
                        "equal speed than points with lower temperatures."
                    )
                last_point = point
        # <<< VORON MOD END

        self.cooling_hysteresis = config.getfloat("cooling_hysteresis", 0.0)
        self.heating_hysteresis = config.getfloat("heating_hysteresis", 0.0)
        self.smooth_readings = config.getint("smooth_readings", 10, minval=1)
        self.stored_temps = []
        for i in range(self.smooth_readings):
            self.stored_temps.append(0.0)
        self.last_temp = 0.0

    # >>> VORON MOD START: handle target temp changes (no-op for percent mode)
    def on_target_changed(self):
        # For percent-based curve we don't need to rebuild anything,
        # because we compute using temp/target on the fly.
        # For legacy absolute points, we ensure the terminal point equals the new target.
        if not getattr(self, "use_percent", False):
            # Update the last point to reflect new target == max speed
            # Remove any existing point at old target and append the new one, then resort.
            new_list = [p for p in self.points if p[0] != self.temperature_fan.target_temp]
            new_list.append([self.temperature_fan.target_temp, self.temperature_fan.get_max_speed()])
            new_list.sort(key=lambda p: p[0])
            self.points = new_list
    # <<< VORON MOD END

    def temperature_callback(self, read_time, temp):
        current_temp, target_temp = self.temperature_fan.get_temp(read_time)
        temp = self.smooth_temps(temp)
        if target_temp <= 0:
            self.controlled_fan.set_tf_speed(read_time, 0.0)
            return
        if temp >= target_temp:
            self.temperature_fan.set_tf_speed(
                read_time, self.temperature_fan.get_max_speed()
            )
            return

        if getattr(self, "use_percent", False):
            # >>> VORON MOD START: percent-of-target curve evaluation
            pct = max(0.0, min(100.0, (temp / target_temp) * 100.0))
            below = [0.0, self.temperature_fan.get_min_speed()]
            above = [100.0, self.temperature_fan.get_max_speed()]
            for p in self.percent_points:
                if p[0] < pct:
                    below = p
                else:
                    above = p
                    break
            self.controlled_fan.set_tf_speed(
                read_time, self.interpolate_percent(below, above, pct)
            )
            # <<< VORON MOD END
        else:
            # Legacy absolute-temperature interpolation
            below = [
                self.temperature_fan.min_temp,
                self.temperature_fan.get_min_speed(),
            ]
            above = [
                self.temperature_fan.max_temp,
                self.temperature_fan.get_max_speed(),
            ]
            for config_temp in self.points:
                if config_temp[0] < temp:
                    below = config_temp
                else:
                    above = config_temp
                    break
            self.controlled_fan.set_tf_speed(
                read_time, self.interpolate(below, above, temp)
            )

    def interpolate(self, below, above, temp):
        return (
            (below[1] * (above[0] - temp)) + (above[1] * (temp - below[0]))
        ) / (above[0] - below[0])

    # >>> VORON MOD START: percent-based interpolation
    def interpolate_percent(self, below, above, pct):
        return (
            (below[1] * (above[0] - pct)) + (above[1] * (pct - below[0]))
        ) / (above[0] - below[0])
    # <<< VORON MOD END

    def smooth_temps(self, current_temp):
        if (
            self.last_temp - self.cooling_hysteresis
            <= current_temp
            <= self.last_temp + self.heating_hysteresis
        ):
            temp = self.last_temp
        else:
            temp = current_temp
        self.last_temp = temp
        for i in range(1, len(self.stored_temps)):
            self.stored_temps[i] = self.stored_temps[i - 1]
        self.stored_temps[0] = temp
        return statistics.median(self.stored_temps)

    def get_type(self):
        return "curve"

def load_config_prefix(config):
    return TemperatureFan(config)
