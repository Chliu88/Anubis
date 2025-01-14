from flask import Flask

from anubis_autograde.exercise.get import (
    get_exercises,
    get_active_exercise,
    get_active_exercise_hint,
    get_user_state,
    reset_exercises,
    is_all_complete,
    get_start_message,
    get_end_message,
)
from anubis_autograde.exercise.verify import run_exercise
from anubis_autograde.utils import text_response, reject_handler, complete_reject, colorize_render

app = Flask(__name__)


@app.get('/start')
@text_response
def start():
    message = colorize_render(get_start_message())
    _, exercise = get_active_exercise()
    if exercise.start_message is not None:
        if len(message) > 1:
            message += '\n'
        message += colorize_render(exercise.start_message)
    return message


@app.get('/current')
@text_response
@complete_reject
def current():
    index, _ = get_active_exercise()
    return str(index)


@app.get('/reset')
@text_response
def reset():
    index = reset_exercises()
    return str(index)


@app.get('/status')
@text_response
def status():
    _, current_exercise = get_active_exercise()
    output = 'Exercise Status:\n'
    arrow = colorize_render('->', termcolor_args=('cyan', None, ['blink']))
    for exercise in get_exercises():
        line_start = '  ' if exercise != current_exercise else arrow
        output += f'{line_start} {exercise.name}\n'
    return output.removesuffix('\n')


@app.get('/hint')
@text_response
@complete_reject
def hint():
    return colorize_render(get_active_exercise_hint(), termcolor_args=("yellow",))


@app.post('/submit')
@text_response
@reject_handler
@complete_reject
def submit():
    # Get options from the form
    user_state = get_user_state()
    exercise = run_exercise(user_state)

    win_message = colorize_render(
        exercise.win_message,
        user_exercise_name=user_state.exercise_name,
        user_command=user_state.command,
        user_output=user_state.output,
    )

    _, current_exercise = get_active_exercise()
    if current_exercise is not None and current_exercise.start_message is not None:
        win_message += f'\n{colorize_render(current_exercise.start_message)}'

    if is_all_complete() and get_end_message() is not None:
        win_message += f'\n{colorize_render(get_end_message(), termcolor_args=("yellow",))}'

    return win_message
