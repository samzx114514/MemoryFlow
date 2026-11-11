"""Start the dedicated server with one lazy capture-hook installation."""
import asyncio
from vllm.v1.engine.async_llm import AsyncLLM

original_rpc=AsyncLLM.collective_rpc
original_add_request=AsyncLLM.add_request


async def collective_rpc(self, method, *args, **kwargs):
    if method != "install_hooks":
        return await original_rpc(self,method,*args,**kwargs)
    if getattr(self,"_mf_capture_installed",False):
        return None
    if not hasattr(self,"_mf_capture_lock"):
        self._mf_capture_lock=asyncio.Lock()
    async with self._mf_capture_lock:
        if not getattr(self,"_mf_capture_installed",False):
            result=await original_rpc(self,method,*args,**kwargs)
            self._mf_capture_installed=True
            return result
    return None


async def add_request(self, request_id, prompt, params, *args, **kwargs):
    effective=getattr(prompt,"sampling_params",None) or params
    extra=getattr(effective,"extra_args",None) or {}
    expected=int(extra.get("mf_batch_size",0))
    if expected<2:
        return await original_add_request(self,request_id,prompt,params,*args,**kwargs)
    group_id=extra["run_id"]
    if not hasattr(self,"_mf_enqueue_lock"):
        self._mf_enqueue_lock=asyncio.Lock()
        self._mf_enqueue_groups={}
    async with self._mf_enqueue_lock:
        if group_id not in self._mf_enqueue_groups:
            await self.pause_generation(mode="keep",clear_cache=False)
            self._mf_enqueue_groups[group_id]=0
    try:
        result=await original_add_request(self,request_id,prompt,params,*args,**kwargs)
    except BaseException:
        async with self._mf_enqueue_lock:
            self._mf_enqueue_groups.pop(group_id,None)
            await self.resume_generation()
        raise
    async with self._mf_enqueue_lock:
        self._mf_enqueue_groups[group_id]+=1
        if self._mf_enqueue_groups[group_id]==expected:
            del self._mf_enqueue_groups[group_id]
            await self.resume_generation()
    return result


AsyncLLM.collective_rpc=collective_rpc
AsyncLLM.add_request=add_request

if __name__=="__main__":
    from vllm.entrypoints.cli.main import main
    main()
