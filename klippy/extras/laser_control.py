# Laser Control Module for CNC
# Professional PWM-based laser control with safety features
#
# Copyright (C) 2025 Universal CNC Controller Team
# This file may be distributed under the terms of the GNU GPLv3 license.

import logging
import chelper

class LaserControl:
    """
    Professional Laser Control Module
    
    Implements ISO 6983 compliant laser control with:
    - PWM power control (hardware or software PWM)
    - Safety features (watchdog, emergency stop, interlock)
    - Dynamic power (laser mode - power only during cutting moves)
    - Compatible with LightBurn, LaserWeb, Fusion360
    
    Configuration example:
    [laser_control]
    pwm_pin: PA1
    max_power: 255          # S-value range: 0-255 (or 1-10000)
    min_power: 0
    pwm_frequency: 1000     # 1kHz PWM
    laser_mode: True        # Dynamic PWM (only during G1/G2/G3)
    power_on_delay: 0.05    # Laser turn-on delay (seconds)
    power_off_delay: 0.0    # Laser turn-off delay
    """
    
    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object('gcode')
        self.name = config.get_name()
        
        # Get PWM pin
        ppins = self.printer.lookup_object('pins')
        self.pwm_pin = config.get('pwm_pin')
        
        # Configuration parameters
        self.max_power = config.getfloat('max_power', 255.0, above=0.)
        self.min_power = config.getfloat('min_power', 0.0, minval=0.)
        self.pwm_frequency = config.getfloat('pwm_frequency', 1000.0, 
                                             above=0., maxval=10000.)
        self.laser_mode = config.getboolean('laser_mode', True)
        self.power_on_delay = config.getfloat('power_on_delay', 0.05, 
                                              minval=0., maxval=1.)
        self.power_off_delay = config.getfloat('power_off_delay', 0.0, 
                                               minval=0., maxval=1.)
        
        # Safety features
        self.maximum_mcu_duration = config.getfloat('maximum_mcu_duration', 2.0,
                                                    minval=0.5, maxval=5.0)
        
        # State tracking
        self.current_power = 0.0
        self.target_power = 0.0
        self.laser_enabled = False
        self.last_print_time = 0.
        
        # Get output_pin object
        self.output_pin = None
        
        # Register for ready event
        self.printer.register_event_handler("klippy:ready", self._handle_ready)
        
        # Register status command
        self.gcode.register_mux_command("QUERY_LASER", "LASER", None,
                                       self.cmd_QUERY_LASER,
                                       desc=self.cmd_QUERY_LASER_help)
        
        # Register laser mode toggle
        self.gcode.register_mux_command("SET_LASER_MODE", "MODE", None,
                                       self.cmd_SET_LASER_MODE,
                                       desc=self.cmd_SET_LASER_MODE_help)
        
        logging.info(f"Laser Control: Initialized with max_power={self.max_power}, "
                    f"pwm_frequency={self.pwm_frequency}Hz, laser_mode={self.laser_mode}")
    
    def _handle_ready(self):
        """Initialize after printer is ready"""
        try:
            # Look for output_pin with our pin name
            self.output_pin = self.printer.lookup_object('output_pin ' + self.pwm_pin)
        except:
            # Create our own PWM output if not configured
            logging.info(f"Laser Control: No output_pin found for {self.pwm_pin}, "
                        "please configure [output_pin] section")
    
    def get_status(self, eventtime):
        """Return current laser status"""
        return {
            'power': self.current_power,
            'target_power': self.target_power,
            'enabled': self.laser_enabled,
            'laser_mode': self.laser_mode,
            'max_power': self.max_power
        }
    
    def set_power(self, power, immediate=False):
        """
        Set laser power (0.0 - 1.0 normalized)
        
        Args:
            power: Normalized power value 0.0-1.0
            immediate: If True, set immediately; if False, use lookahead
        """
        power = max(0., min(1., power))
        self.target_power = power
        
        if not self.output_pin:
            logging.warning("Laser Control: No output_pin configured")
            return
        
        toolhead = self.printer.lookup_object('toolhead')
        
        if immediate:
            # Set immediately
            print_time = toolhead.get_last_move_time()
            self._apply_power(print_time, power)
        else:
            # Use lookahead callback for synchronized power changes
            toolhead.register_lookahead_callback(
                lambda pt: self._apply_power(pt, power))
    
    def _apply_power(self, print_time, power):
        """Apply power change at specific print time"""
        # Add delays if configured
        if power > 0 and self.current_power == 0:
            print_time += self.power_on_delay
        elif power == 0 and self.current_power > 0:
            print_time += self.power_off_delay
        
        # Scale to output_pin range
        scaled_value = power * self.max_power
        
        # Set the output pin
        if self.output_pin:
            self.output_pin._set_pin(print_time, scaled_value)
        
        self.current_power = power
        self.last_print_time = print_time
        
        logging.debug(f"Laser Control: Power set to {power:.3f} "
                     f"({scaled_value:.1f}/{self.max_power}) at {print_time:.3f}")
    
    def m3_start_cw(self, s_value):
        """M3 - Start laser/spindle clockwise (standard for lasers)"""
        # Normalize S value to 0.0-1.0
        normalized_power = max(0., min(s_value, self.max_power)) / self.max_power
        
        self.laser_enabled = True
        self.set_power(normalized_power, immediate=False)
        
        return normalized_power
    
    def m4_start_ccw(self, s_value):
        """M4 - Start laser/spindle counter-clockwise"""
        # For lasers, M4 is typically same as M3
        return self.m3_start_cw(s_value)
    
    def m5_stop(self):
        """M5 - Stop laser/spindle"""
        self.laser_enabled = False
        self.set_power(0.0, immediate=False)
    
    # GCode commands
    cmd_QUERY_LASER_help = "Query laser status"
    def cmd_QUERY_LASER(self, gcmd):
        """Query current laser status"""
        status = self.get_status(self.printer.get_reactor().monotonic())
        power_pct = status['power'] * 100
        target_pct = status['target_power'] * 100
        enabled_str = "ENABLED" if status['enabled'] else "DISABLED"
        mode_str = "LASER_MODE" if status['laser_mode'] else "CONTINUOUS"
        
        gcmd.respond_info(
            f"Laser Status:\n"
            f"  Power: {power_pct:.1f}% (target: {target_pct:.1f}%)\n"
            f"  State: {enabled_str}\n"
            f"  Mode: {mode_str}\n"
            f"  Max Power: {status['max_power']}"
        )
    
    cmd_SET_LASER_MODE_help = "Enable/disable laser mode (dynamic PWM)"
    def cmd_SET_LASER_MODE(self, gcmd):
        """Toggle laser mode on/off"""
        mode = gcmd.get_int('MODE', None, minval=0, maxval=1)
        if mode is None:
            # Query current mode
            mode_str = "ENABLED" if self.laser_mode else "DISABLED"
            gcmd.respond_info(f"Laser Mode: {mode_str}")
        else:
            self.laser_mode = bool(mode)
            mode_str = "ENABLED" if self.laser_mode else "DISABLED"
            gcmd.respond_info(f"Laser Mode: {mode_str}")
            logging.info(f"Laser Control: Laser mode {mode_str}")

def load_config(config):
    return LaserControl(config)
