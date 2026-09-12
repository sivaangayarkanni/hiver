# Citations & acknowledgements

## Assignment / problem framing

- Hiver SDE Intern take-home brief (AppleSupport AI Twitter support agent): classify, retrieve+draft, escalate, golden eval, report.  
- Public discussion of the **Customer Support on Twitter** dataset (Kaggle / research mirrors) informed *style* of synthetic examples. **We did not download or redistribute that dataset in this repo.**

## Libraries

- [scikit-learn](https://scikit-learn.org/) — TF-IDF, LogisticRegression, metrics  
- [NumPy](https://numpy.org/)  
- [Pydantic](https://docs.pydantic.dev/) — schema validation  
- [Typer](https://typer.tiangolo.com/) / [Rich](https://rich.readthedocs.io/) — CLI  
- [httpx](https://www.python-httpx.org/) — OpenAI-compatible HTTP client  
- [pytest](https://pytest.org/) — tests  

## Ideas / patterns

- Retrieval-augmented drafting (RAG-style grounding) — general pattern from Lewis et al., *Retrieval-Augmented Generation for Knowledge-Intensive NLP* (2020), applied here with classical TF-IDF rather than dense retrievers.  
- LLM-as-judge evaluation — pattern popularized in recent eval literature (e.g. G-Eval / MT-Bench style rubrics); our implementation is a minimal JSON rubric, not a reproduction of a specific paper’s protocol.  
- Support escalation with confidence thresholds — common industry pattern in chatbot handoff design (no single paper dependency).

## Data

- All `data/sample` and `data/golden` texts are **original synthetic content** written for this take-home, inspired by publicly visible Apple Support social-care phrasings. Not Apple confidential data. Not Kaggle row copies.
