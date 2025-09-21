import streamlit as st
from crewai import Agent, Task, Crew, LLM
from textwrap import dedent
from dotenv import load_dotenv
import os
import json
import re
import ast

# Optional: pip install json5
try:
    import json5
except ImportError:
    json5 = None

# --- Load environment variables ---
load_dotenv()

# --- Streamlit UI ---
st.set_page_config(
    page_title="🤖 Multi-Agent Builder",
    page_icon="🛠️",
    layout="wide",
)

# --- Custom CSS for Professional Dark Mode ---
st.markdown(
    """
    <style>
    /* Global dark background */
    .stApp {
        background-color: #0e1117;
        color: #e0e0e0;
        font-family: 'Segoe UI', sans-serif;
    }

    /* Banner styling */
    .banner-container {
        display: flex;
        justify-content: center;
        margin-bottom: 20px;
    }
    .banner-container img {
        border-radius: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.6);
        max-width: 100%;
        height: 180px;      /* 👈 force height */
        object-fit: cover;  /* 👈 crop while preserving aspect */
    }

    /* Title styling */
    h1 {
        color: #61dafb;
        text-align: center;
        margin-bottom: 0.5em;
    }

    /* Section headers */
    .stSubheader {
        color: #ffcc00 !important;
    }

    /* Card-like containers */
    .stExpander {
        background-color: #1c1f26 !important;
        border: 1px solid #333;
        border-radius: 10px;
    }

    /* Buttons */
    .stButton button {
        background: linear-gradient(90deg, #61dafb, #007acc);
        color: black;
        border-radius: 8px;
        font-weight: bold;
        padding: 0.6em 1.2em;
        border: none;
        box-shadow: 0 3px 6px rgba(0,0,0,0.3);
    }
    .stButton button:hover {
        background: linear-gradient(90deg, #21a1f1, #005f99);
        color: white;
    }

    /* Text areas */
    textarea {
        background-color: #1c1f26 !important;
        color: #e0e0e0 !important;
        border-radius: 8px;
        border: 1px solid #333 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Configure Azure LLM for CrewAI ---
llm = LLM(
    model="azure/" + os.getenv("AZURE_DEPLOYMENT_NAME"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_base=os.getenv("AZURE_ENDPOINT"),
    api_version=os.getenv("OPENAI_API_VERSION"),
    temperature=0.3,
)

# --- Define Agents ---
manager = Agent(
    role="Project Manager",
    goal="Understand user request, decide what agents are needed, and suggest tools + implementation plan.",
    backstory=dedent("""\
        You are the project manager. 
        You analyze the user request, extract the exact technology stacks mentioned by the user,
        and pass them down to the System Architect, UI Developer, and Backend Developer.

        ⚠️ Hard rules:
        - Always capture the exact frontend and backend stacks explicitly mentioned by the user. 
          (e.g., if the user says React + .NET Core, you must forward React + .NET Core, not alternatives).
        - Do not substitute technologies, only forward what the user requested.
        - If the user does not specify, you may suggest appropriate stacks.
    """),
    allow_delegation=True,
    llm=llm,
)

architect_agent = Agent(
    role="System Architect",
    goal="Design high-level architecture and technology stack based on requirements.",
    backstory=dedent("""\
        You are a skilled software architect.

        ⚠️ Hard rules:
        - You MUST use **exactly** the frontend and backend stacks passed from the Manager.
        - Never replace or suggest alternatives for frontend/backend.
        - You may only add complementary tools (databases, hosting, authentication, logging).
        - When listing stacks, explicitly confirm the user-requested frontend and backend, 
          without modification, duplication, or extension.
        - Example: If Manager says "React + Node.js", you must output "React.js (frontend), Node.js (backend)".

        You MUST always output:
        1. A Mermaid diagram showing system architecture.
        2. A list of chosen technologies for frontend, backend, database, and infrastructure,
           explicitly confirming the user-requested frontend/backend.
    """),
    allow_delegation=False,
    llm=llm,
)

ui_agent = Agent(
    role="UI Developer",
    goal=dedent("""
        Generate frontend code from requirements.

        You MUST always produce output in this structure:

        ### Project Folder Structure
        ```plaintext
        /project-root
          /src
            (list all main files & folders here)
          package.json (if applicable)
          README.md
        ```

        ### File-by-File Code
        For each file:
        - Start with a heading: `#### /path/to/file`
        - Provide the code inside a fenced block with the correct language identifier:
          - ```javascript → React, Vue, Svelte
          - ```typescript → Angular (TS), Next.js with TS
          - ```html → plain HTML templates
          - ```css → stylesheets
          - ```csharp → Blazor Razor components
          - ```dart → Flutter
        - Never leave files empty. If the file is too long, shorten with comments like: // ... rest of code ...

        ### Step-by-Step Instructions
        - Provide clear setup & run instructions as a numbered list.
        - Wrap terminal commands inside ```bash code blocks```.
        - Adapt instructions to the chosen framework:
          - React / Vue → npm install && npm start
          - Angular → npm install && ng serve
          - Blazor → dotnet run
          - Flutter → flutter run
          - Plain HTML → just open index.html in a browser

        ---
        RULES:
        - Do NOT output raw "bash" labels or dangling text.
        - Do NOT repeat sections.
        - Do NOT mix instructions with code.
        - Always adapt folder structure and commands to the selected frontend framework.
    """),
    backstory=dedent("""
        You are a senior frontend engineer who always delivers professional,
        runnable projects with consistent formatting, valid code, and clear setup guides.
    """),
    allow_delegation=False,
    llm=llm,
)

backend_agent = Agent(
    role="Backend Developer",
    goal=dedent("""\
        Generate backend code in the technology specified in the plan.

        You MUST produce:
        1. A full project folder structure (like a tree view).
        2. File-by-file code inside fenced code blocks, with correct paths.
        3. Configuration files (e.g., application.properties, package.json, etc.).
        4. Step-by-step instructions to install dependencies, configure the environment, and run the backend locally.

        Adapt strictly to the requested backend framework:
        - FastAPI / Python
        - ASP.NET Core / C#
        - Node.js / Express
        - Django / Python
        - Spring Boot / Java
    """),
    backstory="You are a backend engineer who delivers complete project skeletons with code and instructions.",
    allow_delegation=False,
    llm=llm,
)

testing_agent = Agent(
    role="QA / Testing Engineer",
    goal=dedent("""\
        Ensure that the generated frontend and backend projects are testable and reliable.

        You MUST:
        1. Generate automated test cases for the project.
        2. For frontend → use a common testing framework:
           - React → Jest + React Testing Library
           - Angular → Jasmine + Karma
           - Vue → Jest / Vitest
           - Blazor → xUnit / bUnit
        3. For backend → use a common testing framework:
           - Node.js → Jest / Mocha
           - ASP.NET Core → xUnit
           - Python (FastAPI/Django) → Pytest
           - Java (Spring Boot) → JUnit
        4. Provide:
           - Folder structure for tests (e.g., `/tests` or `/__tests__`).
           - Example test files with at least one working test.
           - Instructions for running the tests.
    """),
    backstory="You are a QA engineer who always provides runnable automated tests, ensuring generated projects are production-ready.",
    allow_delegation=False,
    llm=llm,
)

# --- JSON Parsing Helpers ---
def safe_json_repair(text: str) -> str:
    """Fix common JSON issues like unterminated strings, trailing commas, bad newlines."""
    text = re.sub(r'"\s*\n\s*"', '" "', text)  # remove unescaped newlines inside quotes
    text = re.sub(r",(\s*[}\]])", r"\1", text)  # remove trailing commas
    return text

def parse_json_response(raw_text: str):
    """Extract JSON from LLM output, tolerant of markdown fences and minor issues."""
    try:
        match = re.search(r"```(?:json)?(.*?)```", raw_text, re.DOTALL)
        if match:
            raw_text = match.group(1).strip()

        raw_text = safe_json_repair(raw_text)
        return json.loads(raw_text)
    except Exception:
        if json5:
            try:
                return json5.loads(raw_text)
            except Exception:
                pass
        try:
            return ast.literal_eval(raw_text)
        except Exception as e:
            return [{"agent": "Manager", "task": f"Could not parse: {e}", "tools": [], "plan": raw_text}]

def enforce_output_consistency(agent_name: str, raw_text: str, user_request: str) -> str:
    """Force agent outputs to align with user-requested stacks without overcorrecting."""
    if agent_name != "System Architect":
        return raw_text

    req_lower = user_request.lower()
    wants_dotnet = any(k in req_lower for k in [".net", "dotnet", "asp.net"])
    wants_node = "node" in req_lower
    wants_react = "react" in req_lower

    # Normalize React
    if wants_react:
        raw_text = re.sub(r"\bReact(\.js){1,}\b", "React.js", raw_text, flags=re.I)

    # Normalize backend
    if wants_dotnet:
        raw_text = re.sub(r"\b(Node\.js|Express(\.js)?|Spring Boot|Django|FastAPI)\b", "ASP.NET Core", raw_text, flags=re.I)
    elif wants_node:
        raw_text = re.sub(r"\b(ASP\.NET Core|Spring Boot|Django|FastAPI)\b", "Node.js", raw_text, flags=re.I)
        raw_text = re.sub(r"\bNode(\.js)?(\s*/\s*Express)?\b", "Node.js / Express", raw_text, flags=re.I)

    # Remove silly duplicates
    raw_text = re.sub(r"\b(ASP\.NET Core|React\.js)\s+with\s+\1\b", r"\1", raw_text)

    return raw_text

def enforce_stack_consistency(user_request: str, plan: list) -> list:
    """Make sure the Architect (and later tasks) stick to the exact frontend/backend stacks mentioned by the user request."""
    req_lower = user_request.lower()
    frontend_stack, backend_stack = None, None

    if "react" in req_lower:
        frontend_stack = "React.js"
    elif "angular" in req_lower:
        frontend_stack = "Angular"
    elif "vue" in req_lower:
        frontend_stack = "Vue.js"
    elif "blazor" in req_lower:
        frontend_stack = "Blazor"

    if ".net" in req_lower or "dotnet" in req_lower:
        backend_stack = "ASP.NET Core"
    elif "spring boot" in req_lower:
        backend_stack = "Spring Boot"
    elif "fastapi" in req_lower:
        backend_stack = "FastAPI"
    elif "django" in req_lower:
        backend_stack = "Django"
    elif "node" in req_lower or "express" in req_lower:
        backend_stack = "Node.js / Express"

    for item in plan:
        if item["agent"] == "System Architect":
            if frontend_stack and frontend_stack not in " ".join(item["tools"]):
                item["tools"] = [frontend_stack] + [t for t in item["tools"] if t != frontend_stack]
                item["plan"] = f"(Adjusted) Use {frontend_stack} for frontend. " + item["plan"]

            if backend_stack and backend_stack not in " ".join(item["tools"]):
                item["tools"] = [backend_stack] + [t for t in item["tools"] if t != backend_stack]
                item["plan"] = f"(Adjusted) Use {backend_stack} for backend. " + item["plan"]

    return plan

def enforce_plan_structure(plan):
    """Ensure parsed output is always a list of dicts with required keys."""
    required_keys = {"agent", "task", "tools", "plan"}

    # If top-level dict has "agents", unwrap it
    if isinstance(plan, dict) and "agents" in plan:
        plan = plan["agents"]

    if not isinstance(plan, list):
        plan = [plan]

    cleaned = []
    for item in plan:
        if not isinstance(item, dict):
            item = {"agent": "Manager", "task": "Invalid item", "tools": [], "plan": str(item)}

        # 🔄 Map alternative keys
        mapped = {
            "agent": item.get("agent") or item.get("role", ""),
            "task": item.get("task") or item.get("taskDescription") or item.get("task_description", ""),
            "tools": item.get("tools") or item.get("toolsFrameworks") or item.get("tools_frameworks") or [],
            "plan": item.get("plan") or item.get("implementationPlan") or item.get("implementation_plan", ""),
        }

        # Guarantee all required keys
        for key in required_keys:
            mapped.setdefault(key, "")

        cleaned.append(mapped)
    return cleaned

# --- Manager analyzes scope ---
def manager_suggests_plan(user_request: str):
    """Ask the manager agent to suggest which agents + tools + plan to use"""
    suggestion_task = Task(
        description=dedent(f"""
            Analyze the following user request: {user_request}

            Break down the solution into phases:
            - System Architect (always included)
            - UI Developer (include only if frontend stack is mentioned)
            - Backend Developer (include only if backend stack is mentioned)
            - QA / Testing Engineer (always include if either frontend or backend is planned)

            For each selected agent, provide:
            1. The agent role
            2. The task description
            3. The exact tools/frameworks they will use 
               (e.g., ["React", "TailwindCSS"] or ["ASP.NET Core", "C#"])
            4. A short implementation plan

            ⚠️ Important:
            - Always output **valid JSON** (machine readable).
            - Do NOT include raw Mermaid diagrams, code, or markdown inside JSON strings.
            - If you need to mention them, just describe in plain text inside the "plan".
            - JSON must remain valid and parseable.
        """),
        expected_output="JSON containing selected agents, tools, and plan",
        agent=manager,
    )

    crew = Crew(agents=[manager], tasks=[suggestion_task], process="sequential", verbose=True)
    raw_result = crew.kickoff()
    plan = parse_json_response(raw_result.raw)
    plan = enforce_plan_structure(plan)

    # 🚨 Drop backend if no backend tools were suggested
    plan = [p for p in plan if not (
        p["agent"] == "Backend Developer" and not p["tools"]
    )]

    # 🚨 Always add QA if frontend or backend exists
    has_ui = any(p["agent"] == "UI Developer" for p in plan)
    has_backend = any(p["agent"] == "Backend Developer" for p in plan)
    has_qa = any(p["agent"] == "QA / Testing Engineer" for p in plan)

    if (has_ui or has_backend) and not has_qa:
        plan.append({
            "agent": "QA / Testing Engineer",
            "task": "Generate automated test cases for the project.",
            "tools": ["Jest", "Pytest", "xUnit", "JUnit"],
            "plan": "Provide a test folder structure, sample tests, and run instructions.",
        })

    return plan

# --- Assign tasks dynamically ---
def assign_agents_from_plan(plan: list):
    """Convert manager's plan into actual CrewAI tasks"""
    tasks = []
    for item in plan:
        if item["agent"] == "System Architect":
            tasks.append(
                Task(
                    description=f"""{item['task']}

                    ⚠️ IMPORTANT:
                    You MUST output:
                    1. A Mermaid diagram showing system architecture (frontend, backend, database, integrations).
                    2. A clear explanation of the chosen tech stack (frontend framework, backend framework, database, hosting/infrastructure).
                    """,
                    expected_output="Architecture design with a Mermaid diagram and chosen tech stack.",
                    agent=architect_agent,
                )
            )
        elif item["agent"] == "UI Developer":
            tech_hint = ", ".join(item["tools"]) if item["tools"] else "a suitable frontend framework"
            tasks.append(
                Task(
                    description=f"""{item['task']}

                    ⚠️ IMPORTANT:
                    You MUST output:
                    1. A complete project folder structure (tree view).
                    2. File-by-file code inside fenced code blocks with correct paths.
                    3. Instructions for installing dependencies and running the project locally.

                    The frontend must use: {tech_hint}.
                    """,
                    expected_output=f"Frontend project ({tech_hint}) including structure, code, and run guide.",
                    agent=ui_agent,
                )
            )
        elif item["agent"] == "Backend Developer":
            tech_hint = ", ".join(item["tools"]) if item["tools"] else "a suitable backend framework"
            tasks.append(
                Task(
                    description=f"""{item['task']}

                    ⚠️ IMPORTANT:
                    You MUST output:
                    1. A complete project folder structure (tree view).
                    2. File-by-file code inside fenced code blocks with correct paths.
                    3. Configuration files (application.properties, package.json, etc.).
                    4. Instructions for installing dependencies, configuring environment, and running locally.

                    The backend must use: {tech_hint}.
                    """,
                    expected_output=f"Backend project ({tech_hint}) including structure, code, configs, and run guide.",
                    agent=backend_agent,
                )
            )
        elif item["agent"] == "QA / Testing Engineer":
            tasks.append(
                Task(
                    description=f"""{item['task']}

                    ⚠️ IMPORTANT:
                    You MUST output:
                    1. A folder structure for tests.
                    2. At least one test file for frontend or backend (depending on requested stack).
                    3. Instructions for running the tests.

                    Framework hint: {", ".join(item["tools"])}.
                    """,
                    expected_output="Automated test cases, folder structure, and run instructions.",
                    agent=testing_agent,
                )
            )
    
    return tasks

# --- Run CrewAI ---
def run_agents(plan: list):
    tasks = assign_agents_from_plan(plan)
    if not tasks:
        return "❌ No relevant agents found for this request."

    # Build agents list dynamically from plan
    selected_agents = [manager]
    for p in plan:
        if p["agent"] == "System Architect":
            selected_agents.append(architect_agent)
        elif p["agent"] == "UI Developer":
            selected_agents.append(ui_agent)
        elif p["agent"] == "Backend Developer":
            selected_agents.append(backend_agent)

    crew = Crew(
        agents=selected_agents,
        tasks=tasks,
        verbose=True,
        process="sequential",
    )
    return crew.kickoff()

# --- Rendering Helper ---
def render_agent_output(agent_output):
    """Render agent output: detect code blocks and display them properly."""
    raw_text = agent_output.raw if agent_output.raw else agent_output.summary
    if not raw_text:
        st.info("⚠️ No output generated.")
        return

    raw_text = enforce_output_consistency(agent_output.agent, raw_text, st.session_state.get("last_user_request", ""))

    code_blocks = re.findall(r"```(\w+)?\n(.*?)```", raw_text, re.DOTALL)

    if code_blocks:
        text_without_code = re.sub(r"```.*?```", "", raw_text, flags=re.DOTALL).strip()
        if text_without_code:
            st.markdown(text_without_code)
        for lang, code in code_blocks:
            lang = lang.lower() if lang else ""
            st.code(code.strip(), language=lang if lang else "text")
    else:
        st.markdown(raw_text)

# --- Streamlit UI ---
st.set_page_config(page_title="Autonomus Multi-Agent Dev(H)Zero", page_icon="🛠️")
st.markdown('<div class="banner-container">', unsafe_allow_html=True)
st.image("banner.png", use_container_width=True)
st.markdown('</div>', unsafe_allow_html=True)

st.title("🤖 Autonomus Multi-Agent Dev(H)Zero (Azure GPT)")

st.markdown("### ✍️ Enter your project request below")
user_prompt = st.text_area(
    "",
    placeholder="e.g., Create a login page with Angular frontend and ASP.NET Core backend",
    height=120,
)

if st.button("Analyze Request"):
    if user_prompt.strip():
        st.session_state.last_user_request = user_prompt
        with st.spinner("Manager analyzing your request..."):
            raw_plan = manager_suggests_plan(user_prompt)
            st.session_state.plan = enforce_stack_consistency(user_prompt, raw_plan)

        st.subheader("✅ Manager Suggestion")
        for idx, item in enumerate(st.session_state.plan, start=1):
            with st.expander(f"🔹 {item['agent']} — {item['task']}"):
                st.markdown(f"**🛠️ Tools:** {', '.join(item['tools'])}")
                st.markdown(f"**📋 Plan:** {item['plan']}")

        st.info("👉 If this looks good, click **Run Agents**. Otherwise, rephrase your request.")
    else:
        st.warning("⚠️ Please enter a request first.")

if st.button("Run Agents"):
    if "plan" in st.session_state and st.session_state.plan:
        with st.spinner("Agents are working..."):
            result = run_agents(st.session_state.plan)

        st.subheader("📌 Final Output")
        if hasattr(result, "tasks_output"):
            for idx, t in enumerate(result.tasks_output, start=1):
                with st.expander(f"🤖 Agent {idx}: {t.agent}"):
                    render_agent_output(t)
        else:
            st.write(result)
    else:
        st.warning("⚠️ Please analyze the request first.")
