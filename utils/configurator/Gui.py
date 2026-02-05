import os
import threading
import yaml
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
        self.geometry("1000x600")

        self.config_files = []
        self.current_config_path = None
        self.loaded_config_text = ""

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

        # Node info text (read-only)
        self.node_text = tk.Text(left_frame, wrap=tk.NONE)
        self.node_text.pack(fill=tk.BOTH, expand=True)
        self.node_text.config(state=tk.DISABLED)

        node_btns = ttk.Frame(left_frame)
        node_btns.pack(fill=tk.X)
        ttk.Button(node_btns, text="Refresh Node Info", command=self.refresh_node_info).pack(side=tk.LEFT, padx=4, pady=4)
        ttk.Button(node_btns, text="Extract Keys", command=self.extract_keys).pack(side=tk.LEFT, padx=4, pady=4)

        # Config editor
        self.config_text = tk.Text(right_frame, wrap=tk.NONE)
        self.config_text.pack(fill=tk.BOTH, expand=True)

        cfg_btns = ttk.Frame(right_frame)
        cfg_btns.pack(fill=tk.X)
        ttk.Button(cfg_btns, text="Revert changes", command=self.revert_changes).pack(side=tk.LEFT, padx=4, pady=4)
        ttk.Button(cfg_btns, text="Save to file...", command=self.save_config_to_file).pack(side=tk.LEFT, padx=4, pady=4)

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
        self.config_text.delete('1.0', tk.END)
        self.config_text.insert(tk.END, txt)

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

            self.node_text.config(state=tk.NORMAL)
            self.node_text.delete('1.0', tk.END)
            self.node_text.insert(tk.END, out)
            self.node_text.config(state=tk.DISABLED)
        threading.Thread(target=work, daemon=True).start()

    def revert_changes(self):
        # restore original loaded text
        self.config_text.delete('1.0', tk.END)
        self.config_text.insert(tk.END, self.loaded_config_text)

    def save_config_to_file(self):
        txt = self.config_text.get('1.0', tk.END)
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
        # Read YAML from editor
        txt = self.config_text.get('1.0', tk.END)
        try:
            yml = yaml.safe_load(txt) or {}
        except Exception as e:
            messagebox.showerror("Error", f"Invalid YAML: {e}")
            return

        config_opts = yml.get('settings', {})
        channels = yml.get('channels', [])

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
