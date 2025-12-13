# Machine Mode Management for CNC and 3D Printing
#
# Copyright (C) 2024  Kevin O'Connor <kevin@koconnor.net>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

import logging

class MachineMode:
    """
    Global machine mode management for CNC and 3D printing operations.
    
    Manages switching between:
    - Machine modes: 'cnc' or '3d_print'
    - Tool modes (CNC only): 'spindle' or 'laser'
    - Axis configurations: XYZ (3), XYZA (4), XYZAB (5), XYZABC (6)
    """
    
    VALID_MODES = ['cnc', '3d_print']
    VALID_TOOL_MODES = ['spindle', 'laser']
    VALID_AXIS = ['XYZ', 'XYZA', 'XYZAB', 'XYZABC']
    
    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object('gcode')
        
        # Get boot-time configuration (UNCHANGEABLE at runtime)
        self.boot_mode = config.get('default_mode', 'cnc')
        self.boot_tool_mode = config.get('default_tool_mode', 'spindle')
        
        # Current runtime mode (can be changed only if allow_mode_switch=True)
        self.machine_mode = self.boot_mode
        self.tool_mode = self.boot_tool_mode
        
        # Allow runtime mode switching? (default: False for safety)
        self.allow_mode_switch = config.getboolean('allow_mode_switch', False)
        
        # Validate boot-time configuration
        if self.boot_mode not in self.VALID_MODES:
            raise config.error(
                f"Invalid default_mode '{self.boot_mode}'. "
                f"Must be one of: {', '.join(self.VALID_MODES)}"
            )
        
        if self.boot_tool_mode not in self.VALID_TOOL_MODES:
            raise config.error(
                f"Invalid default_tool_mode '{self.boot_tool_mode}'. "
                f"Must be one of: {', '.join(self.VALID_TOOL_MODES)}"
            )
        
        # Get axis configuration from printer config
        printer_config = config.getsection('printer')
        axis_config = printer_config.get('axis', 'XYZ').upper()
        
        if axis_config not in self.VALID_AXIS:
            raise config.error(
                f"Invalid axis configuration '{axis_config}'. "
                f"Must be one of: {', '.join(self.VALID_AXIS)}"
            )
        
        self.axis_names = axis_config
        self.axis_count = len(axis_config)
        
        # Initialize module availability flags
        self.has_spindle = False
        self.has_laser = False
        self.has_extruder = False
        
        self.spindle_control = None
        self.laser_control = None
        self.extruder = None
        
        # Register GCode commands
        self.gcode.register_command(
            'SET_MACHINE_MODE',
            self.cmd_SET_MACHINE_MODE,
            desc=self.cmd_SET_MACHINE_MODE_help
        )
        self.gcode.register_command(
            'GET_MACHINE_MODE',
            self.cmd_GET_MACHINE_MODE,
            desc=self.cmd_GET_MACHINE_MODE_help
        )
        
        # Register for ready event
        self.printer.register_event_handler("klippy:ready", self._handle_ready)
        
        switch_status = "ENABLED" if self.allow_mode_switch else "DISABLED (boot-time lock)"
        logging.info(
            f"MachineMode: Initialized - boot_mode={self.boot_mode} (LOCKED), "
            f"boot_tool_mode={self.boot_tool_mode}, axis={self.axis_names}, "
            f"runtime_switching={switch_status}"
        )
    
    def _handle_ready(self):
        """Check for available modules after printer is ready"""
        
        # Check for spindle control
        try:
            self.spindle_control = self.printer.lookup_object('spindle_control')
            self.has_spindle = True
        except:
            self.spindle_control = None
            self.has_spindle = False
        
        # Check for laser control
        try:
            self.laser_control = self.printer.lookup_object('laser_control')
            self.has_laser = True
        except:
            self.laser_control = None
            self.has_laser = False
        
        # Check for extruder
        try:
            self.extruder = self.printer.lookup_object('extruder')
            self.has_extruder = True
        except:
            self.extruder = None
            self.has_extruder = False
        
        # Store machine_mode, tool_mode and axis_names in printer object for global access
        self.printer.machine_mode = self.machine_mode
        self.printer.tool_mode = self.tool_mode
        self.printer.axis_names = self.axis_names
        self.printer.axis_count = self.axis_count
        
        logging.info(
            f"MachineMode: Ready - mode={self.machine_mode}, "
            f"tool_mode={self.tool_mode}, "
            f"spindle={self.has_spindle}, laser={self.has_laser}, "
            f"extruder={self.has_extruder}"
        )
    
    def _validate_mode_availability(self, mode, tool_mode=None):
        """Check if required module is available for given mode"""
        
        if mode == 'cnc':
            # For CNC mode, check tool_mode
            if tool_mode is None:
                tool_mode = self.tool_mode
            
            if tool_mode == 'spindle' and not self.has_spindle:
                raise self.gcode.error(
                    "CNC mode with tool_mode=spindle requires [spindle_control] section in config"
                )
            elif tool_mode == 'laser' and not self.has_laser:
                raise self.gcode.error(
                    "CNC mode with tool_mode=laser requires [laser_control] section in config"
                )
        
        elif mode == '3d_print' and not self.has_extruder:
            raise self.gcode.error(
                "3d_print mode requires [extruder] section in config"
            )
    
    def get_mode(self):
        """Get current machine mode"""
        return self.machine_mode
    
    def get_tool_mode(self):
        """Get current tool mode"""
        return self.tool_mode
    
    def get_axis_names(self):
        """Get axis names (e.g. 'XYZABC')"""
        return self.axis_names
    
    def get_axis_count(self):
        """Get number of axes"""
        return self.axis_count
    
    def get_status(self, eventtime):
        """Return status for mainsail/fluidd"""
        return {
            'machine_mode': self.machine_mode,
            'tool_mode': self.tool_mode,
            'boot_mode': self.boot_mode,
            'boot_tool_mode': self.boot_tool_mode,
            'allow_mode_switch': self.allow_mode_switch,
            'axis_names': self.axis_names,
            'axis_count': self.axis_count,
            'has_spindle': self.has_spindle,
            'has_laser': self.has_laser,
            'has_extruder': self.has_extruder,
            'valid_modes': self.VALID_MODES,
            'valid_tool_modes': self.VALID_TOOL_MODES,
            'valid_axis': self.VALID_AXIS,
        }
    
    cmd_SET_MACHINE_MODE_help = (
        "Switch machine mode between cnc and 3d_print. "
        "Example: SET_MACHINE_MODE MODE=cnc TOOL_MODE=spindle "
        "(only if allow_mode_switch=True in config)"
    )
    def cmd_SET_MACHINE_MODE(self, gcmd):
        """Set machine mode (cnc or 3d_print) and optionally tool mode"""
        
        # Get parameters
        mode = gcmd.get('MODE', self.machine_mode).lower()
        tool_mode = gcmd.get('TOOL_MODE', self.tool_mode).lower()
        
        # Check if trying to switch away from boot_mode
        if mode != self.boot_mode and not self.allow_mode_switch:
            raise gcmd.error(
                f"Runtime mode switching DISABLED. Boot mode is '{self.boot_mode}' (locked). "
                f"Set 'allow_mode_switch: True' in [machine_mode] config to enable runtime switching."
            )
        
        # Validate mode
        if mode not in self.VALID_MODES:
            raise gcmd.error(
                f"Invalid MODE '{mode}'. Must be one of: {', '.join(self.VALID_MODES)}"
            )
        
        # Validate tool_mode (only for CNC mode)
        if mode == 'cnc':
            if tool_mode not in self.VALID_TOOL_MODES:
                raise gcmd.error(
                    f"Invalid TOOL_MODE '{tool_mode}'. "
                    f"Must be one of: {', '.join(self.VALID_TOOL_MODES)}"
                )
            
            # Check if required module is available
            self._validate_mode_availability(mode, tool_mode)
        else:
            # For 3d_print mode, check if extruder is available
            self._validate_mode_availability(mode)
        
        # Store old values
        old_mode = self.machine_mode
        old_tool_mode = self.tool_mode
        
        # Update mode
        self.machine_mode = mode
        self.printer.machine_mode = mode
        
        # Update tool_mode if in CNC mode
        if mode == 'cnc':
            self.tool_mode = tool_mode
            self.printer.tool_mode = tool_mode
        
        # Log change
        if mode == 'cnc':
            logging.info(
                f"MachineMode: Changed from {old_mode} to {mode} "
                f"(tool_mode: {old_tool_mode} -> {tool_mode})"
            )
            gcmd.respond_info(
                f"Machine mode changed to {mode} with tool_mode={tool_mode}"
            )
        else:
            logging.info(f"MachineMode: Changed from {old_mode} to {mode}")
            gcmd.respond_info(f"Machine mode changed to {mode}")
    
    cmd_GET_MACHINE_MODE_help = "Get current machine mode and tool mode"
    def cmd_GET_MACHINE_MODE(self, gcmd):
        """Get current machine mode and tool mode"""
        
        if self.machine_mode == 'cnc':
            msg = f"Machine mode: {self.machine_mode}, Tool mode: {self.tool_mode}"
        else:
            msg = f"Machine mode: {self.machine_mode}"
        
        msg += f", Axis: {self.axis_names} ({self.axis_count} axes)"
        
        # Add boot_mode info
        if self.machine_mode != self.boot_mode or self.tool_mode != self.boot_tool_mode:
            msg += f" (Boot: {self.boot_mode}/{self.boot_tool_mode})"
        else:
            msg += f" (Boot-locked)"
        
        switch_status = "enabled" if self.allow_mode_switch else "disabled"
        msg += f", Runtime switching: {switch_status}"
        
        gcmd.respond_info(msg)
        logging.info(f"MachineMode: Status - {msg}")
    
    def set_tool_mode(self, tool_mode):
        """Set tool mode (spindle or laser) - for CNC mode only"""
        
        if self.machine_mode != 'cnc':
            raise self.gcode.error(
                "tool_mode can only be changed in CNC mode"
            )
        
        if tool_mode not in self.VALID_TOOL_MODES:
            raise self.gcode.error(
                f"Invalid tool_mode '{tool_mode}'. "
                f"Must be one of: {', '.join(self.VALID_TOOL_MODES)}"
            )
        
        # Check if required module is available
        if tool_mode == 'spindle' and not self.has_spindle:
            raise self.gcode.error(
                "tool_mode=spindle requires [spindle_control] section"
            )
        elif tool_mode == 'laser' and not self.has_laser:
            raise self.gcode.error(
                "tool_mode=laser requires [laser_control] section"
            )
        
        old_tool_mode = self.tool_mode
        self.tool_mode = tool_mode
        self.printer.tool_mode = tool_mode
        
        logging.info(f"MachineMode: Tool mode changed from {old_tool_mode} to {tool_mode}")
        return old_tool_mode
    
    def is_3d_print_mode(self):
        """Check if in 3D print mode"""
        return self.machine_mode == '3d_print'
    
    def is_cnc_mode(self):
        """Check if in CNC mode"""
        return self.machine_mode == 'cnc'
    
    def is_spindle_mode(self):
        """Check if in CNC spindle mode"""
        return self.machine_mode == 'cnc' and self.tool_mode == 'spindle'
    
    def is_laser_mode(self):
        """Check if in CNC laser mode"""
        return self.machine_mode == 'cnc' and self.tool_mode == 'laser'

def load_config(config):
    return MachineMode(config)
