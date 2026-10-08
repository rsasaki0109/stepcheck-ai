"""Given instructions must not become evidence or a fabricated successful order."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_qwen3_video_flow import parse_verification, parse_window_verification, aggregate_windows


class ReferenceVerificationTests(unittest.TestCase):
    def setUp(self):
        self.reference={"title":"Reference", "steps":[{"id":"a","label":"A"},{"id":"b","label":"B"}]}
        self.pairs=[[0,2],[4,6],[8,10]]

    def response(self,a,b,status="observed"):
        return json.dumps({"steps":[{"step_id":"a","status":status,"reason":"Visible",
            "evidence_pair_ids":a,"uncertainty":""},{"step_id":"b","status":"observed",
            "reason":"Visible","evidence_pair_ids":b,"uncertainty":""}]})

    def test_reference_reversal_changes_order_without_changing_video_evidence(self):
        raw=self.response([0],[2])
        normal=parse_verification(raw,self.reference,self.pairs,4)
        reverse=parse_verification(raw,{**self.reference,"steps":self.reference['steps'][::-1]},self.pairs,4)
        self.assertEqual(normal['order_status'],'supported_sample_order')
        self.assertEqual(reverse['order_status'],'violated')
        self.assertEqual(normal['steps'][0]['evidence_seconds'],[0,.5])
        self.assertEqual(reverse['steps'][1]['evidence_seconds'],[0,.5])

    def test_overlap_and_unknown_do_not_pass_order(self):
        self.assertEqual(parse_verification(self.response([0],[0]),self.reference,self.pairs,4)['order_status'],'unknown')
        self.assertEqual(parse_verification(self.response([], [2], 'unknown'),self.reference,self.pairs,4)['order_status'],'unknown')

    def test_invalid_citations_and_unsupported_success_rejected(self):
        for invalid in ([],[-1],[3],[1.5],[True]):
            with self.assertRaises(ValueError):
                parse_verification(self.response(invalid,[2]),self.reference,self.pairs,4)

    def test_missing_duplicate_or_invented_steps_rejected(self):
        payload=json.loads(self.response([0],[2]))
        for steps in ([payload['steps'][0]], [payload['steps'][0]]*2,
                      [{**payload['steps'][0],'step_id':'invented'},payload['steps'][1]]):
            with self.assertRaises(ValueError):
                parse_verification(json.dumps({'steps':steps}),self.reference,self.pairs,4)

    def test_sparse_windows_preserve_absolute_citations_and_unreported_unknown(self):
        raw=json.dumps({'steps':[json.loads(self.response([0],[2]))['steps'][0]]})
        window=parse_window_verification(raw,self.reference,[[48,50],[52,54]],4)
        result=aggregate_windows(self.reference,[{'window':'part-3',**window}])
        self.assertEqual(result['steps'][0]['evidence_seconds'],[12,12.5])
        self.assertEqual(result['steps'][1]['status'],'unknown')
        self.assertEqual(result['order_status'],'unknown')

    def test_aggregation_does_not_filter_bad_or_conflicting_model_times(self):
        windows=[{'window':'part-1','steps':[
            {'step_id':'a','status':'observed','evidence_seconds':[2,10]},
            {'step_id':'b','status':'observed','evidence_seconds':[3]}]},
            {'window':'part-3','steps':[{'step_id':'b','status':'observed','evidence_seconds':[12]}]}]
        result=aggregate_windows(self.reference,windows)
        self.assertEqual(result['steps'][1]['evidence_seconds'],[3,12])
        self.assertEqual(result['order_status'],'unknown')

    def test_sparse_windows_still_reject_false_evidence(self):
        bad={'steps':[json.loads(self.response([3],[2]))['steps'][0]]}
        with self.assertRaises(ValueError):
            parse_window_verification(json.dumps(bad),self.reference,self.pairs,4)


if __name__=='__main__':unittest.main()
