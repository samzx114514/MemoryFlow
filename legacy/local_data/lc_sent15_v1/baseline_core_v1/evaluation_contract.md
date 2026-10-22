# Evaluation Contract

- Scope: Train/Dev `single_positive_15` only.
- Primary metric: Hit@1.
- Secondary metrics: MRR and nDCG@5.
- Random Hit@1 baseline: 1/15.
- Ties are broken by candidate ID ascending.
- BM25 must report raw scores; group-normalized variants require a separately named protocol.
- Report overall results and language-stratified results.
- Candidate list position is not a model feature.
- Reserve is excluded and must remain sealed.
