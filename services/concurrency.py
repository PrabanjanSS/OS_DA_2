import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Any
from functools import wraps

# Thread pool for async validation tasks
executor = ThreadPoolExecutor(max_workers=4)

# Locks for critical sections (mutual exclusion)
attempt_lock = threading.Lock()
log_lock = threading.Lock()
# Guards question-pool allocation: the "who already has what" read and the
# "write my allocation" step must not interleave, or two students starting at
# the same moment could be handed the same questions.
allocation_lock = threading.Lock()

def run_in_thread(func: Callable, *args, **kwargs) -> Any:
    """
    Submit a function to be executed in the thread pool.
    Returns a Future object.
    """
    return executor.submit(func, *args, **kwargs)

def with_lock(lock: threading.Lock):
    """
    Decorator to execute a function with a lock (mutual exclusion).
    Prevents race conditions on shared resources.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with lock:  # Critical section - only one thread at a time
                return func(*args, **kwargs)
        return wrapper
    return decorator

def attempt_counter(student_id: int, set_id: int, check_and_increment: Callable) -> bool:
    """
    Thread-safe attempt counter using lock.
    Demonstrates critical section and mutual exclusion.
    """
    with attempt_lock:
        return check_and_increment(student_id, set_id)

def log_submission(log_data: Callable) -> Any:
    """
    Thread-safe logging using lock.
    """
    with log_lock:
        return log_data()
