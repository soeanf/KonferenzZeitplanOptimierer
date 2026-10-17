"""Schlichte, mehrstufige GUI (tkinter + sv-ttk) fuer den Konferenzzeitplan-Optimierer."""
from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ..adapters.teacher_subjects import PRESETS, problem_from_teachers, read_teachers
from ..cli import export, solve
from ..core.model import Labels, Schedule

try:
    import sv_ttk
except ImportError:  # optional: ohne Theme default-Look
    sv_ttk = None

STEPS = ["1  Daten laden", "2  Daten prüfen", "3  Berechnen", "4  Ergebnis"]
ERR = "#c42b1c"
ASSETS = Path(__file__).parent / "assets"
PRESET_TITLES = {
    "fach": "Fachkonferenzen – Lehrkräfte eines Fachs",
    "klasse": "Klassenkonferenzen – Lehrkräfte einer Klasse, eines Jahrgangs oder Kurses",
}
ITEM_MIN_WIDTH = 110


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Konferenzzeitplan-Optimierer")
        self.geometry("1100x720")
        self.minsize(900, 600)
        self._set_icon()
        if sv_ttk:
            sv_ttk.set_theme("light")
        self.option_add("*Font", ("Segoe UI", 10))

        self.teachers: dict[str, list[str]] = {}
        self.disabled: set[tuple[str, str]] = set()  # (Lehrer, Eintrag)
        self.excluded: set[str] = set()  # komplett ausgenommene Lehrer
        self.preset_var = tk.StringVar(value=PRESET_TITLES["fach"])
        self.schedule: Schedule | None = None
        self.path = ""
        self.step = 0
        self._queue: queue.Queue = queue.Queue()
        self._busy = False

        self._build_chrome()
        self._pages = [self._page_load(), self._page_review(), self._page_solve(), self._page_result()]
        self._apply_labels()
        self.show_step(0)

    def _set_icon(self) -> None:
        try:
            if sys.platform == "win32":
                self.iconbitmap(default=str(ASSETS / "icon.ico"))
            else:
                self._icon = tk.PhotoImage(file=str(ASSETS / "icon.png"))
                self.iconphoto(True, self._icon)
        except tk.TclError:
            pass  # fehlendes Icon darf den Start nicht verhindern

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
    @property
    def labels(self) -> Labels:
        for key, title in PRESET_TITLES.items():
            if title == self.preset_var.get():
                return PRESETS[key]
        return PRESETS["fach"]

    def _page_load(self) -> ttk.Frame:
        f = ttk.Frame(self.body)
        box = ttk.Frame(f)
        box.place(relx=0.5, rely=0.4, anchor="center")
        ttk.Label(box, text="Kollegiumsliste laden", font=("Segoe UI", 20, "bold")).pack()
        self.load_hint = ttk.Label(box, text="", foreground="gray", justify="center")
        self.load_hint.pack(pady=(6, 20))

        kind = ttk.Frame(box)
        kind.pack(pady=(0, 20))
        ttk.Label(kind, text="Art der Konferenzen:").pack(side="left", padx=(0, 10))
        combo = ttk.Combobox(kind, textvariable=self.preset_var, state="readonly", width=64,
                             values=list(PRESET_TITLES.values()))
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", lambda _e: self._on_preset_changed())

        ttk.Button(box, text="CSV-Datei auswählen…", style="Accent.TButton", command=self.load_csv).pack()
        self.load_info = ttk.Label(box, text="", justify="center")
        self.load_info.pack(pady=20)
        return f

    def _apply_labels(self) -> None:
        """Passt alle Beschriftungen an die gewaehlte Konferenzart an."""
        lb = self.labels
        self.load_hint.configure(
            text=f"CSV mit den Spalten  Name, {lb.event} 1, {lb.event} 2, …\n"
                 "(eine Zeile je Lehrkraft, beliebig viele Spalten)"
        )
        self.review_hint.configure(
            text=f"Per Klick auf ✓ bzw. ✗ Lehrer*innen oder einzelne {lb.event_plural} ausnehmen – "
                 "ausgenommene Einträge werden nicht berücksichtigt."
        )
        self.s_title.configure(text=f"{lb.event_plural} im Überblick")
        self.slot_head = f"{lb.event_plural} (parallel)"
        self._configure_teacher_columns()
        if self.teachers:
            self._show_load_info()
            self._refresh_review()

    def _on_preset_changed(self) -> None:
        self.schedule = None
        self._apply_labels()
        self.show_step(self.step)

    def _show_load_info(self) -> None:
        lb = self.labels
        items = {s for v in self.teachers.values() for s in v}
        self.load_info.configure(
            text=f"{self.path}\n{len(self.teachers)} Lehrer*innen · {len(items)} {lb.event_plural}"
        )

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
            messagebox.showwarning("Keine Daten", "Die Datei enthält keine Lehrer*innen.")
            return
        self.teachers, self.path = teachers, path
        self.disabled.clear()
        self.excluded.clear()
        self.schedule = None
        self._apply_labels()
        self.show_step(1)

    # ---------- Schritt 2: Pruefen ----------
    def _page_review(self) -> ttk.Frame:
        f = ttk.Frame(self.body)
        ttk.Label(f, text="Daten prüfen", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        self.review_hint = ttk.Label(f, text="", foreground="gray")
        self.review_hint.pack(anchor="w", pady=(2, 12))

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
        self.t_tree = self._make_tree(left, ("chk", "name"), ("", "Lehrer*in"), (36, 170), hscroll=True)
        self.t_tree.tag_configure("changed", foreground="#9a6700")
        self.t_tree.tag_configure("excluded", foreground="#9a9a9a")
        self.t_tree.bind("<Button-1>", self._on_tree_click, add="+")
        self.t_tree.bind("<space>", self._on_space)
        self._n_items = 1

        bulk = ttk.Frame(left)
        bulk.pack(fill="x", pady=(8, 0), before=self.t_tree.master)
        ttk.Label(bulk, text="Lehrer*innen auswählen:").pack(side="left", padx=(0, 10))
        ttk.Button(bulk, text="Alle", command=lambda: self._set_visible(True)).pack(side="left")
        ttk.Button(bulk, text="Keine", command=lambda: self._set_visible(False)).pack(side="left", padx=6)
        ttk.Button(bulk, text="Umkehren", command=self._invert_visible).pack(side="left")

        right = ttk.Frame(main)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)
        self.s_title = ttk.Label(right, text="", font=("Segoe UI", 11, "bold"))
        self.s_title.grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.s_tree = self._make_tree(right, ("fach", "n"), ("", "Teilnehmer"), (150, 80), parent_grid=(1, 0))
        self._s_sort = ("fach", False)  # (Spalte, absteigend)
        for col in ("fach", "n"):
            self.s_tree.heading(col, command=lambda c=col: self._sort_subjects(c))
        self.summary = ttk.Label(f, text="", foreground="gray")
        self.summary.pack(anchor="w", pady=(10, 0))
        return f

    def _make_tree(self, parent, cols, heads, widths, parent_grid=None, hscroll=False) -> ttk.Treeview:
        wrap = ttk.Frame(parent)
        if parent_grid:
            wrap.grid(row=parent_grid[0], column=parent_grid[1], sticky="nsew")
        else:
            wrap.pack(fill="both", expand=True)
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="browse")
        for c, h, w in zip(cols, heads, widths):
            tree.heading(c, text=h)
            tree.column(c, width=w, anchor="w", stretch=True)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        if hscroll:
            hsb = ttk.Scrollbar(wrap, orient="horizontal", command=tree.xview)

            def on_xscroll(lo, hi):  # Leiste nur bei Bedarf zeigen
                if float(lo) <= 0 and float(hi) >= 1:
                    hsb.grid_remove()
                else:
                    hsb.grid(row=1, column=0, sticky="ew")
                hsb.set(lo, hi)

            tree.configure(xscrollcommand=on_xscroll)
        return tree

    def _configure_teacher_columns(self) -> None:
        """Eine Spalte je Eintrag; so viele, wie eine Lehrkraft maximal hat."""
        lb = self.labels
        n = max((len(v) for v in self.teachers.values()), default=1) or 1
        self._n_items = n
        cols = ("chk", "name", *[f"i{k}" for k in range(n)])
        t = self.t_tree
        t.configure(columns=cols, displaycolumns=cols)
        t.heading("chk", text="")
        t.column("chk", width=36, minwidth=36, stretch=False, anchor="center")
        t.heading("name", text="Lehrer*in")
        t.column("name", width=170, minwidth=120, stretch=False, anchor="w")
        for k in range(n):
            t.heading(f"i{k}", text=f"{lb.event} {k + 1}")
            t.column(f"i{k}", width=ITEM_MIN_WIDTH + 10, minwidth=ITEM_MIN_WIDTH, stretch=True, anchor="w")

    def _row_values(self, name: str) -> tuple[tuple, tuple]:
        subjects = self.teachers[name]
        cells = [("✗ " if (name, s) in self.disabled else "✓ ") + s for s in subjects]
        cells += [""] * (self._n_items - len(cells))
        tags = []
        if name in self.excluded:
            tags.append("excluded")
        elif any((name, s) in self.disabled for s in subjects):
            tags.append("changed")
        return ("✗" if name in self.excluded else "✓", name, *cells), tuple(tags)

    def _update_row(self, name: str) -> None:
        if self.t_tree.exists(name):
            values, tags = self._row_values(name)
            self.t_tree.item(name, values=values, tags=tags)

    def _refresh_review(self) -> None:
        query = self.search.get().strip().casefold()
        self.t_tree.delete(*self.t_tree.get_children())
        for name, subjects in self.teachers.items():
            if query and query not in name.casefold() and not any(query in s.casefold() for s in subjects):
                continue
            values, tags = self._row_values(name)
            self.t_tree.insert("", "end", iid=name, values=values, tags=tags)
        self._refresh_subjects()

    def _sort_subjects(self, col: str) -> None:
        col_now, desc = self._s_sort
        if col == col_now:
            desc = not desc
        else:
            desc = col == "n"  # Teilnehmerzahl zuerst absteigend, Fachname aufsteigend
        self._s_sort = (col, desc)
        self._refresh_subjects()

    def _refresh_subjects(self) -> None:
        lb = self.labels
        active = self._active_teachers()
        problem = problem_from_teachers(active, lb)
        col, desc = self._s_sort
        rows = sorted(
            ((fach, len(members)) for fach, members in problem.events.items()),
            key=lambda r: r[0].casefold(),
        )
        if col == "n":
            rows.sort(key=lambda r: r[1], reverse=desc)  # stabil: Gleichstand bleibt alphabetisch
        elif desc:
            rows.reverse()
        self.s_tree.delete(*self.s_tree.get_children())
        for row in rows:
            self.s_tree.insert("", "end", values=row)
        for c, title in (("fach", lb.event), ("n", "Teilnehmer")):
            arrow = (" ▼" if desc else " ▲") if c == col else ""
            self.s_tree.heading(c, text=title + arrow)
        entries = sum(len(v) for v in active.values())
        n_active = len(self.teachers) - len(self.excluded)
        self.summary.configure(
            text=f"{n_active} von {len(self.teachers)} Lehrer*innen aktiv · {len(problem.events)} {lb.event_plural} · {entries} Teilnahmen"
            + (f" · {len(self.disabled)} Einträge abgewählt" if self.disabled else "")
        )

    def _on_tree_click(self, event) -> None:
        if self.t_tree.identify_region(event.x, event.y) != "cell":
            return
        row = self.t_tree.identify_row(event.y)
        col = int(self.t_tree.identify_column(event.x)[1:])
        if not row:
            return
        if col == 1:
            self._toggle_teacher(row)
        elif col >= 3 and col - 3 < len(self.teachers[row]):
            self._toggle_subject(row, self.teachers[row][col - 3])

    def _on_space(self, _event=None) -> str:
        for name in self.t_tree.selection():
            self._toggle_teacher(name)
        return "break"

    def _toggle_teacher(self, name: str) -> None:
        self.excluded.symmetric_difference_update({name})
        self._teachers_changed([name])

    def _set_visible(self, include: bool) -> None:
        names = list(self.t_tree.get_children())
        if include:
            self.excluded.difference_update(names)
        else:
            self.excluded.update(names)
        self._teachers_changed(names)

    def _invert_visible(self) -> None:
        names = list(self.t_tree.get_children())
        self.excluded.symmetric_difference_update(names)
        self._teachers_changed(names)

    def _teachers_changed(self, names: list[str]) -> None:
        self.schedule = None
        for name in names:
            self._update_row(name)
        self._refresh_subjects()

    def _toggle_subject(self, name: str, subject: str) -> None:
        self.disabled.symmetric_difference_update({(name, subject)})
        self.schedule = None
        self._update_row(name)
        self._refresh_subjects()

    def _active_teachers(self) -> dict[str, list[str]]:
        return {
            n: [s for s in subs if (n, s) not in self.disabled]
            for n, subs in self.teachers.items()
            if n not in self.excluded
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

        self.use_parallel = tk.BooleanVar(value=False)
        self.max_parallel = tk.IntVar(value=3)
        row = ttk.Frame(form)
        row.pack(anchor="w", pady=6)
        ttk.Checkbutton(row, text="Höchstens so viele Konferenzen gleichzeitig:",
                        variable=self.use_parallel, command=self._parallel_toggled).pack(side="left")
        self.parallel_spin = ttk.Spinbox(row, from_=1, to=200, textvariable=self.max_parallel, width=5,
                                         state="disabled")
        self.parallel_spin.pack(side="left", padx=10)
        ttk.Label(
            form,
            text="Ohne Haken finden beliebig viele Konferenzen gleichzeitig statt. Eine Begrenzung ist sinnvoll,\n"
                 "wenn z. B. nur eine bestimmte Zahl an Räumen oder Moderator*innen zur Verfügung steht.",
            foreground="gray",
            justify="left",
        ).pack(anchor="w", pady=(0, 4))

        self.objective = tk.StringVar(value="teilnehmer")
        ttk.Label(form, text="Falls die Obergrenze nicht reicht, minimiere …").pack(anchor="w", pady=(16, 4))
        ttk.Radiobutton(form, text="die Anzahl der Lehrer*innen, die Konferenzen verpassen",
                        variable=self.objective, value="teilnehmer").pack(anchor="w", pady=2)
        ttk.Radiobutton(form, text="die Gesamtzahl der verpassten Konferenzen",
                        variable=self.objective, value="verpasst").pack(anchor="w", pady=2)

        row = ttk.Frame(form)
        row.pack(anchor="w", pady=(16, 0))
        ttk.Label(row, text="Zeitlimit (Sekunden):").pack(side="left")
        self.time_limit = tk.IntVar(value=180)
        ttk.Spinbox(row, from_=1, to=3600, textvariable=self.time_limit, width=6).pack(side="left", padx=10)
        ttk.Label(
            form,
            text=(
                "Maximale Rechenzeit. Meist ist der beste Plan nach wenigen Sekunden gefunden. Das Limit greift\n"
                "nur bei sehr großen Datensätzen, bei denen der Nachweis, dass es nicht besser geht,\n"
                "lange dauern kann. Wird es erreicht, erhältst du den besten bis dahin gefundenen, gültigen Plan."
            ),
            foreground="gray",
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        self.progress = ttk.Progressbar(f, mode="indeterminate", length=360)
        self.solve_msg = ttk.Label(f, text="", foreground="gray")
        self.solve_msg.pack(anchor="w", pady=(20, 8))
        return f

    def _limit_toggled(self) -> None:
        self.limit_spin.configure(state="normal" if self.use_limit.get() else "disabled")

    def _parallel_toggled(self) -> None:
        self.parallel_spin.configure(state="normal" if self.use_parallel.get() else "disabled")

    def start_solve(self) -> None:
        try:
            max_slots = int(self.max_slots.get()) if self.use_limit.get() else None
            max_parallel = int(self.max_parallel.get()) if self.use_parallel.get() else None
            limit = float(self.time_limit.get())
        except (tk.TclError, ValueError):
            messagebox.showerror("Eingabe", "Bitte gültige Zahlen eingeben.")
            return
        if (max_slots is not None and max_slots < 1) or (max_parallel is not None and max_parallel < 1) or limit < 1:
            messagebox.showerror("Eingabe", "Werte müssen mindestens 1 sein.")
            return
        lb = self.labels
        problem = problem_from_teachers(self._active_teachers(), lb)
        if not problem.events:
            messagebox.showwarning(f"Keine {lb.event_plural}", f"Es sind keine {lb.event_plural} ausgewählt.")
            return
        self._busy = True
        self.show_step(2)
        self.progress.pack(anchor="w", before=self.solve_msg)
        self.progress.start(12)
        self.solve_msg.configure(text="Berechne optimalen Plan …")
        objective = self.objective.get()

        def work() -> None:
            try:
                self._queue.put(("ok", solve(problem, "cpsat", max_slots, objective, limit, max_parallel)))
            except ValueError as exc:  # Einstellungen passen nicht zusammen
                self._queue.put(("invalid", exc))
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
        self.progress.pack_forget()
        self.solve_msg.configure(text="")
        if kind != "ok":
            self.show_step(2)
            title = "Einstellungen prüfen" if kind == "invalid" else "Berechnung fehlgeschlagen"
            messagebox.showerror(title, str(payload))
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
            text=f"{m.num_slots} Slots · {m.unhappy} Lehrer*innen mit verpassten Konferenzen · "
                 f"{m.missed} verpasste Termine · {m.gaps} Leerlauf-Slots · {s.status}"
        )
        self.res_pane.columnconfigure(0, weight=2, uniform="r")
        self.res_pane.columnconfigure(1, weight=3, uniform="r")
        self.res_pane.rowconfigure(0, weight=1)
        left = ttk.Frame(self.res_pane)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        slot_tree = self._make_tree(left, ("slot", "faecher"), ("Slot", self.slot_head), (60, 300))
        for i, evs in enumerate(s.slots, 1):
            slot_tree.insert("", "end", values=(i, ", ".join(evs)))
        right = ttk.Frame(self.res_pane)
        right.grid(row=0, column=1, sticky="nsew")
        n = len(s.slots)
        cols = ("name", *[f"s{i}" for i in range(n)], "gap", "miss")
        heads = ("Lehrer*in", *[f"Slot {i + 1}" for i in range(n)], "Leerlauf", "Verpasst")
        tree = self._make_tree(right, cols, heads, (140, *[90] * n, 70, 120), hscroll=True)
        tree.column("name", minwidth=120, stretch=False)
        for i in range(n):
            tree.column(f"s{i}", minwidth=90)
        tree.column("gap", minwidth=70)
        tree.column("miss", minwidth=100)
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
