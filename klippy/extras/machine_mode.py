# Machine Mode Management for Klipper CNC/3D Hybrid System
#
# Copyright (C) 2024  Frederik <frederik@klippercnc.dev>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

"""
Machine Mode Module

Manages global machine_mode variable for switching between:
- cnc_spindle: CNC machining with spindle
- cnc_laser: Laser cutting/engraving
- 3d_print: 3D printing with extruder

Supports 3/4/5/6-axis configurations (XYZ, XYZA, XYZAB, XYZABC)

Commands:
- SET_MACHINE_MODE MODE=<mode>
- GET_MACHINE_MODE
"""

import logging


class MachineMode:
    """Manages machine mode switching and axis configuration"""
    
    # Valid machine modes (simplified: cnc or 3d_print)
    VALID_MODES = ['cnc', '3d_print']
    
    # Valid tool modes (only used when machine_mode=cnc)
    VALID_TOOL_MODES = ['spindle', 'laser']
    
    # Valid axis configurations
    VALID_AXIS = ['XYZ', 'XYZA', 'XYZAB', 'XYZABC']
    
    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object('gcode')
        
        # Get initial machine mode from config
        self.machine_mode = config.get('machine_mode', '3d_print').lower()
        
        # Validate machine mode
        if self.machine_mode not in self.VALID_MODES:
            raise config.error(
                f"Invalid machine_mode '{self.machine_mode}'. "
                f"Must be one of: {', '.join(self.VALID_MODES)}"
            )
        
        # Get tool mode (only relevant for CNC mode)
        self.tool_mode = config.get('tool_mode', 'spindle').lower()
        if self.tool_mode not in self.VALID_TOOL_MODES:
            raise config.error(
                f"Invalid tool_mode '{self.tool_mode}'. "
                f"Must be one of: {', '.join(self.VALID_TOOL_MODES)}"
            )
        
        # Get axis configuration
        self.axis_names = config.get('axis', 'XYZ').upper()
        
        # Validate axis configuration
        if self.axis_names not in self.VALID_AXIS:
            raise config.error(
                f"Invalid axis '{self.axis_names}'. "
                f"Must be one of: {', '.join(self.VALID_AXIS)}"
            )
        
        self.axis_count = len(self.axis_names)
        
        # References to tool control modules (set in _handle_ready)
        self.spindle_control = None
        self.laser_control = None
        self.extruder = None
        
        # Module availability flags
        self.has_spindle = False
        self.has_laser = False
        self.has_extruder = False
        
        # Register commands
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
        
        logging.info(
            f"MachineMode: Initialized with mode={self.machine_mode}, "
            f"axis={self.axis_names} ({self.axis_count} axes)"
        )
    
    def _handle_ready(self):
        """Detect available tool control modules"""
        
        # Check for spindle_control
        try:
            self.spindle_control = self.printer.lookup_object('spindle_control')
            self.has_spindle = True
            logging.info("MachineMode: spindle_control detected")
        except:
            self.spindle_control = None
            self.has_spindle = False
        
        # Check for laser_control
        try:
            self.laser_control = self.printer.lookup_object('laser_control')
            self.has_laser = True
            logging.info("MachineMode: laser_control detected")
        except:
            self.laser_control = None
            self.has_laser = False
        
        # Check for extruder
        try:
            self.extruder = self.printer.lookup_object('extruder')
            self.has_extruder = True
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
        )elf.printer.machine_mode = self.machine_mode
        self.printer.axis_names = self.axis_names
        self.printer.axis_count = self.axis_count
        
        logging.info(
            f"MachineMode: Ready - mode={self.machine_mode}, "
            f"spindle={self.has_spindle}, laser={self.has_laser}, "
            f"extruder={self.has_extruder}"
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
            )aise self.gcode.error(
                "3d_print mode requires [extruder] section in config"
            )
    
    def get_mode(self):
        """Get current machine mode"""
        return self.machine_mode
    
    def get_axis_names(self):
        """Get current axis configuration"""
        return self.axis_names
    
    def is_cnc_mode(self):
        """Check if in CNC mode"""
        return self.machine_mode == 'cnc'
    
    def is_3d_print_mode(self):
        """Check if in 3D print mode"""
        return self.machine_mode == '3d_print'
    
    def get_status(self, eventtime):
        """Return status information"""
        return {
            'machine_mode': self.machine_mode,
            'tool_mode': self.tool_mode,
            'axis_names': self.axis_names,
            'axis_count': self.axis_count,
            'has_spindle': self.has_spindle,
            'has_laser': self.has_laser,
            'has_extruder': self.has_extruder,
            'valid_modes': self.VALID_MODES,
            'valid_tool_modes': self.VALID_TOOL_MODES,
            'valid_axis': self.VALID_AXIS,
        }f tool_mode not in self.VALID_TOOL_MODES:
            raise self.gcode.error(
                f"Invalid tool_mode '{tool_mode}'. "
                f"Must be one of: {', '.join(self.VALID_TOOL_MODES)}"
    cmd_SET_MACHINE_MODE_help = (
        "Switch machine mode between cnc and 3d_print. "
        "Example: SET_MACHINE_MODE MODE=cnc TOOL=spindle"
    )   if tool_mode == 'spindle' and not self.has_spindle:
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
        return old_tool_modedle', 'cnc_laser']
    
    def is_3d_print_mode(self):
        """Check if in 3D print mode"""
        return self.machine_mode == '3d_print'
    
    def get_status(self, eventtime):
        """Return status information"""
        return {
            'machine_mode': self.machine_mode,
            'axis_names': self.axis_names,
            'axis_count': self.axis_count,
            'has_spindle': self.has_spindle,
            'has_laser': self.has_laser,
            'has_extruder': self.has_extruder,
            'valid_modes': self.VALID_MODES,
            'valid_axis': self.VALID_AXIS,
        }
    
    cmd_SET_MACHINE_MODE_help = (
        "Switch machine mode between cnc_spindle, cnc_laser, and 3d_print. "
        "Example: SET_MACHINE_MODE MODE=cnc_spindle"
    def cmd_SET_MACHINE_MODE(self, gcmd):
        """Handle SET_MACHINE_MODE command"""
        
        # Get requested mode
        mode = gcmd.get('MODE', None)
        if mode is None:
            raise gcmd.error(
                "SET_MACHINE_MODE requires MODE parameter. "
                f"Valid modes: {', '.join(self.VALID_MODES)}"
            )
        
        mode = mode.lower()
        
        # Validate mode
        if mode not in self.VALID_MODES:
            raise gcmd.error(
                f"Invalid MODE '{mode}'. "
                f"Must be one of: {', '.join(self.VALID_MODES)}"
            )
        
        # Get optional TOOL parameter (only for CNC mode)
        tool_mode = gcmd.get('TOOL', self.tool_mode if mode == 'cnc' else None)
        if tool_mode:
            tool_mode = tool_mode.lower()
            if tool_mode not in self.VALID_TOOL_MODES:
                raise gcmd.error(
                    f"Invalid TOOL '{tool_mode}'. "
                    f"Must be one of: {', '.join(self.VALID_TOOL_MODES)}"
                )
        
        # Check if mode is available
        try:
            if mode == 'cnc':
                self._validate_mode_availability(mode, tool_mode)
            else:
                self._validate_mode_availability(mode)
        except Exception as e:
            raise gcmd.error(str(e))
        
        # Store old modes for logging
        old_mode = self.machine_mode
        old_tool_mode = self.tool_mode
        
        # Switch mode
        self.machine_mode = mode
        self.printer.machine_mode = mode
        
        # Switch tool mode if in CNC mode
        if mode == 'cnc' and tool_mode:
            self.tool_mode = tool_mode
    def cmd_GET_MACHINE_MODE(self, gcmd):
        """Handle GET_MACHINE_MODE command"""
        
        # Build response
        response = f"Machine Mode: {self.machine_mode}\n"
        if self.machine_mode == 'cnc':
            response += f"Tool Mode: {self.tool_mode}\n"
        response += f"Axis Configuration: {self.axis_names} ({self.axis_count} axes)\n"
        response += "\nAvailable Modules:\n"
        response += f"  Spindle: {'✓' if self.has_spindle else '✗'}\n"
        response += f"  Laser: {'✓' if self.has_laser else '✗'}\n"
        response += f"  Extruder: {'✓' if self.has_extruder else '✗'}\n"
        response += "\nAvailable Modes:\n"
        
        for mode in self.VALID_MODES:
            # Check if mode is available
            available = False
            if mode == 'cnc':
                available = self.has_spindle or self.has_laser
            elif mode == '3d_print':
                available = self.has_extruder
            
            status = '✓' if available else '✗'
            current = ' (current)' if mode == self.machine_mode else ''
            response += f"  {mode}: {status}{current}\n"
        
        # Show available tools for CNC mode
        if self.machine_mode == 'cnc':
            response += "\nAvailable Tools (CNC mode):\n"
            for tool in self.VALID_TOOL_MODES:
                available = False
                if tool == 'spindle':
                    available = self.has_spindle
                elif tool == 'laser':
                    available = self.has_laser
                
                status = '✓' if available else '✗'
                current = ' (current)' if tool == self.tool_mode else ''
                response += f"  {tool}: {status}{current}\n"
    
    def cmd_GET_MACHINE_MODE(self, gcmd):
        """Handle GET_MACHINE_MODE command"""
        
        # Build response
        response = f"Machine Mode: {self.machine_mode}\n"
        response += f"Axis Configuration: {self.axis_names} ({self.axis_count} axes)\n"
        response += "\nAvailable Modules:\n"
        response += f"  Spindle: {'✓' if self.has_spindle else '✗'}\n"
        response += f"  Laser: {'✓' if self.has_laser else '✗'}\n"
        response += f"  Extruder: {'✓' if self.has_extruder else '✗'}\n"
        response += "\nAvailable Modes:\n"
        
        for mode in self.VALID_MODES:
            # Check if mode is available
            available = False
            if mode == 'cnc_spindle':
                available = self.has_spindle
            elif mode == 'cnc_laser':
                available = self.has_laser
            elif mode == '3d_print':
                available = self.has_extruder
            
            status = '✓' if available else '✗'
            current = ' (current)' if mode == self.machine_mode else ''
            response += f"  {mode}: {status}{current}\n"
        
        # Add position information if toolhead is ready
        try:
            toolhead = self.printer.lookup_object('toolhead')
            pos = toolhead.get_position()
            
            response += "\nCurrent Position:\n"
            for i, axis in enumerate(self.axis_names):
                response += f"  {axis}: {pos[i]:.3f}\n"
            
            # Add extruder position
            if len(pos) > self.axis_count:
                response += f"  E: {pos[-1]:.3f}\n"
            
            # Add homed status
            kin = toolhead.get_kinematics()
            if hasattr(kin, 'get_status'):
                kin_status = kin.get_status()
                response += "\nHomed Axes:\n"
                for axis in self.axis_names:
                    axis_lower = axis.lower()
                    homed = kin_status.get(f'homed_{axis_lower}', False)
                    response += f"  {axis}: {'✓' if homed else '✗'}\n"
        except:
            # Toolhead not ready yet
            response += "\n(Position information not available - printer not ready)"
        
        gcmd.respond_info(response)


def load_config(config):
    """Load machine_mode module"""
    return MachineMode(config)
