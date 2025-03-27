import os, time

import configfile

class CalibrateFan:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.gcode.register_command('CALIBRATE_FAN',
                                  self.cmd_CALIBRATE_FAN,
                                  desc=self.cmd_CALIBRATE_FAN_help)
        self.current_gcmd = None
        self.calibration_active = False
        self.sample_timer = None 
        self.fan = None
        self.fan_name = None

        self.measure_per_step = 3

        self.printer.register_event_handler("klippy:ready", self._handle_ready)


    cmd_CALIBRATE_FAN_help = "Run fan calibration procedure to determine minimum power required to start fan and maximum power for fan operation." \
    "Usage: CALIBRATE_FAN [FAN=<fan_name>] [STEPS=<steps>]" \
    "FAN: Name of the fan to calibrate. Default: fan" \
    "STEPS: Number of steps to run the fan through. Default: 10" \

    def _handle_ready(self):
        self.sample_timer = self.reactor.register_timer(self._next_calibration_step, self.reactor.NEVER)

    def cmd_CALIBRATE_FAN(self, gcmd):
        if self.calibration_active:
            gcmd.respond_info("Calibration already in progress")
            return
        
        self._reset_state()

        self.current_gcmd = gcmd
        self.calibration_active = True
        
        steps = int(gcmd.get('STEPS', 10))
        self.measure_per_step = int(gcmd.get('MEASURE_PER_STEP', 3))
        self.fan_name = gcmd.get('FAN', 'fan')
        self.fan = self._try_find_fan(self.fan_name)
        if self.fan is None:
            self.fan = self._try_find_fan('fan_generic %s' % self.fan_name)
        if self.fan is None:
            self.fan = self._try_find_fan('heater_fan %s' % self.fan_name)
        if self.fan is None:
            gcmd.respond_error("Fan %s not found" % self.fan_name)
            self.calibration_active = False
            return
        
        # Start calibration sequence
        gcmd.respond_info("Calibrating fan %s" % self.fan_name)
        gcmd.respond_info("Running fan from 0 to 100%% power in %d steps" % steps)
        
        # Start the calibration process
        self.reactor.update_timer(self.sample_timer, self.reactor.NOW)

    def _try_find_fan(self, fan_name):
        try:
            return self.printer.lookup_object(fan_name)
        except configfile.error:
            return None
        

    def _next_calibration_step(self, eventtime):
        if self.current_step == 0:
            fan_rpm = self._measure_fan_speed(eventtime, drop_result=self.current_step == 0)

            if fan_rpm is not None and fan_rpm > 0:
                self.current_gcmd.respond_info("Fan is already spinning at %s, waiting for it to stop" % fan_rpm)
                if not self.initial_fanstop_issued:
                    self._set_fan_power(0)
                    self.initial_fanstop_issued = True
                return self.reactor.monotonic() + 1
        
        self._measure_fan_speed(eventtime)

        # Measure fan speed multiple times per step
        if self.current_measurement < self.measure_per_step:
            self.current_measurement += 1
            return self.reactor.monotonic() + .5

        # Move to next step
        self.current_measurement = 0
        self.current_step += 1

        if self.current_step > self.steps:
            self._calibration_complete()
            return self.reactor.NEVER
            
        # Calculate current power level
        current_power = (100 / self.steps ) * self.current_step
        power_scaled = current_power/100
        
        # Set fan power using proper command syntax
        self.current_gcmd.respond_info("Setting fan power to %d%%" % (current_power))
        self._set_fan_power(power_scaled)
        
        #self.current_gcmd.respond_info("Waiting for %d seconds" % self.step_time)

        current_eventtime = self.reactor.monotonic()
        return current_eventtime + self.step_time

    def _measure_fan_speed(self, eventtime, drop_result=False):
        if not self.calibration_active:
            return None

        status = self.fan.get_status(eventtime)
        
        # Store data
        if not drop_result:
            self.data.append({
                'power': (100 / self.steps ) * self.current_step,
                'rpm': status['rpm']
            })
            rpm_str = str(status['rpm'])
            if status['rpm'] is None:
                rpm_str = 'N/A'
            #self.current_gcmd.respond_info("Fan speed: %s RPM" % rpm_str)

        return status['rpm']

    def _calibration_complete(self):            
        #shutdown fan
        self.current_gcmd.respond_info("Setting fan power to 0%")
        self._set_fan_power(0)
    
        self.current_gcmd.respond_info("Saving calibration data...")
        
        self._save_calibration_data()

        # Cleanup
        self.calibration_active = False
        self._reset_state()

    def _save_calibration_data(self):

        filename = self.get_filename('calibration_data',time.strftime("%Y%m%d_%H%M%S"),self.fan_name)

        with open(filename, 'w') as f:
            f.write("Power, RPM\n")
            for d in self.data:
                f.write("%.2f, %.2f\n" % (d['power'] / 100, d['rpm']))

        self.current_gcmd.respond_info("Calibration data saved to %s" % filename)
    
    def _set_fan_power(self, power):
        #check fan type if fan is Fan then use M106 if fan is GenericFan then use SET_FAN_SPEED        
        if self.fan.__class__.__name__ == 'Fan':
            cmd_str = f"M106 S{power}"
        elif self.fan.__class__.__name__ == 'PrinterFanGeneric':
            power_scaled = int(power * 255)
            cmd_str = f"SET_FAN_SPEED FAN={self.fan_name} SPEED={power_scaled}"
        else:
            self.current_gcmd.respond_info("Fan type not supported %s" % fan.__class__.__name__)
            return

        self.gcode.run_script(cmd_str)

    def _reset_state(self):
        self.current_step = 0
        self.current_measurement = 0
        self.data = []
        self.step_time = 3
        self.steps = 10
        self.current_gcmd = None
        self.initial_fanstop_issued = False
        self.fan = None
        self.fan_name = None

    def get_filename(self, base, name_suffix, fan_name=None):
        name = base
        if fan_name:
            name += '_' + fan_name
        name += '_' + name_suffix
        return os.path.join("/tmp", name + ".csv")        

def load_config(config):
    return CalibrateFan(config)