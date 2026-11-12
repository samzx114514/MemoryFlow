"""Combine immutable compatible-core and new-call artifacts into one frozen batch."""
import hashlib
import json
from pathlib import Path

from pipeline import write


def assemble(root, core):
    frozen=json.loads((root/"formal_inputs.json").read_text())
    for label in ("27b","7b","1_5b"):
        components=[core/f"formal_{label}",root/"added17"/f"formal_{label}"]
        identities=[json.loads((p/"identity.json").read_text()) for p in components]
        for field in ("model","config_sha256","author_sha256"):
            if identities[0][field]!=identities[1][field]:
                raise ValueError(f"Component {field} differs")
        jobs={}
        for component in components:
            if not (component/"completed.json").exists():
                raise ValueError("A component run has not completed")
            for job in json.loads((component/"inputs.json").read_text()):
                if job["id"] in jobs:
                    raise ValueError("Duplicate call ID in components")
                jobs[job["id"]]=(job,component)
        if set(jobs)!={x["id"] for x in frozen}:
            raise ValueError("Component calls differ from the frozen batch")
        output=root/f"formal_{label}";output.mkdir()
        ordered=[]
        for item in frozen:
            job,component=jobs[item["id"]]
            if job["input_sha256"]!=item["input_sha256"] or job["request"]!=item["request"]:
                raise ValueError("Reused input differs from the frozen request")
            ordered.append(job)
            (output/item["id"]).symlink_to(component/item["id"],target_is_directory=True)
        write(output/"inputs.json",ordered)
        write(output/"identity.json",{**{key:identities[0][key] for key in ("model","config_sha256","author_sha256")},
              "components":[{"run":str(p),"identity_sha256":hashlib.sha256((p/"identity.json").read_bytes()).hexdigest()}
                            for p in components],"timing_note":"Quality artifacts reused; use independent live-task measurements for efficiency"})
        write(output/"completed.json",{"calls":len(ordered),"reused_core_calls":13,"new_calls":17})
        drafts=root/"annotation_drafts_v2"/f"formal_{label}"
        drafts.mkdir(parents=True)
        for item in frozen:
            _,component=jobs[item["id"]]
            target=component.parent/"annotation_drafts_v2"/f"formal_{label}"/item["id"]
            (drafts/item["id"]).symlink_to(target,target_is_directory=True)


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root",type=Path)
    parser.add_argument("core",type=Path)
    args=parser.parse_args()
    assemble(args.root,args.core)
