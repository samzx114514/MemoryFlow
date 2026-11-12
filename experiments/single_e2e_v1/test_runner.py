import unittest

from .runner import interval_union, locate, paired


class EndToEndProtocolTest(unittest.TestCase):
    def test_targets_can_move_but_ambiguous_changed_repeats_are_not_assumed(self):
        target={'text':'fact','span':[0,4]}
        found,missing=locate('prefix fact','fact',[target])
        self.assertEqual(found[0]['span'],[7,11])
        self.assertFalse(missing)
        found,missing=locate('fact fact','fact',[target])
        self.assertFalse(found)
        self.assertEqual(missing[0]['reason'],'ambiguous_after_regeneration')
        found,missing=locate('changed','fact',[target])
        self.assertEqual(missing[0]['reason'],'absent')

    def test_frozen_repeated_occurrence_maps_to_corresponding_actual_rows(self):
        targets=[{'text':'fact','span':[6,10]}]
        found,missing=locate('prefix fact. fact','fact. fact',targets)
        self.assertEqual(found[0]['span'],[13,17])
        self.assertFalse(missing)

    def test_pair_denominator_is_common_targets_and_time_is_not_stage_sum(self):
        yf={'located_target_ids':['a:0','a:1','b:0'],'wall_seconds':12,
            'output_tokens_by_call':{'a':'same','b':'left'},'planned_targets':3}
        mf={'located_target_ids':['a:0','b:0'],'wall_seconds':18,
            'output_tokens_by_call':{'a':'same','b':'right'},'planned_targets':3}
        p=paired(yf,mf)
        self.assertEqual(p['common_targets'],2)
        self.assertEqual(p['planned_targets'],3)
        self.assertEqual(p['yf_seconds_per_common_target'],6)
        self.assertEqual(p['mf_seconds_per_common_target'],9)
        self.assertEqual(p['same_output_tokens_calls'],1)

    def test_shared_parallel_intervals_are_counted_once(self):
        self.assertEqual(interval_union([[1,5],[2,4],[4,8],[10,11]]),8)
        self.assertEqual(interval_union([]),0)
