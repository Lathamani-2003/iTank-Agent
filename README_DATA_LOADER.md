# Streamlit Data Loader

This file is intentionally separate from the project's existing README files.

## Included files

- `app.py` — your current Streamlit application.
- `src/direct_connection_editor_component_thin/main.js` — updated interactive worksheet frontend.
- `data_loader.py` — optional cached loader for CSV, Excel, JSON, or JSONL data.
- `README_DATA_LOADER.md` — this documentation only.

## Important

Your current `app.py` does not currently call `pd.read_csv()`,
`pd.read_excel()`, or `pd.read_json()`. Therefore `data_loader.py`
is included as an optional helper and is **not automatically imported**
into `app.py`. This avoids changing existing application behavior.

When your application later needs a data file, use:

```python
from data_loader import load_data

df = load_data(
    "data.csv",
    usecols=["id", "name", "status"],
    dtype={
        "id": "int64",
        "name": "string",
        "status": "string",
    },
)
```

`@st.cache_data` prevents unchanged files from being loaded repeatedly,
and the spinner is shown only during a real cache miss.
