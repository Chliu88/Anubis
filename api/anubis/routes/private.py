import json
import random
import traceback
from typing import List, Dict

from dateutil.parser import parse as date_parse, ParserError
from flask import request, Blueprint, Response
from sqlalchemy import or_, and_

from anubis.models import db, User, Submission, Assignment, AssignmentQuestion, AssignedStudentQuestion
from anubis.utils.auth import get_token
from anubis.utils.cache import cache
from anubis.utils.data import regrade_submission, is_debug
from anubis.utils.data import success_response, error_response
from anubis.utils.decorators import json_response, json_endpoint, load_from_id
from anubis.utils.elastic import log_endpoint
from anubis.utils.redis_queue import enqueue_webhook_rpc
from anubis.utils.logger import logger
from anubis.utils.data import fix_dangling, bulk_stats, get_students, _verify_data_shape

private = Blueprint('private', __name__, url_prefix='/private')


@private.route('/')
def private_index():
    return 'super duper secret'


@private.route('/token/<netid>')
def private_token_netid(netid):
    user = User.query.filter_by(netid=netid).first()
    if user is None:
        return error_response('User does not exist')
    token = get_token(user.netid)
    res = Response(json.dumps(success_response(token)), headers={'Content-Type': 'application/json'})
    res.set_cookie('token', token, httponly=True)
    return res


@private.route('/assignment/<id>/questions/assign')
@log_endpoint('cli', lambda: 'question assign')
@load_from_id(Assignment, verify_owner=False)
@json_response
def private_assignment_question_assign(assignment: Assignment):
    """

    :return:
    """
    AssignedStudentQuestion.query.filter(
        AssignedStudentQuestion.assignment_id == assignment.id
    ).delete()

    raw_questions = AssignmentQuestion.query.filter(
        AssignmentQuestion.assignment_id == assignment.id,
    ).all()

    sequences = list(set(question.sequence for question in raw_questions))
    questions = {sequence: [] for sequence in sequences}
    for question in raw_questions:
        questions[question.sequence].append(question)

    logger.debug('sequences -> ' + str(sequences))
    logger.debug('questions -> ' + str(questions))

    assigned_questions = []
    students = User.query.all()
    logger.debug('students -> ' + str(len(questions)))
    for student in students:
        for sequence, qs in questions.items():
            selected_question = random.choice(qs)
            logger.debug('selected -> ' + str(selected_question.data))
            assigned_question = AssignedStudentQuestion(
                owner=student,
                assignment=assignment,
                question=selected_question,
                response=selected_question.placeholder,
            )
            assigned_questions.append(assigned_question.data)
            db.session.add(assigned_question)

    db.session.commit()
    return success_response({'assigned': assigned_questions})


@private.route('/assignment/<id>/question/sync', methods=['POST'])
@log_endpoint('cli', lambda: 'question sync')
@load_from_id(Assignment, verify_owner=False)
@json_endpoint(required_fields=[('questions', list)])
def private_assignment_question_sync(assignment: Assignment, questions: List[Dict] = None, **kwargs):
    """
    Additive endpoint for assignment questions. Questions will only be created
    if they have not been seen yet.

    In the response, all the questions you've posted will appear to be

    body = {
      questions: [
        {
          question: str
          solution: str
          sequence: int
        },
        ...
      ]
    }

    response = {
      rejected: [ ... ]
      ignored: [ ... ]
      accepted: [ ... ]
    }

    :param assignment: Assignment object
    :param questions: list of question data
    :return:
    """

    # Iterate over questions
    rejected, ignored, accepted = [], [], []
    for question in questions:
        # Verify the fields of the question shape
        shape_good, _ = _verify_data_shape(question, AssignmentQuestion.shape)
        if not shape_good:
            # Reject the question if the shape is bad and continue
            rejected.append({
                'question': question,
                'reason': 'could not verify data shape'
            })
            continue

        # Check to see if question already exists for the current assignment
        exists = AssignmentQuestion.query.filter(
            AssignmentQuestion.assignment_id == assignment.id,
            AssignmentQuestion.question == question['question']
        ).first()
        if exists is not None:
            # If the question exists, ignore it and continue
            ignored.append({
                'question': question,
                'reason': 'already exists'
            })
            continue

        # Create the new question from posted data
        assignment_question = AssignmentQuestion(
            assignment_id=assignment.id,
            question=question['question'],
            solution=question['solution'],
            sequence=question['sequence'],
        )
        db.session.add(assignment_question)
        accepted.append({'question': question})

    db.session.commit()
    return success_response({
        'accepted': accepted,
        'ignored': ignored,
        'rejected': rejected,
    })


@private.route('/assignment/sync', methods=['POST'])
@log_endpoint('cli', lambda: 'assignment-sync')
@json_endpoint(required_fields=[('assignment', dict), ('tests', list)])
def private_assignment_sync(assignment_data: dict, tests: List[str]):
    logger.debug("/private/assignment/sync meta: {}".format(json.dumps(assignment_data, indent=2)))
    logger.debug("/private/assignment/sync tests: {}".format(json.dumps(tests, indent=2)))
    # Find the assignment
    a = Assignment.query.filter(
        Assignment.unique_code == assignment_data['unique_code']
    ).first()

    # Attempt to find the class
    c = Class_.query.filter(
        or_(Class_.name == assignment_data["class"],
            Class_.class_code == assignment_data["class"])
    ).first()
    if c is None:
        return error_response('Unable to find class')

    # Check if it exists
    if a is None:
        a = Assignment(unique_code=assignment_data['unique_code'])

    # Update fields
    a.name = assignment_data['name']
    a.hidden = assignment_data['hidden']
    a.description = assignment_data['description']
    a.pipeline_image = assignment_data['pipeline_image']
    a.class_ = c
    try:
        a.release_date = date_parse(assignment_data['date']['release'])
        a.due_date = date_parse(assignment_data['date']['due'])
        a.grace_date = date_parse(assignment_data['date']['grace'])
    except ParserError:
        logger.error(traceback.format_exc())
        return error_response('Unable to parse datetime'), 406

    db.session.add(a)
    db.session.commit()

    for i in AssignmentTest.query.filter(
    and_(AssignmentTest.assignment_id == a.id,
         AssignmentTest.name.notin_(tests))
    ).all():
        db.session.delete(i)
    db.session.commit()

    for test_name in tests:
        at = AssignmentTest.query.filter(
            Assignment.id == a.id,
            AssignmentTest.name == test_name,
        ).join(Assignment).first()

        if at is None:
            at = AssignmentTest(assignment=a, name=test_name)
            db.session.add(at)
            db.session.commit()

    return success_response({
        'assignment': a.data,
    })


@private.route('/dangling')
@log_endpoint('cli', lambda: 'dangling')
@json_response
def private_dangling():
    """
    This route should hand back a json list of all submissions that are dangling.
    Dangling being that we have no netid to match to the github username that
    submitted the assignment.
    """

    dangling = Submission.query.filter(
        Submission.owner_id == None,
    ).all()
    dangling = [a.data for a in dangling]

    return success_response({
        "dangling": dangling,
        "count": len(dangling)
    })


@private.route('/reset-dangling')
@log_endpoint('reset-dangling', lambda: 'reset-dangling')
@json_response
def private_reset_dangling():
    resets = []
    for s in Submission.query.filter_by(owner_id=None).all():
        s.init_submission_models()
        resets.append(s.data)
    return success_response({'reset': resets})


@private.route('/regrade-submission/<commit>')
@log_endpoint('cli', lambda: 'regrade-commit')
@json_response
def private_regrade_submission(commit):
    s = Submission.query.filter(
        Submission.commit == commit,
        Submission.owner_id != None,
    ).first()

    if s is None:
        return error_response('not found')

    s.init_submission_models()
    enqueue_webhook_rpc(s.id)

    return success_response({
        'submission': s.data,
        'user': s.owner.data
    })


@private.route('/regrade/<assignment_name>')
@log_endpoint('cli', lambda: 'regrade')
@json_response
def private_regrade_assignment(assignment_name):
    """
    This route is used to restart / re-enqueue jobs.

    TODO verify fields that this endpoint is processing

    body = {
      netid
    }

    body = {
      netid
      commit
    }
    """
    assignment = Assignment.query.filter_by(
        name=assignment_name
    ).first()

    if assignment is None:
        return error_response('cant find assignment')

    submission = Submission.query.filter(
        Submission.assignment_id == assignment.id,
        Submission.owner_id != None
    ).all()

    response = []

    for s in submission:
        res = regrade_submission(s)
        response.append({
            'submission': s.id,
            'commit': s.commit,
            'netid': s.netid,
            'success': res['success'],
        })

    return success_response({'submissions': response})


@private.route('/fix-dangling')
@log_endpoint('cli', lambda: 'fix-dangling')
@json_response
def private_fix_dangling():
    return fix_dangling()


@private.route('/stats/<assignment_id>')
@private.route('/stats/<assignment_id>/<netid>')
@log_endpoint('cli', lambda: 'stats')
@json_response
def private_stats_assignment(assignment_id, netid=None):
    netids = request.args.get('netids', None)

    if netids is not None:
        netids = json.loads(netids)
    elif netid is not None:
        netids = [netid]
    else:
        netids = list(map(lambda x: x['netid'], get_students()))

    bests = bulk_stats(assignment_id, netids)
    return success_response({'stats': bests})


from anubis.models import SubmissionTestResult, SubmissionBuild
from anubis.models import AssignmentTest, AssignmentRepo, InClass, Class_

if is_debug():
    @private.route('/seed')
    @json_response
    def private_seed():
        # Yeet
        SubmissionTestResult.query.delete()
        SubmissionBuild.query.delete()
        Submission.query.delete()
        AssignmentRepo.query.delete()
        AssignmentTest.query.delete()
        InClass.query.delete()
        Assignment.query.delete()
        Class_.query.delete()
        User.query.delete()
        db.session.commit()

        # Create
        u = User(netid='jmc1283', github_username='juan-punchman', name='John Cunniff', is_admin=True)
        c = Class_(name='Intro to OS', class_code='CS-UY 3224', section='A', professor='Gustavo')
        ic = InClass(owner=u, class_=c)
        user_items = [u, c, ic]

        # Assignment 1 uniq
        a1 = Assignment(name='uniq', pipeline_image="registry.osiris.services/anubis/assignment/1",
                       hidden=False, release_date='2020-08-22 23:55:00', due_date='2020-08-22 23:55:00', class_=c,
                       github_classroom_url='')
        a1t1 = AssignmentTest(name='Long file test', assignment=a1)
        a1t2 = AssignmentTest(name='Short file test', assignment=a1)
        a1r1 = AssignmentRepo(owner=u, assignment=a1, repo_url='https://github.com/juan-punchman/xv6-public.git',
                              github_username='juan-punchman')
        a1s1 = Submission(commit='test', state='Waiting for resources...', owner=u, assignment=a1,
                        repo=a1r1)
        a1s2 = Submission(commit='0001', state='Waiting for resources...', owner=u, assignment=a1, repo=a1r1)
        assignment_1_items = [a1, a1t1, a1t2, a1r1, a1s1, a1s2]

        # Assignment 2 tail
        a2 = Assignment(name='tail', pipeline_image="registry.osiris.services/anubis/assignment/f1295ac4",
                        unique_code='f1295ac4',
                       hidden=False, release_date='2020-09-03 23:55:00', due_date='2020-09-03 23:55:00', class_=c,
                       github_classroom_url='')
        a2t1 = AssignmentTest(name='Hello world test', assignment=a2)
        a2t2 = AssignmentTest(name='Short file test', assignment=a2)
        a2t3 = AssignmentTest(name='Long file test', assignment=a2)
        a2r2 = AssignmentRepo(owner=u, assignment=a2, repo_url='https://github.com/os3224/assignment-1-spring2020.git',
                              github_username='juan-punchman')
        a2s1 = Submission(commit='2bc7f8d636365402e2d6cc2556ce814c4fcd1489', state='Waiting for resources...', owner=u, assignment=a2,
                        repo=a1r1)
        assignment_2_items = [a2, a2t1, a2t2, a2t3, a2r2, a2s1]

        # Commit
        db.session.add_all(user_items)
        db.session.add_all(assignment_1_items)
        db.session.add_all(assignment_2_items)
        db.session.commit()

        # Init models
        a1s1.init_submission_models()
        a1s2.init_submission_models()
        a2s1.init_submission_models()

        enqueue_webhook_rpc(a2s1.id)

        return success_response('seeded')