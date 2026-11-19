# StudyMate AI

### Your Intelligent Learning Companion

**Transform study materials into meaningful learning experiences with Artificial Intelligence.**

StudyMate AI is an AI-powered web application designed to make learning more interactive, organized, and effective. It helps students transform their study materials into understandable summaries, interactive conversations, visual mind maps, and personalized study plans.

Instead of spending hours manually organizing learning materials, students can use StudyMate AI to explore their notes, understand complex concepts, and manage their learning activities through a single platform.

---

## About the Project

Learning often involves working with large amounts of information from textbooks, lecture notes, PDFs, and other educational resources. Students may spend considerable time reading, identifying important concepts, preparing summaries, and organizing their study schedules.

StudyMate AI aims to simplify this process by combining artificial intelligence with an interactive learning environment.

The platform provides different learning tools that help students move from simply reading information to actively understanding and organizing knowledge.

It brings multiple AI-powered learning capabilities together in one web application.

## Problem Statement

Students frequently face difficulties when managing large volumes of study materials.

Some common challenges include:

- Understanding lengthy and complicated study materials.
- Identifying important concepts from large documents.
- Preparing summaries manually.
- Visualizing relationships between different topics.
- Organizing study schedules effectively.
- Revisiting previously studied information.
- Finding an interactive way to clarify doubts.

Traditional study methods often require students to use multiple applications for these activities.

StudyMate AI addresses these challenges by providing an integrated AI-powered learning environment.

## Project Objectives

The primary objectives of StudyMate AI are:

1. To simplify the process of understanding educational materials.
2. To provide AI-powered assistance for learning-related questions.
3. To convert lengthy study materials into concise summaries.
4. To generate visual mind maps from educational content.
5. To help students organize their preparation through study planning.
6. To provide interactive learning and practice experiences.
7. To maintain study history for easier access to previous learning activities.
8. To create a unified learning platform that brings different study tools together.

## Key Features

### 1. AI Study Assistant

An interactive AI-powered assistant that helps students understand topics, explore concepts, and ask questions.

Students can communicate with the assistant through a conversational interface and receive explanations related to their learning activities.

### 2. Study Material Upload

Students can upload their educational materials to the platform.

The backend processes supported documents and extracts their content for further AI-powered operations.

Supported document formats include:

- PDF
- TXT
- Markdown

### 3. Intelligent Summarization

Convert lengthy study materials into more manageable summaries.

This feature helps students:

- Identify important information.
- Review lengthy documents.
- Understand the main concepts.
- Prepare study notes more efficiently.

### 4. AI-Powered Mind Maps

Transform educational content into structured visual mind maps.

Mind maps help students understand:

- Main concepts.
- Related topics.
- Subtopics.
- Relationships between ideas.

The mind map interface also supports interactive exploration and customization.

### 5. AI Study Planner

Organize study preparation through a personalized study-planning feature.

Students can provide information such as:

- Subject.
- Topics to study.
- Examination date.
- Available study hours.

The application generates a structured study plan based on the provided information.

### 6. Practice and Learning Activities

StudyMate AI includes practice-oriented learning features designed to help students reinforce their understanding.

### 7. Study History

Access previous learning conversations and maintain continuity between study sessions.

This helps students revisit earlier discussions without starting from scratch.

---

## How StudyMate AI Works

The application follows a frontend-backend architecture.

**Step 1 – User Interaction**

Students interact with the application through the React-based frontend.

**Step 2 – Material Upload**

Users upload their supported study materials through the application interface.

**Step 3 – Backend Processing**

The FastAPI backend receives requests, processes documents, and coordinates the required operations.

**Step 4 – AI Processing**

The backend communicates with the configured AI services to perform supported tasks such as answering questions, generating summaries, creating mind maps, and preparing study plans.

**Step 5 – Results Display**

The generated results are returned to the frontend and presented through interactive user interfaces.

---

## Technology Stack

StudyMate AI combines modern frontend technologies, backend development tools, and artificial intelligence services.

### Frontend Development

| Technology   | Purpose                                |
| ------------ | -------------------------------------- |
| React        | Building interactive user interfaces   |
| TypeScript   | Type-safe application development      |
| Vite         | Frontend development and build tooling |
| Tailwind CSS | Styling and interface development      |
| CSS          | Custom visual styling and animations   |

### Backend Development

| Technology | Purpose                     |
| ---------- | --------------------------- |
| Python     | Backend programming         |
| FastAPI    | Building REST API endpoints |
| PyMuPDF    | PDF processing              |
| PyPDF      | PDF text extraction         |
| Pydantic   | Data validation             |

### AI and External Integrations

| Technology            | Purpose                              |
| --------------------- | ------------------------------------ |
| Groq                  | AI-powered application features      |
| Cloudflare Workers AI | Mind map generation                  |
| Supabase              | Database and application integration |

### Development Tools

- Visual Studio Code
- Git
- GitHub
- PowerShell
- npm

---

## System Architecture

StudyMate AI follows a modular architecture that separates the frontend, backend, document-processing services, and AI integrations.

```text
                 STUDYMATE AI
                       |
              User Interface
                       |
                React Frontend
                       |
                  API Layer
                       |
                FastAPI Backend
                       |
          +------------+------------+
          |            |            |
     PDF Service   AI Services   Study Services
          |            |            |
     Document      Groq and     Study Planner
     Processing    Cloudflare   and Other Tasks
                       |
                   Supabase
                       |
                 Application Data
```

The modular structure makes the application easier to maintain, test, and extend.

---

## Project Directory Structure

```text
StudyMate-AI/
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── sections/
│   │   ├── pages/
│   │   ├── hooks/
│   │   └── assets/
│   │
│   ├── public/
│   ├── package.json
│   ├── package-lock.json
│   ├── vite.config.ts
│   └── README.md
│
├── backend/
│   ├── services/
│   │   ├── cloudflare_service.py
│   │   ├── gemini_service.py
│   │   ├── mind_map_service.py
│   │   └── pdf_service.py
│   │
│   ├── tests/
│   ├── main.py
│   ├── requirements.txt
│   └── README.md
│
├── screenshots/
│
├── docs/
│   └── STUDYMATE AI (1).docx.pdf
│
├── .gitignore
└── README.md
```

---

## Getting Started

Follow these instructions to run StudyMate AI locally.

### Prerequisites

Make sure you have installed:

- Node.js
- npm
- Python
- Git

### 1. Clone the Repository

```bash
git clone https://github.com/arshadalbido1998-lab/StudyMate-AI.git
```

Navigate into the project:

```bash
cd StudyMate-AI
```

### 2. Frontend Setup

Navigate to the frontend directory:

```bash
cd frontend
```

Install the required packages:

```bash
npm install
```

Start the development server:

```bash
npm run dev
```

### 3. Backend Setup

Open another terminal and navigate to the backend directory:

```bash
cd backend
```

Create a Python virtual environment:

```bash
python -m venv .venv
```

Activate the environment on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the backend dependencies:

```bash
pip install -r requirements.txt
```

### 4. Environment Configuration

The backend requires configuration for its external AI services and other integrations.

Create a `.env` file in the backend directory and configure the required variables according to the backend documentation.

**Important:** Never commit `.env` files, API keys, access tokens, or private credentials to GitHub.

### 5. Start the Backend Server

Run:

```bash
uvicorn main:app --reload
```

The backend development server will be available at:

```text
http://127.0.0.1:8000
```

---

## Project Documentation

The complete academic project report contains additional information about the project, its implementation, and its development.

[**View the Complete StudyMate AI Project Report (PDF)**](docs/STUDYMATE%20AI%20%281%29.docx.pdf)

---

## Future Enhancements

StudyMate AI can be extended with additional capabilities in future versions.

Potential improvements include:

- Additional AI-powered learning tools.
- Improved document understanding.
- More interactive mind map features.
- Advanced quiz generation.
- Personalized learning recommendations.
- Enhanced progress tracking.
- Additional document formats.
- Improved performance and response times.
- Deployment and production infrastructure.

---

## Project Information

| Detail               | Information                    |
| -------------------- | ------------------------------ |
| Project Name         | StudyMate AI                   |
| Project Type         | AI-Powered Web Application     |
| Frontend             | React and TypeScript           |
| Backend              | Python and FastAPI             |
| AI Integration       | Groq and Cloudflare Workers AI |
| Database Integration | Supabase                       |
| Repository           | GitHub                         |

## Author

**Yashar**

Bachelor of Computer Applications (BCA)

Thiruvalluvar College

---

## Acknowledgement

StudyMate AI was developed as an academic project with the goal of exploring how artificial intelligence can support modern learning experiences.

This project provided an opportunity to work with frontend development, backend programming, API integration, document processing, and AI-powered application development.

---

**Study smarter. Understand better. Learn with StudyMate AI.**
