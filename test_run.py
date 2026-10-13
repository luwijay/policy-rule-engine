import json
from fastapi.testclient import TestClient
from main import app
c = TestClient(app)
plan = json.load(open("sample_meal_plan.json"))
for pol in ["low_sodium", "diabetic"]:
    plan["policy"] = pol
    r = c.post("/validate", json=plan).json()
    print(pol, "compliant:", r["compliant"], "errors:", r["errors"], "warnings:", r["warnings"])
    for v in r["violations"]:
        print("  ", v["rule_id"], v["where"], v["actual"], v["required"])
print(c.post("/validate", json={"policy":"x","meals":[]}).status_code)
print(c.post("/validate", json={"policy":"diabetic","meals":[{"meal_type":"lunch","items":[{"name":"mystery","grams":10}]}]}).status_code)
