import unittest
import pandas as pd
from optical_link.campaign_diagnostics import error_runs,map_errors,paired_change,duration_bounds

class CampaignDiagnosticsTests(unittest.TestCase):
    def test_runs_are_contiguous_and_packet_local(self):
        self.assertEqual(error_runs([7,1,2,3,5],8),[3,1,1])
        self.assertEqual(error_runs([],8),[])
        with self.assertRaises(ValueError):error_runs([1,1],8)
        with self.assertRaises(ValueError):error_runs([8],8)

    def test_real_ragged_hamming_and_rectangular_rs_mapping(self):
        h=map_errors([50,52],140,8,7)
        self.assertEqual(h['coded_indices'],[42,78]);self.assertEqual(h['correction_groups'],[6,11])
        r=map_errors([43,44,45,47],112,8,8)
        self.assertEqual(r['coded_indices'],[47,61,75,103])
        self.assertEqual(r['correction_groups'],[5,7,9,12]);self.assertEqual(r['affected_groups'],4)

    def test_pairing_uses_trial_identity_and_preserves_harms(self):
        f=pd.DataFrame([dict(trial=i,depth=d,success=x) for i,pair in enumerate([(0,1),(0,1),(1,0),(1,1)]) for d,x in zip([1,8],pair)])
        r=paired_change(f.sample(frac=1,random_state=4));self.assertEqual(r['change'],.25)
        self.assertEqual((r['rescued'],r['harmed'],r['unchanged']),(2,1,1))
        self.assertLess(r['ci_low'],r['change']);self.assertGreater(r['ci_high'],r['change'])
        with self.assertRaises(ValueError):paired_change(f.iloc[:-1])

    def test_duration_brackets_are_not_point_estimates(self):
        lo,hi=duration_bounds([35.5,35.9],[36.7,37.1])
        self.assertAlmostEqual(lo,.8);self.assertAlmostEqual(hi,1.6)
        with self.assertRaises(ValueError):duration_bounds([2,3],[1,2])

if __name__=='__main__':unittest.main()
