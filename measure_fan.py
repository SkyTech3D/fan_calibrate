import os
import time
import configfile


class MeasureFan:
    def __init__(self, config):
        # Initialize printer and reactor objects
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')

        # Register the MEASURE_FAN G-code command
        self.gcode.register_command(
            'MEASURE_FAN',
            self.cmd_MEASURE_FAN,
            desc=self.cmd_MEASURE_FAN_help
        )

        # Initialize state variables
        self.current_gcmd = None
        self.measure_active = False
        self.sample_timer = None
        self.fan = None
        self.fan_name = None
        self.measure_per_step = 3

        # Register event handler for when Klipper is ready
        self.printer.register_event_handler("klippy:ready", self._handle_ready)

    # G-code command help text
    cmd_MEASURE_FAN_help = (
        "Run fan measurement procedure to determine minimum power required to start fan "
        "and maximum power for fan operation.\n"
        "Usage: MEASURE_FAN [FAN=<fan_name>] [STEPS=<steps>]\n"
        "FAN: Name of the fan to measure. Default: fan\n"
        "STEPS: Number of steps to run the fan through. Default: 10"
    )

    # Event Handlers
    def _handle_ready(self):
        """Register the timer for measurement steps when Klipper is ready."""
        self.sample_timer = self.reactor.register_timer(self._next_measure_step, self.reactor.NEVER)

    # G-code Command Handlers
    def cmd_MEASURE_FAN(self, gcmd):
        """Handle the MEASURE_FAN G-code command."""
        if self.measure_active:
            gcmd.respond_info("Measure already in progress")
            return

        self._reset_state()

        # Parse G-code parameters
        self.current_gcmd = gcmd
        self.measure_active = True
        self.steps = int(gcmd.get('STEPS', 10))
        self.measure_per_step = int(gcmd.get('MEASURE_PER_STEP', 3))
        self.fan_name = gcmd.get('FAN', 'fan')

        # Find the fan object
        self.fan = self._try_find_fan(self.fan_name)
        if self.fan is None:
            gcmd.respond_error(f"Fan {self.fan_name} not found")
            self.measure_active = False
            return

        # Start calibration
        gcmd.respond_info(f"Measuring fan {self.fan_name} ...")
        gcmd.respond_info(f"Running fan from 0 to 100% power in {self.steps} steps")
        self.reactor.update_timer(self.sample_timer, self.reactor.NOW)

    def _try_find_fan(self, fan_name):
        """Attempt to find the fan object by name."""
        try:
            return self.printer.lookup_object(fan_name)
        except configfile.error:
            return None

    # Measure Logic
    def _next_measure_step(self, eventtime):
        """Perform the next step in the measure process."""
        if self.current_step == 0:
            fan_rpm = self._measure_fan_speed(eventtime, drop_result=True)
            if fan_rpm is not None and fan_rpm > 0:
                self.current_gcmd.respond_info(f"Fan is already spinning at {fan_rpm}, waiting for it to stop")
                if not self.initial_fanstop_issued:
                    self._set_fan_power(0)
                    self.initial_fanstop_issued = True
                return self.reactor.monotonic() + 1

        self._measure_fan_speed(eventtime)

        # Measure fan speed multiple times per step
        if self.current_measurement < self.measure_per_step:
            self.current_measurement += 1
            return self.reactor.monotonic() + 0.5

        # Move to the next step
        self.current_measurement = 0
        self.current_step += 1

        if self.current_step > self.steps:
            self._measure_complete()
            return self.reactor.NEVER

        # Set fan power for the current step
        current_power = (100 / self.steps) * self.current_step
        power_scaled = current_power / 100
        self.current_gcmd.respond_info(f"Setting fan power to {current_power}%")
        self._set_fan_power(power_scaled)

        return self.reactor.monotonic() + self.step_time

    def _measure_fan_speed(self, eventtime, drop_result=False):
        """Measure the fan speed and store the result."""
        if not self.measure_active:
            return None

        status = self.fan.get_status(eventtime)
        if not drop_result:
            self.data.append({
                'power': (100 / self.steps) * self.current_step,
                'rpm': status['rpm']
            })

        return status['rpm']

    def _measure_complete(self):
        """Complete the measure process."""
        self.current_gcmd.respond_info("Setting fan power to 0%")
        self._set_fan_power(0)
        self.current_gcmd.respond_info("Saving calibration data...")
        self._save_measure_data()
        self.measure_active = False
        self._reset_state()

    # Utility Methods
    def _save_measure_data(self):
        """Save the calibration data to a CSV file."""
        filename = self._get_filename('calibration_data', time.strftime("%Y%m%d_%H%M%S"), self.fan_name)
        with open(filename, 'w') as f:
            f.write("Power, RPM\n")
            for d in self.data:
                f.write(f"{d['power'] / 100:.2f}, {d['rpm']:.2f}\n")
        self.current_gcmd.respond_info(f"Calibration data saved to {filename}")

    def _set_fan_power(self, power):
        """Set the fan power using the appropriate G-code command."""
        if self.fan.__class__.__name__ == 'Fan':
            cmd_str = f"M106 S{power}"
        elif self.fan.__class__.__name__ == 'PrinterFanGeneric':
            power_scaled = int(power * 255)
            cmd_str = f"SET_FAN_SPEED FAN={self.fan_name} SPEED={power_scaled}"
        else:
            self.current_gcmd.respond_info(f"Fan type not supported: {self.fan.__class__.__name__}")
            return

        self.gcode.run_script(cmd_str)

    def _reset_state(self):
        """Reset the measure state."""
        self.current_step = 0
        self.current_measurement = 0
        self.data = []
        self.step_time = 3
        self.steps = 10
        self.current_gcmd = None
        self.initial_fanstop_issued = False
        self.fan = None
        self.fan_name = None

    def _get_filename(self, base, name_suffix, fan_name=None):
        """Generate a filename for saving calibration data."""
        name = base
        if fan_name:
            name += f"_{fan_name}"
        name += f"_{name_suffix}"
        return os.path.join("/tmp", f"{name}.csv")


def load_config(config):
    """Load the MeasureFan module."""
    return MeasureFan(config)