from queue import Queue
import sys

# Cola global de logs usada por SSE
log_queue = Queue()

def set_log_queue(queue):
    global log_queue
    log_queue = queue

def log(msg: str):
    """Encola mensaje para el SSE."""
    print(msg, file=sys.stderr, flush=True)
    log_queue.put(msg)
