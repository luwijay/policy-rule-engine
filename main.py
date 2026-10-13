"""
Lab 1: Evidence-Based Policy Rule Engine
Compliance validation engine for diet plans (FastAPI).

Run:  uvicorn main:app --reload
Docs: http://127.0.0.1:8000/docs
"""

import operator
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Diet Policy Rule Engine")

# ---------------------------------------------------------------------------
# 1. FOOD TABLE (sample values per 100 g, rounded, for demo only)
# ---------------------------------------------------------------------------
NUTRIENT_KEYS = ["calories", "sodium_mg", "carbs_g", "sugar_g",
                 "fiber_g", "sat_fat_g", "protein_g"]

FOOD_DB: Dict[str, Dict[str, float]] = {
    "white rice, cooked":   dict(calories=130, sodium_mg=1,    carbs_g=28, sugar_g=0.1, fiber_g=0.4, sat_fat_g=0.1, protein_g=2.7),
    "brown rice, cooked":   dict(calories=112, sodium_mg=5,    carbs_g=23, sugar_g=0.4, fiber_g=1.8, sat_fat_g=0.2, protein_g=2.3),
    "chicken breast, roasted": dict(calories=165, sodium_mg=74, carbs_g=0, sugar_g=0,   fiber_g=0,   sat_fat_g=1,   protein_g=31),
    "broccoli, steamed":    dict(calories=35,  sodium_mg=41,   carbs_g=7,  sugar_g=1.7, fiber_g=3.3, sat_fat_g=0.1, protein_g=2.4),
    "oatmeal, cooked":      dict(calories=71,  sodium_mg=4,    carbs_g=12, sugar_g=0.3, fiber_g=1.7, sat_fat_g=0.4, protein_g=2.5),
    "banana":               dict(calories=89,  sodium_mg=1,    carbs_g=23, sugar_g=12,  fiber_g=2.6, sat_fat_g=0.1, protein_g=1.1),
    "apple":                dict(calories=52,  sodium_mg=1,    carbs_g=14, sugar_g=10,  fiber_g=2.4, sat_fat_g=0,   protein_g=0.3),
    "egg, boiled":          dict(calories=155, sodium_mg=124,  carbs_g=1.1, sugar_g=1.1, fiber_g=0,  sat_fat_g=3.3, protein_g=13),
    "milk, whole":          dict(calories=61,  sodium_mg=43,   carbs_g=4.8, sugar_g=5,  fiber_g=0,   sat_fat_g=1.9, protein_g=3.2),
    "white bread":          dict(calories=265, sodium_mg=491,  carbs_g=49, sugar_g=5,   fiber_g=2.7, sat_fat_g=0.7, protein_g=9),
    "instant noodles":      dict(calories=450, sodium_mg=1800, carbs_g=62, sugar_g=2,   fiber_g=2.5, sat_fat_g=8,   protein_g=9),
    "soy sauce":            dict(calories=53,  sodium_mg=5493, carbs_g=5,  sugar_g=0.4, fiber_g=0.8, sat_fat_g=0,   protein_g=8),
    "soft drink":           dict(calories=42,  sodium_mg=4,    carbs_g=10.6, sugar_g=10.6, fiber_g=0, sat_fat_g=0,  protein_g=0),
    "fried chicken":        dict(calories=250, sodium_mg=500,  carbs_g=10, sugar_g=0,   fiber_g=0.5, sat_fat_g=4,   protein_g=20),
}

# ---------------------------------------------------------------------------
# 2. POLICIES CODIFIED AS DATA (the "rules")
#    Each rule: scope = "meal" or "day", nutrient, op, limit, severity.
#    applies_to limits a meal rule to certain meal types.
#    Thresholds are example values. Replace them with your hospital's policy.
# ---------------------------------------------------------------------------
POLICIES: Dict[str, dict] = {
    "low_sodium": {
        "description": "Low-sodium hospital diet (about 2,000 mg sodium per day)",
        "source": "WHO sodium guideline (under 2,000 mg/day); per-meal limit is an example institutional rule",
        "rules": [
            dict(id="LS-1", scope="day",  nutrient="sodium_mg", op="<=", limit=2000, severity="error",
                 message="Daily sodium is above the 2,000 mg limit."),
            dict(id="LS-2", scope="meal", nutrient="sodium_mg", op="<=", limit=700, severity="error",
                 applies_to=["breakfast", "lunch", "dinner"],
                 message="Main meal sodium is above 700 mg."),
            dict(id="LS-3", scope="meal", nutrient="sodium_mg", op="<=", limit=250, severity="warning",
                 applies_to=["snack"],
                 message="Snack sodium is above 250 mg."),
        ],
    },
    "diabetic": {
        "description": "Consistent-carbohydrate diabetic hospital diet",
        "source": "Example rules based on common consistent-carb meal planning and WHO limits on sugar and saturated fat",
        "rules": [
            dict(id="DM-1", scope="meal", nutrient="carbs_g", op=">=", limit=45, severity="warning",
                 applies_to=["breakfast", "lunch", "dinner"],
                 message="Main meal carbs are below 45 g."),
            dict(id="DM-2", scope="meal", nutrient="carbs_g", op="<=", limit=60, severity="error",
                 applies_to=["breakfast", "lunch", "dinner"],
                 message="Main meal carbs are above 60 g."),
            dict(id="DM-3", scope="meal", nutrient="carbs_g", op="<=", limit=30, severity="error",
                 applies_to=["snack"],
                 message="Snack carbs are above 30 g."),
            dict(id="DM-4", scope="day", nutrient="sugar_pct_energy", op="<=", limit=10, severity="error",
                 message="Sugar is above 10% of daily calories."),
            dict(id="DM-5", scope="day", nutrient="sat_fat_pct_energy", op="<=", limit=10, severity="error",
                 message="Saturated fat is above 10% of daily calories."),
            dict(id="DM-6", scope="day", nutrient="fiber_g", op=">=", limit=25, severity="warning",
                 message="Daily fiber is below 25 g."),
        ],
    },
}

OPS = {"<=": operator.le, ">=": operator.ge}

# ---------------------------------------------------------------------------
# 3. REQUEST / RESPONSE MODELS
# ---------------------------------------------------------------------------
class FoodItem(BaseModel):
    name: str
    grams: float = Field(gt=0)
    per_100g: Optional[Dict[str, float]] = None  # optional custom nutrient values

class Meal(BaseModel):
    meal_type: str = Field(description="breakfast, lunch, dinner, or snack")
    items: List[FoodItem]

class MealPlan(BaseModel):
    policy: str = Field(description="low_sodium or diabetic")
    meals: List[Meal]

# ---------------------------------------------------------------------------
# 4. NUTRIENT MATH
# ---------------------------------------------------------------------------
def item_totals(item: FoodItem) -> Dict[str, float]:
    data = item.per_100g or FOOD_DB.get(item.name.strip().lower())
    if data is None:
        raise HTTPException(
            422, f"Unknown food '{item.name}'. Add it to FOOD_DB or send per_100g values.")
    scale = item.grams / 100
    return {k: data.get(k, 0) * scale for k in NUTRIENT_KEYS}

def add_derived(t: Dict[str, float]) -> Dict[str, float]:
    cal = t["calories"]
    t["sugar_pct_energy"] = (t["sugar_g"] * 4 / cal * 100) if cal else 0
    t["sat_fat_pct_energy"] = (t["sat_fat_g"] * 9 / cal * 100) if cal else 0
    return t

def sum_totals(rows: List[Dict[str, float]]) -> Dict[str, float]:
    total = {k: 0.0 for k in NUTRIENT_KEYS}
    for r in rows:
        for k in NUTRIENT_KEYS:
            total[k] += r[k]
    return add_derived(total)

def rounded(d: Dict[str, float]) -> Dict[str, float]:
    return {k: round(v, 1) for k, v in d.items()}

# ---------------------------------------------------------------------------
# 5. RULE ENGINE
# ---------------------------------------------------------------------------
def check_rule(rule: dict, actual: float, where: str) -> Optional[dict]:
    if OPS[rule["op"]](actual, rule["limit"]):
        return None
    return dict(rule_id=rule["id"], severity=rule["severity"], where=where,
                nutrient=rule["nutrient"], actual=round(actual, 1),
                required=f'{rule["op"]} {rule["limit"]}', message=rule["message"])

def validate(plan: MealPlan) -> dict:
    policy = POLICIES.get(plan.policy)
    if not policy:
        raise HTTPException(404, f"Unknown policy. Choose from: {list(POLICIES)}")

    violations, meal_reports, all_meal_totals = [], [], []
    for i, meal in enumerate(plan.meals, 1):
        totals = sum_totals([item_totals(it) for it in meal.items])
        all_meal_totals.append(totals)
        label = f"meal {i} ({meal.meal_type})"
        for rule in policy["rules"]:
            if rule["scope"] != "meal":
                continue
            if "applies_to" in rule and meal.meal_type.lower() not in rule["applies_to"]:
                continue
            v = check_rule(rule, totals[rule["nutrient"]], label)
            if v:
                violations.append(v)
        meal_reports.append(dict(meal=label, totals=rounded(totals)))

    day = sum_totals(all_meal_totals)
    for rule in policy["rules"]:
        if rule["scope"] == "day":
            v = check_rule(rule, day[rule["nutrient"]], "whole day")
            if v:
                violations.append(v)

    errors = [v for v in violations if v["severity"] == "error"]
    return dict(
        policy=plan.policy,
        compliant=len(errors) == 0,
        errors=len(errors),
        warnings=len(violations) - len(errors),
        violations=violations,
        daily_totals=rounded(day),
        meals=meal_reports,
    )

# ---------------------------------------------------------------------------
# 6. ENDPOINTS
# ---------------------------------------------------------------------------
@app.get("/policies")
def list_policies():
    return POLICIES

@app.get("/foods")
def list_foods():
    return sorted(FOOD_DB)

@app.post("/validate")
def validate_plan(plan: MealPlan):
    return validate(plan)
