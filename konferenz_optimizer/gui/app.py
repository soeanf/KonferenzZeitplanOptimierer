"""Schlichte, mehrstufige GUI (tkinter + sv-ttk) fuer den Konferenzzeitplan-Optimierer."""
from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..adapters.teacher_subjects import problem_from_teachers, read_teachers
from ..cli import export, solve
from ..core.model import Schedule

try:
    import sv_ttk
except ImportError:  # optional: ohne Theme default-Look
    sv_ttk = None

STEPS = ["1  Daten laden", "2  Daten prüfen", "3  Berechnen", "4  Ergebnis"]
OFF = "✗ "  # Praefix fuer abgewaehlte Faecher in der Tabelle
ERR = "#c42b1c"


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Konferenzzeitplan-Optimierer")
        self.geometry("1100x720")
        self.minsize(900, 600)
        if sv_ttk:
            sv_ttk.set_theme("light")
        self.option_add("*Font", ("Segoe UI", 10))

        self.teachers: dict[str, list[str]] = {}
        self.disabled: set[tuple[str, str]] = set()  # (Lehrer, Fach)
        self.schedule: Schedule | None = None
        self.path = ""
        self.step = 0
        self._queue: queue.Queue = queue.Queue()
        self._busy = False
        self._check_vars: dict[str, tk.BooleanVar] = {}
        self._current_teacher: str | None = None

        self._build_chrome()
        self._pages = [self._page_load(), self._page_review(), self._page_solve(), self._page_result()]
        self.show_step(0)

    # ---------- Geruest ----------
    def _build_chrome(self) -> None:
        header = ttk.Frame(self, padding=(20, 14))
        header.pack(fill="x")
        self._step_labels = []
        for text in STEPS:
            lbl = ttk.Label(header, text=text, foreground="gray")
            lbl.pack(side="left", padx=(0, 28))
            self._step_labels.append(lbl)
        ttk.Button(header, text="Hell/Dunkel", command=self._toggle_theme).pack(side="right")
        ttk.Separator(self).pack(fill="x")

        self.body = ttk.Frame(self, padding=20)
        self.body.pack(fill="both", expand=True)

        ttk.Separator(self).pack(fill="x")
        footer = ttk.Frame(self, padding=(20, 12))
        footer.pack(fill="x")
        self.status = ttk.Label(footer, text="", foreground="gray")
        self.status.pack(side="left")
        self.btn_next = ttk.Button(footer, style="Accent.TButton", command=self.on_next)
        self.btn_next.pack(side="right")
        self.btn_back = ttk.Button(footer, text="Zurück", command=lambda: self.show_step(self.step - 1))
        self.btn_back.pack(side="right", padx=8)

    def _toggle_theme(self) -> None:
        if sv_ttk:
            sv_ttk.toggle_theme()
            self._apply_titlebar_theme()

    def _apply_titlebar_theme(self) -> None:
        """Passt die Windows-Titelleiste (DWM) an das aktuelle Theme an."""
        if sys.platform != "win32" or not sv_ttk:
            return
        import ctypes

        self.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
        dark = ctypes.c_int(1 if sv_ttk.get_theme() == "dark" else 0)
        # 20 = DWMWA_USE_IMMERSIVE_DARK_MODE (19 bei aelteren Windows-10-Builds)
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(dark), ctypes.sizeof(dark)) == 0:
                break
        # Neuzeichnen der Titelleiste erzwingen
        self.withdraw()
        self.deiconify()

    def show_step(self, i: int) -> None:
        self.step = max(0, min(i, len(self._pages) - 1))
        for page in self._pages:
            page.pack_forget()
        self._pages[self.step].pack(in_=self.body, fill="both", expand=True)
        for n, lbl in enumerate(self._step_labels):
            lbl.configure(
                foreground="" if n == self.step else "gray",
                font=("Segoe UI", 11, "bold") if n == self.step else ("Segoe UI", 11),
            )
        self.btn_back.state(["!disabled"] if self.step > 0 and not self._busy else ["disabled"])
        texts = ["Weiter", "Weiter", "Berechnen", "Exportieren…"]
        self.btn_next.configure(text=texts[self.step])
        enabled = bool(self.teachers) if self.step < 3 else self.schedule is not None
        self.btn_next.state(["!disabled"] if enabled and not self._busy else ["disabled"])
        if self.step == 1:
            self._refresh_review()
        if self.step == 3:
            self._refresh_result()

    def on_next(self) -> None:
        if self.step == 2:
            self.start_solve()
        elif self.step == 3:
            self.do_export()
        else:
            self.show_step(self.step + 1)

    # ---------- Schritt 1: Laden ----------
    def _page_load(self) -> ttk.Frame:
        f = ttk.Frame(self.body)
        box = ttk.Frame(f)
        box.place(relx=0.5, rely=0.4, anchor="center")
        ttk.Label(box, text="Kollegiumsliste laden", font=("Segoe UI", 20, "bold")).pack()
        ttk.Label(
            box,
            text="CSV mit den Spalten  Name, Fach 1, Fach 2, (Fach 3), (Fach 4)",
            foreground="gray",
        ).pack(pady=(6, 24))
        ttk.Button(box, text="CSV-Datei auswählen…", style="Accent.TButton", command=self.load_csv).pack()
        self.load_info = ttk.Label(box, text="", justify="center")
        self.load_info.pack(pady=20)
        return f

    def load_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="CSV-Datei wählen",
            filetypes=[("CSV-Dateien", "*.csv *.txt"), ("Alle Dateien", "*.*")],
        )
        if not path:
            return
        try:
            teachers = read_teachers(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Fehler beim Lesen", str(exc))
            return
        if not teachers:
            messagebox.showwarning("Keine Daten", "Die Datei enthält keine Lehrer.")
            return
        self.teachers, self.path = teachers, path
        self.disabled.clear()
        self.schedule = None
        self._current_teacher = None
        subjects = {s for v in teachers.values() for s in v}
        self.load_info.configure(text=f"{path}\n{len(teachers)} Lehrer · {len(subjects)} Fächer")
        self.show_step(1)

    # ---------- Schritt 2: Pruefen ----------
    def _page_review(self) -> ttk.Frame:
        f = ttk.Frame(self.body)
        ttk.Label(f, text="Daten prüfen", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(
            f,
            text="Lehrer auswählen und rechts einzelne Fächer abwählen – abgewählte Fächer werden nicht berücksichtigt.",
            foreground="gray",
        ).pack(anchor="w", pady=(2, 12))

        main = ttk.Frame(f)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=3)
        main.columnconfigure(1, weight=1, minsize=280)
        main.rowconfigure(0, weight=1)

        left = ttk.Frame(main)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *_: self._refresh_review())
        ttk.Entry(left, textvariable=self.search).pack(fill="x", pady=(0, 8))
        self.t_tree = self._make_tree(left, ("name", "f1", "f2", "f3", "f4"),
                                      ("Lehrer", "Fach 1", "Fach 2", "Fach 3", "Fach 4"), (170, 120, 120, 120, 120))
        self.t_tree.tag_configure("changed", foreground="#9a6700")
        self.t_tree.bind("<<TreeviewSelect>>", self._on_teacher_select)

        right = ttk.Frame(main)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(2, weight=1)
        right.columnconfigure(0, weight=1)
        self.sel_label = ttk.Label(right, text="Kein Lehrer ausgewählt", font=("Segoe UI", 11, "bold"))
        self.sel_label.grid(row=0, column=0, sticky="w")
        self.check_frame = ttk.Frame(right)
        self.check_frame.grid(row=1, column=0, sticky="ew", pady=(8, 16))
        self.s_tree = self._make_tree(right, ("fach", "n"), ("Fach", "Teilnehmer"), (150, 80), parent_grid=(2, 0))
        self.summary = ttk.Label(f, text="", foreground="gray")
        self.summary.pack(anchor="w", pady=(10, 0))
        return f

    def _make_tree(self, parent, cols, heads, widths, parent_grid=None) -> ttk.Treeview:
        wrap = ttk.Frame(parent)
        if parent_grid:
            wrap.grid(row=parent_grid[0], column=parent_grid[1], sticky="nsew")
        else:
            wrap.pack(fill="both", expand=True)
        tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="browse")
        for c, h, w in zip(cols, heads, widths):
            tree.heading(c, text=h)
            tree.column(c, width=w, anchor="w", stretch=True)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        return tree

    def _refresh_review(self) -> None:
        keep = self._current_teacher
        query = self.search.get().strip().casefold()
        self.t_tree.delete(*self.t_tree.get_children())
        for name, subjects in self.teachers.items():
            if query and query not in name.casefold() and not any(query in s.casefold() for s in subjects):
                continue
            cells = [(OFF if (name, s) in self.disabled else "") + s for s in subjects[:4]]
            cells += [""] * (4 - len(cells))
            changed = any((name, s) in self.disabled for s in subjects)
            self.t_tree.insert("", "end", iid=name, values=(name, *cells), tags=("changed",) if changed else ())
        if keep and self.t_tree.exists(keep):
            self.t_tree.selection_set(keep)
        self._refresh_subjects()

    def _refresh_subjects(self) -> None:
        active = self._active_teachers()
        problem = problem_from_teachers(active)
        self.s_tree.delete(*self.s_tree.get_children())
        for fach, members in sorted(problem.events.items()):
            self.s_tree.insert("", "end", values=(fach, len(members)))
        entries = sum(len(v) for v in active.values())
        self.summary.configure(
            text=f"{len(self.teachers)} Lehrer · {len(problem.events)} Fächer · {entries} Teilnahmen"
            + (f" · {len(self.disabled)} abgewählt" if self.disabled else "")
        )

    def _on_teacher_select(self, _event=None) -> None:
        sel = self.t_tree.selection()
        if not sel or sel[0] == self._current_teacher and self._check_vars:
            return
        name = sel[0]
        self._current_teacher = name
        for w in self.check_frame.winfo_children():
            w.destroy()
        self._check_vars = {}
        self.sel_label.configure(text=name)
        for subject in self.teachers[name]:
            var = tk.BooleanVar(value=(name, subject) not in self.disabled)
            self._check_vars[subject] = var
            ttk.Checkbutton(
                self.check_frame, text=subject, variable=var,
                command=lambda s=subject: self._toggle_subject(name, s),
            ).pack(anchor="w", pady=2)

    def _toggle_subject(self, name: str, subject: str) -> None:
        key = (name, subject)
        if self._check_vars[subject].get():
            self.disabled.discard(key)
        else:
            self.disabled.add(key)
        self.schedule = None
        self._refresh_review()

    def _active_teachers(self) -> dict[str, list[str]]:
        return {
            n: [s for s in subs if (n, s) not in self.disabled]
            for n, subs in self.teachers.items()
        }

    # ---------- Schritt 3: Berechnen ----------
    def _page_solve(self) -> ttk.Frame:
        f = ttk.Frame(self.body)
        ttk.Label(f, text="Einstellungen", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        form = ttk.Frame(f)
        form.pack(anchor="w", pady=20)

        self.use_limit = tk.BooleanVar(value=False)
        self.max_slots = tk.IntVar(value=6)
        row = ttk.Frame(form)
        row.pack(anchor="w", pady=6)
        ttk.Checkbutton(row, text="Obergrenze für hintereinanderliegende Konferenz-Slots:",
                        variable=self.use_limit, command=self._limit_toggled).pack(side="left")
        self.limit_spin = ttk.Spinbox(row, from_=1, to=50, textvariable=self.max_slots, width=5, state="disabled")
        self.limit_spin.pack(side="left", padx=10)

        self.objective = tk.StringVar(value="teilnehmer")
        ttk.Label(form, text="Falls die Obergrenze nicht reicht, minimiere …").pack(anchor="w", pady=(16, 4))
        ttk.Radiobutton(form, text="die Anzahl der Lehrer, die Konferenzen verpassen",
                        variable=self.objective, value="teilnehmer").pack(anchor="w", pady=2)
        ttk.Radiobutton(form, text="die Gesamtzahl der verpassten Konferenzen",
                        variable=self.objective, value="verpasst").pack(anchor="w", pady=2)

        row = ttk.Frame(form)
        row.pack(anchor="w", pady=(16, 0))
        ttk.Label(row, text="Zeitlimit (Sekunden):").pack(side="left")
        self.time_limit = tk.IntVar(value=30)
        ttk.Spinbox(row, from_=1, to=3600, textvariable=self.time_limit, width=6).pack(side="left", padx=10)

        self.progress = ttk.Progressbar(f, mode="indeterminate", length=360)
        self.progress.pack(anchor="w", pady=(20, 0))
        self.solve_msg = ttk.Label(f, text="", foreground="gray")
        self.solve_msg.pack(anchor="w", pady=8)
        return f

    def _limit_toggled(self) -> None:
        self.limit_spin.configure(state="normal" if self.use_limit.get() else "disabled")

    def start_solve(self) -> None:
        try:
            max_slots = int(self.max_slots.get()) if self.use_limit.get() else None
            limit = float(self.time_limit.get())
        except (tk.TclError, ValueError):
            messagebox.showerror("Eingabe", "Bitte gültige Zahlen eingeben.")
            return
        if (max_slots is not None and max_slots < 1) or limit < 1:
            messagebox.showerror("Eingabe", "Werte müssen mindestens 1 sein.")
            return
        problem = problem_from_teachers(self._active_teachers())
        if not problem.events:
            messagebox.showwarning("Keine Fächer", "Es sind keine Fächer ausgewählt.")
            return
        self._busy = True
        self.show_step(2)
        self.progress.start(12)
        self.solve_msg.configure(text="Berechne optimalen Plan …")
        objective = self.objective.get()

        def work() -> None:
            try:
                self._queue.put(("ok", solve(problem, "cpsat", max_slots, objective, limit)))
            except Exception as exc:  # an GUI weiterreichen
                self._queue.put(("err", exc))

        threading.Thread(target=work, daemon=True).start()
        self.after(100, self._poll)

    def _poll(self) -> None:
        try:
            kind, payload = self._queue.get_nowait()
        except queue.Empty:
            self.after(100, self._poll)
            return
        self._busy = False
        self.progress.stop()
        self.solve_msg.configure(text="")
        if kind == "err":
            self.show_step(2)
            messagebox.showerror("Berechnung fehlgeschlagen", str(payload))
            return
        self.schedule = payload
        self.show_step(3)

    # ---------- Schritt 4: Ergebnis ----------
    def _page_result(self) -> ttk.Frame:
        f = ttk.Frame(self.body)
        ttk.Label(f, text="Ergebnis", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        self.kpi = ttk.Label(f, text="", foreground="gray")
        self.kpi.pack(anchor="w", pady=(2, 12))
        self.res_pane = ttk.Frame(f)
        self.res_pane.pack(fill="both", expand=True)
        return f

    def _refresh_result(self) -> None:
        for w in self.res_pane.winfo_children():
            w.destroy()
        s = self.schedule
        if s is None:
            return
        m = s.metrics
        self.kpi.configure(
            text=f"{m.num_slots} Slots · {m.unhappy} Lehrer mit verpassten Konferenzen · "
                 f"{m.missed} verpasste Termine · {m.gaps} Leerlauf-Slots · {s.status}"
        )
        self.res_pane.columnconfigure(0, weight=2, uniform="r")
        self.res_pane.columnconfigure(1, weight=3, uniform="r")
        self.res_pane.rowconfigure(0, weight=1)
        left = ttk.Frame(self.res_pane)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        slot_tree = self._make_tree(left, ("slot", "faecher"), ("Slot", "Fächer (parallel)"), (60, 300))
        for i, evs in enumerate(s.slots, 1):
            slot_tree.insert("", "end", values=(i, ", ".join(evs)))
        right = ttk.Frame(self.res_pane)
        right.grid(row=0, column=1, sticky="nsew")
        n = len(s.slots)
        cols = ("name", *[f"s{i}" for i in range(n)], "gap", "miss")
        heads = ("Lehrer", *[f"Slot {i + 1}" for i in range(n)], "Leerlauf", "Verpasst")
        tree = self._make_tree(right, cols, heads, (140, *[90] * n, 70, 120))
        tree.tag_configure("missed", foreground=ERR)
        for r in s.reports:
            cells = ["/".join(r.slots.get(i, [])) or "–" for i in range(n)]
            tree.insert("", "end", values=(r.name, *cells, r.gaps, ", ".join(r.missed)),
                        tags=("missed",) if r.missed else ())

    def do_export(self) -> None:
        if not self.schedule:
            return
        path = filedialog.asksaveasfilename(
            title="Ergebnis speichern", defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("JSON", "*.json")],
        )
        if not path:
            return
        try:
            export(self.schedule, path)
        except OSError as exc:
            messagebox.showerror("Fehler beim Speichern", str(exc))
            return
        self.status.configure(text=f"Gespeichert: {path}")


def main() -> int:
    App().mainloop()
    return 0
