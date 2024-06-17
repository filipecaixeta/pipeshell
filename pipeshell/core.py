import os
import queue
import subprocess
import time
from datetime import datetime, timedelta
from threading import Event, Lock, Thread
from typing import Dict, List, Optional, Union


class Step:
    """
    A class representing a step in a pipeline.
    """

    def __init__(
        self,
        name: str,
        command: Union[str, list],
        env: Optional[Dict] = None,
        dependencies: Optional[List["Step"]] = None,
        optional_dependencies: Optional[List["Step"]] = None,
        retries: int = 0,
        retry_delay: float = 0.0,
        run_in_background: bool = False,
        wait_for_log: Optional[str] = None,
        allow_failure: bool = False,
        timeout: Optional[float] = None,
        show_output: bool = True,
        env_propagate: bool = True,
        verbose: bool = False,
    ):
        """
        Initialize a Step.

        Args:
            name (str): The name of the step.
            command (Union[str, list]): The command to be executed.
            env (Optional[Dict]): Environment variables to set.
            dependencies (Optional[List[Step]]): Steps that this step depends on.
            optional_dependencies (Optional[List[Step]]): Optional steps that this step depends on.
            retries (int): Number of retries on failure.
            retry_delay (float): Delay between retries in seconds.
            run_in_background (bool): Whether to run this step in the background.
            wait_for_log (Optional[str]): Log message to wait for before starting child dependencies.
            allow_failure (bool): Ignore the exit code of this step.
            timeout (Optional[float]): Timeout for this step in seconds.
            show_output (bool): Whether to show the output.
            env_propagate (bool): Whether to propagate the current environment variables.
            verbose (bool): Whether to show verbose output.
        """
        self.name = name
        self._cmd = command
        self._dependencies = dependencies or []
        self._optional_dependencies = optional_dependencies or []
        self._finished = Event()
        self._mu = Lock()
        self._timeout = timeout
        self._process: subprocess.Popen = None  # type: ignore
        self.exit_code: Union[int, str, None] = None
        self.elapsed_time: Optional[timedelta] = None
        self._show_output = show_output
        self._run_in_background = run_in_background
        self._wait_for_log = wait_for_log
        self._log_found = Event()
        self._ignore_exit_code = allow_failure
        self._retries = retries
        self._retry_delay = retry_delay
        self.start_time: Optional[datetime] = datetime.now() + timedelta(hours=100)
        self._verbose = verbose
        self._env: Dict = {}
        if env_propagate:
            self._env.update(os.environ)
        self._env.update(env or {})

    def _status(self):
        """
        Check the status of the step based on its exit code.

        Returns:
            bool: True if the step is considered successful, False otherwise.
        """
        if self._ignore_exit_code:
            return True
        return self.exit_code == 0

    def __signal__(self, signal: int):
        """
        Send a signal to the process running this step's command.

        Args:
            signal (int): The signal to send.
        """
        self._mu.acquire()
        if self._process:
            self._process.send_signal(signal)
        self._mu.release()

    def __run__(self, stdout_queue: queue.Queue):
        """
        Run the step's command, handling retries, dependencies, and output.
        """
        for dep in self._dependencies:
            dep._finished.wait()
        for dep in self._optional_dependencies:
            dep._finished.wait()

        for dep in self._dependencies:
            if dep.exit_code != 0 and dep.exit_code is not None:
                if self._verbose:
                    stdout_queue.put(
                        (self.name, f"skipped due to failed dependencies: {dep.name}")
                    )
                self.exit_code = "skipped due to failed dependencies"
                return

        args: Dict[str, Dict] = {"env": {}}
        if self._env:
            args["env"] = self._env

        # Run the command
        self.start_time = datetime.now()

        for _ in range(self._retries + 1):
            self._mu.acquire()
            self._process = subprocess.Popen(
                self._cmd,
                **args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True,
                text=True,
            )  # type: ignore
            self._mu.release()

            # Start threads to handle stdout and stderr
            def handle_stream(step_name, stream):
                for line in stream:
                    if self._wait_for_log:
                        if self._wait_for_log in line:
                            self._finished.set()
                            self._log_found.set()
                    if self._show_output:
                        stdout_queue.put((step_name, line))
                stream.close()

            if self._verbose:
                stdout_queue.put((self.name, "started"))

            t_stdout = Thread(
                target=handle_stream, args=(self.name, self._process.stdout)
            )
            t_stderr = Thread(
                target=handle_stream, args=(self.name, self._process.stderr)
            )
            t_stdout.start()
            t_stderr.start()

            # Wait for the process to finish
            try:
                self.exit_code = self._process.wait(timeout=self._timeout)
            except subprocess.TimeoutExpired:
                self.exit_code = "timeout"
                self._process.kill()
                self._process.wait()
            t_stdout.join()
            t_stderr.join()

            if self._verbose:
                stdout_queue.put(
                    (self.name, f"finished with exit code {self.exit_code}")
                )

            if self.exit_code == 0:
                break
            time.sleep(self._retry_delay)

        self.elapsed_time = datetime.now() - self.start_time
        self._finished.set()
