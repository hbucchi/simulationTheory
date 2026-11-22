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
    POST   /api/government any of POLICY_LIMITS (taxes, benefit, policy rate, Basel capital ratio,
                           reserve requirement, lender of last resort, ...), changes live
    POST   /api/policies   {"action": "add", "policy": {...}} | {"action": "update", "id": n, "policy": {...}}
                           | {"action": "remove", "id": n}: public spending policies (policies.py)
    POST   /api/banking    {"enabled": bool, "deposit_rate": r, "loan_spread": r, "liquidity": r,
                            "min_capital": m, "loan_income_share": s}
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
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from simulation import World
from simulation.report import build_report
from simulation.rules import Rules, MODULES
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

    def set_policy(self, changes):
        """Change government / central bank policy while the game runs (see government.py)."""
        with self.lock:
            gov = self.world.government
            for key, value in changes.items():
                if key == "enabled":
                    gov.enabled = value
                else:
                    gov.set(key, value)
            self.world.log("Government switched off: no taxes, spending, policy rate or rules for banks"
                           if not gov.enabled else
                           f"Government policy: taxes {gov.tax_production:.0%} production, {gov.tax_wage:.0%} salary, "
                           f"{gov.tax_profit:.0%} profit; benefit {gov.benefit_rate:.0%} of the wage; policy rate "
                           f"{gov.min_rate:.2%}; banks hold {gov.reserve_requirement:.0%} of deposits at the central bank "
                           f"and equity of {gov.capital_ratio:.1%} of loans; lender of last resort "
                           f"{'on' if gov.lender_of_last_resort else 'off'}")
            return self.world.to_dict(self.detail)

    def change_policies(self, body):
        """Add, edit or remove a public spending policy while the game runs."""
        from simulation.policies import clean
        with self.lock:
            world = self.world
            policies = world.government.policies
            action = body.get("action")
            if action == "add":
                if len(policies.items) >= 50:
                    raise ValueError("at most 50 policies")
                p = policies.add(clean(body.get("policy", {})))
                world.log(f"New policy: {p.label(world.rules)}")
            elif action in ("update", "remove"):
                pid = body.get("id")
                p = policies.get(pid) if isinstance(pid, int) and not isinstance(pid, bool) else None
                if p is None:
                    raise LookupError(f"no policy {pid}")
                if action == "remove":
                    policies.remove(pid)
                    world.log(f"Policy ended: {p.label(world.rules)}")
                else:
                    spec = {**{k: getattr(p, k) for k in p.FIELDS}, **body.get("policy", {})}
                    spec = {k: v for k, v in spec.items() if v is not None}
                    # Switching what a policy does picks a sensible resource or need to start from.
                    if spec.get("kind") == "goods":
                        spec.setdefault("good", next((g for g in ("food", "water") if g in world.rules.active_goods),
                                                     world.rules.active_goods[0]))
                    else:
                        spec.pop("good", None)
                    if spec.get("kind") == "service":
                        spec.setdefault("need", "health")
                    else:
                        spec.pop("need", None)
                    fields = clean(spec)
                    p.good = p.need = None
                    p.update(**fields)
                    world.log(f"Policy changed: {p.label(world.rules)}")
            else:
                raise ValueError('action must be "add", "update" or "remove"')
            return world.to_dict(self.detail)

    def set_market(self, changes):
        """Change how markets work while the game runs (price stickiness)."""
        with self.lock:
            if "price_stickiness" in changes:
                self.world.price_stickiness = changes["price_stickiness"]
                s = self.world.price_stickiness
                self.world.log("Prices are now perfectly flexible" if s == 0 else
                               f"Prices are sticky: each day they close {1 - s:.0%} of the gap to the market price")
            rules = self.world.rules
            if "clearance_enabled" in changes:
                rules.clearance_enabled = changes["clearance_enabled"]
            if "clearance_schedule" in changes:
                rules.clearance_schedule = changes["clearance_schedule"]
            for key in PRICING_LIMITS:
                if key in changes:
                    setattr(rules, key, changes[key])
            if set(PRICING_LIMITS) & set(changes):
                self.world.log(f"Pricing: base = cost + {rules.cost_floor_margin:.0%} margin; stock target "
                               f"{rules.stock_target_days:g} days, prices move up to {rules.stock_adjust_speed:.0%} a day; "
                               f"sellers short of cash give up to {rules.distress_max:.0%} off")
            if {"clearance_enabled", "clearance_schedule"} & set(changes):
                steps = ", ".join(f"{d:.0%} off from {n} days before expiry" for n, d in rules.clearance_schedule)
                self.world.log("Clearance sales: " + (steps if rules.clearance_enabled and steps else "off"))
            return self.world.to_dict(self.detail)

    def set_housing(self, changes):
        """Change the housing market's rules while the game runs."""
        with self.lock:
            h = self.world.housing
            for key, value in changes.items():
                setattr(h, key, int(value) if key == "eviction_days" else value)
            self.world.log(f"Housing rules: minimum price {h.min_multiple:g}x the average good, "
                           f"evictions after {h.eviction_days} days")
            return self.world.to_dict(self.detail)

    def set_banking(self, changes):
        """Switch banking on/off or change its rates while the game runs."""
        with self.lock:
            bank = self.world.banking
            for key, value in changes.items():
                setattr(bank, key, int(value) if key == "mortgage_default_days" else value)
            self.world.log("Banking " + ("on" if bank.enabled else "off (banks wind down)") +
                           f": deposit rate {bank.deposit_rate:.2%}, loan spread {bank.loan_spread:.2%}, "
                           f"keeps {bank.liquidity:.0%} of deposits as cash, "
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


# Pricing settings (cost prices) that can be changed live in the Products tab: name -> (low, high).
PRICING_LIMITS = {'cost_floor_margin': (0, 10), 'stock_target_days': (0.1, 10000), 'stock_adjust_speed': (0, 1), 'distress_days': (0, 10000), 'distress_max': (0, 1)}

# Government / central bank settings that can be changed live: name -> (low, high) or bool.
POLICY_LIMITS = {"min_wage": (0, 1e9), "min_rate": (0, 10), "labor_purchase": (0, 1e6), "capital_ratio": (0, 1),
                 "tax_production": (0, 1), "tax_wage": (0, 1), "tax_profit": (0, 1), "benefit_rate": (0, 10),
                 "reserve_requirement": (0, 1), "reserve_rate": (0, 1), "llr_penalty": (0, 1),
                 "enabled": bool, "balanced_budget": bool, "lender_of_last_resort": bool,
                 "bonds_enabled": bool, "debt_limit": (0, 10), "bond_spread": (0, 0.01), "bond_days": (1, 3600),
                 "pay_period": ("daily", "weekly", "monthly"),
                 "taylor_enabled": bool, "inflation_target": (-0.5, 1), "neutral_rate": (-0.5, 1),
                 "taylor_unemployment": (0, 1)}


def parse_policy(body):
    changes = {}
    for key, value in body.items():
        if key == "detail":
            continue
        if key not in POLICY_LIMITS:
            raise ValueError(f"unknown government setting: {key}")
        if POLICY_LIMITS[key] is not bool and isinstance(POLICY_LIMITS[key][0], str):   # a choice
            if value not in POLICY_LIMITS[key]:
                raise ValueError(f"{key} must be one of {', '.join(POLICY_LIMITS[key])}")
            changes[key] = value
        elif POLICY_LIMITS[key] is bool:
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be true or false")
            changes[key] = value
        else:
            changes[key] = _number(value, key, *POLICY_LIMITS[key])
    return changes


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
                                  ("payout_ratio", 0, 1, False), ("risk_appetite", 0, 1, False),
                                  ("lavishness", 0, 1, False)):
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
                        "auto_excluded": list(rules.auto_excluded), "consumer_needs": list(rules.consumer_needs),
                        "module_notes": rules.module_notes}
            if self.path == "/api/agents":
                return self.sim.add_agent(parse_agent_config(body))
            if self.path == "/api/banking":
                limits = {"deposit_rate": (0, 1), "loan_spread": (0, 1), "liquidity": (0, 1),
                          "min_capital": (0, 1e12), "loan_income_share": (0, 100),
                          "mortgage_years": (0, 100), "mortgage_dti": (0, 1), "mortgage_ltv": (0, 1),
                          "mortgage_premium": (0, 0.01), "mortgage_default_days": (1, 3600)}
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
                return self.sim.set_policy(parse_policy(body))
            if self.path == "/api/market":
                changes = {}
                for key, value in body.items():
                    if key == "detail":
                        continue
                    if key == "clearance_schedule":
                        from simulation.rules import clean_schedule
                        changes[key] = clean_schedule(value)
                    elif key == "clearance_enabled":
                        if not isinstance(value, bool):
                            raise ValueError("clearance_enabled must be true or false")
                        changes[key] = value
                    elif key == "price_stickiness":
                        changes[key] = _number(value, key, 0, 0.99)
                    elif key in PRICING_LIMITS:
                        changes[key] = _number(value, key, *PRICING_LIMITS[key])
                    else:
                        raise ValueError(f"unknown market setting: {key}")
                return self.sim.set_market(changes)
            if self.path == "/api/housing":
                limits = {"min_multiple": (0, 1e6), "rent_yield": (0, 0.01), "eviction_days": (1, 3600)}
                changes = {}
                for key, value in body.items():
                    if key == "detail":
                        continue
                    if key not in limits:
                        raise ValueError(f"unknown housing setting: {key}")
                    changes[key] = _number(value, key, *limits[key], whole=key == "eviction_days")
                return self.sim.set_housing(changes)
            if self.path == "/api/policies":
                return self.sim.change_policies(body)
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
    data = {"goods": CATALOG, "needs": list(NEEDS), "sectors": list(SECTORS), "max_layers": MAX_LAYERS,
            "modules": [{"key": k, "rule": rule, "label": label, "needs": list(needs), "about": about}
                        for k, (rule, label, needs, about) in MODULES.items()]}
    return f"window.CATALOG = {json.dumps(data)};\n"


class ExclusiveServer(ThreadingHTTPServer):
    """A server that refuses a port another server already uses. (On Windows the default lets a
    second server share the port, and the browser then gets pages from either one at random:
    an old version can answer half the requests.)"""
    allow_reuse_address = sys.platform != "win32"

    def server_bind(self):
        if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


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
    try:
        server = ExclusiveServer((host, args.port), Handler)
    except OSError:
        raise SystemExit(f"Port {args.port} is already in use: another copy of the simulation (maybe an older "
                         f"version) is still running. Stop it (close its window, or Ctrl+C there), or start this "
                         f"one on another port: python server.py --port {args.port + 1}")
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
