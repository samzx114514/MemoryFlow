import math
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from evaluate import evaluate, prepare_records, prediction_positions


def fixture():
    sources = {str(i): f'source {i}' for i in range(15)}
    row = dict(example_id='one', split='dev', language='en', query='question',
               target={'text': 'target'}, candidates=[
                   dict(source_id=str(i), label=int(i == 2)) for i in range(15)])
    return row, sources


def test_prepare_preserves_order_without_gold():
    row, sources = fixture()
    records, gold = prepare_records([row], sources)
    assert [s['id'] for s in records[0]['sources']] == list(sources)
    assert set(records[0]) == {'id', 'query', 'target', 'language', 'sources'}
    assert all(set(s) == {'id', 'text'} for s in records[0]['sources'])
    assert gold[0]['gold_id'] == '2'


def test_rank_metrics_and_tie_rule():
    row, sources = fixture()
    _, gold = prepare_records([row], sources)
    scores = {s: 0.0 for s in sources}
    # Lexical ID tie order: 0,1,10,11,12,13,14,2,... => rank 8.
    result = evaluate(gold, [dict(id='one', scores=scores)])
    assert result['overall']['mrr'] == 1 / 8
    assert result['overall']['ndcg_at_5'] == 0
    scores['2'] = 1.0
    assert evaluate(gold, [dict(id='one', scores=scores)])['overall']['hit_at_1'] == 1
    scores['1'] = 2.0
    assert evaluate(gold, [dict(id='one', scores=scores)])['overall']['ndcg_at_5'] == 1 / math.log2(3)


@pytest.mark.parametrize('bad', ['missing', 'duplicate', 'nan', 'extra'])
def test_reject_incomplete_results(bad):
    row, sources = fixture()
    _, gold = prepare_records([row], sources)
    score = dict(id='one', scores={s: 0.0 for s in sources})
    predictions = [score]
    if bad == 'missing':
        predictions = []
    elif bad == 'duplicate':
        predictions *= 2
    elif bad == 'nan':
        score['scores']['2'] = float('nan')
    else:
        score['scores']['other'] = 1
    with pytest.raises(ValueError):
        evaluate(gold, predictions)


def test_causal_shift():
    assert prediction_positions(10, 3) == [9, 10, 11]


def test_replay_matches_upstream_greedy_on_tiny_model():
    torch = pytest.importorskip('torch')
    from transformers import Qwen2Config, Qwen2ForCausalLM
    from evaluate import replay_attention
    from generate_attention import greedy_decode_selected_head
    import numpy as np
    torch.manual_seed(0)
    cfg = Qwen2Config(vocab_size=32, hidden_size=32, intermediate_size=64,
                      num_hidden_layers=2, num_attention_heads=4,
                      num_key_value_heads=2, eos_token_id=None)
    cfg._attn_implementation = 'eager'
    model = Qwen2ForCausalLM(cfg).eval()
    class Tokenizer:
        eos_token_id = None
    prompt = torch.tensor([[1, 4, 7, 8, 9]])
    ids, expected = greedy_decode_selected_head(model, Tokenizer(), prompt, 1, 2, 1, 4, 4)
    observed = replay_attention(model, prompt, ids, 1, 2, 1, 4)
    np.testing.assert_allclose(observed, expected, rtol=0, atol=0)
