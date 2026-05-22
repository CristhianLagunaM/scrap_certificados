from pathlib import Path
import threading

import requests

from . import config


_thread_local = threading.local()


def get_session() -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=config.HTTP_POOL_SIZE,
            pool_maxsize=config.HTTP_POOL_SIZE,
            max_retries=0,
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        _thread_local.session = session
    return session


def download_pdf(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        response = get_session().get(url, timeout=config.DOWNLOAD_TIMEOUT_SECONDS, stream=True)
    except requests.Timeout as exc:
        raise RuntimeError("Timeout al descargar documento") from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"Error de conexion al descargar documento: {exc}") from exc

    if not response.ok:
        response.close()
        raise RuntimeError(f"Error HTTP al descargar documento: {response.status_code}")

    bytes_written = 0
    with response:
        with destination.open("wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 128):
                if chunk:
                    bytes_written += len(chunk)
                    file.write(chunk)

    if bytes_written == 0 or destination.stat().st_size == 0:
        raise RuntimeError("Archivo descargado vacio")
