"""Abbruch bzw. vorzeitiges Beenden laufender Berechnungen (threadsicher).

- cancel(): Berechnung verwerfen (die Solver werfen Cancelled).
- stop():   Berechnung beenden und den bis dahin besten Plan zurueckgeben.
"""
from __future__ import annotations

import threading


class Cancelled(Exception):
    """Die Berechnung wurde vom Benutzer abgebrochen."""


class CancelToken:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cancelled = False
        self._stopped = False
        self._solver = None

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    @property
    def stop_requested(self) -> bool:
        return self._stopped

    def cancel(self) -> None:
        """Von einem beliebigen Thread aufrufbar; stoppt auch einen laufenden CP-SAT-Solver."""
        with self._lock:
            self._cancelled = True
            if self._solver is not None:
                self._solver.stop_search()

    def stop(self) -> None:
        """Beendet die Suche vorzeitig; der bis dahin beste Plan bleibt erhalten."""
        with self._lock:
            self._stopped = True
            if self._solver is not None:
                self._solver.stop_search()

    def raise_if_cancelled(self) -> None:
        if self._cancelled:
            raise Cancelled()

    def attach(self, solver) -> None:
        with self._lock:
            self._solver = solver
            if self._cancelled or self._stopped:
                solver.stop_search()

    def detach(self) -> None:
        with self._lock:
            self._solver = None
