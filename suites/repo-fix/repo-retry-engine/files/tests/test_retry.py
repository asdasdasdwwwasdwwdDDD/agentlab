import pytest

from retrykit import run_with_retry


def test_retries_until_success():
    calls = {'n': 0}

    def flaky():
        calls['n'] += 1
        if calls['n'] < 2:
            raise OSError('boom')
        return 'ok'

    assert run_with_retry(flaky, attempts=3) == 'ok'
    assert calls['n'] == 2


def test_gives_up_after_attempts_and_reraises_original_error():
    calls = {'n': 0}

    def always_fails():
        calls['n'] += 1
        raise OSError('disk full')

    with pytest.raises(OSError, match='disk full'):
        run_with_retry(always_fails, attempts=3)
    assert calls['n'] == 3
