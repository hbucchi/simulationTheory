"""Local web server for the simulation (standard library only).

    python3 server.py            # http://localhost:8000
    python3 server.py --port 9000 --agents 5 --seed 42

API
    GET    /api/state                 current world state
    POST   /api/step   {"steps": n}   advance n ticks (default 1)
    GET    /api/rules                 {"current": rules of this game, "factory": default rules}
    POST   /api/reset  {"rules": {...}, "agents": n, "seed": s}
                                      start a new game. Omitted rules keep the current game's
                                      rules; "agents" overrides rules.agents.
    POST   /api/agents      {...}     create an agent (any field omitted = default)
    POST   /api/agents/<id> {...}     edit an agent (only the fields sent change)
    DELETE /api/agents/<id>           remove an agent

Agent fields: name, x, y, movement, money,
              needs      {hunger, sleep, thirst, boredom: 0..1}   current levels
              rates      {hunger, sleep, thirst, boredom: 0..1}   growth per step
              inventory  {food, water, games: int >= 0}
              production {food, water, games: int >= 0}          1 unit every N steps
              assets     {food, water, games: int >= 0}          productive assets owned
              sleep_recovery  0..1                              sleep recovered per step at rest
"""

import argparse
import json
import re
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from simulation import World
from simulation.rules import Rules
from simulation.agent import NEED_NAMES
from simulation.economy import RESOURCES

STATIC_DIR = Path(__file__).parent / "static"
MAX_STEPS_PER_REQUEST = 1000
MAX_AGENTS = 500
MAX_MOVEMENT = 200
AGENT_PATH = re.compile(r"/api/agents/(\d+)")


class Simulation:
    """Holds the single shared World and serialises access to it."""

    def __init__(self, agents, seed):
        self.lock = threading.Lock()
        self.world = None
        self.reset(Rules.from_dict({"agents": agents}), seed)

    def reset(self, rules, seed):
        world = World(seed=seed, rules=rules)
        world.spawn_random_agents()
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

    def update_agent(self, agent_id, config):
        with self.lock:
            self.world.update_agent(self._get(agent_id), **config)
            return self.world.to_dict()

    def remove_agent(self, agent_id):
        with self.lock:
            self.world.remove_agent(self._get(agent_id))
            return self.world.to_dict()

    def _get(self, agent_id):
        agent = self.world.agent_by_id(agent_id)
        if agent is None:
            raise LookupError(f"no agent {agent_id}")
        return agent

    def rules(self):
        with self.lock:
            return self.world.rules.to_dict()

    def state(self):
        with self.lock:
            return self.world.to_dict()


def _number(value, field, low, high, whole=False):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a number")
    number = float(value)
    if not low <= number <= high:
        raise ValueError(f"{field} must be between {low:g} and {high:g}")
    if whole:
        if number != int(number):
            raise ValueError(f"{field} must be a whole number")
        return int(number)
    return number


def _number_map(body, key, names, low, high, whole=False):
    values = body.get(key)
    if values is None:
        return None
    if not isinstance(values, dict) or set(values) - set(names):
        raise ValueError(f"{key} must map {', '.join(names)} to numbers")
    return {n: _number(v, f"{key}.{n}", low, high, whole) for n, v in values.items()}


def parse_agent_config(body):
    """Validate a create/edit JSON body into World.create_agent / update_agent kwargs."""
    world_size = 1024
    config = {
        "needs": _number_map(body, "needs", NEED_NAMES, 0, 1),
        "rates": _number_map(body, "rates", NEED_NAMES, 0, 1),
        "inventory": _number_map(body, "inventory", RESOURCES, 0, 1e9, whole=True),
        "assets": _number_map(body, "assets", RESOURCES, 0, 1e9, whole=True),
        "production": _number_map(body, "production", RESOURCES, 0, 1e6, whole=True),
    }
    if body.get("name") is not None:
        name = str(body["name"]).strip()
        if not 1 <= len(name) <= 40:
            raise ValueError("name must be 1-40 characters")
        config["name"] = name
    for key, low, high, whole in (("x", 0, world_size, False), ("y", 0, world_size, False),
                                  ("money", 0, 1e12, False), ("movement", 1, MAX_MOVEMENT, True),
                                  ("sleep_recovery", 0, 1, False)):
        if body.get(key) is not None:
            config[key] = _number(body[key], key, low, high, whole)
    return {k: v for k, v in config.items() if v is not None}


class Handler(SimpleHTTPRequestHandler):
    sim = None  # set in main()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def end_headers(self):
        # Always serve the latest page/JS after an update instead of a cached copy.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        if self.path == "/api/state":
            return self._json(self.sim.state())
        if self.path == "/api/rules":
            return self._json({"current": self.sim.rules(), "factory": Rules().to_dict()})
        return super().do_GET()

    def do_POST(self):
        def route(body):
            if self.path == "/api/step":
                steps = _number(body.get("steps", 1), "steps", 1, MAX_STEPS_PER_REQUEST, whole=True)
                return self.sim.step(steps)
            if self.path == "/api/reset":
                rules = body.get("rules")
                rules = Rules.from_dict(rules) if rules is not None else Rules.from_dict(self.sim.rules())
                if body.get("agents") is not None:
                    rules.agents = _number(body["agents"], "agents", 1, MAX_AGENTS, whole=True)
                seed = body.get("seed")
                return self.sim.reset(rules, None if seed in (None, "") else int(seed))
            if self.path == "/api/agents":
                return self.sim.add_agent(parse_agent_config(body))
            match = AGENT_PATH.fullmatch(self.path)
            if match:
                return self.sim.update_agent(int(match[1]), parse_agent_config(body))
            raise LookupError("not found")
        self._handle(route)

    def do_DELETE(self):
        def route(body):
            match = AGENT_PATH.fullmatch(self.path)
            if not match:
                raise LookupError("not found")
            return self.sim.remove_agent(int(match[1]))
        self._handle(route)

    def _handle(self, route):
        try:
            self._json(route(self._read_json()))
        except LookupError as exc:
            self._json({"error": str(exc)}, status=404)
        except (ValueError, TypeError) as exc:
            self._json({"error": str(exc)}, status=400)

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
