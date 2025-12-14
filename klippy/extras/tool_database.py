# Tool Database Management for CNC
# Verwaltet Werkzeug-Datenbank mit Länge, Offset, Verschleiß und Kollisionserkennung
#
# Copyright (C) 2025 Freddy <infactionfreddy@gmail.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

import os
import json
import logging
from datetime import datetime

class ToolType:
    """Werkzeugtypen"""
    DRILL = "drill"
    ENDMILL = "endmill"
    BALLNOSE = "ballnose"
    VBIT = "vbit"
    LASER = "laser"
    PLANER = "planer"
    CUSTOM = "custom"

class Tool:
    """Einzelnes CNC-Werkzeug"""
    def __init__(self, tool_id, name, tool_type, diameter, length, 
                 flute_length=0, offset_x=0, offset_y=0, offset_z=0,
                 max_rpm=0, feedrate=0, plunge_rate=0, 
                 angle=0, description=""):
        self.tool_id = tool_id
        self.name = name
        self.tool_type = tool_type
        self.diameter = diameter  # mm
        self.length = length  # mm
        self.flute_length = flute_length  # Schneidenlänge mm
        
        # Offsets für Tool-Wechsel
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.offset_z = offset_z
        
        # Schnittparameter
        self.max_rpm = max_rpm
        self.feedrate = feedrate  # mm/min
        self.plunge_rate = plunge_rate  # mm/min
        
        # Spezifische Parameter
        self.angle = angle  # V-Bit Winkel oder andere
        
        self.description = description
        
        # Überwachungsparameter
        self.total_runtime = 0  # Sekunden
        self.total_distance = 0  # mm
        self.spindle_on_count = 0
        self.wear_level = 0  # 0-100%
        self.last_used = None
        self.created_at = datetime.now().isoformat()
        self.is_active = True
        
        # Warnungen und Limits
        self.max_runtime = 0  # 0 = unbegrenzt
        self.max_distance = 0  # 0 = unbegrenzt
        self.wear_warning_threshold = 80  # %
        
    def to_dict(self):
        """Konvertiere zu Dictionary für JSON-Speicherung"""
        return {
            'tool_id': self.tool_id,
            'name': self.name,
            'tool_type': self.tool_type,
            'diameter': self.diameter,
            'length': self.length,
            'flute_length': self.flute_length,
            'offset_x': self.offset_x,
            'offset_y': self.offset_y,
            'offset_z': self.offset_z,
            'max_rpm': self.max_rpm,
            'feedrate': self.feedrate,
            'plunge_rate': self.plunge_rate,
            'angle': self.angle,
            'description': self.description,
            'total_runtime': self.total_runtime,
            'total_distance': self.total_distance,
            'spindle_on_count': self.spindle_on_count,
            'wear_level': self.wear_level,
            'last_used': self.last_used,
            'created_at': self.created_at,
            'is_active': self.is_active,
            'max_runtime': self.max_runtime,
            'max_distance': self.max_distance,
            'wear_warning_threshold': self.wear_warning_threshold
        }
    
    @classmethod
    def from_dict(cls, data):
        """Erstelle Tool aus Dictionary"""
        tool = cls(
            tool_id=data['tool_id'],
            name=data['name'],
            tool_type=data['tool_type'],
            diameter=data['diameter'],
            length=data['length'],
            flute_length=data.get('flute_length', 0),
            offset_x=data.get('offset_x', 0),
            offset_y=data.get('offset_y', 0),
            offset_z=data.get('offset_z', 0),
            max_rpm=data.get('max_rpm', 0),
            feedrate=data.get('feedrate', 0),
            plunge_rate=data.get('plunge_rate', 0),
            angle=data.get('angle', 0),
            description=data.get('description', '')
        )
        
        # Lade Überwachungsdaten
        tool.total_runtime = data.get('total_runtime', 0)
        tool.total_distance = data.get('total_distance', 0)
        tool.spindle_on_count = data.get('spindle_on_count', 0)
        tool.wear_level = data.get('wear_level', 0)
        tool.last_used = data.get('last_used')
        tool.created_at = data.get('created_at', datetime.now().isoformat())
        tool.is_active = data.get('is_active', True)
        tool.max_runtime = data.get('max_runtime', 0)
        tool.max_distance = data.get('max_distance', 0)
        tool.wear_warning_threshold = data.get('wear_warning_threshold', 80)
        
        return tool
    
    def update_usage(self, runtime=0, distance=0):
        """Aktualisiere Nutzungsstatistiken"""
        self.total_runtime += runtime
        self.total_distance += distance
        self.last_used = datetime.now().isoformat()
        
        # Berechne Verschleißlevel
        self._calculate_wear()
    
    def _calculate_wear(self):
        """Berechne Verschleißlevel basierend auf Nutzung"""
        wear = 0
        
        if self.max_runtime > 0:
            wear = max(wear, (self.total_runtime / self.max_runtime) * 100)
        
        if self.max_distance > 0:
            wear = max(wear, (self.total_distance / self.max_distance) * 100)
        
        self.wear_level = min(100, wear)
    
    def needs_replacement(self):
        """Prüfe ob Werkzeug ersetzt werden muss"""
        return self.wear_level >= 100 or not self.is_active
    
    def needs_warning(self):
        """Prüfe ob Warnung ausgegeben werden sollte"""
        return self.wear_level >= self.wear_warning_threshold


class ToolDatabase:
    """Verwaltung der CNC Werkzeug-Datenbank"""
    def __init__(self, config):
        self.printer = config.get_printer()
        self.name = config.get_name()
        
        # Datenpfad
        self.data_dir = config.get('data_dir', '~/printer_data/tools')
        self.data_dir = os.path.expanduser(self.data_dir)
        self.db_file = os.path.join(self.data_dir, 'tool_database.json')
        
        # Tool-Datenbank
        self.tools = {}
        self.current_tool = None
        
        # Register commands
        self.gcode = self.printer.lookup_object('gcode')
        self._register_commands()
        
        # Erstelle Datenverzeichnis
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Lade vorhandene Datenbank
        self._load_database()
        
        # Register event handlers
        self.printer.register_event_handler("klippy:ready", self._handle_ready)
        
        logging.info(f"Tool Database initialized with {len(self.tools)} tools")
    
    def _register_commands(self):
        """Registriere G-Code Befehle"""
        self.gcode.register_command('ADD_TOOL', 
                                   self.cmd_ADD_TOOL,
                                   desc=self.cmd_ADD_TOOL_help)
        self.gcode.register_command('UPDATE_TOOL',
                                   self.cmd_UPDATE_TOOL,
                                   desc=self.cmd_UPDATE_TOOL_help)
        self.gcode.register_command('REMOVE_TOOL',
                                   self.cmd_REMOVE_TOOL,
                                   desc=self.cmd_REMOVE_TOOL_help)
        self.gcode.register_command('SELECT_TOOL',
                                   self.cmd_SELECT_TOOL,
                                   desc=self.cmd_SELECT_TOOL_help)
        self.gcode.register_command('LIST_TOOLS',
                                   self.cmd_LIST_TOOLS,
                                   desc=self.cmd_LIST_TOOLS_help)
        self.gcode.register_command('TOOL_INFO',
                                   self.cmd_TOOL_INFO,
                                   desc=self.cmd_TOOL_INFO_help)
        self.gcode.register_command('RESET_TOOL_STATS',
                                   self.cmd_RESET_TOOL_STATS,
                                   desc=self.cmd_RESET_TOOL_STATS_help)
        self.gcode.register_command('EXPORT_TOOLS',
                                   self.cmd_EXPORT_TOOLS,
                                   desc=self.cmd_EXPORT_TOOLS_help)
        self.gcode.register_command('IMPORT_TOOLS',
                                   self.cmd_IMPORT_TOOLS,
                                   desc=self.cmd_IMPORT_TOOLS_help)
    
    def _handle_ready(self):
        """Handle Klipper ready event"""
        self.gcode.respond_info(f"Tool Database ready: {len(self.tools)} tools loaded")
    
    def _load_database(self):
        """Lade Tool-Datenbank von Festplatte"""
        if not os.path.exists(self.db_file):
            logging.info("No existing tool database found, starting fresh")
            return
        
        try:
            with open(self.db_file, 'r') as f:
                data = json.load(f)
                
            for tool_data in data.get('tools', []):
                tool = Tool.from_dict(tool_data)
                self.tools[tool.tool_id] = tool
            
            # Lade aktuelles Tool
            current_id = data.get('current_tool')
            if current_id and current_id in self.tools:
                self.current_tool = self.tools[current_id]
            
            logging.info(f"Loaded {len(self.tools)} tools from database")
            
        except Exception as e:
            logging.error(f"Error loading tool database: {e}")
    
    def _save_database(self):
        """Speichere Tool-Datenbank auf Festplatte"""
        try:
            data = {
                'version': '1.0',
                'saved_at': datetime.now().isoformat(),
                'current_tool': self.current_tool.tool_id if self.current_tool else None,
                'tools': [tool.to_dict() for tool in self.tools.values()]
            }
            
            # Speichere atomar
            temp_file = self.db_file + '.tmp'
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            os.replace(temp_file, self.db_file)
            logging.info(f"Saved {len(self.tools)} tools to database")
            
        except Exception as e:
            logging.error(f"Error saving tool database: {e}")
    
    def add_tool(self, tool):
        """Füge neues Tool zur Datenbank hinzu"""
        if tool.tool_id in self.tools:
            raise self.gcode.error(f"Tool ID {tool.tool_id} already exists")
        
        self.tools[tool.tool_id] = tool
        self._save_database()
        return tool
    
    def update_tool(self, tool_id, **kwargs):
        """Aktualisiere Tool-Parameter"""
        if tool_id not in self.tools:
            raise self.gcode.error(f"Tool ID {tool_id} not found")
        
        tool = self.tools[tool_id]
        
        # Aktualisiere erlaubte Felder
        for key, value in kwargs.items():
            if hasattr(tool, key):
                setattr(tool, key, value)
        
        self._save_database()
        return tool
    
    def remove_tool(self, tool_id):
        """Entferne Tool aus Datenbank"""
        if tool_id not in self.tools:
            raise self.gcode.error(f"Tool ID {tool_id} not found")
        
        # Entferne Tool
        del self.tools[tool_id]
        
        # Reset aktuelles Tool falls nötig
        if self.current_tool and self.current_tool.tool_id == tool_id:
            self.current_tool = None
        
        self._save_database()
    
    def get_tool(self, tool_id):
        """Hole Tool aus Datenbank"""
        return self.tools.get(tool_id)
    
    def select_tool(self, tool_id):
        """Wähle aktuelles Tool"""
        if tool_id not in self.tools:
            raise self.gcode.error(f"Tool ID {tool_id} not found")
        
        tool = self.tools[tool_id]
        
        if not tool.is_active:
            raise self.gcode.error(f"Tool {tool_id} is not active")
        
        if tool.needs_replacement():
            self.gcode.respond_info(f"WARNING: Tool {tool_id} needs replacement!")
        elif tool.needs_warning():
            self.gcode.respond_info(f"WARNING: Tool {tool_id} wear level at {tool.wear_level:.1f}%")
        
        self.current_tool = tool
        self._save_database()
        
        return tool
    
    def get_current_tool(self):
        """Hole aktuelles Tool"""
        return self.current_tool
    
    # G-Code Command Implementations
    
    cmd_ADD_TOOL_help = "Add new tool to database"
    def cmd_ADD_TOOL(self, gcmd):
        """ADD_TOOL ID=<id> NAME=<name> TYPE=<type> DIAMETER=<d> LENGTH=<l> [...]"""
        tool_id = gcmd.get_int('ID')
        name = gcmd.get('NAME')
        tool_type = gcmd.get('TYPE', ToolType.CUSTOM)
        diameter = gcmd.get_float('DIAMETER')
        length = gcmd.get_float('LENGTH')
        
        # Optionale Parameter
        flute_length = gcmd.get_float('FLUTE_LENGTH', 0)
        offset_x = gcmd.get_float('OFFSET_X', 0)
        offset_y = gcmd.get_float('OFFSET_Y', 0)
        offset_z = gcmd.get_float('OFFSET_Z', 0)
        max_rpm = gcmd.get_int('MAX_RPM', 0)
        feedrate = gcmd.get_float('FEEDRATE', 0)
        plunge_rate = gcmd.get_float('PLUNGE_RATE', 0)
        angle = gcmd.get_float('ANGLE', 0)
        description = gcmd.get('DESCRIPTION', '')
        
        tool = Tool(
            tool_id=tool_id,
            name=name,
            tool_type=tool_type,
            diameter=diameter,
            length=length,
            flute_length=flute_length,
            offset_x=offset_x,
            offset_y=offset_y,
            offset_z=offset_z,
            max_rpm=max_rpm,
            feedrate=feedrate,
            plunge_rate=plunge_rate,
            angle=angle,
            description=description
        )
        
        self.add_tool(tool)
        gcmd.respond_info(f"Tool {tool_id} '{name}' added to database")
    
    cmd_UPDATE_TOOL_help = "Update existing tool parameters"
    def cmd_UPDATE_TOOL(self, gcmd):
        """UPDATE_TOOL ID=<id> [PARAMETER=<value> ...]"""
        tool_id = gcmd.get_int('ID')
        
        updates = {}
        
        # Sammle alle Updates
        for param in ['NAME', 'TYPE', 'DESCRIPTION']:
            if gcmd.get(param, None) is not None:
                updates[param.lower()] = gcmd.get(param)
        
        for param in ['DIAMETER', 'LENGTH', 'FLUTE_LENGTH', 'OFFSET_X', 
                     'OFFSET_Y', 'OFFSET_Z', 'FEEDRATE', 'PLUNGE_RATE', 'ANGLE']:
            if gcmd.get_float(param, None) is not None:
                updates[param.lower()] = gcmd.get_float(param)
        
        for param in ['MAX_RPM', 'MAX_RUNTIME', 'MAX_DISTANCE', 'WEAR_WARNING_THRESHOLD']:
            if gcmd.get_int(param, None) is not None:
                updates[param.lower()] = gcmd.get_int(param)
        
        if gcmd.get_int('IS_ACTIVE', None) is not None:
            updates['is_active'] = bool(gcmd.get_int('IS_ACTIVE'))
        
        if not updates:
            raise gcmd.error("No parameters to update")
        
        self.update_tool(tool_id, **updates)
        gcmd.respond_info(f"Tool {tool_id} updated")
    
    cmd_REMOVE_TOOL_help = "Remove tool from database"
    def cmd_REMOVE_TOOL(self, gcmd):
        """REMOVE_TOOL ID=<id>"""
        tool_id = gcmd.get_int('ID')
        self.remove_tool(tool_id)
        gcmd.respond_info(f"Tool {tool_id} removed from database")
    
    cmd_SELECT_TOOL_help = "Select current tool"
    def cmd_SELECT_TOOL(self, gcmd):
        """SELECT_TOOL ID=<id>"""
        tool_id = gcmd.get_int('ID')
        tool = self.select_tool(tool_id)
        
        # Wende Offsets an
        toolhead = self.printer.lookup_object('toolhead')
        current_pos = toolhead.get_position()
        
        # Setze Tool-Offsets
        current_pos[0] += tool.offset_x
        current_pos[1] += tool.offset_y
        current_pos[2] += tool.offset_z
        
        gcmd.respond_info(f"Tool {tool_id} '{tool.name}' selected")
        gcmd.respond_info(f"Type: {tool.tool_type}, Diameter: {tool.diameter}mm, Length: {tool.length}mm")
        gcmd.respond_info(f"Wear Level: {tool.wear_level:.1f}%")
    
    cmd_LIST_TOOLS_help = "List all tools in database"
    def cmd_LIST_TOOLS(self, gcmd):
        """LIST_TOOLS [TYPE=<type>]"""
        filter_type = gcmd.get('TYPE', None)
        
        tools = self.tools.values()
        if filter_type:
            tools = [t for t in tools if t.tool_type == filter_type]
        
        gcmd.respond_info(f"=== Tool Database ({len(tools)} tools) ===")
        
        for tool in sorted(tools, key=lambda t: t.tool_id):
            status = "✓" if tool.is_active else "✗"
            current = " [CURRENT]" if tool == self.current_tool else ""
            wear = f"{tool.wear_level:.0f}%"
            
            gcmd.respond_info(
                f"{status} T{tool.tool_id}: {tool.name} ({tool.tool_type}) "
                f"- Ø{tool.diameter}mm L{tool.length}mm "
                f"- Wear: {wear}{current}"
            )
    
    cmd_TOOL_INFO_help = "Show detailed tool information"
    def cmd_TOOL_INFO(self, gcmd):
        """TOOL_INFO [ID=<id>]"""
        tool_id = gcmd.get_int('ID', None)
        
        if tool_id is None:
            if self.current_tool is None:
                raise gcmd.error("No tool selected")
            tool = self.current_tool
        else:
            tool = self.get_tool(tool_id)
            if tool is None:
                raise gcmd.error(f"Tool {tool_id} not found")
        
        gcmd.respond_info(f"=== Tool {tool.tool_id}: {tool.name} ===")
        gcmd.respond_info(f"Type: {tool.tool_type}")
        gcmd.respond_info(f"Diameter: {tool.diameter}mm")
        gcmd.respond_info(f"Length: {tool.length}mm")
        gcmd.respond_info(f"Flute Length: {tool.flute_length}mm")
        gcmd.respond_info(f"Offsets: X={tool.offset_x} Y={tool.offset_y} Z={tool.offset_z}")
        gcmd.respond_info(f"Max RPM: {tool.max_rpm}")
        gcmd.respond_info(f"Feedrate: {tool.feedrate} mm/min")
        gcmd.respond_info(f"Plunge Rate: {tool.plunge_rate} mm/min")
        if tool.angle > 0:
            gcmd.respond_info(f"Angle: {tool.angle}°")
        gcmd.respond_info(f"Description: {tool.description}")
        gcmd.respond_info(f"---")
        gcmd.respond_info(f"Runtime: {tool.total_runtime:.1f}s")
        gcmd.respond_info(f"Distance: {tool.total_distance:.1f}mm")
        gcmd.respond_info(f"Spindle Cycles: {tool.spindle_on_count}")
        gcmd.respond_info(f"Wear Level: {tool.wear_level:.1f}%")
        gcmd.respond_info(f"Active: {'Yes' if tool.is_active else 'No'}")
        gcmd.respond_info(f"Created: {tool.created_at}")
        if tool.last_used:
            gcmd.respond_info(f"Last Used: {tool.last_used}")
    
    cmd_RESET_TOOL_STATS_help = "Reset tool usage statistics"
    def cmd_RESET_TOOL_STATS(self, gcmd):
        """RESET_TOOL_STATS ID=<id>"""
        tool_id = gcmd.get_int('ID')
        tool = self.get_tool(tool_id)
        
        if tool is None:
            raise gcmd.error(f"Tool {tool_id} not found")
        
        tool.total_runtime = 0
        tool.total_distance = 0
        tool.spindle_on_count = 0
        tool.wear_level = 0
        
        self._save_database()
        gcmd.respond_info(f"Tool {tool_id} statistics reset")
    
    cmd_EXPORT_TOOLS_help = "Export tools to JSON file"
    def cmd_EXPORT_TOOLS(self, gcmd):
        """EXPORT_TOOLS [FILENAME=<name>]"""
        filename = gcmd.get('FILENAME', 'tools_export.json')
        filepath = os.path.join(self.data_dir, filename)
        
        try:
            data = {
                'exported_at': datetime.now().isoformat(),
                'tools': [tool.to_dict() for tool in self.tools.values()]
            }
            
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            
            gcmd.respond_info(f"Exported {len(self.tools)} tools to {filepath}")
        except Exception as e:
            raise gcmd.error(f"Export failed: {e}")
    
    cmd_IMPORT_TOOLS_help = "Import tools from JSON file"
    def cmd_IMPORT_TOOLS(self, gcmd):
        """IMPORT_TOOLS FILENAME=<name> [OVERWRITE=<0|1>]"""
        filename = gcmd.get('FILENAME')
        overwrite = gcmd.get_int('OVERWRITE', 0)
        
        filepath = os.path.join(self.data_dir, filename)
        
        if not os.path.exists(filepath):
            raise gcmd.error(f"File not found: {filepath}")
        
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            imported = 0
            skipped = 0
            
            for tool_data in data.get('tools', []):
                tool = Tool.from_dict(tool_data)
                
                if tool.tool_id in self.tools and not overwrite:
                    skipped += 1
                    continue
                
                self.tools[tool.tool_id] = tool
                imported += 1
            
            self._save_database()
            
            gcmd.respond_info(f"Imported {imported} tools, skipped {skipped}")
            
        except Exception as e:
            raise gcmd.error(f"Import failed: {e}")
    
    def get_status(self, eventtime):
        """Status für Moonraker API"""
        current = None
        if self.current_tool:
            current = {
                'id': self.current_tool.tool_id,
                'name': self.current_tool.name,
                'type': self.current_tool.tool_type,
                'diameter': self.current_tool.diameter,
                'length': self.current_tool.length,
                'wear_level': self.current_tool.wear_level
            }
        
        return {
            'tool_count': len(self.tools),
            'current_tool': current,
            'tools': [
                {
                    'id': t.tool_id,
                    'name': t.name,
                    'type': t.tool_type,
                    'diameter': t.diameter,
                    'length': t.length,
                    'wear_level': t.wear_level,
                    'is_active': t.is_active
                }
                for t in self.tools.values()
            ]
        }


def load_config(config):
    return ToolDatabase(config)
