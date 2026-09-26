import csv
import json

import numpy as np
import pytest

from cranio.backend.gnm_backend import LABEL_TO_VERTEX
from cranio.config import PipelineConfig
from cranio.io_csv import read_marker_csv, write_marker_csv_v3
from cranio.landmarks import ADDED_LANDMARKS, marker_labels
from cranio.paper_reference import TABLE2, PAPER_LABELS, reference_metadata
from cranio.pipeline import run_pipeline


def test_table2_transcription_against_printed_page30():
    # Independent check against the 21 numeric rows in the supplied PDF.
    expected = [4.5, 4.5, 7, 2.5, 10, 11, 12.25, 10, 13, 8,
                4, 8.5, 6.25, 12, 11.5, 7, 6.25, 10.5, 18, 17.5, 17]
    assert [row[3] for row in TABLE2] == expected
    assert [len(row[2]) for row in TABLE2] == [1] * 10 + [2] * 11
    assert len(PAPER_LABELS) == 32 and len(set(PAPER_LABELS)) == 32
    assert reference_metadata()['gnm_correspondences_in_paper'] is False


def test_union_preserves_distinct_anatomical_sites():
    extended, legacy, paper = map(set, [marker_labels(), marker_labels('LEGACY_27'), marker_labels('PAPER_32')])
    assert len(extended) == 48 and len(legacy) == 27 and len(ADDED_LANDMARKS) == 21
    assert extended == legacy | paper
    assert len(set(LABEL_TO_VERTEX.values())) == 48
    for a, b in [('Menton', 'Gnathion'), ('Suborbitale_Dr', 'Infraorbitale_Dr'),
                 ('LateralOrbit_Dr', 'Orbita_Dr_Ext'), ('Infradentale_BuzaInf', 'Pogonion')]:
        assert LABEL_TO_VERTEX[a] != LABEL_TO_VERTEX[b]


def _fixture_rows(marker_file):
    lines = marker_file.read_text(encoding='utf-8').splitlines()
    return list(csv.DictReader(lines[2:])), json.loads(lines[1][1:])


def test_documentation_marker_is_retained_but_cannot_affect_fit(tmp_path, model_file, marker_file):
    rows, meta = _fixture_rows(marker_file)
    rows[0].update(x=9000, y=8000, z=7000, use_for_fit=0, bone_status='inferred',
                   mapping_reviewed=0, marker_notes='missing bone; documentation only')
    write_marker_csv_v3(marker_file, rows, meta)
    targets, skipped, parsed = read_marker_csv(marker_file, {}, {})
    assert len(targets) == 11 and skipped[0][0] == 'P0'
    assert parsed['marker_records']['P0']['target_xyz_mm'] == [9000, 8000, 7000]
    cfg = PipelineConfig(input=marker_file, npz=model_file, output=tmp_path / 'face.obj',
                         strict=True, regularization='30')
    assert run_pipeline(cfg) == 0
    report = json.loads(open(cfg.output_json).read())
    assert report['metrics']['final_fit']['rmse_mm'] < .001
    assert np.max(np.abs(report['identity_coefficients'])) < .001
    assert len(report['landmarks']) == 11
    assert report['marker_metadata']['marker_records']['P0']['bone_status'] == 'inferred'


@pytest.mark.parametrize('field,value', [('use_for_fit', 'yes'), ('mapping_reviewed', 'yes'),
                                        ('bone_status', 'validated')])
def test_invalid_review_fields_are_rejected(marker_file, field, value):
    rows, meta = _fixture_rows(marker_file)
    rows[0][field] = value
    write_marker_csv_v3(marker_file, rows, meta)
    with pytest.raises(ValueError, match=field):
        read_marker_csv(marker_file, {}, {})


def test_strict_rejects_explicitly_unreviewed_mapping(tmp_path, model_file, marker_file):
    rows, meta = _fixture_rows(marker_file)
    rows[0]['mapping_reviewed'] = '0'
    write_marker_csv_v3(marker_file, rows, meta)
    cfg = PipelineConfig(input=marker_file, npz=model_file, output=tmp_path / 'face.obj', strict=True)
    assert run_pipeline(cfg) == 2
    assert not (tmp_path / 'face.obj').exists()


def test_strict_cli_exclusion_applies_before_review_gate(tmp_path, model_file, marker_file):
    rows, meta = _fixture_rows(marker_file)
    rows[0].update(mapping_reviewed=0, tissue_source='legacy-unvalidated')
    write_marker_csv_v3(marker_file, rows, meta)
    cfg = PipelineConfig(input=marker_file, npz=model_file, output=tmp_path / 'face.obj',
                         strict=True, exclude=['P0'], regularization='30')
    assert run_pipeline(cfg) == 0
    report = json.loads(open(cfg.output_json).read())
    assert len(report['landmarks']) == 11


def test_repaired_bone_and_cranial_modification_are_reported(tmp_path, model_file, marker_file):
    rows, meta = _fixture_rows(marker_file)
    rows[0].update(bone_status='reconstructed', mapping_reviewed=1,
                   tissue_source='DOI:10.4995/var.2024.24796; reviewed for this synthetic test')
    meta['cranial_modification'] = 'present'
    write_marker_csv_v3(marker_file, rows, meta)
    cfg = PipelineConfig(input=marker_file, npz=model_file, output=tmp_path / 'face.obj', regularization='30')
    assert run_pipeline(cfg) == 0
    report = json.loads(open(cfg.output_json).read())
    warnings = ' '.join(report['warnings'])
    assert 'repaired/inferred' in warnings and 'cranial modification' in warnings
    assert 'not a universal tissue table' in warnings
