import os
import queue
import signal
import sys
from datetime import datetime
from threading import Event, Thread

from .core import Step
from .log import print_stdout


def gather_all_steps(initial_steps):
    visited = set()

    def traverse(steps):
        for step in steps:
            if step not in visited:
                visited.add(step)
                if step._dependencies:
                    traverse(step._dependencies)

    traverse(initial_steps)
    return visited


def run(*steps: Step):
    stdout_queue: queue.Queue = queue.Queue()
    all_steps_finished: Event = Event()
    steps_threads = []

    start_time = datetime.now()
    all_steps = gather_all_steps(steps)

    t_print = Thread(
        target=print_stdout, args=(all_steps, stdout_queue, all_steps_finished)
    )
    t_print.start()

    # Register the signal handler
    sig_count = 0

    def signal_handler(signum, frame):
        print("Received signal", signum)
        nonlocal sig_count
        sig_count += 1
        if sig_count > 1:
            for step in all_steps:
                step.__signal__(signal.SIGKILL)
            sys.exit(1)
        for step in all_steps:
            step.__signal__(signum)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    for step in all_steps:
        t = Thread(target=step.__run__, args=(stdout_queue,))
        t.start()
        steps_threads.append(t)

    for t in steps_threads:
        t.join()

    success = all(step._status() for step in all_steps)
    message_color = "\033[92m" if success else "\033[91m"
    stdout_queue.put((None, None))
    try:
        columns = os.get_terminal_size().columns
    except OSError:
        columns = 80

    stdout_queue.put((None, f"\n{message_color}" + "=" * columns + "\n"))
    stdout_queue.put((None, f"Pipeline finished in {datetime.now() - start_time}\n"))
    all_steps = sorted(all_steps, key=lambda x: x.start_time)
    for step in all_steps:
        if isinstance(step.exit_code, int):
            message_color = "\033[92m" if step.exit_code == 0 else "\033[91m"
            stdout_queue.put(
                (
                    step.name,
                    f"{message_color}finished with exit code {step.exit_code} in {step.elapsed_time.total_seconds()} seconds\n",
                )
            )
        else:
            stdout_queue.put((step.name, f"\033[91m{step.exit_code}\n"))

    all_steps_finished.set()
    t_print.join()

    if not success:
        sys.exit(1)


def pipeline(name: str, *steps: Step):
    if len(sys.argv) > 1 and sys.argv[1] == name:
        run(*steps)
