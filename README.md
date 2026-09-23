# Jerryy's AI

> **Jerryy's AI** — Autonomous AI Exam Preparation Model & Interactive 3D WebGL Studio.

![Jerryy's AI](frontend/index.html)

---

## 🎨 Overview

**Jerryy's AI** is an intelligent model purpose-built for comprehensive exam preparation, syllabus mastery, and problem solving combined with an interactive real-time WebGL physics engine. Jerryy's AI helps students and educators deconstruct complex curricula, master high-yield topics, and test conceptual retention.

As you explore Jerryy's AI, the background 3D gravity field of 96 glass and matte spheres dynamically morphs and fluidly interpolates in real-time.

---

## ✨ Features

- 🤖 **Jerryy's AI Exam Preparation Model**:
  - Contextual domain intelligence (Fintech, Cyberpunk, Healthcare, Luxury, Gaming, SaaS, E-Commerce, Nature, Minimalist).
  - Exact HEX matching with algorithmic color harmonies (Monochromatic, Analogous, Complementary, Triadic, Split-Complementary).
  - Dynamic palette generator: Primary, Secondary, Accent, Neutral Background, Surface Card, and High-Contrast Text colors.
- 🔮 **3D Physics Simulation**:
  - Powered by Three.js (WebGL).
  - 96 floating spheres with dual physical shaders (specular glass & smooth matte).
  - Verlet physics integration, collision resolution, and smooth cursor repulsion force.
  - Smooth color lerping on every palette recommendation.
- 📐 **Accessibility & WCAG 2.1 Auditing**:
  - Real-time contrast ratio calculations against light and dark backgrounds.
  - Instant compliance rating (AAA, AA, Large Text, or Warning).
- 📋 **Export & Copy**:
  - Click-to-copy HEX codes.
  - Instant export to CSS Variables, JSON format, and Tailwind CSS configuration.
- 💎 **Aesthetics & Typography**:
  - Premium dark glassmorphic UI.
  - Elegant typography featuring Google Fonts **Raleway** and **JetBrains Mono**.

---

## 🚀 Quick Start

### 1. Standalone Frontend (No build tools required)
You can directly open `index.html` in any modern web browser or serve it with any static server:

```bash
# Using Python built-in server:
python -m http.server 3000

# Or using npx serve:
npx serve .
```

Visit `http://localhost:8000` to interact with Jerryy's AI and the 3D physics engine.

---

### 2. Full-Stack with Python FastAPI Backend

To enable server-side processing and extended AI color suggestions:

```bash
# Navigate to backend directory
cd backend

# Install dependencies
pip install -r requirements.txt

# Run the FastAPI server with Uvicorn
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at:
- **Interactive API Docs (Swagger UI)**: `http://localhost:8000/docs`
- **Chat Endpoint**: `POST http://localhost:8000/api/chat`
- **Health Check**: `GET http://localhost:8000/api/health`

---

## 📂 Project Structure

```text
Jerryy-s-AI/
├── index.html              # Standalone single-file frontend with Three.js & Jerryy's AI UI
├── frontend/
│   ├── index.html          # Frontend app source with Supabase Auth & DB sync
│   └── chat.html           # Dedicated chat view
├── backend/
│   ├── main.py             # FastAPI backend server with CORS & endpoints
│   ├── ollama_client.py    # Local Ollama client bridge
│   ├── chat_profiles.py    # Domain-specific system prompts
│   ├── requirements.txt    # Python dependencies
│   └── README.md           # Backend documentation
├── supabase/
│   └── schema.sql          # Supabase SQL schema (conversations, messages, RLS)
├── .gitignore              # Git ignore rules for Python & temp files
└── README.md               # Project overview & documentation
```

---

## 🛠️ Tech Stack

- **Frontend**: HTML5, Vanilla CSS3 (Custom Design System), JavaScript (ES Modules), Three.js (r160)
- **Backend**: Python 3.10+, FastAPI, Uvicorn, Pydantic, HTTPX
- **Fonts**: [Raleway](https://fonts.google.com/specimen/Raleway), [JetBrains Mono](https://fonts.google.com/specimen/JetBrains+Mono)

---

## 📄 License

MIT License. Feel free to use and customize for your projects!
