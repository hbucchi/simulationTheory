"""Local web server for the simulation (standard library only).

    python3 server.py            # http://localhost:8000
    python3 server.py --port 9000 --agents 5 --seed 42

API
    GET  /api/state                 current world state
    POST /api/step   {"steps": n}   advance n ticks (default 1)
    POST /api/reset  {"agents": n, "seed": s}  rebuild the world
    POST /api/agents {"inventory": {...}, "money": m, "production": {...}, "movement": n}
                                    add one agent (any field omitted = default)
"""

import argparse
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from simulation import World
from simulation.economy import RESOURCES

STATIC_DIR = Path(__file__).parent / "static"
MAX_STEPS_PER_REQUEST = 1000
MAX_AGENTS = 500
MAX_MOVEMENT = 200


class Simulation:
    """Holds the single shared World and serialises access to it."""

    def __init__(self, agents, seed):
        self.lock = threading.Lock()
        self.reset(agents, seed)

    def reset(self, agents, seed):
        world = World(seed=seed)
        world.spawn_random_agents(agents)
        with self.lock:
            self.world = world
            return world.to_dict()

    def step(self, steps):
        with self.lock:
            for _ in range(steps):
                self.world.step()
            return self.world.to_dict()

    def add_agent(self, config):
        with self.lock:
            if len(self.world.agents) >= MAX_AGENTS:
                raise ValueError(f"at most {MAX_AGENTS} agents")
            self.world.create_agent(**config)
            return self.world.to_dict()

    def state(self):
        with self.lock:
            return self.world.to_dict()


def _non_negative_int(value, field):
    if isinstance(value, bool) or int(value) != float(value) or int(value) < 0:
        raise ValueError(f"{field} must be a whole number >= 0")
    return int(value)


def parse_agent_config(body):
    """Validate the JSON body of POST /api/agents into World.create_agent kwargs."""
    config = {}
    for key in ("inventory", "production"):
        values = body.get(key) or {}
        if not isinstance(values, dict) or set(values) - set(RESOURCES):
            raise ValueError(f"{key} must map {', '.join(RESOURCES)} to numbers")
        config[key] = {r: _non_negative_int(v, f"{key}.{r}") for r, v in values.items()}
    if body.get("money") is not None:
        money = float(body["money"])
        if not money >= 0:
            raise ValueError("money must be >= 0")
        config["money"] = money
    if body.get("movement") is not None:
        movement = _non_negative_int(body["movement"], "movement")
        if not 1 <= movement <= MAX_MOVEMENT:
            raise ValueError(f"movement must be between 1 and {MAX_MOVEMENT}")
        config["movement"] = movement
    return config


class Handler(SimpleHTTPRequestHandler):
    sim = None  # set in main()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self):
        if self.path == "/api/state":
            return self._json(self.sim.state())
        return super().do_GET()

    def do_POST(self):
        try:
            body = self._read_json()
            if self.path == "/api/step":
                steps = int(body.get("steps", 1))
                if not 1 <= steps <= MAX_STEPS_PER_REQUEST:
                    raise ValueError(f"steps must be between 1 and {MAX_STEPS_PER_REQUEST}")
                return self._json(self.sim.step(steps))
            if self.path == "/api/reset":
                agents = int(body.get("agents", 3))
                if not 1 <= agents <= MAX_AGENTS:
                    raise ValueError(f"agents must be between 1 and {MAX_AGENTS}")
                seed = body.get("seed")
                seed = None if seed in (None, "") else int(seed)
                return self._json(self.sim.reset(agents, seed))
            if self.path == "/api/agents":
                return self._json(self.sim.add_agent(parse_agent_config(body)))
        except (ValueError, TypeError) as exc:
            return self._json({"error": str(exc)}, status=400)
        self._json({"error": "not found"}, status=404)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        data = json.loads(self.rfile.read(length))
        if not isinstance(data, dict):
            raise ValueError("body must be a JSON object")
        return data

    def _json(self, payload, status=200):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        if not self.path.startswith("/api/"):
            super().log_message(fmt, *args)


def main():
    parser = argparse.ArgumentParser(description="Run the agent simulation server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--agents", type=int, default=3)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    Handler.sim = Simulation(args.agents, args.seed)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Simulation running at http://{args.host}:{args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
