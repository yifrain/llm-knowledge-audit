import json
import logging
from typing import Any


def event(name: str, **fields: Any) -> None:
    logging.getLogger("llmka").info(json.dumps({"event": name, **fields}, sort_keys=True))
