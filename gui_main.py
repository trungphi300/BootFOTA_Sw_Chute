import threading
import subprocess
import sys
import io
import contextlib
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from master import Master
from slave import Slave
from BootFOTA_Sw_Chute.analysis_hex import analysis_hex


class TextRedirector(io.StringIO):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def write(self, s):
        self.text_widget.configure(state="normal")
        self.text_widget.insert("end", s)
        self.text_widget.see("end")
        self.text_widget.configure(state="disabled")

    def flush(self):
        pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BootFOTA UI")
        self.geometry("800x600")

        self.mode_var = tk.StringVar(value="request_status")

        # Top frame: mode selection
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=8)

        ttk.Label(top, text="Mode:").pack(side="left")
        modes = ["request_status", "barone_test", "slave_boot", "master_boot"]
        mode_cb = ttk.Combobox(top, values=modes, textvariable=self.mode_var, state="readonly", width=20)
        mode_cb.pack(side="left", padx=8)
        mode_cb.bind("<<ComboboxSelected>>", lambda e: self.update_fields())

        # dynamic fields
        self.fields_frame = ttk.Frame(self)
        self.fields_frame.pack(fill="x", padx=8)

        # Common fields defaults
        self.host_var = tk.StringVar(value="192.168.1.254")
        self.port_var = tk.IntVar(value=1111)

        # Mode-specific vars
        self.id_master_var = tk.IntVar(value=1)
        self.qty_master_var = tk.IntVar(value=1)
        self.id_master_start_var = tk.IntVar(value=1)
        self.version_master_var = tk.IntVar(value=36)
        self.hex_path_var = tk.StringVar(value="")

        self.id_slave_var = tk.IntVar(value=1)
        self.qty_slave_var = tk.IntVar(value=1)
        self.sq_slave_start_var = tk.IntVar(value=1)
        self.version_slave_var = tk.IntVar(value=36)

        # Buttons
        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=8, pady=6)
        ttk.Button(btns, text="Run", command=self.on_run).pack(side="left")
        ttk.Button(btns, text="Stop", command=self.on_stop).pack(side="left", padx=6)
        ttk.Button(btns, text="Clear Log", command=self.on_clear).pack(side="left")

        # Log
        self.log = tk.Text(self, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, padx=8, pady=4)

        # redirect stdout
        self.stdout_redirect = TextRedirector(self.log)

        self.process = None
        self._worker = None

        self.update_fields()

    def update_fields(self):
        for w in self.fields_frame.winfo_children():
            w.destroy()

        # Common host/port
        row = ttk.Frame(self.fields_frame)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Host:").pack(side="left")
        ttk.Entry(row, textvariable=self.host_var, width=20).pack(side="left", padx=4)
        ttk.Label(row, text="Port:").pack(side="left", padx=8)
        ttk.Entry(row, textvariable=self.port_var, width=8).pack(side="left", padx=4)

        mode = self.mode_var.get()
        if mode == "request_status":
            row = ttk.Frame(self.fields_frame)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text="Master ID:").pack(side="left")
            ttk.Entry(row, textvariable=self.id_master_var, width=8).pack(side="left", padx=4)

        elif mode == "barone_test":
            row = ttk.Frame(self.fields_frame)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text="(Runs barone_test.py) No extra inputs required.").pack(side="left")

        elif mode == "master_boot":
            # hex path
            row = ttk.Frame(self.fields_frame)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text="Hex Path:").pack(side="left")
            ttk.Entry(row, textvariable=self.hex_path_var, width=60).pack(side="left", padx=4)
            ttk.Button(row, text="Browse", command=self.browse_hex).pack(side="left", padx=4)

            row = ttk.Frame(self.fields_frame)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text="Qty Master:").pack(side="left")
            ttk.Entry(row, textvariable=self.qty_master_var, width=6).pack(side="left", padx=4)
            ttk.Label(row, text="First ID:").pack(side="left", padx=6)
            ttk.Entry(row, textvariable=self.id_master_start_var, width=6).pack(side="left", padx=4)
            ttk.Label(row, text="Version:").pack(side="left", padx=6)
            ttk.Entry(row, textvariable=self.version_master_var, width=6).pack(side="left", padx=4)

        elif mode == "slave_boot":
            row = ttk.Frame(self.fields_frame)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text="Hex Path:").pack(side="left")
            ttk.Entry(row, textvariable=self.hex_path_var, width=60).pack(side="left", padx=4)
            ttk.Button(row, text="Browse", command=self.browse_hex).pack(side="left", padx=4)

            row = ttk.Frame(self.fields_frame)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text="Master ID:").pack(side="left")
            ttk.Entry(row, textvariable=self.id_master_var, width=6).pack(side="left", padx=4)
            ttk.Label(row, text="Qty Slave:").pack(side="left", padx=6)
            ttk.Entry(row, textvariable=self.qty_slave_var, width=6).pack(side="left", padx=4)
            ttk.Label(row, text="First SQ:").pack(side="left", padx=6)
            ttk.Entry(row, textvariable=self.sq_slave_start_var, width=6).pack(side="left", padx=4)
            ttk.Label(row, text="Version:").pack(side="left", padx=6)
            ttk.Entry(row, textvariable=self.version_slave_var, width=6).pack(side="left", padx=4)

    def browse_hex(self):
        p = filedialog.askopenfilename(title="Select HEX file", filetypes=[("HEX files", "*.hex"), ("All files", "*")])
        if p:
            self.hex_path_var.set(p)

    def on_clear(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def on_stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process = None
        if self._worker and self._worker.is_alive():
            messagebox.showinfo("Info", "Worker is running; it will stop after current step if possible.")

    def write_log(self, s: str):
        self.log.configure(state="normal")
        self.log.insert("end", s)
        self.log.see("end")
        self.log.configure(state="disabled")

    def on_run(self):
        mode = self.mode_var.get()
        # run in background thread
        t = threading.Thread(target=self._run_mode, args=(mode,), daemon=True)
        self._worker = t
        t.start()

    def _run_mode(self, mode):
        # capture stdout prints into log
        with contextlib.redirect_stdout(self.stdout_redirect):
            try:
                host = self.host_var.get()
                port = int(self.port_var.get())
                if mode == "request_status":
                    ID = int(self.id_master_var.get())
                    m = Master(host, port)
                    print(f"Requesting status for Master {ID} @ {host}:{port}")
                    res = m.request_status_master(ID)
                    print("Result:", res)

                elif mode == "barone_test":
                    # run barone_test.py as subprocess
                    print("Running barone_test.py (subprocess)...")
                    self.process = subprocess.Popen([sys.executable, "BootFOTA_Sw_Chute/barone_test.py"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    for line in self.process.stdout:
                        print(line, end="")
                    self.process.wait()
                    print("barone_test finished with code", self.process.returncode)

                elif mode == "master_boot":
                    hexp = self.hex_path_var.get()
                    if not hexp:
                        print("Please select HEX file")
                        return
                    print("Analysing hex file...", hexp)
                    num_line, list_data_flash, size_hex, addr_start, addr_end = analysis_hex(hexp, "word")
                    print(f"Lines: {num_line}, addr_start: {hex(addr_start)}, addr_end: {hex(addr_end)}, size: {size_hex}")

                    qty = int(self.qty_master_var.get())
                    start_id = int(self.id_master_start_var.get())
                    version = int(self.version_master_var.get())

                    for idx in range(start_id, start_id + qty):
                        print(f"\n=== Working on Master ID {idx} ===")
                        m = Master(host, port)
                        if not m.reset_master(idx, retry=3):
                            print("Reset failed, skipping")
                            continue
                        time_sleep = 0.1
                        # run bootfota
                        if not m.run_bootFOTA_Fw_master(idx, retry=3):
                            print("Run bootfota failed, skipping")
                            continue
                        if not m.start_bootFota_process(idx, addr_start=addr_start, addr_end=addr_end, retry=3):
                            print("Start bootfota process failed, skipping")
                            continue
                        if not m.flashing_master_process(idx, list_data_flash, retry=3):
                            print("Flashing failed, skipping")
                            continue
                        if not m.run_Application_fw_master(idx, addr_start, version, self.MASTER_CHUTE_CIRCUIT if hasattr(m, 'MASTER_CHUTE_CIRCUIT') else 0x01, retry=3):
                            print("Run application failed")
                        print(f"Master {idx} done")

                elif mode == "slave_boot":
                    hexp = self.hex_path_var.get()
                    if not hexp:
                        print("Please select HEX file")
                        return
                    print("Analysing hex file...", hexp)
                    num_line, list_data_flash, size_hex, addr_start, addr_end = analysis_hex(hexp, "word")
                    print(f"Lines: {num_line}, addr_start: {hex(addr_start)}, addr_end: {hex(addr_end)}, size: {size_hex}")

                    ID_master = int(self.id_master_var.get())
                    qty = int(self.qty_slave_var.get())
                    start_sq = int(self.sq_slave_start_var.get())
                    version = int(self.version_slave_var.get())

                    for sq in range(start_sq, start_sq + qty):
                        print(f"\n=== Booting Slave {sq} on Master {ID_master} ===")
                        s = Slave(host, port)
                        # ensure master is in forward mode
                        if not s.run_FWD_master(ID_master, retry=3):
                            print("Run forward mode failed")
                        if not s.start_bootFota_process(ID_master, sq, addr_start=addr_start, addr_end=addr_end, retry=3):
                            print("Start bootfota on slave failed")
                            continue
                        if not s.flashing_slave_process(ID_master, sq, list_data_flash, retry=3):
                            print("Flashing slave failed")
                            continue
                        if not s.run_Application_fw_slave(ID_master, sq, addr_start, version, s.SLAVE_CHUTE_CIRCUIT if hasattr(s, 'SLAVE_CHUTE_CIRCUIT') else 0x02, retry=3):
                            print("Run app on slave failed")
                        print(f"Slave {sq} done")

            except Exception as e:
                print("Error while running mode:", e)


if __name__ == "__main__":
    app = App()
    app.mainloop()
