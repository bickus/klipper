from mcu import MCU_endstop, MCU_trsync, TriggerDispatch
from extras.query_endstops import QueryEndstops
from extras.manual_stepper import ManualStepper

import logging

class EndlessSpool_Endstop_Extensions:
    def endstop_clear_steppers(self):
        self._dispatch.clear_steppers()

class EndlessSpool_TriggerDispatch_Extensions:
    def dispatch_clear_steppers(self):
        logging.info("TriggerDispatch ::: clear_steppers")
        for trsync in self._trsyncs:
            trsync.clear_steppers()
class EndlessSpool_Trsync_Extensions:
    def trsync_clear_steppers(self):
        logging.info("MCU_trsync oid='%s' ::: clear_steppers",
                self._oid)
        self._steppers.clear()
        return

class EndlessSpool_QueryEndstop_Extensions:
    def lookup_endstop(self, name):
        for mcu_endstop, endstop_name in self.endstops:
            if endstop_name == name:
                return mcu_endstop
        return None

class EndlessSpool_ManualStepper_Extensions:
    def new_init(self, config):
        logging.info("EndlessSpool_ManualStepper_Extensions ::: new_init for '%s'", config.get_name())
        self.old_init(config)
        if config.get('flexi_home', None) is not None:
            self.flexi_home = True
            self._should_reenable_switch = True
            self.gcode = self.printer.lookup_object('gcode')
            stepper_name = config.get_name().split()[1]
            self.gcode.register_mux_command('MANUAL_STEPPER_FLEXI_HOME', "STEPPER",
                                    stepper_name, self.cmd_MANUAL_STEPPER_FLEXI_HOME)
        else:
            self.flexi_home = False

    def get_current_endstop_state(self, endstop_name):
        endless_spool = self.printer.lookup_object('endless_spool')
        switch = endless_spool.lookup_flexi_filament_switch(endstop_name)
        if (switch is None):
            raise self.printer.command_error(
                "filament_switch_sensor '%s' not found" % endstop_name)
        return switch.get_status(None)['filament_detected']

    def disable_filament_switch(self, endstop_name):
        logging.info("manual_stepper '%s' ::: disable_filament_switch ::: endstop_name='%s'",
                     self.rail.get_name(), endstop_name)
        endless_spool = self.printer.lookup_object('endless_spool')
        switch = endless_spool.lookup_flexi_filament_switch(endstop_name)
        if (switch is None):
            raise self.printer.command_error(
                "filament_switch_sensor '%s' not found" % endstop_name)
        is_enabled_switch = switch.get_status(None)['enabled']
        self._should_reenable_switch = is_enabled_switch
        if (is_enabled_switch):
            switch.disable()
            logging.info("manual_stepper '%s' ::: disable_filament_switch ::: endstop_name='%s' ::: disabled",
                     self.rail.get_name(), endstop_name)
            
    def enable_filament_switch(self, endstop_name):
        logging.info("manual_stepper '%s' ::: enable_filament_switch ::: endstop_name='%s' ::: should_reenable_switch='%s'",
                     self.rail.get_name(), endstop_name, self._should_reenable_switch)
        endless_spool = self.printer.lookup_object('endless_spool')
        switch = endless_spool.lookup_flexi_filament_switch(endstop_name)
        if (switch is None):
            raise self.printer.command_error(
                "filament_switch_sensor '%s' not found" % endstop_name)
        if (self._should_reenable_switch):
            switch.enable()
            self._should_reenable_switch=False
            logging.info("manual_stepper '%s' ::: enable_filament_switch ::: endstop_name='%s' ::: enabled",
                     self.rail.get_name(), endstop_name)

    def do_flexi_homing(self, movepos, speed, accel, triggered, check_trigger, endstop_name):
        logging.info("manual_stepper '%s' ::: do_flexi_homing ::: endstop_name='%s'",
                     self.rail.get_name(), endstop_name)
        if not self.flexi_home:
            raise self.printer.command_error(
                "This manual stepper does not support flexi home. Add flexi_home: true in the config section")
        
        self.homing_accel = accel
        self.do_set_position(0)
        pos = [movepos, 0., 0., 0.]
        query_endstops = self.printer.lookup_object('query_endstops')
        endstop=query_endstops.lookup_endstop(endstop_name)
        if endstop is None:
            raise self.printer.command_error(
                "No endstop found")
        endstop.clear_steppers()
        endstop.add_stepper(self.rail)
        endstops=[]
        endstops.append((endstop, endstop_name))
        phoming = self.printer.lookup_object('homing')
        phoming.manual_home(self, endstops, pos, speed,
                            triggered, check_trigger)

    def cmd_MANUAL_STEPPER_FLEXI_HOME(self, gcmd):
        speed = gcmd.get_float('SPEED', self.velocity, above=0.)
        accel = gcmd.get_float('ACCEL', self.accel, minval=0.)
        movepos = gcmd.get_float('DISTANCE', 2500)
        endstop_name=gcmd.get('ENDSTOP', None)
        trigger = gcmd.get('TRIGGER','AUTO').lower()

        # validate arguments
        if (endstop_name is None):
            raise self.printer.command_error("ENDSTOP argument should be provided")
        if (trigger not in ['auto','release','trigger']):
            raise self.printer.command_error("TRIGGER argument should be either AUTO, RELEASE or TRIGGER")
        
        triggerValue = True
        if (trigger=='release'):
            triggerValue=False
        elif (trigger=='auto'):
            triggerValue=not self.get_current_endstop_state(endstop_name)

        self.disable_filament_switch(endstop_name)
        try:
            self.do_flexi_homing(movepos, speed, accel, triggerValue, True, endstop_name)
            logging.info("manual_stepper '%s' ::: do_flexi_homing ::: completed @ '%s'",
                     self.rail.get_name(), self.get_position()[0])
        except self.printer.command_error as e:
            self.flush_step_generation()
            self.enable_filament_switch(endstop_name)
            raise self.printer.command_error(e)

        self.flush_step_generation()                
        self.enable_filament_switch(endstop_name)

class EndlessSpool:
    initialized = False

    def __init__(self, config):
        if (not EndlessSpool.initialized):
            self._extend_core_klipper()
            self._extend_manual_stepper()
            EndlessSpool.initialized=True

        self.printer = config.get_printer()
        self.is_enabled = config.get('enable', 'True')
        self._filament_switches=[]

    def _extend_core_klipper(self):
        logging.info("EndlessSpool ::: extend core")
        MCU_endstop.clear_steppers = EndlessSpool_Endstop_Extensions.endstop_clear_steppers
        TriggerDispatch.clear_steppers = EndlessSpool_TriggerDispatch_Extensions.dispatch_clear_steppers
        MCU_trsync.clear_steppers = EndlessSpool_Trsync_Extensions.trsync_clear_steppers
        QueryEndstops.lookup_endstop = EndlessSpool_QueryEndstop_Extensions.lookup_endstop

    def _extend_manual_stepper(self):
        logging.info("EndlessSpool ::: extend manual stepper")
        ManualStepper.enable_filament_switch=EndlessSpool_ManualStepper_Extensions.enable_filament_switch
        ManualStepper.disable_filament_switch=EndlessSpool_ManualStepper_Extensions.disable_filament_switch
        ManualStepper.do_flexi_homing=EndlessSpool_ManualStepper_Extensions.do_flexi_homing
        ManualStepper.cmd_MANUAL_STEPPER_FLEXI_HOME=EndlessSpool_ManualStepper_Extensions.cmd_MANUAL_STEPPER_FLEXI_HOME
        ManualStepper.get_current_endstop_state=EndlessSpool_ManualStepper_Extensions.get_current_endstop_state

        ManualStepper.old_init=ManualStepper.__init__
        ManualStepper.__init__=EndlessSpool_ManualStepper_Extensions.__dict__['new_init']

        return

    def register_flexi_filament_switch(self, name, switch):
        self._filament_switches.append((name,switch))

    def lookup_flexi_filament_switch(self, name):
        for switch_name, switch in self._filament_switches:
            if switch_name == name:
                return switch
        return None


def load_config(config):
    return EndlessSpool(config)



