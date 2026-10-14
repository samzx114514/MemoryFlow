import sys
from pathlib import Path
import pytest
import torch

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))
from memoryflow.source_prior_relational import DirectionalRelation, SourcePrior, SymmetricRelation, finite_json, freeze_module, prior_challenging_ids
sys.path.insert(0, str(ROOT / "scripts"))
from run_m6d_source_prior_relational import forbid, component_folds
from plan_m6d_parallel import partition, units


def test_symmetric_relation_swap_invariant_eval():
    torch.manual_seed(0); model = SymmetricRelation(4).eval(); a = torch.randn(3, 4); b = torch.randn(3, 4)
    assert torch.allclose(model(a, b), model(b, a), atol=1e-6, rtol=0)


def test_directional_relation_has_distinct_projections_and_can_differ():
    torch.manual_seed(0); model = DirectionalRelation(4, 2).eval(); a = torch.randn(3, 4); b = torch.randn(3, 4)
    assert model.target_projection is not model.source_projection
    assert not torch.allclose(model(a, b), model(b, a), atol=1e-6, rtol=0)


def test_source_prior_does_not_accept_target():
    model = SourcePrior(4)
    with pytest.raises(TypeError): model(torch.zeros(1, 4), torch.zeros(1, 4))


def test_freeze_module_blocks_gradients():
    model = SourcePrior(4); freeze_module(model)
    assert not any(p.requires_grad for p in model.parameters())


def test_blind_path_guard_rejects_before_io():
    with pytest.raises(RuntimeError, match="Blind path forbidden"):
        forbid("not_allowed_blind_data.jsonl")


def test_component_folds_keep_document_and_source_hash_connected():
    examples = [
        {"target_group_id":"a", "document_group_id":"d1", "candidate_source_ids":["s1"]},
        {"target_group_id":"b", "document_group_id":"d2", "candidate_source_ids":["s1"]},
        {"target_group_id":"c", "document_group_id":"d3", "candidate_source_ids":["s3"]},
        {"target_group_id":"d", "document_group_id":"d4", "candidate_source_ids":["s4"]},
        {"target_group_id":"e", "document_group_id":"d5", "candidate_source_ids":["s5"]},
    ]
    folds, info = component_folds(examples, {"s1":"h1", "s3":"h3", "s4":"h4", "s5":"h5"})
    assert folds is not None
    containing = [i for i, fold in enumerate(folds) if {"a", "b"} & {x["target_group_id"] for x in fold}]
    assert len(containing) == 1


def test_shards_are_disjoint_and_cover_pending_units():
    pending = units()
    shards = partition(pending, 4)
    encoded = lambda u: tuple(sorted(u.items()))
    combined = [encoded(u) for shard in shards for u in shard]
    assert len(combined) == len(set(combined)) == len(pending)
    assert set(combined) == {encoded(u) for u in pending}


def test_prior_challenging_excludes_all_positive_group_without_max_failure():
    selected, counts = prior_challenging_ids({
        "all_positive": [{"label": 1, "logit": 0.2}, {"label": 1, "logit": 0.3}],
        "challenging": [{"label": 1, "logit": 0.2}, {"label": 0, "logit": 0.4}],
    })
    assert selected == {"challenging"}
    assert counts == {"eligible": 1, "excluded_no_positive": 0, "excluded_no_negative": 1}


def test_finite_json_turns_nan_and_infinity_into_null():
    assert finite_json({"x": float("nan"), "y": [float("inf"), 1.0]}) == {"x": None, "y": [None, 1.0]}
