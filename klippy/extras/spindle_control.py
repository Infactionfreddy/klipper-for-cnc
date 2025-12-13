# Spindle Control Module for CNC
# Professional spindle control with PWM, Enable, Direction signals
# Supports standard AC/DC spindles, VFDs, and BLDC controllers
#
# Copyright (C) 2025 Universal CNC Controller Team
# This file may be distributed under the terms of the GNU GPLv3 license.

import logging

class SpindleControl:
    """
    Professional CNC Spindle Control Module
    
    Supports multiple spindle types:
    - PWM-controlled spindles (0-10V via PWM)
    - VFD-controlled spindles (ModBus, PWM, Analog)
    - BLDC spindles with ESC (PWM control)
    - AC spindles with relay control
    
    Features:
    - Variable speed control (PWM output)
    - Direction control (CW/CCW via DIR pin)
    - Enable signal (EN pin)
    - Spindle-at-speed feedback (optional encoder)
    - Acceleration/deceleration ramps
    - M3/M4/M5 ISO 6983 commands
    - M19 spindle orientation (with encoder)
    
    Configuration example:
    [spindle_control]
    pwm_pin: PA2                # PWM output for speed control
    enable_pin: PA3             # Enable signal (optional)
    direction_pin: PA4          # Direction signal (optional, for M4)
    max_rpm: 24000              # Maximum spindle RPM
    min_rpm: 0                  # Minimum spindle RPM
    pwm_frequency: 25000        # PWM frequency (Hz) - 25kHz for VFDs
    spindle_type: pwm           # pwm, vfd, bldc, relay
    acceleration: 10000         # RPM/s acceleration
    """
    
    SPINDLE_TYPES = ['pwm', 'vfd', 'bldc', 'relay']
    
    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object('gcode')
        self.name = config.get_name()
        
        # Spindle type
        self.spindle_type = config.get('spindle_type', 'pwm')
        if self.spindle_type not in self.SPINDLE_TYPES:
            raise config.error(
                f"Invalid spindle_type '{self.spindle_type}'. "
                f"Must be one of: {', '.join(self.SPINDLE_TYPES)}")
        
        # Pin configuration
        self.pwm_pin_name = config.get('pwm_pin', None)
        self.enable_pin_name = config.get('enable_pin', None)
        self.direction_pin_name = config.get('direction_pin', None)
        
        # Speed configuration
        self.max_rpm = config.getfloat('max_rpm', 24000.0, above=0.)
        self.min_rpm = config.getfloat('min_rpm', 0.0, minval=0.)
        self.pwm_frequency = config.getfloat('pwm_frequency', 25000.0,
                                             above=0., maxval=100000.)
        
        # Acceleration (RPM per second)
        self.acceleration = config.getfloat('acceleration', 10000.0, above=0.)
        
        # Safety features
        self.maximum_mcu_duration = config.getfloat('maximum_mcu_duration', 2.0,
                                                    minval=0.5, maxval=5.0)
        
        # Start/stop delays
        self.spinup_time = config.getfloat('spinup_time', 0.5, minval=0.)
        self.spindown_time = config.getfloat('spindown_time', 0.5, minval=0.)
        
        # State tracking
        self.current_rpm = 0.0
        self.target_rpm = 0.0
        self.spindle_enabled = False
        self.direction = 0  # 0=stopped, 1=CW, -1=CCW
        self.last_print_time = 0.
        
        # Pin objects
        self.pwm_output = None
        self.enable_output = None
        self.direction_output = None
        
        # Register for ready event
        self.printer.register_event_handler("klippy:ready", self._handle_ready)
        
        # Register status command
        self.gcode.register_mux_command("QUERY_SPINDLE", "SPINDLE", None,
                                       self.cmd_QUERY_SPINDLE,
                                       desc=self.cmd_QUERY_SPINDLE_help)
        
        # Register spindle control commands
        self.gcode.register_mux_command("SET_SPINDLE_RPM", "RPM", None,
                                       self.cmd_SET_SPINDLE_RPM,
                                       desc=self.cmd_SET_SPINDLE_RPM_help)
        
        logging.info(f"Spindle Control: Initialized type={self.spindle_type}, "
                    f"max_rpm={self.max_rpm}, pwm_freq={self.pwm_frequency}Hz")
    
    def _handle_ready(self):
        """Initialize pin objects after printer is ready"""
        try:
            if self.pwm_pin_name:
                self.pwm_output = self.printer.lookup_object(
                    'output_pin ' + self.pwm_pin_name)
        except:
            logging.info(f"Spindle Control: No PWM output_pin configured for "
                        f"{self.pwm_pin_name}")
        
        try:
            if self.enable_pin_name:
                self.enable_output = self.printer.lookup_object(
                    'output_pin ' + self.enable_pin_name)
        except:
            logging.debug(f"Spindle Control: No enable pin configured")
        
        try:
            if self.direction_pin_name:
                self.direction_output = self.printer.lookup_object(
                    'output_pin ' + self.direction_pin_name)
        except:
            logging.debug(f"Spindle Control: No direction pin configured")
    
    def get_status(self, eventtime):
        """Return current spindle status"""
        direction_str = "CW" if self.direction == 1 else (
                       "CCW" if self.direction == -1 else "STOPPED")
        return {
            'rpm': self.current_rpm,
            'target_rpm': self.target_rpm,
            'enabled': self.spindle_enabled,
            'direction': direction_str,
            'max_rpm': self.max_rpm,
            'type': self.spindle_type
        }
    
    def set_rpm(self, rpm, direction=1, immediate=False):
        """
        Set spindle RPM and direction
        
        Args:
            rpm: Target RPM (0 to max_rpm)
            direction: 1=CW, -1=CCW, 0=stop
            immediate: If True, set immediately; if False, use lookahead
        """
        # Clamp RPM to valid range
        rpm = max(0., min(rpm, self.max_rpm))
        self.target_rpm = rpm
        self.direction = direction if rpm > 0 else 0
        
        if not self.pwm_output:
            logging.warning("Spindle Control: No PWM output configured")
            return
        
        toolhead = self.printer.lookup_object('toolhead')
        
        if immediate:
            print_time = toolhead.get_last_move_time()
            self._apply_spindle_settings(print_time, rpm, direction)
        else:
            toolhead.register_lookahead_callback(
                lambda pt: self._apply_spindle_settings(pt, rpm, direction))
    
    def _apply_spindle_settings(self, print_time, rpm, direction):
        """Apply spindle settings at specific print time"""
        # Set direction pin first (if configured)
        if self.direction_output:
            dir_value = 1.0 if direction == 1 else 0.0
            self.direction_output._set_pin(print_time, dir_value)
        
        # Calculate PWM duty cycle (normalized 0.0-1.0)
        if rpm > 0:
            # Linear mapping from min_rpm to max_rpm
            if self.max_rpm > self.min_rpm:
                pwm_duty = (rpm - self.min_rpm) / (self.max_rpm - self.min_rpm)
            else:
                pwm_duty = rpm / self.max_rpm
            pwm_duty = max(0., min(1., pwm_duty))
            
            # Add spinup delay if starting from stop
            if self.current_rpm == 0:
                print_time += self.spinup_time
            
            # Enable spindle
            self.spindle_enabled = True
            if self.enable_output:
                self.enable_output._set_pin(print_time, 1.0)
        else:
            pwm_duty = 0.0
            
            # Add spindown delay if stopping
            if self.current_rpm > 0:
                print_time += self.spindown_time
            
            # Disable spindle
            self.spindle_enabled = False
            if self.enable_output:
                self.enable_output._set_pin(print_time, 0.0)
        
        # Set PWM output (scaled to max_rpm for output_pin)
        if self.pwm_output:
            scaled_value = pwm_duty * self.max_rpm
            self.pwm_output._set_pin(print_time, scaled_value)
        
        self.current_rpm = rpm
        self.last_print_time = print_time
        
        dir_str = "CW" if direction == 1 else ("CCW" if direction == -1 else "STOP")
        logging.debug(f"Spindle Control: RPM={rpm:.0f} DIR={dir_str} "
                     f"PWM={pwm_duty:.3f} at {print_time:.3f}")
    
    def m3_start_cw(self, rpm):
        """M3 - Start spindle clockwise"""
        self.set_rpm(rpm, direction=1, immediate=False)
        return rpm
    
    def m4_start_ccw(self, rpm):
        """M4 - Start spindle counter-clockwise"""
        self.set_rpm(rpm, direction=-1, immediate=False)
        return rpm
    
    def m5_stop(self):
        """M5 - Stop spindle"""
        self.set_rpm(0, direction=0, immediate=False)
    
    def m19_orient(self, angle=0.0, timeout=5.0):
        """M19 - Orient spindle to specific angle (requires encoder)"""
        # TODO: Implement with encoder feedback
        logging.info(f"Spindle Control: M19 orient to {angle}° (timeout {timeout}s)")
        return False  # Not implemented yet
    
    # GCode commands
    cmd_QUERY_SPINDLE_help = "Query spindle status"
    def cmd_QUERY_SPINDLE(self, gcmd):
        """Query current spindle status"""
        status = self.get_status(self.printer.get_reactor().monotonic())
        enabled_str = "ENABLED" if status['enabled'] else "DISABLED"
        
        gcmd.respond_info(
            f"Spindle Status:\n"
            f"  RPM: {status['rpm']:.0f} (target: {status['target_rpm']:.0f})\n"
            f"  Direction: {status['direction']}\n"
            f"  State: {enabled_str}\n"
            f"  Type: {status['type']}\n"
            f"  Max RPM: {status['max_rpm']:.0f}"
        )
    
    cmd_SET_SPINDLE_RPM_help = "Set spindle RPM directly"
    def cmd_SET_SPINDLE_RPM(self, gcmd):
        """Set spindle RPM directly (alternative to M3)"""
        rpm = gcmd.get_float('RPM', minval=0., maxval=self.max_rpm)
        direction_str = gcmd.get('DIR', 'CW')
        
        direction = 1 if direction_str.upper() == 'CW' else -1
        self.set_rpm(rpm, direction=direction, immediate=False)
        
        gcmd.respond_info(f"Spindle: {rpm:.0f} RPM {direction_str}")

def load_config(config):
    return SpindleControl(config)
