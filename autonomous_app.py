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


# ==============================
# Load Environment
# ==============================
load_dotenv()


# ==============================
# Configure OpenRouter Grok LLM
# ==============================
llm = LLM(
    model="openrouter/x-ai/grok-4-fast:free",
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
    temperature=0.3,
)


# ==============================
# Base Manager Agent
# ==============================
manager = Agent(
    role="Project Manager",
    goal="Understand user request, decide what agents are needed, and dynamically create a project plan.",
    backstory=dedent("""\
        You are the project manager.
        You analyze the user request, decide which worker agents are required,
        and suggest tools, libraries, and frameworks each agent will use.
        You can delegate and recursively assign tasks to other agents.
    """),
    allow_delegation=True,
    llm=llm,
)

dynamic_agents = {"Project Manager": manager}


# ==============================
# Agent Factory
# ==============================
def get_or_create_agent(role: str, goal: str = "", backstory: str = "", allow_delegation=False):
    """Fetch or create an agent dynamically based on role name."""
    if role in dynamic_agents:
        return dynamic_agents[role]

    agent = Agent(
        role=role,
        goal=goal or f"Fulfill the responsibilities of a {role}.",
        backstory=backstory or f"You are a skilled {role} who can perform tasks autonomously.",
        allow_delegation=allow_delegation,
        llm=llm,
    )
    dynamic_agents[role] = agent
    return agent


# ==============================
# JSON Helpers
# ==============================
def parse_json_response(raw_text: str):
    """Extract JSON from LLM output, tolerant of markdown fences and formatting issues."""
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
            return [
                {"agent": "Manager", "task": f"Could not parse: {e}", "tools": [], "plan": raw_text}
            ]


def enforce_plan_structure(plan):
    """Normalize LLM plan output into a list of dicts with consistent keys."""
    if not isinstance(plan, list):
        plan = [plan]

    normalized = []
    for item in plan:
        if not isinstance(item, dict):
            item = {"agent": "Manager", "task": "Invalid item", "tools": [], "plan": str(item)}

        normalized.append({
            "agent": item.get("agent") or item.get("agent_role") or item.get("role") or "—",
            "task": item.get("task") or item.get("task_description") or "—",
            "tools": item.get("tools") or item.get("tools_frameworks") or [],
            "plan": item.get("plan") or item.get("implementation_plan") or "—",
        })
    return normalized


# ==============================
# Manager Suggestion
# ==============================
def manager_suggests_plan(user_request: str):
    """Ask the manager agent to suggest agents + tools + plan in JSON format."""
    suggestion_task = Task(
        description=dedent(f"""
            Analyze the following user request: {user_request}

            Break down the solution into phases.
            For each selected agent, provide:
            1. The agent role
            2. The task description
            3. The exact tools/frameworks they will use
            4. A short implementation plan

            ⚠️ Respond strictly in JSON list format.
        """),
        expected_output="JSON containing selected agents, tools, and plan",
        agent=manager,
    )

    crew = Crew(agents=[manager], tasks=[suggestion_task], process="sequential", verbose=True)
    raw_result = crew.kickoff()
    plan = parse_json_response(raw_result.raw)
    return enforce_plan_structure(plan)


# ==============================
# Task Builder
# ==============================
def build_tasks_from_plan(plan: list):
    """Turn Manager's JSON plan into actual CrewAI tasks with dynamic agents."""
    tasks = []
    for item in plan:
        role = item["agent"]
        task_desc = item["task"]
        tools = item.get("tools", [])
        plan_notes = item.get("plan", "")

        if isinstance(tools, str):
            tools = [tools]

        agent = get_or_create_agent(
            role=role,
            goal=f"Use {', '.join(tools)} to {task_desc}" if tools else task_desc,
            backstory=f"You are the {role}. You specialize in using {', '.join(tools)}.",
            allow_delegation=(role == "Project Manager"),
        )

        tasks.append(
            Task(
                description=f"""{task_desc}

                Tools to use: {', '.join(tools) if tools else "any suitable tools"}.
                Plan notes: {plan_notes}
                """,
                expected_output=f"Deliverables for: {role}",
                agent=agent,
            )
        )
    return tasks


# ==============================
# Run Dynamic Flow
# ==============================
def run_dynamic_flow(user_request: str):
    """Full loop: manager analyzes, creates agents+tasks, then executes autonomously."""
    plan = manager_suggests_plan(user_request)
    tasks = build_tasks_from_plan(plan)

    crew = Crew(
        agents=[a for a in dynamic_agents.values() if isinstance(a, Agent)],  # ✅ Only Agents
        tasks=tasks,
        verbose=True,
        process="sequential",
    )
    return crew.kickoff()


# ==============================
# Rendering Helpers
# ==============================
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


# ==============================
# Streamlit UI
# ==============================
st.set_page_config(page_title="🤖 Dynamic Multi-Agent Builder", page_icon="🛠️")
st.title("🤖 Dynamic Multi-Agent Builder (OpenRouter Grok AI)")

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
            agent_role = item.get("agent", "—")
            task_desc = item.get("task", "—")
            tools = item.get("tools", [])
            if isinstance(tools, str):
                tools = [tools]
            plan_text = item.get("plan", "—")

            with st.expander(f"📌 Phase {idx}: {agent_role} — {task_desc}"):
                st.markdown(f"**🛠️ Tools:** {', '.join(tools) if tools else '—'}")
                st.markdown(f"**📋 Plan:** {plan_text}")

        st.info("👉 If this looks good, click **Run Agents**. Otherwise, rephrase your request.")
    else:
        st.warning("⚠️ Please enter a request first.")

if st.button("Run Agents"):
    if "plan" in st.session_state and st.session_state.plan:
        with st.spinner("Agents are working..."):
            result = run_dynamic_flow(user_prompt)

        st.subheader("📌 Final Output")
        if hasattr(result, "tasks_output"):
            for idx, t in enumerate(result.tasks_output, start=1):
                with st.expander(f"🤖 Agent {idx}: {t.agent}"):
                    render_agent_output(t)
        else:
            st.write("❌ No result produced.")
    else:
        st.warning("⚠️ Please analyze the request first.")
