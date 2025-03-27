import os, time

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
        self.fan_name = None
        self.rpm_threshold = None
        self.save = False
        self.measure_per_step = 3

        self.printer.register_event_handler("klippy:ready", self._handle_ready)


    cmd_CALIBRATE_FAN_help = "Run fan calibration procedure to determine minimum power required to start fan and maximum power for fan operation." \
    "Usage: CALIBRATE_FAN [FAN=<fan_name>] [STEPS=<steps>] [RPM_THRESHOLD=<rpm_threshold>]" \
    "FAN: Name of the fan to calibrate. Default: fan" \
    "STEPS: Number of steps to run the fan through. Default: 10" \
    "RPM_THRESHOLD: Minimum RPM value increase to consider the fan speed as increasing. Default: 100"

    def _handle_ready(self):
        self.sample_timer = self.reactor.register_timer(self._next_calibration_step, self.reactor.NEVER)

    def cmd_CALIBRATE_FAN(self, gcmd):
        if self.calibration_active:
            gcmd.respond_error("Calibration already in progress")
            return
        self.current_gcmd = gcmd
        self.calibration_active = True
        
        steps = int(gcmd.get('STEPS', 10))
        self.measure_per_step = int(gcmd.get('MEASURE_PER_STEP', 3))
        self.fan_name = gcmd.get('FAN', 'fan')
        fan = self.printer.lookup_object(self.fan_name)
        if fan is None:
            gcmd.respond_error("Fan not found")
            return
        
        self.rpm_threshold = int(gcmd.get('RPM_THRESHOLD', 100))

        self.save = gcmd.get('SAVE', False)

        # Start calibration sequence
        gcmd.respond_info("Calibrating fan %s" % self.fan_name)
        gcmd.respond_info("Running fan from 0 to 100%% power in %d steps" % steps)
        
        
        # Initialize state
        self.current_step = 0
        self.current_measurement = 0
        self.data = []
        self.step_time = 3
        self.steps = steps
        self.initial_fanstop_issued = False
        
        # Start the calibration process
        self.reactor.update_timer(self.sample_timer, self.reactor.NOW)

    def _next_calibration_step(self, eventtime):

        if self.current_step == 0:
            fan_rpm = self._measure_fan_speed(eventtime, drop_result=self.current_step == 0)

            if fan_rpm is not None and fan_rpm > 0:
                self.current_gcmd.respond_info("Fan is already spinning at %s, waiting for it to stop" % fan_rpm)
                if not self.initial_fanstop_issued:
                    self.gcode.run_script("M106 S0")
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
        power_scaled = int((current_power/100) * 255)
        
        # Set fan power using proper command syntax
        cmd_str = f"M106 S{power_scaled}"
        self.current_gcmd.respond_info("Setting fan power to %d%% with command: %s" % (current_power, cmd_str))
        self.gcode.run_script(cmd_str)
        
        self.current_gcmd.respond_info("Waiting for %d seconds" % self.step_time)

        current_eventtime = self.reactor.monotonic()
        return current_eventtime + self.step_time

    def _measure_fan_speed(self, eventtime, drop_result=False):
        if not self.calibration_active:
            return None

        fan = self.printer.lookup_object('fan')
        status = fan.get_status(eventtime)
        
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
        # Analyze collected data
        min_power = None
        min_rpm = None
        max_power = None
        max_rpm = None
        
        for d in self.data:
            if d['rpm'] is None:
                continue
            #find the min power setting that causes the fan to spin
            if d['rpm'] > 0 and (min_power is None or d['rpm'] < min_rpm):
                min_power = d['power'] / 100
                min_rpm = d['rpm']
            #find the max power setting from where the rpm is not increasing within a threshold (self.rpm_threshold)
            if d['rpm'] > 0 and (max_power is None or d['rpm'] > (max_power + self.rpm_threshold)):
                max_power = d['power'] / 100
                max_rpm = d['rpm']

        #shutdown fan
        cmd_str = f"M106 S0"
        self.current_gcmd.respond_info("Setting fan power to 0%")
        self.gcode.run_script(cmd_str)
    
        # Report results
        self.current_gcmd.respond_info("Fan calibration complete!")
        self.current_gcmd.respond_info("Minimum power for fan rotation: %.1f%% @ %.1f RPM" %
                         (min_power if min_power is not None else 0, min_rpm if min_rpm is not None else 0))
        self.current_gcmd.respond_info("Maximum power for fan operation: %.1f%% @ %.1f RPM" %
                         (max_power if max_power is not None else 0, max_rpm if max_rpm is not None else 0)
                         )
        self.current_gcmd.respond_info("Saving calibration data...")

        if self.save:
            self.save_state(min_power, max_power)
        
        self._save_calibration_data()

        # Cleanup
        self.calibration_active = False
        self.current_gcmd = None
        self.initial_fanstop_issued = False
        self.fan_name = None
        self.rpm_threshold = None
        self.save = False

    def _save_calibration_data(self):

        filename = self.get_filename('calibration_data',time.strftime("%Y%m%d_%H%M%S"),self.fan_name)

        with open(filename, 'w') as f:
            f.write("Power, RPM\n")
            for d in self.data:
                f.write("%.2f, %.2f\n" % (d['power'] / 100, d['rpm']))

        self.current_gcmd.respond_info("Calibration data saved to %s" % filename)
    
    def get_filename(self, base, name_suffix, fan=None):
        name = base
        if fan:
            name += '_' + fan
        name += '_' + name_suffix
        return os.path.join("/tmp", name + ".csv")
    
    def save_state(self, min_power, max_power):
        configfile = self.printer.lookup_object('configfile')
        # Save the current parameters (for use with SAVE_CONFIG)
        configfile.set(self.fan_name, 'min_power', "%.2f" % min_power)
        configfile.set(self.fan_name, 'max_power', "%.2f" % max_power)

        self.current_gcmd.respond_info(
            "%s: min_power set to %.2f, max_power set to %.2f\n"
            "The SAVE_CONFIG command will update the printer config "
            "file and restart the printer."
            % (self.fan_name, min_power, max_power)
        )
        

def load_config(config):
    return CalibrateFan(config)