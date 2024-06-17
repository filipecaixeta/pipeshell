import re
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from pipeshell import Step, run


# Helper function to assert the output of the print function
# This function will ignore the time taken to execute the command
def assert_stdout(
    mock_print: MagicMock, expected_output: list, same_order: bool = True
):
    actual_output = []
    for call in mock_print.mock_calls:
        actual = re.sub(r"\d+\.\d+", "X", call.args[0])
        actual = re.sub(r"\x1b\[\d+m", "", actual)
        actual_output.append(actual)

    if same_order:
        for i, output in enumerate(expected_output):
            if output != actual_output[i]:
                raise AssertionError(
                    f"Expected output not found: {output}\nActual: {actual_output}"
                )
    else:
        for output in expected_output:
            if output not in actual_output:
                raise AssertionError(
                    f"Expected output not found: {output}\nActual: {actual_output}"
                )


@patch("sys.exit")
@patch("builtins.print")
class TestPipeline(unittest.TestCase):
    def test_single_step(self, mock_print: MagicMock, mock_exit: MagicMock):
        step = Step(name="echo_test", command='echo "Hello, World!"')
        run(step)
        assert_stdout(
            mock_print,
            [
                "echo_test | Hello, World!",
                "\n================================================================================\n",
                "Pipeline finished in 0:00:X\n",
                "echo_test | finished with exit code 0 in X seconds",
                "",
            ],
        )
        mock_exit.assert_not_called()

    def test_step_dependencies(self, mock_print: MagicMock, mock_exit: MagicMock):
        first_step = Step(name="first", command='echo "First step executed"')
        second_step = Step(
            name="second",
            command='echo "Second step executed"',
            dependencies=[first_step],
        )
        run(first_step, second_step)
        assert_stdout(
            mock_print,
            [
                " first | First step executed",
                "second | Second step executed",
                "\n================================================================================\n",
                "Pipeline finished in 0:00:X\n",
                " first | finished with exit code 0 in X seconds",
                "second | finished with exit code 0 in X seconds",
                "",
            ],
            same_order=True,
        )
        mock_exit.assert_not_called()

    def test_failed_dependency(self, mock_print: MagicMock, mock_exit: MagicMock):
        failing_step = Step(name="fail_step", command="exit 1")
        dependent_step = Step(
            name="dependent",
            command='echo "This should not execute"',
            dependencies=[failing_step],
        )
        run(failing_step, dependent_step)
        assert_stdout(
            mock_print,
            [
                "\n================================================================================\n",
                "Pipeline finished in 0:00:X\n",
                "fail_step | finished with exit code 1 in X seconds",
                "dependent | skipped due to failed dependencies",
                "",
            ],
            same_order=True,
        )
        mock_exit.assert_called_once_with(1)

    def test_background_step(self, mock_print: MagicMock, mock_exit: MagicMock):
        background_step = Step(
            name="background",
            command="sleep 1; echo 'background echo'",
            run_in_background=True,
        )
        next_step = Step(
            name="next", command='echo "Next step"', dependencies=[background_step]
        )
        run(background_step, next_step)
        # This should print that the background task is still running when the next step executes
        assert_stdout(
            mock_print,
            [
                "background | background echo",
                "      next | Next step",
                "\n================================================================================\n",
                "Pipeline finished in 0:00:X\n",
                "background | finished with exit code 0 in X seconds",
                "      next | finished with exit code 0 in X seconds",
                "",
            ],
            same_order=True,
        )
        mock_exit.assert_not_called()

    def test_background_step_failure(self, mock_print: MagicMock, mock_exit: MagicMock):
        background_step = Step(
            name="background", command="exit 1", run_in_background=True, verbose=True
        )
        next_step = Step(
            name="next",
            command='echo "Next step"',
            dependencies=[background_step],
            verbose=True,
        )
        run(background_step, next_step)
        assert_stdout(
            mock_print,
            [
                "background | started",
                "background | finished with exit code 1",
                "      next | skipped due to failed dependencies: background",
                "\n================================================================================\n",
                "Pipeline finished in 0:00:X\n",
                "background | finished with exit code 1 in X seconds",
                "      next | skipped due to failed dependencies",
                "",
            ],
            same_order=True,
        )
        mock_exit.assert_called_once_with(1)

    def test_wait_for_log(self, mock_print: MagicMock, mock_exit: MagicMock):
        background_step = Step(
            name="background",
            command="sleep 1; echo 'Server started, listening'; sleep 1; echo 'Server stopped'; exit 1",
            run_in_background=True,
            wait_for_log="Server started, listening",
            allow_failure=True,
        )
        next_step = Step(
            name="next", command='echo "Next step"', dependencies=[background_step]
        )
        run(background_step, next_step)
        assert_stdout(
            mock_print,
            [
                "background | Server started, listening",
                "      next | Next step",
                "background | Server stopped",
                "\n================================================================================\n",
                "Pipeline finished in 0:00:X\n",
                "background | finished with exit code 1 in X seconds",
                "      next | finished with exit code 0 in X seconds",
                "",
            ],
            same_order=True,
        )
        mock_exit.assert_not_called()

    def test_fail_wait_for_log(self, mock_print: MagicMock, mock_exit: MagicMock):
        background_step = Step(
            name="background",
            command="exit 1",
            run_in_background=True,
            wait_for_log="Server started, listening",
            allow_failure=True,
        )
        next_step = Step(
            name="next", command='echo "Next step"', dependencies=[background_step]
        )
        run(background_step, next_step)
        assert_stdout(
            mock_print,
            [
                "\n================================================================================\n",
                "Pipeline finished in 0:00:X\n",
                "background | finished with exit code 1 in X seconds",
                "      next | skipped due to failed dependencies",
                "",
            ],
            same_order=True,
        )
        mock_exit.assert_called_once_with(1)

    def test_retry(self, mock_print, mock_exit):
        fail_until = datetime.now() + timedelta(seconds=1)
        # Fail until 1 second from now and then succeed
        retry_step = Step(
            name="retry",
            command=f"""
                if [ $(date +%s) -lt {int(fail_until.timestamp())} ]; then
                    echo 'Fail';
                    exit 1;
                else
                    echo 'Success';
                    exit 0;
                fi
            """,
            retries=100,
            retry_delay=0.1,
        )
        run(retry_step)
        assert_stdout(
            mock_print,
            [
                "retry | Fail",
                "retry | Success",
                "\n================================================================================\n",
                "Pipeline finished in 0:00:X\n",
                "retry | finished with exit code 0 in X seconds",
                "",
            ],
            same_order=False,
        )
        mock_exit.assert_not_called()


# Run the tests
if __name__ == "__main__":
    unittest.main()
