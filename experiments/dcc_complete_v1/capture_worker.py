"""Request-isolated Q/K capture for exact-token replay through vLLM batches."""
import json
import hashlib
import os
import re
import time
from pathlib import Path

import torch
from safetensors.torch import save_file
from vllm.model_executor.layers.attention.attention import get_attention_context
from vllm.forward_context import get_forward_context
from vllm_hook_plugins.workers._common import get_query_metadata
from vllm_hook_plugins.workers._common import iter_matching_req_ids


class CaptureWorker:
    _hooks_installed = False

    def install_hooks(self):
        if self._hooks_installed:
            return
        layer = int(os.environ["MF_LAYER"])
        head = int(os.environ["MF_HEAD"])
        matches = [(n, m) for n, m in self.model_runner.model.named_modules()
                   if re.search(rf"layers\.{layer}\.self_attn\.attn$", n)]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one attention module at layer {layer}, found {len(matches)}")
        name, module = matches[0]
        heads, kv_heads, dimension = module.num_heads, module.num_kv_heads, module.head_size
        if not 0 <= head < heads:
            raise ValueError("Query head is outside this TP=1 model")
        kv_head = head // (heads // kv_heads)
        self._mf_states = {}
        self._mf_batches = {}
        self._mf_current_batch = None
        def begin_batch(*_):
            metadata=get_forward_context().attn_metadata
            starts,_=get_query_metadata(metadata)
            if starts is None:
                self._mf_current_batch=None
                return
            ids=list(self.model_runner.input_batch.req_ids[:len(starts)-1])
            phases=[]
            for req_id in ids:
                state=self.model_runner.requests.get(req_id)
                extra=state.sampling_params.extra_args if state and state.sampling_params else {}
                phases.append((extra or {}).get("mf_phase","other"))
            begin=torch.cuda.Event(enable_timing=True)
            end=torch.cuda.Event(enable_timing=True)
            batch_id=len(self._mf_batches)
            begin.record()
            self._mf_batches[batch_id]={"begin":begin,"end":end,"requests":ids,"phases":phases}
            self._mf_current_batch=batch_id
        def end_batch(*_):
            if self._mf_current_batch is not None:
                self._mf_batches[self._mf_current_batch]["end"].record()
        self.model_runner.model.register_forward_pre_hook(begin_batch)
        self.model_runner.model.register_forward_hook(end_batch)
        self._mf_config = {
            "target_layer": layer, "target_query_head": head, "target_kv_head": kv_head,
            "head_dim": dimension, "attention_multiplier": float(getattr(module.impl, "scale", dimension ** -0.5)),
            "execution_mode": "vllm_independent_sequences", "capture_entrypoint": name,
        }
        original = module.impl.forward

        def forward(attn_layer, query, key, value, kv_cache, attn_metadata, *args, **kwargs):
            output = original(attn_layer, query, key, value, kv_cache, attn_metadata, *args, **kwargs)
            if query is None or key is None:
                return output
            metadata, bound, _, _ = get_attention_context(module.layer_name)
            if bound is not module:
                raise RuntimeError("Attention metadata belongs to another layer")
            starts = metadata.query_start_loc
            if starts is None:
                return output
            batch = self.model_runner.input_batch
            request_ids = batch.req_ids
            q = query.reshape(-1, heads, dimension)
            k = key.reshape(-1, kv_heads, dimension)
            size = len(starts) - 1
            now = time.time()
            for index in range(size):
                req_id = request_ids[index]
                state = self.model_runner.requests.get(req_id)
                if state is None or state.sampling_params is None:
                    continue
                extra = state.sampling_params.extra_args or {}
                if extra.get("output_qk") is None:
                    continue
                left, right = int(starts[index]), int(starts[index + 1])
                if right <= left:
                    continue
                offset = int(batch.num_computed_tokens_cpu[index])
                entry = self._mf_states.setdefault(req_id, {"q": [], "k": [], "next": 0, "schedule": [],
                    "packed":bool(extra.get("mf_batch"))})
                if entry["next"] != offset:
                    raise RuntimeError(f"Capture gap for {req_id}: {entry['next']} versus {offset}")
                entry["q"].append(q[left:right, head].detach().clone())
                entry["k"].append(k[left:right, kv_head].detach().clone())
                entry["next"] += right - left
                entry["schedule"].append({
                    "time": now, "batch_size": size, "sequence_index": index, "sequence_start": offset,
                    "new_tokens": right - left, "request_id": req_id,
                    "is_prefill": len(state.output_token_ids) == 0,
                    "batch_id": self._mf_current_batch,
                })
            return output

        module.impl.forward = forward
        self._hooks_installed = True

    def flush_disk(self, external_req_ids, run_id, hook_dir):
        entries = []
        for external in external_req_ids:
            for req_id in iter_matching_req_ids(self._mf_states, external):
                entries.append((external,self._mf_states.pop(req_id)))
        if not entries:
            return False
        if len(entries) != 1:
            raise ValueError("Each recorded call must have a unique run_id")
        external,entry = entries[0]
        q, k = torch.cat(entry["q"]).cpu().contiguous(), torch.cat(entry["k"]).cpu().contiguous()
        if len(q) != len(k) or len(q) != entry["next"]:
            raise RuntimeError("Captured Q/K rows differ")
        destination = Path(hook_dir) / run_id / "tp_rank_0"
        if entry["packed"]:
            destination=destination/hashlib.sha256(external.encode()).hexdigest()[:16]
        destination.mkdir(parents=True, exist_ok=False)
        save_file({"q": q, "k": k}, destination / "qk.safetensors.tmp")
        os.replace(destination / "qk.safetensors.tmp", destination / "qk.safetensors")
        timings=[]
        for batch_id in sorted({x["batch_id"] for x in entry["schedule"] if x["batch_id"] is not None}):
            event=self._mf_batches[batch_id]
            event["end"].synchronize()
            timings.append({"batch_id":batch_id,"cuda_ms":event["begin"].elapsed_time(event["end"]),
                            "requests":event["requests"],"phases":event["phases"]})
        header = {"external_request_id":external,"gpu_batches":timings,"config": self._mf_config, "rows": len(q), "schedule": entry["schedule"],
                  "layer_order": [{"key_q": "q", "key_k": "k"}]}
        (destination / "qk.json.tmp").write_text(json.dumps(header))
        os.replace(destination / "qk.json.tmp", destination / "qk.json")
        return True

    def clear_captured_states(self, external_req_id):
        for req_id in list(iter_matching_req_ids(self._mf_states, external_req_id)):
            self._mf_states.pop(req_id, None)

    def get_captured_states(self, external_req_id):
        raise ValueError("This worker uses save_to_disk=1 for recorded calls")
