"""Tkinter GUI for controlling a cef168 lens controller board over serial."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from . import config as cfgmod
from . import protocol as proto
from .device import LensController, list_available_ports

POLL_INTERVAL_S = 0.5


class LensApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("cef168 Lens Control")
        self.geometry("480x520")
        self.resizable(False, False)

        self.config_data = cfgmod.load_config()
        self.lens: LensController | None = None
        self._status_queue: "queue.Queue[object]" = queue.Queue()
        self._poll_stop = threading.Event()
        self._poll_thread: threading.Thread | None = None

        self._build_connection_frame()
        self._build_status_frame()
        self._build_focus_frame()
        self._build_aperture_frame()
        self._build_calibrate_frame()

        self._set_controls_enabled(False)
        self._refresh_ports()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(200, self._drain_status_queue)

    # -- connection -----------------------------------------------------

    def _build_connection_frame(self) -> None:
        frame = ttk.LabelFrame(self, text="Connection")
        frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(frame, text="Port:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.port_var = tk.StringVar(value=self.config_data.last_port or "")
        self.port_combo = ttk.Combobox(frame, textvariable=self.port_var, width=20)
        self.port_combo.grid(row=0, column=1, padx=5, pady=5)

        ttk.Button(frame, text="Refresh", command=self._refresh_ports).grid(
            row=0, column=2, padx=5, pady=5
        )

        ttk.Label(frame, text="Baud:").grid(row=0, column=3, padx=5, pady=5, sticky="w")
        self.baud_var = tk.StringVar(value=str(self.config_data.last_baudrate))
        ttk.Entry(frame, textvariable=self.baud_var, width=8).grid(
            row=0, column=4, padx=5, pady=5
        )

        self.connect_btn = ttk.Button(frame, text="Connect", command=self._on_connect_clicked)
        self.connect_btn.grid(row=0, column=5, padx=5, pady=5)

        ttk.Button(frame, text="Save profile...", command=self._save_profile_dialog).grid(
            row=1, column=1, padx=5, pady=5, sticky="w"
        )

        self.profile_var = tk.StringVar()
        self.profile_combo = ttk.Combobox(
            frame, textvariable=self.profile_var, width=20, state="readonly"
        )
        self.profile_combo.grid(row=1, column=2, columnspan=2, padx=5, pady=5)
        self.profile_combo.bind("<<ComboboxSelected>>", self._on_profile_selected)
        self._refresh_profiles()

        self.status_label = ttk.Label(self, text="Disconnected", foreground="red")
        self.status_label.pack(anchor="w", padx=15)

    def _refresh_ports(self) -> None:
        ports = [p.device for p in list_available_ports()]
        self.port_combo["values"] = ports
        if not self.port_var.get() and ports:
            self.port_var.set(ports[0])

    def _refresh_profiles(self) -> None:
        names = [p.name for p in self.config_data.profiles]
        self.profile_combo["values"] = names

    def _on_profile_selected(self, _event=None) -> None:
        profile = self.config_data.get_profile(self.profile_var.get())
        if profile:
            self.port_var.set(profile.port)
            self.baud_var.set(str(profile.baudrate))

    def _save_profile_dialog(self) -> None:
        name = simpledialog.askstring("Save profile", "Profile name:", parent=self)
        if not name:
            return
        self.config_data.upsert_profile(
            cfgmod.ConnectionProfile(
                name=name, port=self.port_var.get(), baudrate=int(self.baud_var.get() or 115200)
            )
        )
        cfgmod.save_config(self.config_data)
        self._refresh_profiles()

    def _on_connect_clicked(self) -> None:
        if self.lens is not None:
            self._disconnect()
            return
        port = self.port_var.get().strip()
        if not port:
            messagebox.showerror("Error", "Please choose a serial port.")
            return
        try:
            baud = int(self.baud_var.get())
        except ValueError:
            messagebox.showerror("Error", "Baud rate must be a number.")
            return
        try:
            self.lens = LensController(port, baudrate=baud)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            messagebox.showerror("Connection failed", str(exc))
            return

        self.config_data.last_port = port
        self.config_data.last_baudrate = baud
        cfgmod.save_config(self.config_data)

        self.status_label.config(text=f"Connected to {port}", foreground="green")
        self.connect_btn.config(text="Disconnect")
        self._set_controls_enabled(True)
        self._start_polling()

    def _disconnect(self) -> None:
        self._stop_polling()
        if self.lens is not None:
            self.lens.close()
            self.lens = None
        self.status_label.config(text="Disconnected", foreground="red")
        self.connect_btn.config(text="Connect")
        self._set_controls_enabled(False)

    def _on_close(self) -> None:
        self._disconnect()
        self.destroy()

    # -- status polling --------------------------------------------------

    def _build_status_frame(self) -> None:
        frame = ttk.LabelFrame(self, text="Live status")
        frame.pack(fill="x", padx=10, pady=5)

        self.focus_status_var = tk.StringVar(value="focus: -")
        self.moving_status_var = tk.StringVar(value="moving: -")
        self.time_status_var = tk.StringVar(value="move time: -")

        ttk.Label(frame, textvariable=self.focus_status_var).pack(anchor="w", padx=10)
        ttk.Label(frame, textvariable=self.moving_status_var).pack(anchor="w", padx=10)
        ttk.Label(frame, textvariable=self.time_status_var).pack(anchor="w", padx=10)

    def _start_polling(self) -> None:
        self._poll_stop.clear()
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def _stop_polling(self) -> None:
        self._poll_stop.set()
        if self._poll_thread is not None:
            self._poll_thread.join(timeout=2)
            self._poll_thread = None

    def _poll_loop(self) -> None:
        while not self._poll_stop.is_set():
            lens = self.lens
            if lens is not None:
                try:
                    status = lens.get_status()
                    self._status_queue.put(status)
                except proto.CefError as exc:
                    self._status_queue.put(exc)
            self._poll_stop.wait(POLL_INTERVAL_S)

    def _drain_status_queue(self) -> None:
        try:
            while True:
                item = self._status_queue.get_nowait()
                if isinstance(item, Exception):
                    self.moving_status_var.set(f"moving: error ({item})")
                else:
                    self.focus_status_var.set(f"focus: {item.focus_position}")
                    self.moving_status_var.set(f"moving: {item.moving}")
                    self.time_status_var.set(f"move time: {item.move_time_ms} ms")
        except queue.Empty:
            pass
        self.after(200, self._drain_status_queue)

    # -- focus -----------------------------------------------------------

    def _build_focus_frame(self) -> None:
        frame = ttk.LabelFrame(self, text="Focus")
        frame.pack(fill="x", padx=10, pady=5)

        self.focus_value_var = tk.StringVar()
        row = ttk.Frame(frame)
        row.pack(fill="x", padx=5, pady=5)
        ttk.Label(row, text="Position:").pack(side="left")
        ttk.Entry(row, textvariable=self.focus_value_var, width=10).pack(side="left", padx=5)
        self._add_button(row, "Set", self._focus_set)
        self._add_button(row, "Get", self._focus_get)

        row2 = ttk.Frame(frame)
        row2.pack(fill="x", padx=5, pady=5)
        self._add_button(row2, "<< Min", self._focus_min)
        self._add_button(row2, "- 50", lambda: self._focus_move(-50))
        self._add_button(row2, "- 10", lambda: self._focus_move(-10))
        self._add_button(row2, "+ 10", lambda: self._focus_move(10))
        self._add_button(row2, "+ 50", lambda: self._focus_move(50))
        self._add_button(row2, "Inf >>", self._focus_inf)

        row3 = ttk.Frame(frame)
        row3.pack(fill="x", padx=5, pady=5)
        ttk.Label(row3, text="Speed (1-4):").pack(side="left")
        self.speed_var = tk.StringVar(value="2")
        ttk.Combobox(
            row3, textvariable=self.speed_var, values=["1", "2", "3", "4"], width=3, state="readonly"
        ).pack(side="left", padx=5)
        self._add_button(row3, "Apply", self._speed_set)

        self._focus_controls = [frame]

    def _focus_set(self) -> None:
        self._safe_call(lambda: self.lens.set_focus(int(self.focus_value_var.get())))

    def _focus_get(self) -> None:
        def action():
            value = self.lens.get_focus()
            self.focus_value_var.set(str(value))

        self._safe_call(action)

    def _focus_move(self, delta: int) -> None:
        self._safe_call(lambda: self.lens.move_focus(delta))

    def _focus_min(self) -> None:
        self._safe_call(self.lens.move_focus_to_min)

    def _focus_inf(self) -> None:
        self._safe_call(self.lens.move_focus_to_infinity)

    def _speed_set(self) -> None:
        self._safe_call(lambda: self.lens.set_focus_speed(int(self.speed_var.get())))

    # -- aperture --------------------------------------------------------

    def _build_aperture_frame(self) -> None:
        frame = ttk.LabelFrame(self, text="Aperture")
        frame.pack(fill="x", padx=10, pady=5)

        self.aperture_value_var = tk.StringVar()
        row = ttk.Frame(frame)
        row.pack(fill="x", padx=5, pady=5)
        ttk.Label(row, text="f-stop:").pack(side="left")
        ttk.Entry(row, textvariable=self.aperture_value_var, width=10).pack(side="left", padx=5)
        self._add_button(row, "Set", self._aperture_set)
        self._add_button(row, "Get range", self._aperture_get_range)

        row2 = ttk.Frame(frame)
        row2.pack(fill="x", padx=5, pady=5)
        self._add_button(row2, "Open 1 stop", lambda: self._aperture_adjust(1.0))
        self._add_button(row2, "Close 1 stop", lambda: self._aperture_adjust(-1.0))

        self._aperture_controls = [frame]

    def _aperture_set(self) -> None:
        self._safe_call(lambda: self.lens.set_aperture(float(self.aperture_value_var.get())))

    def _aperture_get_range(self) -> None:
        def action():
            r = self.lens.get_aperture_range()
            self.aperture_value_var.set(f"{r.min}-{r.max}")

        self._safe_call(action)

    def _aperture_adjust(self, stops: float) -> None:
        self._safe_call(lambda: self.lens.adjust_aperture(stops))

    # -- calibration -------------------------------------------------------

    def _build_calibrate_frame(self) -> None:
        frame = ttk.LabelFrame(self, text="Calibration")
        frame.pack(fill="x", padx=10, pady=5)
        self._add_button(frame, "Run calibration", self._calibrate)
        self._calibrate_controls = [frame]

    def _calibrate(self) -> None:
        if not messagebox.askyesno(
            "Calibrate", "This traverses the full focus range. Continue?"
        ):
            return
        self._safe_call(self.lens.calibrate)

    # -- helpers -----------------------------------------------------------

    def _add_button(self, parent, text: str, command) -> ttk.Button:
        btn = ttk.Button(parent, text=text, command=command)
        btn.pack(side="left", padx=3)
        return btn

    def _safe_call(self, action) -> None:
        if self.lens is None:
            messagebox.showerror("Error", "Not connected.")
            return
        try:
            action()
        except proto.CefError as exc:
            messagebox.showerror("Device error", str(exc))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Error", str(exc))

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for group in (
            getattr(self, "_focus_controls", []),
            getattr(self, "_aperture_controls", []),
            getattr(self, "_calibrate_controls", []),
        ):
            for frame in group:
                self._set_frame_state(frame, state)

    def _set_frame_state(self, widget, state: str) -> None:
        for child in widget.winfo_children():
            try:
                child.configure(state=state)
            except tk.TclError:
                pass
            self._set_frame_state(child, state)


def main() -> int:
    app = LensApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
