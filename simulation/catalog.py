"""The default industries: one per good, grouped by sector (TRBC-style, the classification
investing.com's screener uses) and stacked in layers by what they use.

Layer = 1 for a primary (extraction) industry, otherwise 1 + the deepest layer among its
inputs, so it is worked out from the recipes (see rules.industry_layer) rather than stored.

Each entry:
  id         the good's name everywhere in the code and the API
  label      shown in the UI
  sector     TRBC economic sector
  industry   TRBC-style industry
  inputs     {input good: units used per unit made}; {} = primary
  effects    {need: fit} what consuming one unit does to each need, fit from -1 to 1. Positive:
             relieves relief_per_unit x fit x (1 + layer_bonus x (layer - 1)), so deeper layers
             relieve more; negative: worsens it by relief_per_unit x |fit| (harm isn't scaled by
             layer). Fast food relieves hunger and boredom but harms health. {} = only an input.
             Sleep can only be harmed (it is recovered by resting). The biggest benefit is the
             good's main need.
  shelf_life steps a unit lasts before it is thrown away (0 = never expires)
  productivity  (optional) units per unit of labour, for industries more labour-intensive than
             their layer's default (deeper layers need less labour per unit, see rules.py)
  stock      default starting units per agent
  plan       share of its main need an average agent is expected to cover with this good (used to size
             the default industries; the shares of a need's goods add up to 1)
  shares     default asset shares per agent (owned by 10% of the agents), sized to demand: each need
             is split over its goods (e.g. thirst 70% water, 30% beverages), inputs are added down
             the layers, and every industry gets 2x the capacity that takes (at least 0.02)
"""

CATALOG = [
    # ---------------- Layer 1: extraction (capital + labour only) ----------------
    {"id": "grain", "label": "Grain", "sector": "Consumer Non-Cyclicals", "industry": "Fishing & Farming",
     "inputs": {}, "effects": {"hunger": 0.6}, "shelf_life": 800, "stock": 30, "shares": 0.27, "plan": 0},
    {"id": "livestock", "label": "Livestock", "sector": "Consumer Non-Cyclicals", "industry": "Fishing & Farming",
     "inputs": {}, "effects": {"hunger": 0.6, "health": -0.1}, "shelf_life": 0, "stock": 0, "shares": 0.09, "plan": 0},
    {"id": "water", "label": "Water", "sector": "Utilities", "industry": "Water & Related Utilities",
     "inputs": {}, "effects": {"thirst": 1.0}, "shelf_life": 0, "stock": 100, "shares": 0.69, "plan": 0.7},
    {"id": "wood", "label": "Timber", "sector": "Basic Materials", "industry": "Forest & Wood Products",
     "inputs": {}, "effects": {"energy": 0.5, "shelter": 0.1, "health": -0.1}, "shelf_life": 0, "stock": 20, "shares": 0.21, "plan": 0.1},
    {"id": "crude_oil", "label": "Crude oil", "sector": "Energy", "industry": "Oil & Gas Exploration and Production",
     "inputs": {}, "effects": {"energy": 0.2, "health": -0.3}, "shelf_life": 0, "stock": 0, "shares": 0.09, "plan": 0},
    {"id": "natural_gas", "label": "Natural gas", "sector": "Energy", "industry": "Natural Gas Utilities",
     "inputs": {}, "effects": {"energy": 0.6}, "shelf_life": 0, "stock": 0, "shares": 0.07, "plan": 0},
    {"id": "coal", "label": "Coal", "sector": "Energy", "industry": "Coal",
     "inputs": {}, "effects": {"energy": 0.4, "health": -0.3}, "shelf_life": 0, "stock": 0, "shares": 0.07, "plan": 0},
    {"id": "ore", "label": "Metal ore", "sector": "Basic Materials", "industry": "Metals & Mining",
     "inputs": {}, "effects": {}, "shelf_life": 0, "stock": 0, "shares": 0.02, "plan": 0},
    {"id": "stone", "label": "Stone & sand", "sector": "Basic Materials", "industry": "Construction Materials",
     "inputs": {}, "effects": {"shelter": 0.3}, "shelf_life": 0, "stock": 0, "shares": 0.02, "plan": 0},
    {"id": "herbs", "label": "Medicinal herbs", "sector": "Healthcare", "industry": "Fishing & Farming (botanicals)",
     "inputs": {}, "effects": {"health": 0.6, "hunger": 0.1}, "shelf_life": 100, "stock": 5, "shares": 0.1, "plan": 0.3},

    # ---------------- Layer 2: first processing ----------------
    {"id": "food", "label": "Food", "sector": "Consumer Non-Cyclicals", "industry": "Food Processing",
     "inputs": {"grain": 1.0}, "effects": {"hunger": 1.0, "health": 0.1}, "shelf_life": 200, "stock": 30, "shares": 0.08, "plan": 0.5},
    {"id": "meat", "label": "Meat", "sector": "Consumer Non-Cyclicals", "industry": "Food Processing (meat)",
     "inputs": {"livestock": 1.0}, "effects": {"hunger": 1.0, "boredom": 0.1}, "shelf_life": 50, "stock": 0, "shares": 0.04, "plan": 0.15},
    {"id": "beverages", "label": "Beverages", "sector": "Consumer Non-Cyclicals", "industry": "Beverages",
     "inputs": {"water": 1.0, "grain": 0.2}, "effects": {"thirst": 1.0, "boredom": 0.2, "health": -0.1}, "shelf_life": 600, "stock": 0, "shares": 0.06, "plan": 0.3},
    {"id": "electricity", "label": "Electricity", "sector": "Utilities", "industry": "Electric Utilities",
     "inputs": {"coal": 0.5, "natural_gas": 0.5}, "effects": {"energy": 1.0, "boredom": 0.1, "shelter": 0.1}, "shelf_life": 20, "stock": 0, "shares": 0.04, "plan": 0.5},
    {"id": "fuel", "label": "Fuel", "sector": "Energy", "industry": "Oil & Gas Refining and Marketing",
     "inputs": {"crude_oil": 1.0}, "effects": {"energy": 0.7, "health": -0.1}, "shelf_life": 1500, "stock": 20, "shares": 0.03, "plan": 0.4},
    {"id": "steel", "label": "Steel", "sector": "Basic Materials", "industry": "Iron & Steel",
     "inputs": {"ore": 1.0, "coal": 0.5}, "effects": {}, "shelf_life": 0, "stock": 0, "shares": 0.02, "plan": 0},
    {"id": "chemicals", "label": "Chemicals", "sector": "Basic Materials", "industry": "Chemicals",
     "inputs": {"crude_oil": 0.5, "natural_gas": 0.5}, "effects": {"health": 0.2}, "shelf_life": 2000, "stock": 0,
     "shares": 0.02, "plan": 0},
    {"id": "lumber", "label": "Lumber", "sector": "Basic Materials", "industry": "Paper & Forest Products",
     "inputs": {"wood": 1.0}, "effects": {"shelter": 0.5, "energy": 0.2}, "shelf_life": 0, "stock": 0, "shares": 0.02, "plan": 0.2},
    {"id": "cement", "label": "Cement", "sector": "Basic Materials", "industry": "Construction Materials (cement)",
     "inputs": {"stone": 1.0, "coal": 0.3}, "effects": {}, "shelf_life": 1000, "stock": 0, "shares": 0.02, "plan": 0},
    {"id": "textiles", "label": "Textiles", "sector": "Consumer Cyclicals", "industry": "Textiles & Leather Goods",
     "inputs": {"grain": 0.5}, "effects": {"shelter": 0.4}, "shelf_life": 3000, "stock": 0, "shares": 0.02, "plan": 0},
    {"id": "games", "label": "Toys & games", "sector": "Consumer Cyclicals", "industry": "Leisure Products",
     "inputs": {"wood": 1.0}, "effects": {"boredom": 1.0, "sleep": -0.05}, "shelf_life": 0, "stock": 100, "shares": 0.05, "plan": 0.5},

    {"id": "spirits", "label": "Beer, wine & spirits", "sector": "Consumer Non-Cyclicals", "industry": "Brewers & Distillers",
     "inputs": {"grain": 0.5, "water": 0.5}, "effects": {"boredom": 0.7, "thirst": 0.2, "health": -0.5, "sleep": -0.1},
     "shelf_life": 2000, "stock": 0, "shares": 0.02, "plan": 0.1},

    # ---------------- Layer 3: manufacturing ----------------
    {"id": "fast_food", "label": "Fast food", "sector": "Consumer Cyclicals", "industry": "Restaurants & Bars",
     "inputs": {"food": 0.5, "meat": 0.5, "electricity": 0.1}, "effects": {"hunger": 1.0, "boredom": 0.4, "health": -0.4},
     "shelf_life": 30, "stock": 0, "shares": 0.02, "plan": 0.15, "productivity": 5.0},
    {"id": "meals", "label": "Packaged meals", "sector": "Consumer Non-Cyclicals", "industry": "Food Retail & Distribution",
     "inputs": {"food": 0.5, "meat": 0.5, "electricity": 0.2}, "effects": {"hunger": 1.0, "health": 0.1}, "shelf_life": 150,
     "stock": 0, "shares": 0.02, "plan": 0.2},
    {"id": "plastics", "label": "Plastics", "sector": "Basic Materials", "industry": "Commodity Chemicals",
     "inputs": {"chemicals": 1.0, "electricity": 0.2}, "effects": {}, "shelf_life": 0, "stock": 0, "shares": 0.02, "plan": 0},
    {"id": "pharmaceuticals", "label": "Pharmaceuticals", "sector": "Healthcare", "industry": "Pharmaceuticals",
     "inputs": {"chemicals": 0.5, "herbs": 0.5}, "effects": {"health": 1.0}, "shelf_life": 800, "stock": 5, "shares": 0.02, "plan": 0.5},
    {"id": "machinery", "label": "Machinery", "sector": "Industrials", "industry": "Machinery, Equipment & Components",
     "inputs": {"steel": 1.0, "electricity": 0.3}, "effects": {}, "shelf_life": 0, "stock": 0, "shares": 0.02, "plan": 0},
    {"id": "housing", "label": "Housing", "sector": "Real Estate", "industry": "Homebuilding & Construction Supplies",
     "inputs": {"lumber": 0.5, "cement": 1.0, "steel": 0.3}, "effects": {"shelter": 1.0, "health": 0.1, "energy": 0.1}, "shelf_life": 0,
     "stock": 5, "shares": 0.02, "plan": 0.5, "productivity": 4.0},
    {"id": "apparel", "label": "Apparel", "sector": "Consumer Cyclicals", "industry": "Apparel & Accessories",
     "inputs": {"textiles": 1.0, "electricity": 0.1}, "effects": {"shelter": 0.5, "boredom": 0.1}, "shelf_life": 3000, "stock": 5,
     "shares": 0.02, "plan": 0.3},

    # ---------------- Layer 4: advanced manufacturing ----------------
    {"id": "electronics", "label": "Electronics", "sector": "Technology", "industry": "Electronic Equipment & Parts",
     "inputs": {"steel": 0.3, "plastics": 0.5, "electricity": 0.5, "machinery": 0.1}, "effects": {"boredom": 0.6, "energy": -0.2, "sleep": -0.1},
     "shelf_life": 4000, "stock": 0, "shares": 0.02, "plan": 0},
    {"id": "medical_devices", "label": "Medical devices", "sector": "Healthcare", "industry": "Healthcare Equipment & Supplies",
     "inputs": {"plastics": 0.5, "steel": 0.3, "machinery": 0.1}, "effects": {"health": 1.0}, "shelf_life": 4000,
     "stock": 0, "shares": 0.02, "plan": 0},

    # ---------------- Layer 5: services built on technology ----------------
    {"id": "telecom", "label": "Telecom services", "sector": "Telecommunications", "industry": "Telecommunications Services",
     "inputs": {"electronics": 0.3, "electricity": 0.5}, "effects": {"boredom": 1.0, "energy": -0.1}, "shelf_life": 25, "stock": 0,
     "shares": 0.02, "plan": 0.1},
    {"id": "media", "label": "Media", "sector": "Consumer Cyclicals", "industry": "Media & Publishing",
     "inputs": {"electronics": 0.2, "electricity": 0.3}, "effects": {"boredom": 1.0, "sleep": -0.1}, "shelf_life": 40, "stock": 0,
     "shares": 0.02, "plan": 0.2},
    {"id": "healthcare", "label": "Healthcare services", "sector": "Healthcare", "industry": "Healthcare Providers & Services",
     "inputs": {"pharmaceuticals": 0.5, "medical_devices": 0.3}, "effects": {"health": 1.0}, "shelf_life": 25,
     "stock": 0, "shares": 0.02, "plan": 0.2, "productivity": 6.0},

    # ---------------- Layer 6 ----------------
    {"id": "software", "label": "Software & IT", "sector": "Technology", "industry": "Software & IT Services",
     "inputs": {"electronics": 0.1, "telecom": 0.2}, "effects": {"boredom": 1.0, "energy": -0.1, "sleep": -0.1}, "shelf_life": 30, "stock": 0,
     "shares": 0.02, "plan": 0.1},
]

BY_ID = {entry["id"]: entry for entry in CATALOG}

SECTORS = ("Energy", "Basic Materials", "Industrials", "Consumer Cyclicals", "Consumer Non-Cyclicals",
           "Healthcare", "Technology", "Telecommunications", "Utilities", "Real Estate")
