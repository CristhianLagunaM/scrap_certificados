from queue import Queue

# Cola global de logs usada por SSE
log_queue = Queue()

def log(msg: str):
    """Encola mensaje para el SSE."""
    log_queue.put(msg)
