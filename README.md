# Agentic AI Hand Sketch to Professional PPT Diagram

This is a complete Streamlit mini-project demo.

## What it does

1. Upload a hand-drawn site sketch.
2. Optionally upload a professional PPT/software-edited reference image.
3. OpenCV enhances the hand sketch.
4. A Sketch Understanding Agent extracts components and connections.
5. A Reference Style Agent learns reusable visual rules from the professional example.
6. A Topology Review Agent validates IDs and connections.
7. The engineer can correct extracted tables in the dashboard.
8. The app generates:
   - Editable PowerPoint (`.pptx`)
   - PNG preview
   - Structured engineering JSON

The final diagram is rendered with real PowerPoint shapes and connectors, so every component remains editable.

## Quick start on Windows

1. Extract the ZIP.
2. Double-click `setup.bat`.
3. For online AI mode, open `.env` and add:

```env
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-5
```

4. Double-click `run.bat`.
5. Open the displayed Streamlit URL.

## Test without an API key

The dashboard starts in **Offline demo mode** and uses the bundled images plus a predefined interpreted topology. This validates:

- image upload workflow,
- preprocessing,
- review tables,
- diagram generation,
- PPT download,
- PNG download,
- JSON download.

Disable Offline demo mode to use OpenAI vision.

## Project structure

```text
agentic_sketch_to_ppt_demo/
├── app.py
├── requirements.txt
├── .env.example
├── setup.bat
├── run.bat
├── setup.sh
├── run.sh
├── samples/
│   ├── hand_sketch.png
│   └── reference_ppt_image.png
├── outputs/
│   ├── sample_generated_diagram.pptx
│   └── sample_generated_diagram.png
└── src/
    ├── models.py
    ├── image_utils.py
    ├── ai_pipeline.py
    ├── offline_sample.py
    └── renderers.py
```

## Important accuracy note

The AI output is an engineering draft. Handwriting, arrow direction, pipe sizes, motor mapping, and capacities must be reviewed before customer or installation use.

## Recommended production upgrades

- User login and project history
- Save corrections in PostgreSQL
- Store approved sketch-to-PPT pairs
- Retrieve similar approved diagrams before generation
- Add company logos and reusable PPT templates
- Add approval workflow and version control
- Add cloud storage and audit logs
