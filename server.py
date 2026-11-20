"""Local web server for the simulation (standard library only).

    python3 server.py            # http://localhost:8000
    python3 server.py --port 9000 --agents 5 --seed 42

API
    GET    /api/state                 current world state
    POST   /api/step   {"steps": n}   advance n ticks (default 1)
    GET    /api/rules                 {"current": rules of this game, "factory": default rules}
    GET    /api/report?window=N       game report over the last N steps (all kept steps if omitted)
    POST   /api/reset  {"rules": {...}, "agents": n, "seed": s}
                                      start a new game. Omitted rules keep the current game's
                                      rules; "agents" overrides rules.agents.
    POST   /api/agents      {...}     create an agent (any field omitted = default)
    POST   /api/agents/<id> {...}     edit an agent (only the fields sent change)
    DELETE /api/agents/<id>           remove an agent
    POST   /api/government {"min_rate": r, "labor_purchase": n}
    POST   /api/banking    {"enabled": bool, "deposit_rate": r, "loan_spread": r, "reserve_ratio": r,
                            "capital_ratio": r, "min_capital": m, "loan_income_share": s}
                           (any subset; changes live)
                                      change government policy while the game runs

Agent fields: name, x, y, movement, money,
              needs      {hunger, sleep, thirst, boredom: 0..1}   current levels
              rates      {hunger, sleep, thirst, boredom: 0..1}   growth per step
              inventory  {food, water, games, grain, wood: int >= 0}
              labor_capacity >= 0                                 most labour it can give per step
              assets     {food, water, games, grain, wood: >= 0} shares of each industry's assets owned
Industry recipes are game rules ("inputs" in POST /api/reset), e.g. {"food": {"grain": 1}}.
              sleep_recovery  0..1                              sleep recovered per step at rest
"""

import argparse
import json
import re
import socket
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from simulation import World
from simulation.report import build_report
from simulation.rules import Rules
from simulation.agent import NEED_NAMES
from simulation.catalog import CATALOG, SECTORS
from simulation.rules import MAX_LAYERS, NEEDS
from simulation.economy import GOODS, RESOURCES

STATIC_DIR = Path(__file__).parent / "static"
MAX_STEPS_PER_REQUEST = 1000
# Most agents the UI can ask to see in full at once (cards on screen + the one being edited).
MAX_DETAIL = 200
MAX_AGENTS = 5000
MAX_MOVEMENT = 200
AGENT_PATH = re.compile(r"/api/agents/(\d+)")


class Simulation:
    """Holds the single shared World and serialises access to it."""

    def __init__(self, agents, seed):
        self.lock = threading.Lock()
        self.world = None
        self.detail = None   # agent ids the UI shows in full (None: World's default; "all": everyone)
        self.reset(Rules.from_dict({"agents": agents}), seed)

    def reset(self, rules, seed):
        world = World(seed=seed, rules=rules)
        world.spawn_random_agents()
        with self.lock:
            self.world = world
            return world.to_dict(self.detail)

    def step(self, steps):
        with self.lock:
            for _ in range(steps):
                self.world.step()
            return self.world.to_dict(self.detail)

    def add_agent(self, config):
        with self.lock:
            if len(self.world.agents) >= MAX_AGENTS:
                raise ValueError(f"at most {MAX_AGENTS} agents")
            self.world.create_agent(**config)
            return self.world.to_dict(self.detail)

    def update_agent(self, agent_id, config):
        with self.lock:
            self.world.update_agent(self._get(agent_id), **config)
            return self.world.to_dict(self.detail)

    def set_policy(self, min_rate, labor_purchase):
        with self.lock:
            gov = self.world.government
            if min_rate is not None:
                gov.min_rate = min_rate
            if labor_purchase is not None:
                gov.labor_purchase = labor_purchase
            self.world.log(f"Government policy: minimum rate {gov.min_rate:.2%}, "
                           f"buying {gov.labor_purchase:g} labour per step")
            return self.world.to_dict(self.detail)

    def set_banking(self, changes):
        """Switch banking on/off or change its rates while the game runs."""
        with self.lock:
            bank = self.world.banking
            for key, value in changes.items():
                setattr(bank, key, value)
            self.world.log("Banking " + ("on" if bank.enabled else "off (banks wind down)") +
                           f": deposit rate {bank.deposit_rate:.2%}, loan spread {bank.loan_spread:.2%}, "
                           f"reserve ratio {bank.reserve_ratio:.0%}, capital ratio {bank.capital_ratio:.0%}, "
                           f"minimum capital {bank.min_capital:,.0f}, lends up to "
                           f"{bank.loan_income_share:.0%} of a month's income")
            return self.world.to_dict(self.detail)

    def remove_agent(self, agent_id):
        with self.lock:
            self.world.remove_agent(self._get(agent_id))
            return self.world.to_dict(self.detail)

    def _get(self, agent_id):
        agent = self.world.agent_by_id(agent_id)
        if agent is None:
            raise LookupError(f"no agent {agent_id}")
        return agent

    def rules(self):
        with self.lock:
            return self.world.rules.to_dict()

    def report(self, window):
        with self.lock:
            return build_report(self.world, window)

    def state(self):
        with self.lock:
            return self.world.to_dict(self.detail)


def parse_detail(value):
    """Agents the UI wants in full: "all", or a list of ids (at most MAX_DETAIL)."""
    if value == "all" or value is None:
        return value
    if not isinstance(value, list):
        raise ValueError("detail must be \"all\" or a list of agent ids")
    ids = set()
    for v in value[:MAX_DETAIL]:
        if str(v).strip().lstrip("-").isdigit():
            ids.add(int(v))
    return ids


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
        "assets": _number_map(body, "assets", GOODS, 0, 1e9),

    }
    if body.get("name") is not None:
        name = str(body["name"]).strip()
        if not 1 <= len(name) <= 40:
            raise ValueError("name must be 1-40 characters")
        config["name"] = name
    for key, low, high, whole in (("x", 0, world_size, False), ("y", 0, world_size, False),
                                  ("money", 0, 1e12, False), ("movement", 1, MAX_MOVEMENT, True),
                                  ("sleep_recovery", 0, 1, False), ("labor_capacity", 0, 1e6, False),
                                  ("payout_ratio", 0, 1, False)):
        if body.get(key) is not None:
            config[key] = _number(body[key], key, low, high, whole)
    return {k: v for k, v in config.items() if v is not None}


class Handler(SimpleHTTPRequestHandler):
    sim = None  # set in main()
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      ".webmanifest": "application/manifest+json", ".svg": "image/svg+xml"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def end_headers(self):
        # Always serve the latest page/JS after an update instead of a cached copy.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        if self.path == "/catalog.js":
            return self._script(catalog_script())
        if self.path.partition("?")[0] == "/api/state":
            query = dict(p.split("=", 1) for p in self.path.partition("?")[2].split("&") if "=" in p)
            if "detail" in query:
                self.sim.detail = parse_detail(query["detail"].split(",") if query["detail"] != "all" else "all")
            return self._json(self.sim.state())
        if self.path.startswith("/api/report"):
            query = dict(p.split("=", 1) for p in self.path.partition("?")[2].split("&") if "=" in p)
            window = query.get("window", "")
            return self._json(self.sim.report(int(window) if window.isdigit() and int(window) > 0 else None))
        if self.path == "/api/rules":
            return self._json({"current": self.sim.rules(), "factory": Rules().to_dict()})
        return super().do_GET()

    def do_POST(self):
        def route(body):
            if "detail" in body:
                self.sim.detail = parse_detail(body["detail"])
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
            if self.path == "/api/rules/resolve":
                # What the rules become once the server fills them in (industries sized for this game's
                # layers and exclusions, stock of missing goods converted): for the setup preview.
                rules = Rules.from_dict(body.get("rules") or {})
                return {"rules": rules.to_dict(), "active": list(rules.active_goods),
                        "auto_excluded": list(rules.auto_excluded), "consumer_needs": list(rules.consumer_needs)}
            if self.path == "/api/agents":
                return self.sim.add_agent(parse_agent_config(body))
            if self.path == "/api/banking":
                limits = {"deposit_rate": (0, 1), "loan_spread": (0, 1), "reserve_ratio": (0, 1),
                          "capital_ratio": (0, 1), "min_capital": (0, 1e12), "loan_income_share": (0, 100)}
                changes = {}
                for key, value in body.items():
                    if key == "detail":
                        continue
                    if key == "enabled":
                        if not isinstance(value, bool):
                            raise ValueError("enabled must be true or false")
                        changes[key] = value
                    elif key in limits:
                        changes[key] = _number(value, key, *limits[key])
                    else:
                        raise ValueError(f"unknown banking setting: {key}")
                return self.sim.set_banking(changes)
            if self.path == "/api/government":
                rate = body.get("min_rate")
                buy = body.get("labor_purchase")
                return self.sim.set_policy(None if rate is None else _number(rate, "min_rate", 0, 10),
                                           None if buy is None else _number(buy, "labor_purchase", 0, 1e6))
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

    def _script(self, text):
        data = text.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, payload, status=200):
        data = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        if not self.path.startswith("/api/"):
            super().log_message(fmt, *args)


def catalog_script():
    """The industry catalog and needs for the browser, as window.CATALOG (loaded before app.js)."""
    data = {"goods": CATALOG, "needs": list(NEEDS), "sectors": list(SECTORS), "max_layers": MAX_LAYERS}
    return f"window.CATALOG = {json.dumps(data)};\n"


def lan_address():
    """This computer's address on the local network (no traffic is sent: UDP connect only picks a route)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def main():
    parser = argparse.ArgumentParser(description="Run the agent simulation server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--lan", action="store_true",
                        help="listen on every network interface so a phone on the same Wi-Fi can open it")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--agents", type=int, default=3)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    host = "0.0.0.0" if args.lan else args.host
    Handler.sim = Simulation(args.agents, args.seed)
    server = ThreadingHTTPServer((host, args.port), Handler)
    print(f"Simulation running at http://localhost:{args.port}  (Ctrl+C to stop)")
    if host == "0.0.0.0":
        print(f"On your phone (same Wi-Fi): http://{lan_address()}:{args.port}")
        print("Anyone on this network can open and control the game while it runs.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
