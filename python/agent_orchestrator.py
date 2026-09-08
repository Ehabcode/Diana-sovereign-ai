"""Local Diana Agent Orchestrator.

The orchestrator is intentionally small and dependency-light. It owns task
state, a worker per task, a low-frequency scheduler, and optional persistence.
The actual work is injected by the Flask server so the module remains testable.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event, RLock, Thread
from typing import Any, Callable
import json
import re
import time
import uuid


Executor = Callable[[dict[str, Any], Callable[..., None], Callable[[], bool]], str | dict[str, Any]]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def safe_text(value: Any, limit: int = 12000) -> str:
    return str(value or "").strip()[:limit]


def next_daily_run(time_text: str, now: datetime | None = None) -> str:
    now = now or utc_now()
    try:
        hour, minute = [int(part) for part in str(time_text or "09:00").split(":", 1)]
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    except (TypeError, ValueError):
        candidate = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate.isoformat()


class AgentOrchestrator:
    def __init__(self, data_dir: Path, executor: Executor):
        self.data_dir = Path(data_dir)
        self.executor = executor
        self.tasks_file = self.data_dir / "agent_tasks.json"
        self.schedules_file = self.data_dir / "agent_schedules.json"
        self.knowledge_file = self.data_dir / "agent_knowledge.json"
        self.lock = RLock()
        self.tasks: dict[str, dict[str, Any]] = {}
        self.schedules: dict[str, dict[str, Any]] = {}
        self.cancel_events: dict[str, Event] = {}
        self.scheduler_stop = Event()
        self._load()
        self.scheduler_thread = Thread(target=self._scheduler_loop, name="diana-agent-scheduler", daemon=True)
        self.scheduler_thread.start()

    def _load(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        try:
            payload = json.loads(self.tasks_file.read_text(encoding="utf-8"))
            for task in payload if isinstance(payload, list) else []:
                if isinstance(task, dict) and task.get("id"):
                    task["status"] = "interrupted" if task.get("status") in {"queued", "running"} else task.get("status", "done")
                    self.tasks[str(task["id"])] = task
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            self.tasks = {}
        try:
            payload = json.loads(self.schedules_file.read_text(encoding="utf-8"))
            for schedule in payload if isinstance(payload, list) else []:
                if isinstance(schedule, dict) and schedule.get("id"):
                    self.schedules[str(schedule["id"])] = schedule
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            self.schedules = {}

    def _persist_tasks(self) -> None:
        visible = sorted(self.tasks.values(), key=lambda item: item.get("created_at", ""), reverse=True)[:80]
        self.tasks_file.write_text(json.dumps(visible, ensure_ascii=False, indent=2), encoding="utf-8")

    def _persist_schedules(self) -> None:
        self.schedules_file.write_text(json.dumps(list(self.schedules.values()), ensure_ascii=False, indent=2), encoding="utf-8")

    def _save_knowledge_note(self, task: dict[str, Any], result: str) -> None:
        try:
            existing = json.loads(self.knowledge_file.read_text(encoding="utf-8")) if self.knowledge_file.exists() else []
            if not isinstance(existing, list):
                existing = []
            existing.append({
                "id": f"note-{uuid.uuid4().hex[:10]}",
                "title": safe_text(task.get("command"), 140),
                "content": safe_text(result, 30000),
                "mode": "knowledge",
                "created_at": iso_now(),
            })
            self.knowledge_file.write_text(json.dumps(existing[-100:], ensure_ascii=False, indent=2), encoding="utf-8")
        except (OSError, json.JSONDecodeError):
            pass

    def list_knowledge(self, limit: int = 20) -> list[dict[str, Any]]:
        try:
            notes = json.loads(self.knowledge_file.read_text(encoding="utf-8")) if self.knowledge_file.exists() else []
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            notes = []
        return notes[-max(1, min(limit, 100)):][::-1] if isinstance(notes, list) else []

    def _public_task(self, task: dict[str, Any]) -> dict[str, Any]:
        # Private task results are still available to the active UI process, but
        # never written to disk by _persist_tasks.
        return {key: value for key, value in task.items() if key != "_cancel_event"}

    def list_tasks(self, limit: int = 12) -> list[dict[str, Any]]:
        with self.lock:
            values = sorted(self.tasks.values(), key=lambda item: item.get("updated_at", ""), reverse=True)[: max(1, min(limit, 50))]
            return [self._public_task(item) for item in values]

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self.lock:
            task = self.tasks.get(str(task_id))
            return self._public_task(task) if task else None

    def _emit(self, task_id: str, *, message: str | None = None, step: str | None = None, progress: int | None = None, status: str | None = None) -> None:
        with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                return
            if message:
                task.setdefault("events", []).append({"at": iso_now(), "message": safe_text(message, 500)})
                task["events"] = task["events"][-40:]
            if step is not None:
                task["step"] = safe_text(step, 120)
            if progress is not None:
                task["progress"] = max(0, min(100, int(progress)))
            if status is not None:
                task["status"] = status
            task["updated_at"] = iso_now()
            if not task.get("private"):
                try:
                    self._persist_tasks()
                except OSError:
                    pass

    def create_task(self, command: str, persona: str = "texty", mode: str = "auto", private: bool = False, source: str = "chat") -> dict[str, Any]:
        command = safe_text(command, 8000)
        if not command:
            raise ValueError("empty agent command")
        task_id = f"agent-{uuid.uuid4().hex[:12]}"
        cancel_event = Event()
        task: dict[str, Any] = {
            "id": task_id,
            "command": command,
            "persona": persona if persona in {"texty", "coding"} else "texty",
            "mode": mode if mode in {"auto", "local", "research", "knowledge"} else "auto",
            "private": bool(private),
            "source": source,
            "status": "queued",
            "step": "QUEUED",
            "progress": 0,
            "events": [{"at": iso_now(), "message": "Task accepted by local orchestrator"}],
            "result": "",
            "error": "",
            "created_at": iso_now(),
            "updated_at": iso_now(),
        }
        with self.lock:
            self.tasks[task_id] = task
            self.cancel_events[task_id] = cancel_event
            if not private:
                self._persist_tasks()
        Thread(target=self._run_task, args=(task_id,), name=f"diana-agent-{task_id}", daemon=True).start()
        return self._public_task(task)

    def _run_task(self, task_id: str) -> None:
        with self.lock:
            task = self.tasks.get(task_id)
            cancel_event = self.cancel_events.get(task_id)
        if not task or not cancel_event:
            return
        self._emit(task_id, status="running", step="PLANNER", progress=8, message="Planner is breaking the request into safe steps")
        try:
            result = self.executor(task, lambda **kwargs: self._emit(task_id, **kwargs), cancel_event.is_set)
            if cancel_event.is_set():
                self._emit(task_id, status="cancelled", step="CANCELLED", progress=100, message="Task cancelled")
            else:
                if isinstance(result, dict):
                    text = safe_text(result.get("result", ""), 30000)
                    extras = {key: value for key, value in result.items() if key != "result"}
                else:
                    text = safe_text(result, 30000)
                    extras = {}
                with self.lock:
                    task = self.tasks.get(task_id)
                    if task:
                        task["result"] = text
                        task.update(extras)
                        if task.get("mode") == "knowledge" and not task.get("private"):
                            self._save_knowledge_note(task, text)
                self._emit(task_id, status="done", step="COMPLETE", progress=100, message="Task completed locally")
        except Exception as exc:  # The UI should receive a readable failure, never a dead worker.
            self._emit(task_id, status="error", step="ERROR", progress=100, message=f"Agent error: {exc}")
            with self.lock:
                if task_id in self.tasks:
                    self.tasks[task_id]["error"] = safe_text(exc, 2000)
        finally:
            with self.lock:
                self.cancel_events.pop(task_id, None)
                task = self.tasks.get(task_id)
                if task and not task.get("private"):
                    try:
                        self._persist_tasks()
                    except OSError:
                        pass

    def cancel_task(self, task_id: str) -> bool:
        with self.lock:
            event = self.cancel_events.get(str(task_id))
            if not event:
                return False
            event.set()
            return True

    def list_schedules(self) -> list[dict[str, Any]]:
        with self.lock:
            return sorted(self.schedules.values(), key=lambda item: item.get("created_at", ""), reverse=True)

    def create_schedule(self, name: str, command: str, frequency: str = "daily", time_text: str = "09:00", interval_minutes: int = 1440, persona: str = "texty", mode: str = "auto") -> dict[str, Any]:
        schedule_id = f"schedule-{uuid.uuid4().hex[:10]}"
        now = utc_now()
        frequency = frequency if frequency in {"daily", "interval"} else "daily"
        try:
            interval_minutes = max(5, min(int(interval_minutes), 7 * 24 * 60))
        except (TypeError, ValueError):
            interval_minutes = 1440
        next_run = next_daily_run(time_text, now) if frequency == "daily" else (now + timedelta(minutes=interval_minutes)).isoformat()
        schedule = {
            "id": schedule_id,
            "name": safe_text(name, 80) or "DIANA ROUTINE",
            "command": safe_text(command, 2000),
            "frequency": frequency,
            "time": time_text if frequency == "daily" else "",
            "interval_minutes": interval_minutes,
            "persona": persona if persona in {"texty", "coding"} else "texty",
            "mode": mode if mode in {"auto", "local", "research", "knowledge"} else "auto",
            "enabled": True,
            "next_run_at": next_run,
            "last_run_at": None,
            "created_at": iso_now(),
        }
        with self.lock:
            self.schedules[schedule_id] = schedule
            self._persist_schedules()
        return schedule

    def toggle_schedule(self, schedule_id: str, enabled: bool) -> dict[str, Any] | None:
        with self.lock:
            schedule = self.schedules.get(str(schedule_id))
            if not schedule:
                return None
            schedule["enabled"] = bool(enabled)
            if schedule["enabled"] and not schedule.get("next_run_at"):
                schedule["next_run_at"] = next_daily_run(schedule.get("time", "09:00")) if schedule.get("frequency") == "daily" else (utc_now() + timedelta(minutes=int(schedule.get("interval_minutes", 1440)))).isoformat()
            self._persist_schedules()
            return schedule

    def delete_schedule(self, schedule_id: str) -> bool:
        with self.lock:
            existed = self.schedules.pop(str(schedule_id), None) is not None
            if existed:
                self._persist_schedules()
            return existed

    def _scheduler_loop(self) -> None:
        while not self.scheduler_stop.wait(20):
            now = utc_now()
            due: list[dict[str, Any]] = []
            with self.lock:
                for schedule in self.schedules.values():
                    if not schedule.get("enabled") or not schedule.get("next_run_at"):
                        continue
                    try:
                        due_at = datetime.fromisoformat(schedule["next_run_at"])
                    except (TypeError, ValueError):
                        due_at = now + timedelta(days=1)
                    if due_at <= now:
                        due.append(dict(schedule))
                for schedule in due:
                    frequency = schedule.get("frequency")
                    schedule_id = schedule["id"]
                    schedule["last_run_at"] = iso_now()
                    schedule["next_run_at"] = next_daily_run(schedule.get("time", "09:00"), now) if frequency == "daily" else (now + timedelta(minutes=int(schedule.get("interval_minutes", 1440)))).isoformat()
                if due:
                    self._persist_schedules()
            for schedule in due:
                try:
                    self.create_task(schedule["command"], schedule.get("persona", "texty"), schedule.get("mode", "auto"), False, "schedule")
                except ValueError:
                    pass

    def close(self) -> None:
        self.scheduler_stop.set()
