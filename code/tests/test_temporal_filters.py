import unittest
import numpy as np
from optical_link.receiver_layers import ewma, kalman


class TemporalFilterTests(unittest.TestCase):
    def test_ewma_recurrence_irregular_time(self):
        t = [0, .1, .3]
        y = [0, 10, 0]
        a = 1-np.exp(-1)
        np.testing.assert_allclose(ewma(t, y, tau_seconds=.1), [0, 10*a, 10*a*np.exp(-2)])

    def test_kalman_hand_computed(self):
        # R=2, P0=2; dt=1 -> Ppred=3, K=3/5, P=6/5.
        # dt=2 -> Ppred=16/5, K=8/13.
        np.testing.assert_allclose(kalman([0, 1, 3], [0, 10, 0],
            q_per_second=1, measurement_variance=2), [0, 6, 30/13])

    def test_constant_and_singleton_and_reset(self):
        for fn in (ewma, kalman):
            np.testing.assert_array_equal(fn([0, .03, .2], [8, 8, 8]), [8, 8, 8])
            np.testing.assert_array_equal(fn([0], [9]), [9])
            fn([0, 1], [100, 200])
            self.assertEqual(fn([0], [7])[0], 7)

    def test_no_future_data(self):
        for fn in (ewma, kalman):
            np.testing.assert_array_equal(fn([0, .1, .3], [1, 20, 100])[:2], fn([0, .1], [1, 20]))

    def test_large_r_and_small_q(self):
        result = kalman(np.arange(100), np.r_[0, np.ones(99)*10],
                        q_per_second=0, measurement_variance=1e6, initial_variance=1)
        self.assertTrue(np.isfinite(result).all())
        self.assertLess(result[-1], .01)

    def test_validation(self):
        for fn in (ewma, kalman):
            for t,y in [([], []), ([0,0],[1,2]), ([1,0],[1,2]), ([0],[np.nan]), ([np.inf],[1]), ([0,1],[2])]:
                with self.assertRaises(ValueError): fn(t,y)
        for tau in (0, -1, np.inf, np.nan):
            with self.assertRaises(ValueError): ewma([0],[1],tau_seconds=tau)
        for kw in ({'q_per_second': -1}, {'measurement_variance': 0},
                   {'initial_variance': 0}, {'measurement_variance': np.inf}):
            with self.assertRaises(ValueError): kalman([0],[1],**kw)
