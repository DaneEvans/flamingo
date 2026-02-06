import os
import threading
import yaml
import json
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from configure_node_27 import runCmd, doCompareSettings, getNewSettings, doCompareChannels, extractKeysFromInfo, writeKeysToFile, readKeysFromFile


HERE = os.path.dirname(__file__)
CONFIG_DIR = os.path.join(HERE, "configs")
KEYS_FILE = os.path.join(HERE, "keys.txt")


class ConfiguratorGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Flamingo Configurator GUI")
        self.state('zoomed')  # Fullscreen on Windows

        self.config_files = []
        self.current_config_path = None
        self.loaded_config_text = ""
        self.original_config = {}  # {key: value} from file
        self.config_rows = {}  # {key: (checkbox_var, value_var, asterisk_label)}

        # Top frame for names and dropdown
        top = ttk.Frame(self)
        top.pack(side=tk.TOP, fill=tk.X, padx=6, pady=6)

        ttk.Label(top, text="Config:").pack(side=tk.LEFT)
        self.config_var = tk.StringVar()
        self.config_combo = ttk.Combobox(top, textvariable=self.config_var, state='readonly', width=60)
        self.config_combo.pack(side=tk.LEFT, padx=6)
        self.config_combo.bind('<<ComboboxSelected>>', lambda e: self.load_selected_config())

        ttk.Button(top, text="Refresh list", command=self.refresh_config_list).pack(side=tk.LEFT, padx=6)

        # last used config label (filled from keys.txt using nodeId)
        self.last_used_var = tk.StringVar(value="last config used: None")
        ttk.Label(top, textvariable=self.last_used_var).pack(side=tk.LEFT, padx=12)

        # Name fields
        names = ttk.Frame(self)
        names.pack(side=tk.TOP, fill=tk.X, padx=6)
        ttk.Label(names, text="Long name:").pack(side=tk.LEFT)
        self.longname_var = tk.StringVar()
        self.longname_entry = ttk.Entry(names, textvariable=self.longname_var, width=30)
        self.longname_entry.pack(side=tk.LEFT, padx=6)

        ttk.Label(names, text="Short name:").pack(side=tk.LEFT)
        self.shortname_var = tk.StringVar()
        self.shortname_entry = ttk.Entry(names, textvariable=self.shortname_var, width=15)
        self.shortname_entry.pack(side=tk.LEFT, padx=6)

        # Middle panes: left node info, right editable config
        middle = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        middle.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        left_frame = ttk.Labelframe(middle, text="Node: meshtastic --info")
        right_frame = ttk.Labelframe(middle, text="Config (editable)")
        middle.add(left_frame, weight=1)
        middle.add(right_frame, weight=1)

        # Left panel: split into info (top) and preferences (bottom)
        # Top: Node info text (read-only)
        info_frame = ttk.Labelframe(left_frame, text="Info")
        info_frame.pack(fill=tk.BOTH, expand=False, padx=4, pady=4)
        self.node_text = tk.Text(info_frame, wrap=tk.NONE, height=15)
        self.node_text.pack(fill=tk.BOTH, expand=True)
        self.node_text.config(state=tk.DISABLED)

        # Bottom: Preferences editor (structured rows)
        prefs_frame = ttk.Labelframe(left_frame, text="Preferences")
        prefs_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        
        self.prefs_canvas = tk.Canvas(prefs_frame, bg='white')
        prefs_scrollbar = ttk.Scrollbar(prefs_frame, orient=tk.VERTICAL, command=self.prefs_canvas.yview)
        self.prefs_frame = ttk.Frame(self.prefs_canvas)
        self.prefs_frame.bind("<Configure>", lambda e: self.prefs_canvas.configure(scrollregion=self.prefs_canvas.bbox("all")))
        self.prefs_canvas.create_window((0, 0), window=self.prefs_frame, anchor="nw")
        self.prefs_canvas.configure(yscrollcommand=prefs_scrollbar.set)
        self.prefs_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        prefs_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Track original and current prefs
        self.original_prefs = {}
        self.prefs_rows = {}

        node_btns = ttk.Frame(left_frame)
        node_btns.pack(fill=tk.X)
        ttk.Button(node_btns, text="Refresh Node Info", command=self.refresh_node_info).pack(side=tk.LEFT, padx=4, pady=4)
        ttk.Button(node_btns, text="Store Private Key", command=self.extract_keys).pack(side=tk.LEFT, padx=4, pady=4)

        # Config editor: structured rows with checkbox, key, value, asterisk
        # Container for canvas and buttons
        config_container = ttk.Frame(right_frame)
        config_container.pack(fill=tk.BOTH, expand=True)
        
        self.config_canvas = tk.Canvas(config_container, bg='white')
        scrollbar = ttk.Scrollbar(config_container, orient=tk.VERTICAL, command=self.config_canvas.yview)
        self.config_frame = ttk.Frame(self.config_canvas)
        self.config_frame.bind("<Configure>", lambda e: self.config_canvas.configure(scrollregion=self.config_canvas.bbox("all")))
        self.config_canvas.create_window((0, 0), window=self.config_frame, anchor="nw")
        self.config_canvas.configure(yscrollcommand=scrollbar.set)
        self.config_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Buttons at bottom (always visible)
        cfg_btns = ttk.Frame(right_frame)
        cfg_btns.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Button(cfg_btns, text="Revert changes", command=self.revert_changes).pack(side=tk.LEFT, padx=4, pady=4)
        ttk.Button(cfg_btns, text="Save to file...", command=self.save_config_to_file).pack(side=tk.LEFT, padx=4, pady=4)
        ttk.Button(cfg_btns, text="Select All", command=self.select_all_configs).pack(side=tk.LEFT, padx=4, pady=4)
        ttk.Button(cfg_btns, text="Deselect All", command=self.deselect_all_configs).pack(side=tk.LEFT, padx=4, pady=4)

        # Bottom controls: toggles and actions
        bottom = ttk.Frame(self)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=6, pady=6)

        # Toggles
        self.test_var = tk.BooleanVar(value=False)
        self.set_var = tk.BooleanVar(value=False)
        self.retain_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bottom, text="Test (echo only)", variable=self.test_var).pack(side=tk.LEFT, padx=6)
        ttk.Checkbutton(bottom, text="Perform writes (set)", variable=self.set_var).pack(side=tk.LEFT, padx=6)
        ttk.Checkbutton(bottom, text="Retain keys if available", variable=self.retain_var).pack(side=tk.LEFT, padx=6)

        ttk.Button(bottom, text="Write changes to node", command=self.threaded_write).pack(side=tk.RIGHT, padx=6)
        ttk.Button(bottom, text="Quit", command=self.destroy).pack(side=tk.RIGHT, padx=6)

        # initialise
        self.refresh_config_list()
        self.refresh_node_info()

    def refresh_config_list(self):
        self.config_files = []
        if not os.path.isdir(CONFIG_DIR):
            os.makedirs(CONFIG_DIR, exist_ok=True)
        # discover recursively, present relative paths from CONFIG_DIR
        for root, dirs, files in os.walk(CONFIG_DIR):
            for fn in files:
                if fn.lower().endswith(('.yml', '.yaml')):
                    full = os.path.join(root, fn)
                    rel = os.path.relpath(full, CONFIG_DIR).replace('\\', '/')
                    self.config_files.append(rel)
        self.config_combo['values'] = self.config_files
        if self.config_files:
            # select first if nothing selected
            if not self.config_var.get():
                self.config_var.set(self.config_files[0])
                self.load_selected_config()

    def update_last_used_label(self, nodeId: str):
        # Look up nodeId in KEYS_FILE (first column) and get 4th column as last config
        last = None
        try:
            if os.path.exists(KEYS_FILE):
                with open(KEYS_FILE, 'r', encoding='utf-8') as f:
                    first = True
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        if first and line.startswith('nodeId,'):
                            first = False
                            continue
                        parts = line.split(',', 3)
                        if len(parts) == 4:
                            existing_node = parts[0].strip()
                            if existing_node == nodeId:
                                last = parts[3].strip()
                                break
                        first = False
        except Exception:
            last = None
        display = f"last config used: {last}" if last else "last config used: None"
        self.last_used_var.set(display)

    def load_selected_config(self):
        sel = self.config_var.get()
        if not sel:
            return
        path = os.path.join(CONFIG_DIR, sel)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                txt = f.read()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read {path}: {e}")
            return
        self.current_config_path = path
        self.loaded_config_text = txt

        # Parse YAML and populate structured editor
        try:
            data = yaml.safe_load(txt) or {}
            self.original_config = {}
            settings = data.get('settings', {})
            if settings:
                for k, v in settings.items():
                    self.original_config[k] = v
            # Also include channels if present
            channels = data.get('channels', [])
            if channels:
                self.original_config['__channels__'] = channels
        except Exception as e:
            messagebox.showerror("Error", f"Failed to parse YAML: {e}")
            self.original_config = {}

        self.render_config_editor()

        # try to parse and fill long/short
        try:
            data = yaml.safe_load(txt) or {}
            settings = data.get('settings', {})
            ln = settings.get('user.longname', '')
            sn = settings.get('user.shortname', '')
            # If keys are nested under 'user', also accept that
            if not ln and 'user' in data and isinstance(data['user'], dict):
                ln = data['user'].get('longname','')
                sn = data['user'].get('shortname','')
            self.longname_var.set(ln)
            self.shortname_var.set(sn)
        except Exception:
            self.longname_var.set('')
            self.shortname_var.set('')

    def render_config_editor(self):
        """Render config rows from original_config, grouped by section"""
        # Clear existing rows
        for widget in self.config_frame.winfo_children():
            widget.destroy()
        self.config_rows = {}

        # Group by section (prefix before first dot)
        sections = {}
        for key, orig_value in self.original_config.items():
            if key == '__channels__':
                continue
            if '.' in key:
                section = key.split('.')[0]
            else:
                section = '__other__'
            if section not in sections:
                sections[section] = []
            sections[section].append((key, orig_value))

        # Render each section with header and rows
        for section_name in sorted(sections.keys()):
            if section_name == '__other__':
                # Render unsectioned items at the top
                for key, orig_value in sorted(sections[section_name]):
                    self.add_config_row(key, orig_value)
            else:
                # Section header
                header = ttk.Frame(self.config_frame)
                header.pack(fill=tk.X, padx=4, pady=(8, 2))
                ttk.Label(header, text=section_name.upper(), font=('TkDefaultFont', 10, 'bold')).pack(anchor='w')
                
                # Render items in this section
                for key, orig_value in sorted(sections[section_name]):
                    self.add_config_row(key, orig_value)

    def add_config_row(self, key: str, orig_value):
        """Add a single row to the config editor"""
        row = ttk.Frame(self.config_frame)
        row.pack(fill=tk.X, padx=4, pady=2)

        # Checkbox for "send this setting"
        check_var = tk.BooleanVar(value=True)
        check = ttk.Checkbutton(row, variable=check_var, width=6)
        check.pack(side=tk.LEFT, padx=2)

        # Key label
        key_label = tk.Label(row, text=key, width=30, anchor='w', justify=tk.LEFT)
        key_label.pack(side=tk.LEFT, padx=2)

        # Value entry
        value_var = tk.StringVar(value=str(orig_value))
        entry = ttk.Entry(row, textvariable=value_var, width=40)
        entry.pack(side=tk.LEFT, padx=2)

        # Asterisk label (shows if changed) - fixed width to prevent offset
        asterisk_label = tk.Label(row, text=" ", width=3, anchor='w', foreground='red', font=('TkDefaultFont', 10, 'bold'))
        asterisk_label.pack(side=tk.LEFT, padx=2)

        # Bind value changes to update asterisk and bold formatting
        def on_value_change(*args, k=key, ov=orig_value, al=asterisk_label, kl=key_label, vv=value_var):
            current = vv.get()
            if str(ov) != current:
                al.config(text="*", foreground='red')
                kl.config(font=('TkDefaultFont', 10, 'bold'))
            else:
                al.config(text=" ")
                kl.config(font=('TkDefaultFont', 10))

        # use trace_add for modern tkinter
        try:
            value_var.trace_add('write', on_value_change)
        except Exception:
            # fallback
            value_var.trace('w', on_value_change)

        self.config_rows[key] = (check_var, value_var, asterisk_label)

    def select_all_configs(self):
        """Check all config checkboxes"""
        for key, (check_var, _, _) in self.config_rows.items():
            check_var.set(True)

    def deselect_all_configs(self):
        """Uncheck all config checkboxes"""
        for key, (check_var, _, _) in self.config_rows.items():
            check_var.set(False)

    def render_prefs_editor(self):
        """Render preferences rows from original_prefs, grouped by section"""
        for widget in self.prefs_frame.winfo_children():
            widget.destroy()
        self.prefs_rows = {}

        # Group by section
        sections = {}
        for key, val in self.original_prefs.items():
            if isinstance(val, dict):
                sections[key] = val
            else:
                if '__other__' not in sections:
                    sections['__other__'] = {}
                sections[key] = val

        # Render each section with header and rows
        for section_name in sorted(sections.keys()):
            if section_name == '__other__':
                continue
            section_data = sections[section_name]
            
            # Section header
            header = ttk.Frame(self.prefs_frame)
            header.pack(fill=tk.X, padx=4, pady=(8, 2))
            ttk.Label(header, text=section_name.upper(), font=('TkDefaultFont', 10, 'bold')).pack(anchor='w')
            
            # Render items in this section
            if isinstance(section_data, dict):
                for subkey, subval in sorted(section_data.items()):
                    full_key = f"{section_name}.{subkey}"
                    self.add_pref_row(full_key, subval)

    def add_pref_row(self, key: str, orig_value):
        """Add a single preference row (no checkbox)"""
        row = ttk.Frame(self.prefs_frame)
        row.pack(fill=tk.X, padx=20, pady=2)

        # Key label (extract just the subkey part)
        subkey = key.split('.')[-1] if '.' in key else key
        key_label = tk.Label(row, text=subkey, width=30, anchor='w', justify=tk.LEFT)
        key_label.pack(side=tk.LEFT, padx=2)

        # Value entry
        value_var = tk.StringVar(value=str(orig_value))
        entry = ttk.Entry(row, textvariable=value_var, width=50)
        entry.pack(side=tk.LEFT, padx=2)

        # Asterisk label
        asterisk_label = tk.Label(row, text=" ", width=3, anchor='w', foreground='red', font=('TkDefaultFont', 10, 'bold'))
        asterisk_label.pack(side=tk.LEFT, padx=2)

        # Bind value changes
        def on_value_change(*args, k=key, ov=orig_value, al=asterisk_label, kl=key_label, vv=value_var):
            current = vv.get()
            if str(ov) != current:
                al.config(text="*", foreground='red')
                kl.config(font=('TkDefaultFont', 10, 'bold'))
            else:
                al.config(text=" ")
                kl.config(font=('TkDefaultFont', 10))

        try:
            value_var.trace_add('write', on_value_change)
        except Exception:
            value_var.trace('w', on_value_change)

        self.prefs_rows[key] = (value_var, asterisk_label)

    def format_info_display(self, info_dict):
        """Format info dict as human-readable text"""
        lines = []
        for key, val in sorted(info_dict.items()):
            if isinstance(val, dict):
                lines.append(f"{key}: {json.dumps(val)}")
            else:
                lines.append(f"{key}: {val}")
        return '\n'.join(lines)

    def format_json_section(self, line_text, blacklist=None):
        """Format a line containing JSON (e.g., 'My info: { ... }') into nicely formatted text
        
        Args:
            line_text: The line to format (e.g., "My info: { ... }")
            blacklist: Set or list of keys to exclude from output
        """
        if blacklist is None:
            blacklist = set()
        else:
            blacklist = set(blacklist)
        
        # e.g., "My info: { ... }" -> extract prefix and JSON part
        if ':' not in line_text:
            return line_text
        parts = line_text.split(':', 1)
        prefix = parts[0].strip()
        json_part = parts[1].strip()
        
        try:
            obj = json.loads(json_part)
            if isinstance(obj, dict):
                formatted_lines = [f"{prefix}:"]
                for k, v in sorted(obj.items()):
                    # Check if key matches blacklist (exact or with has* pattern)
                    if k in blacklist:
                        continue
                    if k.startswith('has') and 'has*' in blacklist:
                        continue
                    formatted_lines.append(f"  {k}: {v}")
                return '\n'.join(formatted_lines)
        except Exception:
            pass
        return line_text

    def format_nodes_section(self, block_text, nodes_dict):
        """Format nodes display: drop node ID keys, blacklist certain fields
        
        Returns:
            Tuple of (formatted_text, user_id) where user_id is the node's user.id
        """
        BLACKLIST = {'isFavorite', 'num', 'user.longName', 'user.shortName'}
        
        # Extract just the first node's data (not wrapped in its ID key)
        user_id = None
        if isinstance(nodes_dict, dict) and len(nodes_dict) > 0:
            first_key = next(iter(nodes_dict))
            first_node = nodes_dict[first_key]
            # Extract user.id if available
            if isinstance(first_node.get('user'), dict):
                user_id = first_node['user'].get('id')
        else:
            return block_text, None
        
        # Recursively filter blacklisted keys
        def filter_node(obj, prefix=''):
            if isinstance(obj, dict):
                filtered = {}
                for k, v in obj.items():
                    full_key = f"{prefix}.{k}" if prefix else k
                    if full_key not in BLACKLIST:
                        filtered[k] = filter_node(v, full_key)
                return filtered
            return obj
        
        filtered_node = filter_node(first_node)
        
        # Dump as YAML
        lines = ['OurNode:']
        yaml_str = yaml.dump(filtered_node, default_flow_style=False)
        for line in yaml_str.splitlines():
            lines.append('  ' + line)  # indent node content
        
        return '\n'.join(lines), user_id

    def refresh_node_info(self):
        def work():
            out = runCmd("meshtastic --info", echoOnly=self.test_var.get(), silent=True)
            # Parse Owner line (e.g. "Owner: slim bringup 5949 (slim)") and autofill names
            for line in out.splitlines():
                line = line.strip()
                m = re.match(r'^Owner:\s*(.*?)\s*\((.*?)\)', line)
                if m:
                    ln = m.group(1).strip()
                    sn = m.group(2).strip()
                    # Use Tk main thread to update vars
                    self.after(0, lambda ln=ln, sn=sn: (self.longname_var.set(ln), self.shortname_var.set(sn)))
                    break

            # Extract nodeId from info and update last-used config label
            try:
                keys = extractKeysFromInfo(out, "meshtastic")
                if keys and keys.get('nodeId'):
                    nodeId = keys.get('nodeId')
                    self.after(0, lambda nid=nodeId: self.update_last_used_label(nid))
                else:
                    self.after(0, lambda: self.last_used_var.set("last config used: None"))
            except Exception:
                self.after(0, lambda: self.last_used_var.set("last config used: None"))

            # Split output: extract info section (before "Preferences:") and preferences section
            lines = out.splitlines()
            if len(lines) > 2:
                body = lines[2:]
            else:
                body = lines[:]
            
            # Find where Preferences: starts
            prefs_start_idx = None
            for idx, l in enumerate(body):
                if l.strip().startswith('Preferences:'):
                    prefs_start_idx = idx
                    break
            # Extract preferences JSON block by finding matching braces
            if prefs_start_idx is not None:
                info_body = body[:prefs_start_idx]
                # Extract just the Preferences section by finding matching braces
                prefs_start_line = body[prefs_start_idx]
                # Strip "Preferences: " prefix
                if prefs_start_line.startswith('Preferences:'):
                    prefs_start_line = prefs_start_line[len('Preferences:'):].lstrip()
                
                # Find the closing brace of the Preferences JSON object
                brace_count = 0
                json_lines = []
                started = False
                for i in range(prefs_start_idx, len(body)):
                    line = body[i]
                    
                    if not started:
                        # Process the first line (may have "Preferences: {")
                        json_lines.append(prefs_start_line)
                        brace_count += prefs_start_line.count('{') - prefs_start_line.count('}')
                        started = True
                        if brace_count == 0:
                            break
                        continue
                    
                    # For subsequent lines, check if next section starts
                    if line.strip().startswith('Module preferences:') or line.strip().startswith('Channels:'):
                        break
                    
                    json_lines.append(line)
                    brace_count += line.count('{') - line.count('}')
                    if brace_count == 0:
                        break
                
                prefs_text = '\n'.join(json_lines)
                try:
                    parsed = json.loads(prefs_text)
                    if isinstance(parsed, dict):
                        self.original_prefs = parsed
                    else:
                        self.original_prefs = {}
                except Exception:
                    self.original_prefs = {}
            else:
                info_body = body
                self.original_prefs = {}
            # Now process info_body: filter "Nodes in mesh:" to show only first node
            # Find the start of the Nodes in mesh section
            start_idx = None
            for idx, l in enumerate(info_body):
                if 'Nodes in mesh:' in l:
                    start_idx = idx
                    break

            if start_idx is None:
                # Format My info and Metadata sections, no Nodes section
                formatted_body = []
                for line in info_body:
                    stripped = line.strip()
                    if stripped.startswith('My info:'):
                        # Hide: deviceId, rebootCount
                        formatted_body.extend(self.format_json_section(line, blacklist={'deviceId', 'rebootCount'}).splitlines())
                    elif stripped.startswith('Metadata:'):
                        # Hide: canShutdown, excludedModules, has*
                        formatted_body.extend(self.format_json_section(line, blacklist={'canShutdown', 'excludedModules', 'has*'}).splitlines())
                    else:
                        formatted_body.append(line)
                display_text = '\n'.join(formatted_body)
            else:
                # Find the end of the Nodes in mesh block by scanning braces
                i = start_idx
                n = len(info_body)
                started = False
                brace_depth = 0
                block_lines = []
                while i < n:
                    l = info_body[i]
                    if not started:
                        # include the header line
                        block_lines.append(l)
                        if '{' in l:
                            started = True
                            brace_depth += l.count('{') - l.count('}')
                        i += 1
                        continue
                    else:
                        block_lines.append(l)
                        brace_depth += l.count('{') - l.count('}')
                        i += 1
                        if started and brace_depth == 0:
                            break

                block_end = i - 1

                # Parse the block_lines as YAML to extract nodes
                block_text = '\n'.join(block_lines)
                try:
                    parsed = yaml.safe_load(block_text)
                except Exception:
                    parsed = None

                nodes_dict = None
                if isinstance(parsed, dict):
                    # parsed may be { 'Nodes in mesh': { ... } } or directly the mapping
                    if 'Nodes in mesh' in parsed and isinstance(parsed['Nodes in mesh'], dict):
                        nodes_dict = parsed['Nodes in mesh']
                    else:
                        # maybe parsed is the dict itself
                        nodes_dict = parsed

                # Format the node block with blacklist filtering
                user_id = None
                if isinstance(nodes_dict, dict) and len(nodes_dict) > 0:
                    new_block_text, user_id = self.format_nodes_section(block_text, nodes_dict)
                    new_block_lines = new_block_text.splitlines()
                else:
                    # fallback: keep original block_lines
                    new_block_lines = block_lines

                # Assemble display: before block, new block, after block
                before = info_body[:start_idx]
                after = info_body[block_end + 1:]
                
                # Format My info and Metadata sections, and append user_id to Owner line
                formatted_before = []
                for line in before:
                    stripped = line.strip()
                    if stripped.startswith('Owner:') and user_id:
                        # Append user_id to Owner line
                        formatted_before.append(f"{line} -- {user_id}")
                    elif stripped.startswith('My info:'):
                        # Hide: deviceId, rebootCount
                        formatted_before.extend(self.format_json_section(line, blacklist={'deviceId', 'rebootCount'}).splitlines())
                    elif stripped.startswith('Metadata:'):
                        # Hide: canShutdown, excludedModules, has*
                        formatted_before.extend(self.format_json_section(line, blacklist={'canShutdown', 'excludedModules', 'has*'}).splitlines())
                    else:
                        formatted_before.append(line)
                
                display_lines = formatted_before + new_block_lines + after
                display_text = '\n'.join(display_lines)

            
            # Update info section in main thread
            self.after(0, lambda: (
                self.node_text.config(state=tk.NORMAL),
                self.node_text.delete('1.0', tk.END),
                self.node_text.insert(tk.END, display_text),
                self.node_text.config(state=tk.DISABLED)
            ))
            
            # Update preferences editor in main thread
            self.after(0, self.render_prefs_editor)
        
        threading.Thread(target=work, daemon=True).start()

    def revert_changes(self):
        """Revert all changes to original values"""
        for key, (_, value_var, _) in self.config_rows.items():
            orig_val = self.original_config.get(key, '')
            value_var.set(str(orig_val))

    def save_config_to_file(self):
        """Save current config to YAML file"""
        # Build YAML from current rows
        config_data = {'settings': {}}
        for key, (_, value_var, _) in self.config_rows.items():
            val_str = value_var.get().strip()
            # Try to parse as JSON, int, bool, or keep as string
            try:
                if val_str.lower() in ('true', 'false'):
                    config_data['settings'][key] = val_str.lower() == 'true'
                elif val_str.isdigit() or (val_str.startswith('-') and val_str[1:].isdigit()):
                    config_data['settings'][key] = int(val_str)
                elif val_str.startswith('{') or val_str.startswith('['):
                    config_data['settings'][key] = json.loads(val_str)
                else:
                    config_data['settings'][key] = val_str
            except Exception:
                config_data['settings'][key] = val_str

        # Preserve channels if they exist
        if '__channels__' in self.original_config:
            config_data['channels'] = self.original_config['__channels__']

        txt = yaml.dump(config_data, default_flow_style=False)
        path = filedialog.asksaveasfilename(defaultextension='.yml', initialdir=CONFIG_DIR)
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(txt)
            messagebox.showinfo("Saved", f"Saved to {path}")
            self.refresh_config_list()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save: {e}")

    def extract_keys(self):
        def work():
            out = runCmd("meshtastic --info", echoOnly=self.test_var.get(), silent=True)
            keys = extractKeysFromInfo(out, "meshtastic")
            if keys:
                writeKeysToFile(keys['nodeId'], keys['private_key'], keys['public_key'], self.current_config_path or '')
                messagebox.showinfo("Keys", f"Extracted keys for {keys['nodeId']}")
            else:
                messagebox.showwarning("Keys", "Failed to extract keys from node info")
        threading.Thread(target=work, daemon=True).start()

    def threaded_write(self):
        threading.Thread(target=self.write_to_node, daemon=True).start()

    def write_to_node(self):
        # Build config from checked rows only
        config_opts = {}
        for key, (check_var, value_var, _) in self.config_rows.items():
            if check_var.get():  # only include checked items
                val_str = value_var.get().strip()
                # Try to parse as JSON, int, bool, or keep as string
                try:
                    if val_str.lower() in ('true', 'false'):
                        config_opts[key] = val_str.lower() == 'true'
                    elif val_str.isdigit() or (val_str.startswith('-') and val_str[1:].isdigit()):
                        config_opts[key] = int(val_str)
                    elif val_str.startswith('{') or val_str.startswith('['):
                        config_opts[key] = json.loads(val_str)
                    else:
                        config_opts[key] = val_str
                except Exception:
                    config_opts[key] = val_str

        channels = self.original_config.get('__channels__', [])

        # apply top name overrides
        ln = self.longname_var.get().strip()
        sn = self.shortname_var.get().strip()
        if ln:
            config_opts['user.longname'] = ln
        if sn:
            config_opts['user.shortname'] = sn

        # Build getcmd to read current settings
        getcmd = "meshtastic"
        for key in config_opts.keys():
            if key in ("user.longname", "user.shortname"):
                continue
            getcmd += f" --get {key}"

        # Run info and getcmd
        infocmd = "meshtastic --info"
        info_out = runCmd(infocmd, echoOnly=self.test_var.get(), silent=True)
        get_out = runCmd(getcmd, echoOnly=self.test_var.get(), silent=True) if getcmd != "meshtastic" else ""

        # Determine existing settings
        combined_out = "\n".join(info_out.splitlines()[:5]) + "\n" + get_out
        old_settings = doCompareSettings(combined_out, None)
        new_settings = getNewSettings(old_settings, config_opts)

        # If retain keys requested, attempt to restore previous keys before other writes
        if self.retain_var.get():
            keys_info = extractKeysFromInfo(info_out, "meshtastic")
            if keys_info and keys_info.get('nodeId'):
                saved = readKeysFromFile(keys_info['nodeId'])
                if saved:
                    pk = saved.get('private_key')
                    if pk and self.set_var.get():
                        cmd = f"meshtastic --set security.private_key base64:{pk}"
                        runCmd(cmd, echoOnly=self.test_var.get(), reboot=(not self.test_var.get()))

        # Show planned changes
        if not new_settings:
            messagebox.showinfo("No changes", "No settings differ from node's current settings.")
        else:
            if not self.set_var.get():
                messagebox.showinfo("Planned changes", f"Planned changes:\n{new_settings}")
            else:
                # Apply settings
                setcmd = "meshtastic"
                # Owner settings need special handling
                for key, value in new_settings.items():
                    if key == "user.longname":
                        setcmd += f" --set-owner '{value}'"
                    elif key == "user.shortname":
                        setcmd += f" --set-owner-short {value}"
                    elif key == "security.admin_key":
                        continue
                    else:
                        setcmd += f" --set {key} {value}"
                runCmd(setcmd, echoOnly=self.test_var.get(), reboot=(not self.test_var.get()))

                # Handle admin keys
                if new_settings.get('security.admin_key') is not None:
                    admin_vals = new_settings['security.admin_key']
                    admin_cmd = "meshtastic"
                    for v in admin_vals:
                        admin_cmd += f" --set security.admin_key {v}"
                    runCmd(admin_cmd, echoOnly=self.test_var.get(), reboot=(not self.test_var.get()))

        # Channels
        if channels:
            if not doCompareChannels(info_out, channels):
                if self.set_var.get():
                    for cdict in channels:
                        cmd = f"meshtastic --ch-set name {cdict['name']} --ch-set psk {cdict['psk']} --ch-index {cdict['index']}"
                        runCmd(cmd, echoOnly=self.test_var.get(), reboot=(not self.test_var.get()))
                else:
                    messagebox.showinfo("Channels", "Channels differ but not applying (set disabled).")

        # After writes, refresh node info and attempt to extract keys
        self.refresh_node_info()
        if not self.test_var.get():
            info_out2 = runCmd(infocmd, echoOnly=self.test_var.get(), silent=True)
            keys = extractKeysFromInfo(info_out2, "meshtastic")
            if keys:
                writeKeysToFile(keys['nodeId'], keys['private_key'], keys['public_key'], self.current_config_path or '')

        messagebox.showinfo("Done", "Write operation finished.")


def main():
    app = ConfiguratorGUI()
    app.mainloop()


if __name__ == '__main__':
    main()
