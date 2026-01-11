# Yuhlia Assistant

Yuhlia is an agentic AI prototype for investment product discovery in the Yuh app.
It helps users understand investing concepts and explore available products from a real SQLite catalog, without giving financial advice.

The project focuses on intent classification, structured product retrieval, guardrails, and evaluation of LLM behaviour rather than UI polish or recommendations.

---

## What this project does

* Supports multi turn, chat based conversations
* Classifies user intent into:

  * Yuh related product availability
  * General investing knowledge
* Extracts structured filters from natural language (ETF, region, fees, ESG, etc.)
* Retrieves products from a SQLite database using:

  * Deterministic SQL filters
  * Semantic RAG fallback via embeddings
* Enforces strict guardrails to prevent financial advice
* Separates product rendering from language generation
* Evaluates multiple LLMs for:

  * Context correctness
  * Product handling
  * Guardrail compliance
  * Cost

---

## Architecture (high level)

```
Streamlit UI
   ↓
conversation.py (orchestrator)
   ↓
intent classification
   ↓
filter extraction (LLM)
   ↓
product retrieval
   ├─ SQL (structured)
   └─ RAG (semantic fallback)
   ↓
response generation
   ↓
guardrail validation
   ↓
UI renders text + product table
```

---

## Project structure

```
.
├── app.py                  # Streamlit UI
├── conversation.py         # Core orchestration logic
├── agents.py               # LLM calls, intent, filters, guardrails
├── database.py             # SQLite product queries
├── models.py               # Data models
├── ui_components.py        # Product table + UI helpers
├── yuh_products.db         # Product catalog (SQLite)

├── rag/
│   ├── build_product_index.py   # Builds product embedding index
│   ├── build_web_index.py       # Builds website grounding index
│   └── retrieve.py              # RAG retrieval functions

├── eval/
│   ├── run_eval.py              # Context evaluation
│   ├── run_eval_products.py     # Product handling evaluation
│   ├── eval_models.py           # Multi model evaluation runner
│   ├── render_results.py        # HTML report for single runs
│   └── render_model_comparison.py # Model comparison report
```

---

## Guardrails and constraints

Yuhlia is intentionally constrained:

* No financial advice
* No recommendations
* No buy, sell, timing, or performance predictions
* No product invention
* Product tables are rendered only when explicitly allowed by intent and data

Guardrails are enforced via:

* Prompt level constraints
* Post generation validation
* Automatic rewrites on failure

---

## Running the app

### Prerequisites

* Python 3.10+
* An OpenAI API key

```bash
export OPENAI_API_KEY=your_key_here
```

### Install dependencies

```bash
pip install -r requirements.txt
```

### Run Streamlit app

```bash
streamlit run app.py
```

---

## Building RAG indexes (optional)

Product embeddings:

```bash
python rag/build_product_index.py
```

Website grounding embeddings:

```bash
python rag/build_web_index.py
```

If indexes are not built, the system will fall back gracefully.

---

## Running evaluations

Evaluate a model:

```bash
python eval/run_eval.py
python eval/run_eval_products.py
```

Render results:

```bash
python eval/render_results.py
```

Run a full multi model evaluation:

```bash
python eval/eval_models.py
```

Render results:

```bash
python eval/render_model_comparison.py
```

Outputs include:

* Pass rates
* Failure reasons
* Token usage
* Estimated cost per model

---

## What this project is not

* Not a production ready chatbot
* Not optimised for latency or scale

This is a research and evaluation driven prototype focused on correctness, control, and observability.

---

## License

Internal / educational use only.
Product data and branding belong to their respective owners.

