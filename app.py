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
        You analyze the user request, decide which worker agents are required,
        and suggest tools, libraries, and frameworks each agent will use.
    """),
    allow_delegation=True,
    llm=llm,
)

architect_agent = Agent(
    role="System Architect",
    goal="Design high-level architecture and technology stack based on requirements.",
    backstory=dedent("""\
        You are a skilled software architect. 
        You design the system layout before implementation, selecting frontend, backend, and database technologies.
        You also produce diagrams (Mermaid/Markdown) when useful.
    """),
    allow_delegation=False,
    llm=llm,
)

ui_agent = Agent(
    role="UI Developer",
    goal=dedent("""\
        Generate frontend code from requirements.
        You MUST adapt to the framework specified in the plan:
        - If tools include React → generate React/JSX
        - If tools include Angular → generate Angular (TypeScript + HTML templates)
        - If tools include Vue.js → generate Vue Single File Component
        - If tools include Blazor → generate C# Razor component
        - If tools include plain HTML/CSS → generate static HTML + CSS
        Always follow the exact stack requested by the manager.
    """),
    backstory="You are a skilled frontend engineer who writes clean, framework-specific code.",
    allow_delegation=False,
    llm=llm,
)

backend_agent = Agent(
    role="Backend Developer",
    goal=dedent("""\
        Generate backend code in the technology specified in the plan.
        You MUST adapt to the requested backend framework:
        - FastAPI/Python
        - ASP.NET Core / C#
        - Node.js / Express
        - Django / Python
        - Spring Boot / Java
        Always follow the exact stack requested by the manager.
    """),
    backstory="You are a versatile backend engineer skilled in multiple frameworks and languages.",
    allow_delegation=False,
    llm=llm,
)

# --- JSON Parsing Helper ---
def parse_json_response(raw_text: str):
    """Extract JSON from LLM output, tolerant of markdown fences and minor issues."""
    try:
        match = re.search(r"```(?:json)?(.*?)```", raw_text, re.DOTALL)
        if match:
            raw_text = match.group(1).strip()
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

def enforce_plan_structure(plan):
    """Ensure parsed output is always a list of dicts with required keys."""
    required_keys = {"agent", "task", "tools", "plan"}
    if not isinstance(plan, list):
        plan = [plan]
    cleaned = []
    for item in plan:
        if not isinstance(item, dict):
            item = {"agent": "Manager", "task": "Invalid item", "tools": [], "plan": str(item)}
        for key in required_keys:
            item.setdefault(key, "")
        cleaned.append(item)
    return cleaned

# --- Manager analyzes scope ---
def manager_suggests_plan(user_request: str):
    """Ask the manager agent to suggest which agents + tools + plan to use"""
    suggestion_task = Task(
        description=dedent(f"""
            Analyze the following user request: {user_request}

            Break down the solution into phases:
            - System Architect (decides high-level design and stack)
            - UI Developer (frontend)
            - Backend Developer (backend)

            For each selected agent, provide:
            1. The agent role
            2. The task description
            3. The exact tools/frameworks they will use 
               (e.g., ["React", "TailwindCSS"] or ["ASP.NET Core", "C#"])
            4. A short implementation plan

            ⚠️ Important: Always output specific frameworks.
            Example: Instead of "frontend", use "React" or "Angular".
            Example: Instead of "dotnet", use "ASP.NET Core" and "C#".

            Respond strictly in JSON list format, e.g.:
            [
              {{
                "agent": "System Architect",
                "task": "Design architecture with frontend, backend, and database",
                "tools": ["Mermaid", "Markdown"],
                "plan": "High-level design diagram + stack decision"
              }},
              {{
                "agent": "UI Developer",
                "task": "Build login page UI",
                "tools": ["React", "TailwindCSS"],
                "plan": "Responsive login form"
              }},
              {{
                "agent": "Backend Developer",
                "task": "Build authentication API",
                "tools": ["ASP.NET Core", "C#"],
                "plan": "JWT authentication service"
              }}
            ]
        """),
        expected_output="JSON containing selected agents, tools, and plan",
        agent=manager,
    )

    crew = Crew(agents=[manager], tasks=[suggestion_task], process="sequential", verbose=True)
    raw_result = crew.kickoff()

    plan = parse_json_response(raw_result.raw)
    return enforce_plan_structure(plan)

# --- Assign tasks dynamically ---
def assign_agents_from_plan(plan: list):
    """Convert manager's plan into actual CrewAI tasks"""
    tasks = []
    for item in plan:
        if item["agent"] == "System Architect":
            tasks.append(
                Task(
                    description=item["task"],
                    expected_output="Architecture design with diagrams and chosen tech stack.",
                    agent=architect_agent,
                )
            )
        elif item["agent"] == "UI Developer":
            tech_hint = ", ".join(item["tools"]) if item["tools"] else "a suitable frontend framework"
            tasks.append(
                Task(
                    description=f"""{item['task']}

                    ⚠️ IMPORTANT: The frontend must be implemented using {tech_hint}.
                    """,
                    expected_output=f"Frontend code ({tech_hint}) implementing the requested UI.",
                    agent=ui_agent,
                )
            )
        elif item["agent"] == "Backend Developer":
            tech_hint = ", ".join(item["tools"]) if item["tools"] else "a suitable backend framework"
            tasks.append(
                Task(
                    description=f"""{item['task']}

                    ⚠️ IMPORTANT: The backend must be implemented using {tech_hint}.
                    """,
                    expected_output=f"Backend code ({tech_hint}) implementing the requested logic.",
                    agent=backend_agent,
                )
            )
    return tasks

# --- Run CrewAI ---
def run_agents(plan: list):
    tasks = assign_agents_from_plan(plan)
    if not tasks:
        return "❌ No relevant agents found for this request."
    crew = Crew(
        agents=[manager, architect_agent, ui_agent, backend_agent],
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
st.set_page_config(page_title="🤖 Multi-Agent Builder", page_icon="🛠️")
st.title("🤖 Multi-Agent Dynamic Builder (Azure GPT)")

user_prompt = st.text_area(
    "Enter your request:",
    placeholder="e.g., Create a login page with Angular frontend and ASP.NET Core backend",
)

if st.button("Analyze Request"):
    if user_prompt.strip():
        with st.spinner("Manager analyzing your request..."):
            st.session_state.plan = manager_suggests_plan(user_prompt)

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
