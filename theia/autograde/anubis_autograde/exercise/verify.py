import os
import traceback

from anubis_autograde.exercise.find import find_exercise
from anubis_autograde.exercise.get import get_exercises
from anubis_autograde.logging import log
from anubis_autograde.models import UserState, Exercise, FileSystemCondition, ExistState, EnvVarCondition
from anubis_autograde.utils import RejectionException, expand_path


def verify_exercise(user_state: UserState) -> Exercise:
    exercise, _ = find_exercise(user_state.exercise_name)
    if exercise is None:
        raise RejectionException('Exercise not found!')
    return exercise


def verify_required(exercise: Exercise, _: UserState):
    _, index = find_exercise(exercise.name)
    exercises = get_exercises()

    for required_exercise_index in range(index):
        required_exercise = exercises[required_exercise_index]
        if not required_exercise.complete:
            raise RejectionException(f'Required exercise not complete: {required_exercise.name}')


def verify_command_regex(exercise: Exercise, user_state: UserState):
    # Check command against regex
    if exercise.command_regex is None:
        return

    log.info(f'exercise.command_regex = {exercise.command_regex}')

    command_match = exercise.command_regex.match(user_state.command)
    if command_match is None:
        raise RejectionException('Sorry your command does not seem right.')


def verify_cwd_regex(exercise: Exercise, user_state: UserState):
    # Check cwd against regex
    if exercise.cwd_regex is None:
        return

    log.info(f'exercise.cwd_regex = {exercise.cwd_regex}')

    cwd_match = exercise.cwd_regex.match(user_state.cwd)
    if cwd_match is None:
        raise RejectionException('Sorry your current working directory does not seem right.')


def verify_output_regex(exercise: Exercise, user_state: UserState):
    # Check output against regex
    if exercise.output_regex is None:
        return

    log.info(f'exercise.command_regex = {exercise.command_regex}')

    output_match = exercise.output_regex.match(user_state.output)
    if output_match is None:
        raise RejectionException('Sorry your output does not seem right.')


def verify_filesystem_conditions(exercise: Exercise, user_state: UserState):
    if exercise.filesystem_conditions is None:
        return

    for filesystem_condition in exercise.filesystem_conditions:
        filesystem_condition: FileSystemCondition
        base_path = user_state.cwd if filesystem_condition.relative else os.environ['HOME']
        path = os.path.join(base_path, filesystem_condition.path)
        path = expand_path(path)

        exists = os.path.exists(path)
        isdir = os.path.isdir(path)

        # Check State
        if filesystem_condition.state == ExistState.PRESENT and not exists:
            raise RejectionException(f'File or Directory: {path} should exist')
        if filesystem_condition.state != ExistState.PRESENT and exists:
            raise RejectionException(f'File or Directory: {path} should not exist')

        # Check directory
        if filesystem_condition.directory and not isdir:
            raise RejectionException(f'File: {path} should be a directory')
        if not filesystem_condition.directory and isdir:
            raise RejectionException(f'Directory: {path} should be a file')

        # Check content
        if filesystem_condition.content is not None:
            with open(path, 'r') as f:
                content = f.read()
                if content != filesystem_condition.content:
                    raise RejectionException(f'File: {path} does not match expected content')

        # Check content regex
        if filesystem_condition.content_regex is not None:
            with open(path, 'r') as f:
                content = f.read()
                content_match = filesystem_condition.content_regex.match(content)
                if content_match is None:
                    raise RejectionException(f'File: {path} does not match expected content')


def verify_env_var_conditions(exercise: Exercise, user_state: UserState):
    if exercise.env_var_conditions is None:
        return

    for env_var_condition in exercise.env_var_conditions:
        env_var_condition: EnvVarCondition

        name = env_var_condition.name
        value = user_state.environ.get(name, None)
        exists = value is not None

        if env_var_condition.state == ExistState.ABSENT and exists:
            raise RejectionException(f'Environment Variable: "{name}" should not be set')
        if env_var_condition.state == ExistState.PRESENT and not exists:
            raise RejectionException(f'Environment Variable: "{name}" should be set')

        if env_var_condition.value_regex is not None:
            value_match = env_var_condition.value_regex.match(value)
            if value_match is None:
                raise RejectionException(f'Environment Variable: "{name}" does not match expected value')


def run_eject_function(exercise: Exercise, user_state: UserState):
    log.info(f'Running eject function for exercise={exercise} user_state={user_state}')
    try:
        complete = exercise.eject_function(exercise, user_state)

        # Verify that the return value for the eject function is actually a bool
        if not isinstance(complete, bool):
            log.error(f'return of eject_function for {exercise.name} was not bool complete={complete}')
            return

        exercise.complete = complete
    except Exception:
        log.error(f'{traceback.format_exc()}\neject_function for {exercise.name} threw error')


def run_exercise(user_state: UserState) -> Exercise:
    exercise = verify_exercise(user_state)
    verify_required(exercise, user_state)

    # If eject function specified, then run that and return
    if exercise.eject_function is not None:
        run_eject_function(exercise, user_state)
        return exercise

    verify_command_regex(exercise, user_state)
    verify_output_regex(exercise, user_state)
    verify_cwd_regex(exercise, user_state)
    verify_filesystem_conditions(exercise, user_state)
    verify_env_var_conditions(exercise, user_state)

    exercise.complete = True

    return exercise
