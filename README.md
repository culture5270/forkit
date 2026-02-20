# Fork It!

A web app that suggests a random food when you can't decide what to eat.

## Running locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Then open [http://localhost:8000](http://localhost:8000) and click **Fork It!**

## API

```
GET /api/random
```

Returns a random food suggestion:

```json
{"food": "Tacos"}
```
