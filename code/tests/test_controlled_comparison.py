"""Ensure CLI selection delegates to the unchanged original controlled engine."""
from pathlib import Path
import csv
import gzip
import importlib.util
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from optical_link.controlled_comparison import run_controlled
from optical_link.coding_experiments import DEFAULT_CONFIG, run_study

ROOT=Path(__file__).resolve().parents[2]


def tool(name):
    directory=str(ROOT/'code/tools')
    if directory not in sys.path: sys.path.insert(0,directory)
    spec=importlib.util.spec_from_file_location('test_tool_'+name,ROOT/'code/tools'/f'{name}.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


class ControlledTests(unittest.TestCase):
    def test_wrapper_matches_original_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/'selected';b=Path(tmp)/'original'
            run_controlled(ROOT,a,trials=1)
            expected=run_study(ROOT/'code',b,dict(DEFAULT_CONFIG,trials_per_condition=1))
            self.assertEqual(json.loads((a/'summary.json').read_text()),expected)
            config=json.loads((a/'config.json').read_text())
            self.assertEqual(config,dict(DEFAULT_CONFIG,trials_per_condition=1))
            self.assertEqual(len(json.loads((a/'scenarios.json').read_text())),24)
            with gzip.open(a/'trials.csv.gz','rt') as stream:rows=list(csv.DictReader(stream))
            self.assertEqual(len(rows),240)
            self.assertEqual({r['depth'] for r in rows},{'1','8'})

    def test_cli_defaults_and_residual_opt_in(self):
        module=tool('run_recording_comparison')
        for option,seed,trials in [([],20261024,2000),(['--simulation','residual'],20261027,200)]:
            with patch.object(module,'run',return_value='out') as run:
                module.main(['--mode','modeled',*option])
            kwargs=run.call_args[1]
            self.assertEqual(kwargs['seed'],seed)
            self.assertEqual(kwargs['trials'],trials)
            self.assertEqual(kwargs['simulation'],'residual' if option else 'controlled')

    def test_batch_runs_shared_controlled_study_once(self):
        module=tool('run_batch_comparison')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);registry=root/'data/screen/prepared'
            for name in ['one','two']:
                folder=registry/name;folder.mkdir(parents=True)
                (folder/'recording.json').write_text(json.dumps(dict(id=name)))
            with patch.object(module,'ROOT',root),patch.object(module.run_recording_comparison,'main') as single,patch('optical_link.controlled_comparison.run_controlled') as sim:
                module.main(['--source','screen','--mode','both','--trials','1'])
            self.assertEqual(single.call_count,2)
            self.assertEqual(sim.call_count,1)
            for call in single.call_args_list:
                command=call[0][0]
                self.assertEqual(command[command.index('--mode')+1],'physical')
            self.assertEqual(sim.call_args[1],dict(seed=20261024,trials=1))


if __name__=='__main__':unittest.main()
