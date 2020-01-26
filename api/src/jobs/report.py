import docker
import requests


from .utils import report_panic, PipelineException


def report(client, repo_url, submission, volume_name):
    """
    Report results of tests to api

    :client docker.client: docker clien
    :netid str: netid of student
    :assignment: name of assignment being tested
    :submission Submissions: id of submission
    :volume_name str: name of persistent volume
    """

    netid=submission.netid
    assignment=submission.assignment

    name = '{netid}-{commit}-{assignment}-{id}-report'.format(
        netid=submission.netid,
        commit=submission.commit,
        assignment=submission.assignment,
        id=submission.id,
    )

    try:
        container=client.containers.run(
            'os3224-report',
            name=name,
            command=['python3', 'main.py', netid, assignment, str(submission.id)],
            network='traefik-proxy',
            detach=True,
            volumes={
                volume_name: {
                    'bind': '/mnt/submission',
                    'mode': 'rw',
                },
            },
        )
        container.wait(timeout=10)
        container.reload()
        logs = container.logs().decode()

        # Check that the container had a successful exit code
        if container.attrs['State']['ExitCode'] != 0:
            raise PipelineException('report failue')

    except PipelineException as e:
        raise report_panic(str(e) + '\n' + logs, submission.id)

    except requests.exceptions.ReadTimeout:
        # Kill container if it has reached its timeout
        container.kill()
        raise report_panic('report timeout\n', submission.id)

    finally:
        container=client.containers.get(name)
        container.remove(force=True)
