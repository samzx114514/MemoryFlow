"""Check wide-query aggregation against explicit paths on an early dev target."""
import argparse
import signal
from pathlib import Path

from cohort import read, sha, write
from run import original_scores, rank
from provenance_v2.compact_query import CompactQuery
from provenance_v2.full_query import FullQuery


def verify(common, replay, protocol, output):
    p = read(protocol)
    if sha(common/"cases.json") != p["cases_sha256"]:
        raise ValueError("Cases changed")
    dev = set(p["development_target_ids"])
    case = min((c for c in read(common/"cases.json") if c["case_id"] in dev), key=lambda c:(c["call_id"],c["case_id"]))
    aliases = {(o["event"],*o["span"]):c["canonical_id"] for c in case["candidates"] for o in c["occurrences"]}
    key = lambda r: aliases[r["message_index"],*r["message_char_span"]]
    episode = replay/case["sample_id"]/"episode"
    span = (case["target"]["start"],case["target"]["end"])
    results=[]
    def timeout(signum, frame):
        raise TimeoutError("Explicit reference exceeded 30 seconds")
    prior=signal.signal(signal.SIGALRM,timeout)
    try:
        for width in p["config"]["widths"]:
            signal.setitimer(signal.ITIMER_REAL,30)
            old=FullQuery(episode/"forest.json",episode/"matrices",width,16)
            new=CompactQuery(episode/"forest.json",episode/"matrices",width,16)
            try:
                explicit=old.walk(case["call_id"],span)
                compact=new.walk(case["call_id"],span,root_key=key,limits=p["config"]["limits"])
                a,b=original_scores(explicit,key),compact["root_scores"]
                if set(a)!=set(b):
                    raise ValueError("Wide-query material set mismatch")
                error=max((abs(a[k]-b[k]) for k in a),default=0)
                assert compact["status"]=="complete" and len(explicit["paths"])==compact["path_count"]
                assert error<1e-10 and rank(a)[:10]==rank(b)[:10]
                results.append({"width":width,"depth":16,"paths":len(explicit["paths"]),
                                "score_max_abs_difference":error,"top10_equal":True})
            finally:
                old.matrices.clear();new.matrices.clear()
                signal.setitimer(signal.ITIMER_REAL,0)
    finally:
        signal.signal(signal.SIGALRM,prior)
    if output.exists():
        raise FileExistsError(output)
    write(output,{"case_id":case["case_id"],"protocol_sha256":sha(protocol),"checks":results,
                  "selection":"Earliest call in the frozen dev cohort; no method score selection."})


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ["common","replay","protocol","output"]:
        parser.add_argument("--"+name,type=Path,required=True)
    args=parser.parse_args()
    verify(args.common,args.replay,args.protocol,args.output)
