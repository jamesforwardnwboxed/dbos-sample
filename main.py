import os

import uvicorn
from dbos import DBOS, DBOSConfig
from fastapi import FastAPI

app = FastAPI()

@DBOS.step()
def step_one(name: str) -> int:
    print(f"Hello {name}")
    print("Step one completed!")
    return len(name)

@DBOS.step()
def step_two(name: str, name_length: int):
    print(f"Step two completed for {name}; the name has {name_length} characters.")

@app.get("/")
@DBOS.workflow()
def dbos_workflow(name: str = "world"):
    name_length = step_one(name)
    existing_file = os.path.join(os.path.dirname(__file__), "existing.txt")
    if not os.path.exists(existing_file):
        with open(existing_file, "w"):
            pass
        os._exit(1)
    step_two(name, name_length)

if __name__ == "__main__":
    config: DBOSConfig = {
        "name": "dbos-starter",
        "system_database_url": os.environ.get("DBOS_SYSTEM_DATABASE_URL"),
    }
    DBOS(config=config)
    DBOS.launch()
    uvicorn.run(app, host="0.0.0.0", port=8000)
