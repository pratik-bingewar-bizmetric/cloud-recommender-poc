#!/usr/bin/env python3
"""Databricks Apps Production Supervisor & Unified Gateway.

This script serves as the production entrypoint for deploying the Bizmetric FinOps
application inside Azure Databricks Apps.

Key Responsibilities:
1. Detects assigned $DATABRICKS_APP_PORT and binds the public server to 0.0.0.0.
2. Manages FastAPI backend (internal port) and Next.js frontend (public gateway).
3. Provides automatic fallback to FastAPI static hosting if Node.js runtime is absent.
4. Implements graceful shutdown (SIGTERM / SIGINT) and process lifecycle supervision.
5. Emits structured production logging.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.request import urlopen

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"


def log(event: str, **kwargs: Any) -> None:
    """Emit formatted operational log."""
    details = " ".join(f"{k}={v}" for k, v in kwargs.items())
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%SZ', time.gmtime())}] [databricks-app] {event} {details}".strip(), flush=True)


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a network port is responding."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def wait_for_health(url: str, timeout_seconds: float = 20.0, interval: float = 0.5) -> bool:
    """Poll a health URL until HTTP 200 is returned or timeout expires."""
    start = time.time()
    while time.time() - start < timeout_seconds:
        try:
            with urlopen(url, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def main() -> int:
    # 1. Parse Port & Bind Configuration
    # Databricks Apps assigns a dynamic port via DATABRICKS_APP_PORT
    app_port_str = os.environ.get("DATABRICKS_APP_PORT") or os.environ.get("PORT") or "8000"
    try:
        public_port = int(app_port_str)
    except ValueError:
        public_port = 8000

    # Internal port for FastAPI when Next.js acts as the public reverse proxy
    internal_backend_port = 8001 if public_port == 8000 else 8000

    log(
        "supervisor_initializing",
        public_port=public_port,
        internal_backend_port=internal_backend_port,
        python_version=sys.version.split()[0],
        cwd=str(ROOT_DIR),
    )

    # 2. Check Node.js runtime availability
    node_available = False
    try:
        node_res = subprocess.run(["node", "--version"], capture_output=True, text=True, check=False)
        if node_res.returncode == 0:
            node_available = True
            log("runtime_detected", node_version=node_res.stdout.strip())
    except FileNotFoundError:
        log("runtime_notice", detail="node binary not in PATH; will use Python static gateway if enabled")

    # Force standalone Python mode if specified or if Node is absent
    use_standalone_python = (
        os.environ.get("STANDALONE_PYTHON", "false").lower() in ("true", "1") or not node_available
    )

    processes: list[subprocess.Popen[Any]] = []

    def shutdown_handler(signum: int, _frame: Any) -> None:
        log("shutdown_signal_received", signal=signum)
        for p in processes:
            if p.poll() is None:
                try:
                    p.terminate()
                except Exception:
                    pass
        time.sleep(1.0)
        for p in processes:
            if p.poll() is None:
                try:
                    p.kill()
                except Exception:
                    pass
        sys.exit(0)

    # Register OS signals for graceful termination
    signal.signal(signal.SIGINT, shutdown_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, shutdown_handler)

    try:
        if not use_standalone_python:
            # ==============================================================
            # DUAL-PROCESS MODE: FastAPI (Internal) + Next.js (Public Gateway)
            # ==============================================================
            log(
                "starting_dual_process_architecture",
                backend_port=internal_backend_port,
                frontend_port=public_port,
            )

            # Start FastAPI backend bound to 127.0.0.1
            backend_env = os.environ.copy()
            backend_env["PYTHONPATH"] = str(BACKEND_DIR / "src")
            backend_env["API_PORT"] = str(internal_backend_port)
            backend_env["API_HOST"] = "127.0.0.1"

            backend_cmd = [
                sys.executable,
                "-m",
                "uvicorn",
                "cloud_recommender.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(internal_backend_port),
                "--log-level",
                "info",
            ]

            log("launching_backend", cmd=" ".join(backend_cmd))
            backend_proc = subprocess.Popen(backend_cmd, cwd=str(BACKEND_DIR), env=backend_env)
            processes.append(backend_proc)

            # Wait for backend health probe
            health_url = f"http://127.0.0.1:{internal_backend_port}/health"
            log("awaiting_backend_health", url=health_url)
            if not wait_for_health(health_url, timeout_seconds=25.0):
                log("backend_health_timeout", error="FastAPI failed to respond within 25 seconds")
                shutdown_handler(signal.SIGTERM, None)
                return 1

            log("backend_healthy", url=health_url)

            # Start Next.js frontend bound to 0.0.0.0:$DATABRICKS_APP_PORT
            frontend_env = os.environ.copy()
            frontend_env["PORT"] = str(public_port)
            frontend_env["HOSTNAME"] = "0.0.0.0"
            frontend_env["INTERNAL_BACKEND_URL"] = f"http://127.0.0.1:{internal_backend_port}"
            frontend_env["NODE_ENV"] = "production"

            # Check if production build exists; if not, build or run dev
            dot_next = FRONTEND_DIR / ".next"
            if not dot_next.exists():
                log("frontend_build_missing", action="running npm run build")
                build_res = subprocess.run(["npm", "run", "build"], cwd=str(FRONTEND_DIR), check=False)
                if build_res.returncode != 0:
                    log("frontend_build_failed", code=build_res.returncode)

            # Determine npm or node start command
            frontend_cmd = ["npx", "next", "start", "-p", str(public_port), "-H", "0.0.0.0"]
            log("launching_frontend_gateway", cmd=" ".join(frontend_cmd))
            frontend_proc = subprocess.Popen(
                frontend_cmd,
                cwd=str(FRONTEND_DIR),
                env=frontend_env,
                shell=(sys.platform == "win32"),
            )
            processes.append(frontend_proc)

            log("application_live", public_url=f"http://0.0.0.0:{public_port}")

            # Monitor child processes
            while True:
                time.sleep(1.0)
                for p in processes:
                    exit_code = p.poll()
                    if exit_code is not None:
                        log("child_process_exited", pid=p.pid, exit_code=exit_code)
                        shutdown_handler(signal.SIGTERM, None)
                        return exit_code

        else:
            # ==============================================================
            # STANDALONE PYTHON GATEWAY MODE
            # FastAPI directly binds to 0.0.0.0:$DATABRICKS_APP_PORT
            # ==============================================================
            log("starting_standalone_python_gateway", port=public_port)

            backend_env = os.environ.copy()
            backend_env["PYTHONPATH"] = str(BACKEND_DIR / "src")
            backend_env["API_PORT"] = str(public_port)
            backend_env["API_HOST"] = "0.0.0.0"

            backend_cmd = [
                sys.executable,
                "-m",
                "uvicorn",
                "cloud_recommender.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                str(public_port),
                "--log-level",
                "info",
            ]

            proc = subprocess.Popen(backend_cmd, cwd=str(BACKEND_DIR), env=backend_env)
            processes.append(proc)
            return proc.wait()

    except Exception as exc:
        log("supervisor_exception", error=str(exc))
        shutdown_handler(signal.SIGTERM, None)
        return 1


if __name__ == "__main__":
    sys.exit(main())

