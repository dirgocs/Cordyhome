from __future__ import annotations

import logging

import uvicorn

from .app import create_app
from .config import Config


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    config = Config.from_env()
    app = create_app(config)
    logging.getLogger("cordyhome").info(
        "Cordyhome em http://%s:%s (dados em %s)", config.host, config.port, config.data_dir
    )
    uvicorn.run(app, host=config.host, port=config.port, log_level="warning", proxy_headers=True)


if __name__ == "__main__":
    main()
