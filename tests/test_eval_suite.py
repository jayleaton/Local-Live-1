from jarvis.eval.runner import run_suite_sync


def test_phase0_eval_suite_all_pass():
    outcomes = run_suite_sync()
    failures = [(o.name, o.detail) for o in outcomes if not o.passed]
    assert not failures, f"eval failures: {failures}"
    assert len(outcomes) >= 10
