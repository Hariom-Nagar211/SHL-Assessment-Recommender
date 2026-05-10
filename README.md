# Conversational SHL Assessment Recommender

FastAPI service for recommending SHL assessments from a local SHL Individual Test Solutions catalog.

The API is stateless: every `/chat` request includes the full conversation history, and the service reconstructs the next response from that history.

## Features

- Clarifies vague requests before recommending.
- Recommends 1 to 10 catalog-backed SHL assessments.
- Refines recommendations when the user changes constraints.
- Compares known assessments such as OPQ and GSA using catalog data.
- Refuses off-topic requests and prompt-injection attempts.
- Ensures every recommendation URL comes from the local SHL catalog.

## Project Structure

```text
.
├── main.py                    # FastAPI app and endpoints
├── recommender.py             # Catalog loading, retrieval, ranking, comparison logic
├── schemas.py                 # Request/response schemas
├── test_app.py                # Local behavior tests
├── shl_product_catalog.json   # Scraped SHL catalog data
├── requirements.txt           # Python dependencies
├── pytest.ini                 # Pytest config
└── approach.md                # Short design document
```

## API

### Health

```http
GET /health
```

Response:

```json
{
  "status": "ok"
}
```

### Chat

```http
POST /chat
```

Request:

```json
{
  "messages": [
    {
      "role": "user",
      "content": "Hiring a mid-level Java developer who works with stakeholders"
    }
  ]
}
```

Response:

```json
{
  "reply": "Got it. Here are 10 SHL assessments that fit mid-level java developer.",
  "recommendations": [
    {
      "name": "Global Skills Assessment",
      "url": "https://www.shl.com/products/product-catalog/view/global-skills-assessment/",
      "test_type": "C"
    }
  ],
  "end_of_conversation": false
}
```

## Local Setup

Create and activate a virtual environment:

```bash
python -m venv .venv
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the API:

```bash
uvicorn main:app --reload
```

Open:

```text
http://127.0.0.1:8000/health
```

## Run Tests

```bash
python -m pytest test_app.py -q
```

Expected result:

```text
6 passed
```

## Design Summary

The recommender uses deterministic retrieval and ranking over the local catalog. This keeps recommendations grounded, fast, and easy to test. It avoids hallucinated assessments by serializing recommendation results only from loaded catalog items.

See [approach.md](approach.md) for the detailed design notes and interview discussion points.
