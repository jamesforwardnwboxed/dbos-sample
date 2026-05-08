import uvicorn
from dbos import DBOS

from app_runtime import app, build_dbos_config

if __name__ == "__main__":
    DBOS(config=build_dbos_config())
    DBOS.launch()
    uvicorn.run(app, host="0.0.0.0", port=8000)
