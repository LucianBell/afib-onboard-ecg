import numpy as np

from src.decision import alert_condition, count_alerts, episode_detection, rolling_votes, window_states


def test_window_states():
    s = window_states([True, True, True, False, True], [0.9, 0.2, 0.001, 0.9, 0.95], 0.01,
                      [False, False, False, False, True])
    assert list(s) == ["AFIB", "INCERTO", "NAO_AFIB", "SINAL_RUIM", "INCERTO"]


def test_rolling_and_alerts():
    v = np.array([1, 0, 1, 1, 0, 0, 0, 1, 1, 1], bool)
    assert rolling_votes(v, 3).tolist() == [1, 1, 2, 2, 2, 1, 0, 1, 2, 3]
    cond = alert_condition(v, 2, 3)
    assert count_alerts(cond) == 2  # dois episódios contínuos da condição


def test_episode_detection_all_positive():
    rng = np.random.default_rng(0)
    det, first = episode_detection(np.zeros(100, bool), np.ones(100, bool), 3, 5, 10, 50, rng)
    assert det.all() and (first == 3).all()
    det, _ = episode_detection(np.zeros(100, bool), np.zeros(100, bool), 1, 1, 10, 50, rng)
    assert not det.any()
