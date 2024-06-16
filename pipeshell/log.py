import queue
import re
from threading import Event
from typing import Any, Dict, List

from .core import Step

# Basic ANSI color codes
colors = [
    "\033[32m",  # Green
    "\033[34m",  # Blue
    "\033[35m",  # Magenta
    "\033[36m",  # Cyan
    "\033[33m",  # Yellow
    "\033[31m",  # Red
    "\033[92m",  # Bright Green
    "\033[94m",  # Bright Blue
    "\033[95m",  # Bright Magenta
    "\033[96m",  # Bright Cyan
    "\033[93m",  # Bright Yellow
    "\033[91m",  # Bright Red
]

style_codes = {
    "1": "bold",
    "2": "dim",
    "3": "italic",
    "4": "underline",
    "5": "blink",
    "7": "inverse",
    "8": "hidden",
    "9": "strikethrough",
}

reset_codes = {
    "22": ["bold", "dim"],
    "23": ["italic"],
    "24": ["underline"],
    "25": ["blink"],
    "27": ["inverse"],
    "28": ["hidden"],
    "29": ["strikethrough"],
}


def update_ansi_state(line: str, state: Dict[str, Any]) -> None:
    if not state:
        state.update(
            {
                "bold": False,
                "dim": False,
                "italic": False,
                "underline": False,
                "blink": False,
                "inverse": False,
                "hidden": False,
                "strikethrough": False,
                "foreground": None,
                "background": None,
            }
        )

    ansi_codes = re.findall(r"\033\[[0-9;]*m", line)
    for code in ansi_codes:
        parts = code[2:-1].split(";")
        i = 0
        while i < len(parts):
            part = parts[i]
            if part == "0":  # Reset all styles and colors
                state.update({key: False for key in style_codes.values()})
                state["foreground"], state["background"] = None, None
            elif part in style_codes:  # Set styles
                state[style_codes[part]] = True
            elif part in reset_codes:  # Reset styles
                for reset_style in reset_codes[part]:
                    state[reset_style] = False
            elif part.isdigit():
                int_part = int(part)
                if (
                    30 <= int_part <= 37 or 90 <= int_part <= 97
                ):  # Basic and bright foreground colors
                    state["foreground"] = f"\033[{int_part}m"
                elif (
                    40 <= int_part <= 47 or 100 <= int_part <= 107
                ):  # Basic and bright background colors
                    state["background"] = f"\033[{int_part}m"
                elif part == 38 and parts[i + 1] == "5":  # 256-color foreground
                    state["foreground"] = f"\033[38;5;{parts[i + 2]}m"
                    i += 2
                elif part == 48 and parts[i + 1] == "5":  # 256-color background
                    state["background"] = f"\033[48;5;{parts[i + 2]}m"
                    i += 2
                elif part == 38 and parts[i + 1] == "2":  # Truecolor foreground
                    state[
                        "foreground"
                    ] = f"\033[38;2;{parts[i + 2]};{parts[i + 3]};{parts[i + 4]}m"
                    i += 4
                elif part == 48 and parts[i + 1] == "2":  # Truecolor background
                    state[
                        "background"
                    ] = f"\033[48;2;{parts[i + 2]};{parts[i + 3]};{parts[i + 4]}m"
                    i += 4
            i += 1


def build_ansi_code(state: Dict[str, Any]) -> str:
    # Construct the full ANSI sequence from the current state
    codes = []
    for key, value in state.items():
        if value:
            if key in style_codes.values() and value is True:
                codes.append(
                    list(style_codes.keys())[list(style_codes.values()).index(key)]
                )
            elif key in ["foreground", "background"] and value is not None:
                # Append full ANSI code for colors
                codes.append(value[2:-1])

    return "\033[" + ";".join(codes) + "m" if codes else "\033[0m"


def print_stdout(
    steps: List[Step], stdout_queue: queue.Queue, all_steps_finished: Event
):
    names = [step.name for step in steps]
    max_name_len = max(map(len, names))

    # Assign a color to each step, cycle through colors if there are more steps than colors
    step_colors = {name: colors[i % len(colors)] for i, name in enumerate(names)}

    # Map to maintain the current ANSI state for each step
    current_ansi_state: Dict[str, Dict] = {name: {} for name in names}

    while not all_steps_finished.is_set() or not stdout_queue.empty():
        try:
            step_name, line = stdout_queue.get(timeout=0.01)
        except queue.Empty:
            continue

        if step_name is None:
            if line is None:
                # resets everything
                current_ansi_state = {name: {} for name in names}
                continue
            print("\033[0m" + line + "\033[0m")
            continue

        # Extract ANSI codes from the line
        codes = build_ansi_code(current_ansi_state[step_name])
        update_ansi_state(line, current_ansi_state[step_name])
        # Prepare the output line with step-specific color and maintained ANSI state
        color = step_colors[step_name]
        step_name_formatted = f"{color}{step_name.rjust(max_name_len)}\033[0m"
        print(f"{step_name_formatted} | {codes}{line.rstrip()}\033[0m")

    print("\033[0m")
