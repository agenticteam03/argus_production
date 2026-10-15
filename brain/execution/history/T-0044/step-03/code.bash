# (archived) T-0044 step 3, run 2026-10-15 by conantkd's agent over ssh; leases vm-095 + vm-166, session 38fca4f6c9f1.
# The comparison ran in ONE-OFF containers of the deployed image (argus-v18-agent:1, branch 5751405) with the step-3
# files mounted over it: the running worker was not changed. vm-095 only; the worker stays ARGUS_RETRIEVAL=tfidf.

# --- C.0 [LAPTOP · bash] the items (the recall node's own queries, replayed offline) and the files to the VM ---------
PYTHONPATH=. python -m argus.evaluation.retrieval > items.jsonl            # 44 class cases with runbook labels
PYTHONPATH=. python -m argus.evaluation.retrieval --score                   # the TF-IDF table, locally
ssh argus-vm095 mkdir -p /tmp/t0044
scp argus/adapters/outbound/rag.py argus/evaluation/retrieval.py argus/__main__.py argus/infrastructure/wiring.py \
    items.jsonl argus-vm095:/tmp/t0044/

# --- C.1 / C.2 [VM vm-095 · bash] score TF-IDF and the hybrid; C.2 first rebuilds the index (sections with titles) ----
grep -q "^holder=conantkd " /opt/argus-v18/SESSION && echo "SESSION OK" || exit 1
T=/tmp/t0044; chmod 644 $T/*
run() { sudo docker run --rm -i --network argus-v18-core --memory 256m --cpus 0.5 \
  -v /opt/argus-v18/secrets/agent:/run/argus-secrets:ro \
  -v $T/rag.py:/app/argus/adapters/outbound/rag.py:ro -v $T/retrieval.py:/app/argus/evaluation/retrieval.py:ro \
  -v $T/__main__.py:/app/argus/__main__.py:ro -v $T/wiring.py:/app/argus/infrastructure/wiring.py:ro \
  -e ARGUS_WEAVIATE_URL=http://argus-v18-weaviate:8080 --entrypoint python argus-v18-agent:1 -m argus runbooks "$@"; }
run index </dev/null                                         # C.2 only
run compare --skip-titles < $T/rag-items.jsonl
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1

# --- C.9 [VM vm-095 · bash] clean up; [LAPTOP] release ---------------------------------------------------------------
rm -rf /tmp/t0044
python brain/tools/brain.py release
