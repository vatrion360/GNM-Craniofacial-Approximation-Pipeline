import json
from pathlib import Path

from scripts.run_baseline import main


def test_baseline_replay_and_drift(tmp_path, marker_file, model_file, monkeypatch, capsys):
    suite = tmp_path / 'suite.json'
    config = {'full': ['--input', marker_file.name, '--regularization', '20'],
              'partial': ['--input', marker_file.name, '--exclude', 'P1', '--regularization', '20']}
    suite.write_text(json.dumps(config))
    other = tmp_path / 'unrelated'
    other.mkdir()
    monkeypatch.chdir(other)
    base = tmp_path / 'baseline'
    args = ['--suite', str(suite), '--model', str(model_file)]
    assert main([*args, '--record', str(base)]) == 0
    original = (base / 'snapshot.json').read_bytes()
    cases = json.loads(original)['cases']
    assert cases['full']['metrics']['statistical_fit']['count'] == cases['partial']['metrics']['statistical_fit']['count'] + 1
    assert set(base.iterdir()) == {base / 'snapshot.json', base / 'environment.json'}
    assert str(tmp_path) not in original.decode()
    assert main([*args, '--compare', str(base)]) == 0
    assert main([*args, '--record', str(base)]) == 2
    config['partial'][-1] = '10'
    suite.write_text(json.dumps(config))
    assert main([*args, '--compare', str(base)]) == 1
    assert 'partial/current' in capsys.readouterr().out
    assert (base / 'snapshot.json').read_bytes() == original
    assert not list(tmp_path.glob('*.obj'))


def test_incomplete_or_redirected_run_never_publishes(tmp_path, marker_file, model_file):
    suite = tmp_path / 'suite.json'
    base = tmp_path / 'new'
    redirected = tmp_path / 'unwanted.obj'
    valid = ['--input', marker_file.name, '--regularization', '20']
    for bad in (['--input', 'missing.csv'], [*valid, '--output', str(redirected)],
                [*valid, '--npz', 'different.npz'], [*valid, '--overwrite']):
        suite.write_text(json.dumps({'valid': valid, 'invalid': bad}))
        assert main(['--suite', str(suite), '--model', str(model_file), '--record', str(base)]) == 2
        assert not base.exists() and not redirected.exists()
        assert Path(marker_file).is_file()
