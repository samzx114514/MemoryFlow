# Paper / supplementary code contract

## Identity

- Checkpoint: `MEMORYFLOW_YIFENG_QWEN25_HEAD_PROBE_V1`
- ZIP SHA256: `f44074df6a22596c9a78b2ab3f815ce9c2486f2225db6377c9aaad9e8a48487e` (matches expected value).
- Audited immutable source: `/data2/pkuiti/songzhengxing_intern/codex_files/yifeng_method_lcsent15_comparison_v1/third_party_readonly/AAAI27_supplementary_material`.
- Entry point: `probe_citation_head.py`; downstream consumer: `generate_attention.py`.
- Python requirement: `>=3.10`; declared packages: numpy >=1.26, openai >=1.30, sentence-transformers >=3.0, torch >=2.2, tqdm >=4.66, transformers >=4.43.

## Frozen paper-faithful protocol

- Base model: `Qwen/Qwen2.5-7B-Instruct`; embedding model: `BAAI/bge-m3`.
- Input: LongCite-45k official Train only. The probe selects 100 Chinese and 100 English records through `random.Random(seed)`; the supplied code default is seed `42`, so a future executable run must use `42`, not a newly invented sample list.
- Prompt: a vanilla QA prompt containing the source document and question, without citation instructions. The tokenizer chat template is used if available, with `add_generation_prompt=True` and `enable_thinking=False`.
- Decoding: greedy `argmax`; supplied probe default `--max-new-tokens 800`. There is no independently declared source-input truncation limit in this entry point.
- Attention: prompt prefill does not return attentions. For each generated token, the code requests `output_attentions=True` and retains, for every layer/head, the top-attended position within the document span. This is an online top-position representation, not persistence of full attention tensors.
- Clause alignment: generated text is split by language-specific punctuation; token spans are recovered for each clause. BGE-M3 encodes clauses and evidence sentences with normalized embeddings; each clause is aligned to its highest-cosine evidence sentence.
- Scoring: valid if cosine >= 0.70; invalid if cosine <= 0.65; the open interval is ignored. For valid clauses, the score adds cosine-weighted grounding on the aligned evidence span. For invalid clauses, it subtracts confidence-weighted concentration on any source sentence. Each component is normalized by its own accumulated denominator. Overall head score is valid reward minus invalid penalty, averaged across scored instances; Top-1 is selected, with no ensemble.

## Output / recovery

The supplied entry point serializes model identifiers, thresholds, seed and an ordered list of layer/head/score records to JSON. It does not provide an official fixed head artifact, a persisted sample-ID list, or resumable per-instance contributions. The checkpoint therefore requires a new create-only wrapper only after all immutable inputs are available.

## Readiness decision

The required Qwen snapshot is present. BGE-M3 and a revision/checksum-verifiable official LongCite-45k Train file are absent from the allowed checked locations. No samples were selected, no environment was created, and no GPU work or probing was started.
