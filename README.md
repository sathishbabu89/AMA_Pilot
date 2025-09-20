

# 📖 README.md (Draft)

```markdown
# 🤖 Multi-Agent Dynamic Builder (CrewAI + Azure OpenAI + Streamlit)

---

## 🌟 Overview

This project is an **autonomous multi-agent system** that can **analyze user requirements, design a solution, and implement frontend + backend code automatically**.  

It leverages **[CrewAI](https://github.com/joaomdmoura/crewAI)** for orchestrating LLM-powered agents, integrates with **Azure OpenAI GPT models**, and provides a **Streamlit web interface** for human-in-the-loop control.  

Think of it as your **AI-powered software team**:
- 🧑‍💼 **Project Manager** – interprets user requirements and decides who should work on them.  
- 🏗️ **System Architect** – designs the high-level architecture, diagrams, and technology stack.  
- 🎨 **UI Developer** – generates frontend code in the requested framework.  
- ⚙️ **Backend Developer** – builds backend APIs in the specified language/framework.  

---

## 🚀 Key Features

- **Autonomous Analysis** → Agents read your request and decide how to break it down.  
- **Flexible Framework Choice** → Supports React, Angular, Vue, Blazor, ASP.NET Core, FastAPI, Django, Express, Spring Boot, and more.  
- **Dynamic Planning** → Manager produces a JSON plan that is enforced across agents.  
- **Human-in-the-Loop** → You review the plan before execution.  
- **Rich Code Rendering** → Frontend & backend code snippets are neatly displayed in Streamlit.  
- **Azure GPT Integration** → Uses enterprise-grade Azure OpenAI endpoints.  

---

## 🏗️ Architecture

This project follows a **multi-agent architecture** powered by CrewAI:

```

User Request --> Project Manager --> System Architect --> UI Developer --> Backend Developer --> Output Code

````

- **Project Manager**: Reads natural language input, outputs a structured JSON plan (agents, tasks, tools, and steps).  
- **System Architect**: Designs high-level system diagrams (Mermaid/Markdown), defines stack.  
- **UI Developer**: Generates UI code using the frameworks requested in the plan.  
- **Backend Developer**: Generates API/backend code using requested backend frameworks.  
- **Streamlit UI**: Lets the human approve/reject plans, view results, and iterate.  

---

## 📦 Installation

### 1️⃣ Clone Repository

```bash
git clone https://github.com/yourusername/multi-agent-builder.git
cd multi-agent-builder
````

### 2️⃣ Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate   # Linux/Mac
venv\Scripts\activate      # Windows
```

### 3️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

Dependencies include:

* `streamlit` → Web UI
* `crewai` → Multi-agent orchestration
* `python-dotenv` → Env management
* `json5` → Flexible JSON parsing (optional)

---

## 🔑 Environment Setup

Create a `.env` file in the root folder with your Azure OpenAI credentials:

```ini
AZURE_OPENAI_API_KEY=your_api_key_here
AZURE_DEPLOYMENT_NAME=your_model_deployment_name
AZURE_ENDPOINT=https://your-resource-name.openai.azure.com/
OPENAI_API_VERSION=2024-05-01-preview
```

---

## ▶️ Running the App

Start the Streamlit app:

```bash
streamlit run app.py
```

Visit: [http://localhost:8501](http://localhost:8501)

---

## 🖥️ Usage Flow

### 1. Enter Your Request

Example:

```
Create a login page with Angular frontend and ASP.NET Core backend
```

### 2. Manager Suggestion

* The **Project Manager Agent** analyzes the request.
* Produces a structured JSON plan:

```json
[
  {
    "agent": "System Architect",
    "task": "Design architecture with frontend and backend",
    "tools": ["Mermaid", "Markdown"],
    "plan": "High-level diagram + tech decision"
  },
  {
    "agent": "UI Developer",
    "task": "Build login page",
    "tools": ["Angular", "TypeScript"],
    "plan": "Responsive form with validation"
  },
  {
    "agent": "Backend Developer",
    "task": "Build authentication API",
    "tools": ["ASP.NET Core", "C#"],
    "plan": "JWT-based authentication"
  }
]
```

### 3. Review Plan

You see each agent’s role, tools, and implementation plan in expandable panels.

### 4. Run Agents

* Architect designs diagrams
* UI Developer writes Angular code
* Backend Developer writes C# ASP.NET Core code

### 5. View Results

* Code blocks displayed in syntax-highlighted sections.
* Markdown + diagrams rendered inline.

---

## 🔍 Code Walkthrough

### 🔹 `manager_suggests_plan`

* Asks the **Project Manager** agent to convert user request → structured JSON plan.

### 🔹 `assign_agents_from_plan`

* Converts JSON plan → CrewAI tasks, assigning them to Architect, UI, and Backend agents.

### 🔹 `run_agents`

* Orchestrates execution of all agents in sequence.

### 🔹 `render_agent_output`

* Detects ` ```code blocks``` ` in agent output and renders them properly in Streamlit.

---

## 🛠️ Agents

### 🧑‍💼 Project Manager

* Role: Break down user request into actionable steps.
* Output: JSON describing tasks, tools, and plans.

### 🏗️ System Architect

* Role: Produce high-level design + diagrams.
* Tools: Mermaid, Markdown.

### 🎨 UI Developer

* Role: Generate frontend code.
* Supports: React, Angular, Vue, Blazor, HTML/CSS.

### ⚙️ Backend Developer

* Role: Generate backend code.
* Supports: FastAPI, ASP.NET Core, Django, Express, Spring Boot.

---

## 📊 Example Output

**Request:**

```
Create a login page with React frontend and FastAPI backend
```

**Result:**

* **UI Developer Output**: React login form with TailwindCSS.
* **Backend Developer Output**: FastAPI app with JWT authentication.

---

## ⚡ Advanced Features

* 🔄 **JSON Parsing Resilience** → Handles malformed LLM JSON with `json5` or fallback to `ast.literal_eval`.
* 🔌 **Pluggable Agents** → Easily add new roles like Database Engineer or DevOps Engineer.
* 🧑‍⚖️ **Human Oversight** → Approve manager plans before execution.
* 🖼️ **Code Rendering** → Supports multiple languages with syntax highlighting.

---

## 📈 Roadmap

* [ ] Add **Database Engineer Agent**
* [ ] Add **DevOps Agent** for CI/CD + deployment
* [ ] Integrate **Monitoring Agent** for observability
* [ ] Support **cloud deployment flows** (Azure App Service, AWS Lambda)
* [ ] Expand UI for live collaboration (multi-user session)

---

## 🤝 Contributing

1. Fork repo
2. Create feature branch
3. Submit PR

We welcome:

* New agents
* Better code parsing/rendering
* Deployment extensions

---

## 📜 License

MIT License.

---

## 🙌 Acknowledgements

* [CrewAI](https://github.com/joaomdmoura/crewAI) for agent orchestration
* [Streamlit](https://streamlit.io/) for UI
* [Azure OpenAI](https://learn.microsoft.com/en-us/azure/cognitive-services/openai/) for LLM backend


Would you like me to also include **screenshots (as placeholders in the README)** so it feels more like a polished GitHub project?
```
