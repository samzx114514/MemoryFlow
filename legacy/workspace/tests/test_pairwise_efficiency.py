import torch
from memoryflow.anchor_attention import build_packed_layout
from memoryflow.pairwise_efficiency import batched_pairwise_raw_scores,inject_batched_anchor,padded_pairwise_tensors

def test_padded_batch_has_safe_padding_rows():
    layouts=[build_packed_layout([[1,2]],[3],anchor_token_id=9),build_packed_layout([[1]],[3],anchor_token_id=9)]
    ids,pos,mask=padded_pairwise_tensors(layouts,pad_token_id=9,device="cpu")
    assert ids.shape[0]==2 and mask.shape[-1]==ids.shape[1]
    for row,layout in enumerate(layouts):
        for p in range(layout.sequence_length,ids.shape[1]):assert mask[row,0,p,p]==0

def test_batched_anchor_injection_and_score():
    layouts=[build_packed_layout([[1]],[2],anchor_token_id=9),build_packed_layout([[3]],[4],anchor_token_id=9)]
    base=torch.zeros(2,4,3);anchor=torch.tensor([1.,2.,3.]);out=inject_batched_anchor(base,layouts,anchor)
    assert torch.equal(out[0,layouts[0].target_anchor_position],anchor)
    attention=[torch.zeros(2,2,4,4) for _ in range(8)]
    for layer in attention:
        for i,l in enumerate(layouts):layer[i,:,l.target_anchor_position,l.source_anchor_positions[0]]=i+1
    assert torch.equal(batched_pairwise_raw_scores(attention,layouts),torch.tensor([1.,2.]))
