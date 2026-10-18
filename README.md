# CrisisGraph — AI-Powered Disaster Intelligence Platform

CrisisGraph is an AI-powered disaster intelligence and resource coordination platform designed to help emergency responders understand disaster situations, analyze incident dependencies, identify nearby emergency facilities, and support faster, data-driven response decisions.

By combining live earthquake data, graph-based visualization, facility discovery, and Gemini AI-powered assessments, CrisisGraph aims to make disaster information easier to understand and act upon.

## Features

- **Live Disaster Monitoring:** Ingests earthquake information from the USGS earthquake data service.
- **Interactive Incident Graph:** Visualizes disaster incidents and their known relationships with relevant locations, facilities, and resources.
- **AI-Powered Assessment:** Uses Google Gemini to analyze incident information and generate disaster assessments.
- **Emergency Facility Discovery:** Helps identify nearby emergency facilities using the project's discovery integrations.
- **Resource Coordination:** Supports resource assessment and allocation based on available data and known relationships.
- **Incident Dependency Analysis:** Represents connections and potential dependencies that may affect disaster response.
- **Interactive Dashboard:** Provides a web interface for exploring incidents and their associated information.
- **Transparent Results:** Distinguishes available information from inferred or unknown data to reduce misleading conclusions.

## Technology Stack

| Component | Technology |
|---|---|
| Backend | Python, FastAPI |
| API Server | Uvicorn |
| Frontend | HTML, CSS, JavaScript |
| AI Integration | Google Gemini API |
| Disaster Data | USGS Earthquake API |
| Database | SQLite, if configured in the current implementation |
| Testing | pytest |

## Project Structure

```text
CrisisGraph/
├── backend/
│   ├── app/
│   │   ├── agent.py
│   │   ├── allocator.py
│   │   ├── assess.py
│   │   ├── db.py
│   │   ├── discover.py
│   │   ├── ingest.py
│   │   ├── main.py
│   │   └── seed.py
│   └── tests/
├── docs/
│   └── frontend/
│       ├── index.html
│       ├── incident.html
│       ├── api.js
│       ├── app.css
│       └── theme.js
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

*Note: Adjust the structure above to match the actual files in your repository.*

## Prerequisites

Before running CrisisGraph, install:

- Python 3.10 or later, subject to dependency requirements.
- pip, the Python package manager.
- Git.
- A Google Gemini API key for AI-powered assessments.

## Installation and Setup

### 1. Clone the Repository

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
cd CrisisGraph
```

Replace `YOUR_GITHUB_REPOSITORY_URL` with your actual GitHub repository URL.

### 2. Create a Virtual Environment

For Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, use Command Prompt:

```bat
.venv\Scripts\activate.bat
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the location expected by your backend configuration.

```env
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=your_supported_gemini_model
```

Replace the placeholder values with your actual API key and a model supported by your Gemini API configuration.

**Security:** Never commit your `.env` file, API keys, or other secrets to GitHub. Keep a `.env.example` file containing placeholders only.

### 5. Start the Backend

From the project root, run:

```powershell
uvicorn backend.app.main:app --reload
```

If the import path differs in your repository, use the command appropriate for your backend entry point.

### 6. Open the Frontend

Open `docs/frontend/index.html` in your browser if the frontend is designed to run directly as a static page. If your setup requires a local web server, serve the frontend using your preferred static server and ensure the API base URL points to the running backend.

With the default Uvicorn configuration, the following addresses are commonly used:

- **Application API:** `http://127.0.0.1:800