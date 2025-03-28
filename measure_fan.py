import os
import time
import configfile
from enum import Enum

class SpinupState(Enum):
            NONE = -1
            FIND_MAX_SET = 0
            FIND_MAX_QUERY = 1
            INITIAL = 2
            WAITING_FOR_SPINUP = 3
            STABILIZE = 4
            TARGET = 5

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
        self.gcode.register_command(
            'MEASURE_FAN_SPINUP',
            self.cmd_MEASURE_FAN_SPINUP,
            desc=self.cmd_MEASURE_FAN_help
        )

        # Initialize state variables
        self.current_gcmd = None
        self.measure_active = False
        self.sample_timer = None
        self.fan = None
        self.fan_name = None
        self.printer_ready = False

        self.rpm_measure_state = {
            'steps': 10,
            'measure_per_step': 3,
            'step_time': 3,
            'current_step': 0,
            'current_measurement': 0,
            'data': [],
            'initial_fanstop_issued': False
        }

        self.spinup_measure_state = {
            'initial_power': 0,
            'target_power': 0,
            'step_time': .1,
            'rpm_threshold': 100,
            'start_time': None,
            'state': SpinupState.NONE,
            'max_rpm': 0,
        }

        # Register event handler for when Klipper is ready
        self.printer.register_event_handler("klippy:ready", self._handle_ready)
        self.printer.register_event_handler("klippy:shutdown", self._handle_shutdown)

    # G-code command help text
    cmd_MEASURE_FAN_help = (
        "Run fan measurement procedure to determine minimum power required to start fan "
        "and maximum power for fan operation.\n"
        "Usage: MEASURE_FAN [FAN=<fan_name>] [STEPS=<steps>]\n"
        "FAN: Name of the fan to measure. Default: fan\n"
        "STEPS: Number of steps to run the fan through. Default: 10"
    )

    cmd_MEASURE_FAN_SPINUP_help = (
        "Run fan measurement procedure to determine the time it takes for the fan to reach a target RPM "
        "from an initial power value.\n"
        "Usage: MEASURE_FAN_SPINUP [FAN=<fan_name>] [INITIAL_POWER=<initial_power>] [TARGET_POWER=<target_power>] [STEP_TIME=<step_time>]\n"
        "FAN: Name of the fan to measure. Default: fan\n"
        "INITIAL_POWER: Initial power value to start the fan from. Default: 0\n"
        "TARGET_POWER: Target power value to reach. Default: 1\n"
        "STEP_TIME: Time in seconds to wait between setting the fan power. Default: 0.1\n"
        "RPM_THRESHOLD: RPM difference threshold to consider the fan as stabilized. Default: 100"
    )

    # Event Handlers
    def _handle_ready(self):
        """Register the timer for measurement steps when Klipper is ready."""
        self.printer_ready = True
        #self.sample_timer = self.reactor.register_timer(self._next_measure_step, self.reactor.NEVER)

    def _handle_shutdown(self):
        """Reset the measure state when Klipper is shutdown."""
        self._reset_state()

    # G-code Command Handlers
    def cmd_MEASURE_FAN(self, gcmd):
        """Handle the MEASURE_FAN G-code command."""
        if self.measure_active:
            gcmd.respond_info("Measure already in progress")
            return

        self._reset_state()
        self.sample_timer = self.reactor.register_timer(self._next_rpm_measure_step, self.reactor.NEVER)

        # Parse G-code parameters
        self.current_gcmd = gcmd
        self.measure_active = True
        self.rpm_measure_state['steps'] = int(gcmd.get('STEPS', 10))
        self.rpm_measure_state['measure_per_step'] = int(gcmd.get('MEASURE_PER_STEP', 3))
        self.fan_name = gcmd.get('FAN', 'fan')

        # Find the fan object
        self.fan = self._try_find_fan(self.fan_name)
        if self.fan is None:
            gcmd.respond_error(f"Fan {self.fan_name} not found")
            self.measure_active = False
            return

        # Start calibration
        gcmd.respond_info(f"Measuring fan {self.fan_name} ...")
        gcmd.respond_info(f"Running fan from 0 to 100% power in {self.rpm_measure_state['steps']} steps")
        self.reactor.update_timer(self.sample_timer, self.reactor.NOW)

    def cmd_MEASURE_FAN_SPINUP(self, gcmd):
        """Handle the MEASURE_FAN_SPINUP G-code command."""
        if self.measure_active:
            gcmd.respond_info("Measure already in progress")
            return

        self._reset_state()
        self.sample_timer = self.reactor.register_timer(self._next_spinup_measure_step, self.reactor.NEVER)

        # Parse G-code parameters
        self.current_gcmd = gcmd
        self.measure_active = True
        self.spinup_measure_state['initial_power'] = float(gcmd.get('INITIAL_POWER', 0))
        self.spinup_measure_state['target_power'] = float(gcmd.get('TARGET_POWER', 1))
        self.spinup_measure_state['step_time'] = float(gcmd.get('STEP_TIME', 0.01))
        self.spinup_measure_state['rpm_threshold'] = float(gcmd.get('RPM_THRESHOLD', 100))
        self.fan_name = gcmd.get('FAN', 'fan')

        # Find the fan object
        self.fan = self._try_find_fan(self.fan_name)
        if self.fan is None:
            gcmd.respond_error(f"Fan {self.fan_name} not found")
            self.measure_active = False
            return

        self.spinup_measure_state['state'] = SpinupState.FIND_MAX_SET

        # Start calibration
        gcmd.respond_info(f"Measuring fan {self.fan_name} ...")
        self.reactor.update_timer(self.sample_timer, self.reactor.NOW)

    def _try_find_fan(self, fan_name):
        """Attempt to find the fan object by name."""
        try:
            return self.printer.lookup_object(fan_name)
        except configfile.error:
            return None

    # Measure Logic
    def _next_rpm_measure_step(self, eventtime):
        """Perform the next step in the measure process."""
        state = self.rpm_measure_state

        if state['current_step'] == 0:
            fan_rpm = self._measure_fan_speed(eventtime)
            if fan_rpm is not None and fan_rpm > 0:
                self.current_gcmd.respond_info(f"Fan is already spinning at {fan_rpm}, waiting for it to stop")
                if not state['initial_fanstop_issued']:
                    self._set_fan_power(0)
                    state['initial_fanstop_issued'] = True
                return self.reactor.monotonic() + 1

        fan_rpm = self._measure_fan_speed(eventtime)

        if fan_rpm is not None:
            state['data'].append({
                'power': (100 / state['steps']) * state['current_step'],
                'rpm': fan_rpm
            })

        # Measure fan speed multiple times per step
        if state['current_measurement'] < state['measure_per_step']:
            state['current_measurement'] += 1
            return self.reactor.monotonic() + 0.5

        # Move to the next step
        state['current_measurement'] = 0
        state['current_step'] += 1

        if state['current_step'] > state['steps']:
            self._rpm_measure_complete()
            return self.reactor.NEVER

        # Set fan power for the current step
        current_power = (100 / state['steps']) * state['current_step']
        power_scaled = current_power / 100
        self.current_gcmd.respond_info(f"Setting fan power to {current_power:.2f}%")
        self._set_fan_power(power_scaled)

        return self.reactor.monotonic() + state['step_time']

    # Spinup Measure Logic
    # This is a separate measure process that only measures the fan from a given initial power value (giving it the step_time to spin up)
    # then sets the fan_power to a given target power value and measures the RPM in shit time periods waiting the RPM to stabilize then prints out the time it took the fan to reach that RPM
    def _next_spinup_measure_step(self, eventtime):
        state = self.spinup_measure_state


        if state['state'] == SpinupState.FIND_MAX_SET:
            self.current_gcmd.respond_info("Setting fan to target power to find target RPM")
            self._set_fan_power(state['target_power'])
            state['state'] = SpinupState.FIND_MAX_QUERY
            return self.reactor.monotonic() + 5
        elif state['state'] == SpinupState.FIND_MAX_QUERY:
            rpm = self._measure_fan_speed(eventtime)
            state['max_rpm'] = rpm
            self.current_gcmd.respond_info(f"Target RPM is {rpm}")
            state['state'] = SpinupState.INITIAL
            return self.reactor.NOW
        elif state['state'] == SpinupState.INITIAL:
            self.current_gcmd.respond_info("Setting fan to initial power")
            self._set_fan_power(state['initial_power'])
            state['state'] = SpinupState.WAITING_FOR_SPINUP

            #Give the fan enough time to reach the target RPM
            return self.reactor.monotonic() + 3
        elif state['state'] == SpinupState.WAITING_FOR_SPINUP:
            self._set_fan_power(state['target_power'])
            state['state'] = SpinupState.STABILIZE
            state['start_time'] = self.reactor.monotonic()
            return self.reactor.monotonic() + state['step_time']
        elif state['state'] == SpinupState.STABILIZE:
            fan_rpm = self._measure_fan_speed(eventtime)
            if fan_rpm is None:
                self.current_gcmd.respond_info("Fan RPM is not readable, aborting measurement")
                self._reset_state()
                self.measure_active = False
                return self.reactor.NEVER
            elif abs(state['max_rpm'] - fan_rpm ) > state['rpm_threshold']:
                return self.reactor.monotonic() + state['step_time']
            elif abs(state['max_rpm'] - fan_rpm ) < state['rpm_threshold']:
                state['state'] = SpinupState.TARGET
                duration = self.reactor.monotonic() - state['start_time']
                self.current_gcmd.respond_info(f"Fan reached target RPM in {duration:.2f} seconds")
                self._spinup_measure_complete()
                return self.reactor.NEVER
            else:
                self.current_gcmd.respond_info("Unknown error, aborting measurement")
                self._reset_state()
                self.measure_active = False
                return self.reactor.NEVER
            
            
        else:
            self._reset_state()
            self.measure_active = False
            return self.reactor.NEVER
    
    def _measure_fan_speed(self, eventtime):
        """Measure the fan speed and store the result."""
        if not self.measure_active:
            return None

        status = self.fan.get_status(eventtime)
        return status['rpm']

    def _rpm_measure_complete(self):
        """Complete the measure process."""
        self.current_gcmd.respond_info("Setting fan power to 0%")
        self._set_fan_power(0)
        self.current_gcmd.respond_info("Saving calibration data...")
        self._save_measure_data(self.rpm_measure_state['data'])
        self.measure_active = False
        self._reset_state()

    def _spinup_measure_complete(self):
        """Complete the measure process."""
        self._set_fan_power(0)
        self.current_gcmd.respond_info("Measurement complete")
        self.measure_active = False
        self._reset_state()

    # Utility Methods
    def _save_measure_data(self, data, name="calibration_data",):
        """Save the calibration data to a CSV file."""
        filename = self._get_filename(name, time.strftime("%Y%m%d_%H%M%S"), self.fan_name)
        with open(filename, 'w') as f:
            f.write("Power, RPM\n")
            for d in data:
                f.write(f"{d['power'] / 100:.2f}, {d['rpm']:.2f}\n")
        self.current_gcmd.respond_info(f"Calibration data saved to {filename}")

    def _set_fan_power(self, power):
        """Set the fan power using the appropriate G-code command."""
        if self.fan.__class__.__name__ == 'PrinterFan':
            power_scaled = int(power * 255)
            cmd_str = f"M106 S{power_scaled}"
        elif self.fan.__class__.__name__ == 'PrinterFanGeneric':
            cmd_str = f"SET_FAN_SPEED FAN={self.fan_name} SPEED={power}"
        else:
            self.current_gcmd.respond_info(f"Fan type not supported: {self.fan.__class__.__name__}")
            return

        self.current_gcmd.respond_info(f"Sending command: {cmd_str}")
        self.gcode.run_script(cmd_str)

    def _reset_state(self):
        """Reset the measure state."""
        self.rpm_measure_state = {
            'current_step': 0,
            'current_measurement': 0,
            'data': [],
            'steps': 10,
            'measure_per_step': 3,
            'step_time': 3,
            'initial_fanstop_issued': False
        }
        self.spinup_measure_state = {
            'initial_power': 0,
            'target_power': 0,
            'step_time': .1,
            'start_time': None,
            'state': SpinupState.NONE,
            'data': [],
            'max_rpm': 0,
        }
        self.current_gcmd = None
        self.measure_active = False
        self.fan = None
        self.fan_name = None
        self.printer_ready = False
        if self.sample_timer is not None:
            self.reactor.update_timer(self.sample_timer, self.reactor.NEVER)
            self.reactor.unregister_timer(self.sample_timer)
        self.sample_timer = None

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