# devzero_v2.py
import os
import re
import json
import ast
import sqlite3
import threading
from datetime import datetime
from textwrap import dedent
from typing import Any, Dict, List, Optional
import io
import zipfile
from pathlib import Path
import streamlit as st
from dotenv import load_dotenv
import git
import tempfile, shutil, time

CACHE_DIR = Path("repo_cache")  # local cache for GitHub repo

# CrewAI imports (assumed available in your environment)
from crewai import Agent, Task, Crew, LLM

def detect_file_type(content: str, agent_name: str):
    """
    Detect file extension based on content or agent name.
    """
    content_lower = content.lower()

    if "import React" in content or "<div" in content:
        return ".jsx"
    elif "angular" in agent_name.lower():
        return ".ts"
    elif "class " in content and "public static void main" in content:
        return ".java"
    elif "def " in content or "import " in content_lower:
        return ".py"
    elif "package main" in content:
        return ".go"
    elif "using System" in content:
        return ".cs"
    elif content.strip().startswith("apiVersion:") or content.strip().startswith("kind:"):
        return ".yaml"
    elif "CREATE TABLE" in content or "INSERT INTO" in content:
        return ".sql"
    elif agent_name.lower().startswith("test"):
        return ".java"
    elif content.strip().startswith("{") and content.strip().endswith("}"):
        return ".json"
    else:
        return ".txt"

def extract_filename_from_content(content: str):
    """
    Extract a file name if present in the first few lines of the AI output.
    Supports formats like:
        // File: UserController.java
        # File: app.py
        <!-- File: index.html -->
        /* File: service.go */
    """
    file_pattern = re.compile(r"(?:\/\/|#|<!--|\/\*)\s*File:\s*([\w.\-\\/]+)", re.IGNORECASE)
    match = file_pattern.search(content)
    if match:
        filename = Path(match.group(1)).name.strip()
        return filename
    return None

def save_agent_outputs_to_repo(outputs_list, base_path: Path):
    """
    Recursively saves agent outputs into structured folders (e.g., frontend, backend, etc.).
    Supports any file types (code, text, DB scripts, test scripts, DevOps files, etc.)
    """
    code_ext_map = {
        "python": ".py",
        "py": ".py",
        "javascript": ".js",
        "js": ".js",
        "html": ".html",
        "css": ".css",
        "json": ".json",
        "txt": ".txt",
        "java": ".java",
        "": ".txt"  # Fallback for any other unrecognized code block types
    }

    for i, item in enumerate(outputs_list):
        agent_name = item["agent"].replace(" ", "_")
        agent_folder = base_path / f"{i+1}_{agent_name}"
        agent_folder.mkdir(parents=True, exist_ok=True)

        output = item["output"]

        # Debugging: Print the output to check the structure
        print(f"Saving output for agent {agent_name}: {output}")

        # If output is a dictionary, save each file in the folder
        if isinstance(output, dict):
            for filename, content in output.items():
                file_path = agent_folder / filename
                # Detect if content is bytes or text
                if isinstance(content, bytes):
                    file_path.write_bytes(content)
                else:
                    file_path.write_text(str(content), encoding="utf-8")
        else:
            # Check if the output contains code blocks or regular text
            code_blocks = re.findall(r"```(\w+)?\n(.*?)```", str(output), re.DOTALL)
            if code_blocks:
                # Handle code blocks separately
                for block_idx, (lang, code) in enumerate(code_blocks, start=1):
                    file_extension = code_ext_map.get(lang.lower() if lang else "", ".txt")
                    filename = f"{agent_name}_part{block_idx}{file_extension}"
                    file_path = agent_folder / filename
                    file_path.write_text(code.strip(), encoding="utf-8")
            else:
                # Save the regular text output as "output.txt"
                file_path = agent_folder / "output.txt"
                file_path.write_text(str(output), encoding="utf-8")




def push_outputs_to_github(outputs_list, phase_index: int):
    """
    Push structured agent outputs as a folder to GitHub.
    Handles Windows file locks safely.
    """
    repo_url = os.getenv("GITHUB_REPO")
    token = os.getenv("GITHUB_TOKEN")
    branch = os.getenv("GITHUB_BRANCH", "main")

    if not repo_url or not token:
        st.error("GitHub repo or token not configured.")
        return False

    repo_url_with_token = repo_url.replace("https://", f"https://{token}@")

    # Create a temp folder manually
    tmpdir = tempfile.mkdtemp()
    tmp_path = Path(tmpdir)

    try:
        # Clone the repo
        repo = git.Repo.clone_from(repo_url_with_token, tmp_path, branch=branch)

        # Create a phase-specific folder
        phase_folder = tmp_path / f"phase_{phase_index+1}"
        phase_folder.mkdir(parents=True, exist_ok=True)

        # Save outputs recursively
        save_agent_outputs_to_repo(outputs_list, phase_folder)

        # Add, commit, push
        repo.git.add(all=True)
        repo.index.commit(f"🤖 MCP: Added structured outputs for phase {phase_index+1}")
        repo.remote(name="origin").push(branch)

        # Explicitly close repo to release file handles
        if hasattr(repo, "close"):
            repo.close()
        else:
            del repo

        return True

    except Exception as e:
        st.error(f"Failed to push to GitHub: {e}")
        return False

    finally:
        # Safe cleanup
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

def push_zip_to_github(zip_bytes: bytes, filename: str = "agent_outputs.zip"):
    """
    Push a ZIP file to GitHub using a persistent local clone (Windows-safe).
    """
    repo_url = os.getenv("GITHUB_REPO")
    token = os.getenv("GITHUB_TOKEN")
    branch = os.getenv("GITHUB_BRANCH", "main")

    if not repo_url or not token:
        st.error("GitHub repo or token not configured.")
        return False

    repo_url_with_token = repo_url.replace("https://", f"https://{token}@")

    try:
        # ✅ Step 1: Clone once (or pull latest)
        if not CACHE_DIR.exists():
            st.info("📥 Cloning repository (first time setup)...")
            repo = git.Repo.clone_from(repo_url_with_token, CACHE_DIR, branch=branch)
        else:
            repo = git.Repo(CACHE_DIR)
            repo.git.checkout(branch)
            repo.remote(name="origin").pull()

        # ✅ Step 2: Write ZIP file
        file_path = CACHE_DIR / filename
        file_path.write_bytes(zip_bytes)

        # ✅ Step 3: Commit and push
        repo.git.add(all=True)
        commit_msg = f"🤖 MCP: Added {filename} from DevHero"
        repo.index.commit(commit_msg)

        origin = repo.remote(name="origin")
        origin.push(branch)

        # Give Windows time to release file handles (safety)
        time.sleep(0.5)

        st.success(f"✅ {filename} pushed to GitHub successfully!")
        return True

    except git.exc.GitCommandError as e:
        st.error(f"Git error: {e}")
        return False

    except Exception as e:
        st.error(f"Failed to push to GitHub: {e}")
        return False


def make_zip_bytes(folder_path: str, zip_name: str = "frontend_code.zip") -> bytes:
    """
    Create an in-memory zip of a folder and return bytes.
    """
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, folder_path)
                zf.write(abs_path, arcname=rel_path)
    zip_buffer.seek(0)
    return zip_buffer.getvalue()

def save_agent_outputs_and_zip(outputs: list, zip_name: str = "agent_outputs.zip") -> bytes:
    """
    Save agent outputs (including code blocks) to a temp folder and return a ZIP bytes object.
    Detects code blocks from LLM output and saves them as proper code files.
    """
    import tempfile

    code_ext_map = {
        "python": ".py",
        "py": ".py",
        "javascript": ".js",
        "js": ".js",
        "html": ".html",
        "css": ".css",
        "json": ".json",
        "txt": ".txt",
        "": ".txt"  # Fallback for any other unrecognized code block types
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        for idx, out in enumerate(outputs, start=1):
            agent_name = re.sub(r"\W+", "_", out.get("agent", f"agent_{idx}"))
            raw_text = out.get("output", "")

            # Extract code blocks (like ```python ... ``` from the LLM output)
            code_blocks = re.findall(r"```(\w+)?\n(.*?)```", raw_text, re.DOTALL)
            if code_blocks:
                for block_idx, (lang, code) in enumerate(code_blocks, start=1):
                    ext = code_ext_map.get(lang.lower() if lang else "", ".txt")
                    filename = f"{agent_name}_part{block_idx}{ext}"
                    (tmp_path / filename).write_text(code.strip(), encoding="utf-8")
            else:
                # If no code block, just save as txt file
                (tmp_path / f"{agent_name}.txt").write_text(raw_text, encoding="utf-8")

        # Now create the ZIP file with proper folder structure
        zip_bytes = io.BytesIO()
        with zipfile.ZipFile(zip_bytes, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in tmp_path.rglob("*"):
                zf.write(file, arcname=file.name)
        zip_bytes.seek(0)
        return zip_bytes.getvalue()



# Optional: json5 tolerant parsing
try:
    import json5
except ImportError:
    json5 = None

# -----------------------------
# Load env
# -----------------------------
load_dotenv()

# -----------------------------
# LLM config (DeepSeek)
# -----------------------------
llm = LLM(
    model=os.getenv("DEVZERO_LLM_MODEL", "deepseek-chat"),
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
    temperature=float(os.getenv("DEVZERO_TEMPERATURE", "0.3")),
    # max_tokens=int(os.getenv("DEVZERO_MAX_TOKENS", "2000")),
)

# -----------------------------
# Memory & Execution Logger
# -----------------------------
class ContextMemory:
    """Simple persistent/in-memory context store with SQLite backing optionally."""

    def __init__(self, db_path: Optional[str] = None):
        self.lock = threading.Lock()
        self.db_path = db_path
        if db_path:
            self._init_db()
        else:
            self.store: List[Dict[str, Any]] = []

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                """CREATE TABLE IF NOT EXISTS memory (
                    id INTEGER PRIMARY KEY,
                    key TEXT,
                    agent TEXT,
                    content TEXT,
                    summary TEXT,
                    tags TEXT,
                    created_at TEXT
                )"""
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_memory_key ON memory(key)")
            conn.commit()

    def remember(self, key: str, content: Any, agent: Optional[str]=None, summary: Optional[str]=None, tags: Optional[List[str]]=None):
        timestamp = datetime.utcnow().isoformat() + "Z"
        tags_json = json.dumps(tags or [])
        content_json = content if isinstance(content, str) else json.dumps(content)
        if self.db_path:
            with self.lock, sqlite3.connect(self.db_path) as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO memory (key, agent, content, summary, tags, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (key, agent, content_json, summary, tags_json, timestamp),
                )
                conn.commit()
                return cur.lastrowid
        else:
            with self.lock:
                rec = {
                    "id": len(self.store) + 1,
                    "key": key,
                    "agent": agent,
                    "content": content_json,
                    "summary": summary,
                    "tags": tags or [],
                    "created_at": timestamp,
                }
                self.store.append(rec)
                return rec["id"]

    def recall(self, key: Optional[str] = None, agent: Optional[str] = None, latest: bool = True, limit: int = 10):
        if self.db_path:
            q = "SELECT id, key, agent, content, summary, tags, created_at FROM memory"
            filters = []
            params = []
            if key:
                filters.append("key = ?")
                params.append(key)
            if agent:
                filters.append("agent = ?")
                params.append(agent)
            if filters:
                q += " WHERE " + " AND ".join(filters)
            q += " ORDER BY created_at DESC"
            if limit:
                q += f" LIMIT {limit}"
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.cursor()
                cur.execute(q, params)
                rows = cur.fetchall()
            items = [
                {
                    "id": r[0],
                    "key": r[1],
                    "agent": r[2],
                    "content": (r[3]),
                    "summary": r[4],
                    "tags": json.loads(r[5] or "[]"),
                    "created_at": r[6],
                }
                for r in rows
            ]
            return items[0] if latest and items else items
        else:
            with self.lock:
                filtered = list(reversed(self.store))
                if key:
                    filtered = [r for r in filtered if r["key"] == key]
                if agent:
                    filtered = [r for r in filtered if r["agent"] == agent]
                if latest:
                    return filtered[0] if filtered else None
                return filtered[:limit]

    def latest_from_agent(self, agent: str):
        return self.recall(agent=agent, latest=True)

    def all(self, limit: int = 100):
        if self.db_path:
            return self.recall(limit=limit, latest=False)
        else:
            with self.lock:
                return list(reversed(self.store))[:limit]


class ExecutionLogger:
    def __init__(self, db_path: Optional[str] = None):
        self.lock = threading.Lock()
        self.db_path = db_path
        if db_path:
            self._init_db()
        else:
            self.logs: List[Dict[str, Any]] = []

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                """CREATE TABLE IF NOT EXISTS exec_logs (
                    id INTEGER PRIMARY KEY,
                    task_id TEXT,
                    agent TEXT,
                    input_text TEXT,
                    output_text TEXT,
                    metadata TEXT,
                    created_at TEXT
                )"""
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_exec_agent ON exec_logs(agent)")
            conn.commit()

    def log(self, task_id: str, agent: str, input_text: str, output_text: str, metadata: Optional[Dict]=None):
        timestamp = datetime.utcnow().isoformat() + "Z"
        metadata_json = json.dumps(metadata or {})
        if self.db_path:
            with self.lock, sqlite3.connect(self.db_path) as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO exec_logs (task_id, agent, input_text, output_text, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (task_id, agent, input_text, output_text, metadata_json, timestamp),
                )
                conn.commit()
                return cur.lastrowid
        else:
            with self.lock:
                rec = {
                    "id": len(self.logs) + 1,
                    "task_id": task_id,
                    "agent": agent,
                    "input_text": input_text,
                    "output_text": output_text,
                    "metadata": metadata or {},
                    "created_at": timestamp,
                }
                self.logs.append(rec)
                return rec["id"]

    def query_by_agent(self, agent: str = None, limit: int = 50):
        if self.db_path:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.cursor()
                if agent:
                    cur.execute(
                        "SELECT id, task_id, agent, input_text, output_text, metadata, created_at FROM exec_logs WHERE agent=? ORDER BY created_at DESC LIMIT ?",
                        (agent, limit),
                    )
                else:
                    cur.execute(
                        "SELECT id, task_id, agent, input_text, output_text, metadata, created_at FROM exec_logs ORDER BY created_at DESC LIMIT ?",
                        (limit,),
                    )
                rows = cur.fetchall()
            return [
                {
                    "id": r[0],
                    "task_id": r[1],
                    "agent": r[2],
                    "input_text": r[3],
                    "output_text": r[4],
                    "metadata": json.loads(r[5] or "{}"),
                    "created_at": r[6],
                }
                for r in rows
            ]
        else:
            with self.lock:
                logs = list(reversed(self.logs))
                if agent:
                    logs = [l for l in logs if l["agent"] == agent]
                return logs[:limit]


# -----------------------------
# Initialize memory & logger
# -----------------------------
PERSISTENCE_DB = os.getenv("DEVZERO_DB_PATH", None)  # e.g., "devzero_state.db"
memory = ContextMemory(db_path=PERSISTENCE_DB)
exec_logger = ExecutionLogger(db_path=PERSISTENCE_DB)

# -----------------------------
# Basic Manager setup
# -----------------------------
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

# dynamic agents registry
dynamic_agents: Dict[str, Agent] = {"Project Manager": manager}

# -----------------------------
# JSON parsing helpers
# -----------------------------
def parse_json_response(raw_text: str):
    """Extract JSON from LLM output, tolerant of markdown fences and formatting issues."""
    try:
        if not raw_text:
            return []
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

# -----------------------------
# Helper: Summarize Memory (human readable)
# -----------------------------
def summarize_memory(memory_items: List[Dict[str, Any]]) -> str:
    """Return a short human-friendly summary of recent memory items."""
    lines = []
    for m in memory_items:
        # If content is JSON plan (list of dicts), summarize agents/tasks
        try:
            content = m.get("content")
            # content might be a JSON string
            parsed = json.loads(content) if isinstance(content, str) and (content.strip().startswith("[") or content.strip().startswith("{")) else content
            if isinstance(parsed, list):
                roles = []
                for entry in parsed:
                    if isinstance(entry, dict):
                        role = entry.get("agent") or entry.get("role") or entry.get("agent_role") or "Unknown"
                        task = entry.get("task") or entry.get("task_description") or ""
                        roles.append(f"**{role}**: {task}")
                if roles:
                    lines.append(f"- {m.get('agent', 'Manager')} @ {m.get('created_at', '')[:19]} → " + "; ".join(roles))
                    continue
            # fallback: use summary or first 120 chars of content
            summary = m.get("summary") or (str(parsed)[:120] + ("…" if len(str(parsed)) > 120 else ""))
            lines.append(f"- {m.get('agent', 'Unknown')} @ {m.get('created_at', '')[:19]} — {summary}")
        except Exception:
            lines.append(f"- {m.get('agent', 'Unknown')} @ {m.get('created_at', '')[:19]} — (unreadable)")
    return "\n".join(lines) if lines else "_(no memory items)_"

# -----------------------------
# Agent factory (attach memory & logger)
# -----------------------------
def get_or_create_agent(role: str, goal: str = "", backstory: str = "", allow_delegation=False):
    if role in dynamic_agents:
        return dynamic_agents[role]

    agent = Agent(
        role=role,
        goal=goal or f"Fulfill the responsibilities of a {role}.",
        backstory=backstory or f"You are a skilled {role} who can perform tasks autonomously.",
        allow_delegation=allow_delegation,
        llm=llm,
    )

    # attach helpers (non-invasive)
    agent._memory = memory
    agent._exec_logger = exec_logger
    agent._agent_id = f"{role}-{len(dynamic_agents)+1}"

    dynamic_agents[role] = agent
    return agent

# -----------------------------
# Manager suggestion & refinement
# -----------------------------
def manager_suggests_plan(user_request: str):
    suggestion_task = Task(
        description=dedent(f"""
            Analyze the following user request: {user_request}

            Your goal is to create an efficient development plan using as few agents as possible.
            - If the task is focused on one domain (e.g., only frontend or only backend), use ONE agent.
            - If multiple domains are explicitly mentioned (e.g., frontend + backend), create a separate agent per domain.
            - Avoid creating micro-agents for small subtasks like styling, validation, or testing unless explicitly requested.
            - Focus on practicality and efficient delegation.

            For each selected agent, provide:
            1. agent (name of the role)
            2. task (main responsibility)
            3. tools (frameworks/libraries to use)
            4. plan (concise implementation plan)

            ⚠️ Respond strictly in JSON list format.
        """),
        expected_output="JSON containing selected agents, tools, and plan",
        agent=manager,
    )

    crew = Crew(agents=[manager], tasks=[suggestion_task], process="sequential", verbose=False)
    raw_result = crew.kickoff()

    # crew.kickoff() return shape may vary; attempt to extract raw text
    raw_text = None
    try:
        # many SDKs place model output under .raw or .text
        raw_text = getattr(raw_result, "raw", None) or getattr(raw_result, "text", None) or str(raw_result)
    except Exception:
        raw_text = str(raw_result)

    plan = parse_json_response(raw_text)
    plan = enforce_plan_structure(plan)

    # persist the plan to memory
    plan_id = f"plan:{datetime.utcnow().timestamp()}"
    memory.remember(key=plan_id, content=plan, agent="Manager", summary="Manager generated plan", tags=["plan"])
    st.session_state.plan_id = plan_id

    return plan

def manager_refine_plan(existing_plan, feedback, user_request):
    refine_task = Task(
        description=dedent(f"""
            You are provided a previously generated plan (JSON). The user wants the plan refined.
            Existing plan: {json.dumps(existing_plan, indent=2)}
            User feedback: {feedback}
            Original request: {user_request}

            Please return a corrected/refined plan in JSON list format with fields: agent, task, tools, plan.
        """),
        expected_output="Refined plan JSON",
        agent=manager,
    )
    crew = Crew(agents=[manager], tasks=[refine_task], process="sequential", verbose=False)
    raw_result = crew.kickoff()
    raw_text = getattr(raw_result, "raw", None) or getattr(raw_result, "text", None) or str(raw_result)
    plan = parse_json_response(raw_text)
    plan = enforce_plan_structure(plan)

    memory.remember(
        key=f"plan:refined:{datetime.utcnow().timestamp()}",
        content=plan,
        agent="Manager",
        summary=f"Refined plan after feedback: {feedback}",
        tags=["plan", "refined"],
    )
    return plan

# -----------------------------
# Task builder
# -----------------------------
def build_tasks_from_plan(plan: list):
    tasks: List[Task] = []
    for idx, item in enumerate(plan, start=1):
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

        # include a small context snapshot for the agent
        context_snapshot = memory.all(limit=10)

        tasks.append(
            Task(
                description=f"""{task_desc}

                Tools to use: {', '.join(tools) if tools else 'any suitable tools'}.
                Plan notes: {plan_notes}

                Context snapshot: {json.dumps(context_snapshot, default=str)[:3000]}
                """,
                expected_output=f"Deliverables for: {role}",
                agent=agent,
            )
        )
    return tasks

# -----------------------------
# Run dynamic flow with logging & memory
# -----------------------------
def run_dynamic_flow(plan: Optional[List[Dict]] = None, user_request: Optional[str] = None):
    """
    Run agents for the provided plan. If plan is None, manager will generate a plan from user_request.
    """
    if plan is None:
        if not user_request:
            raise ValueError("Either plan or user_request must be provided to run_dynamic_flow.")
        plan = manager_suggests_plan(user_request)

    tasks = build_tasks_from_plan(plan)

    # Build a scoped agent list: only agents referenced in tasks (plus manager)
    task_agents = {t.agent for t in tasks}
    agents_for_crew = [a for name, a in dynamic_agents.items() if (name in task_agents) or name == 'Project Manager' or a in task_agents]

    crew = Crew(
        agents=agents_for_crew,
        tasks=tasks,
        verbose=False,
        process="sequential",
    )

    result = crew.kickoff()

    # result may contain a variety of shapes; try to iterate tasks_output
    task_outputs = getattr(result, "tasks_output", None) or getattr(result, "outputs", None)

    # If not present, attempt to parse result directly
    if not task_outputs:
        try:
            task_outputs = list(result)
        except Exception:
            task_outputs = [result]

    stored_outputs = []

    for idx, t in enumerate(task_outputs, start=1):
        try:
            agent_name = getattr(t, "agent", None) or getattr(t, "agent_name", None) or getattr(t, "role", None) or f"agent_{idx}"
            output_text = getattr(t, "raw", None) or getattr(t, "text", None) or getattr(t, "summary", None) or str(t)
            task_id = getattr(t, "id", f"task:{agent_name}:{datetime.utcnow().timestamp()}")
            input_text = getattr(t, "input", "") if hasattr(t, "input") else ""
        except Exception:
            agent_name = f"agent_{idx}"
            output_text = str(t)
            task_id = f"task:{agent_name}:{datetime.utcnow().timestamp()}"
            input_text = ""

        # 1) log execution
        exec_logger.log(task_id=task_id, agent=agent_name, input_text=input_text, output_text=output_text, metadata={"phase_index": idx})

        # 2) persist output to memory
        mem_key = f"{agent_name}:{task_id}"
        memory.remember(key=mem_key, content=output_text, agent=agent_name, summary=(output_text[:500] if output_text else None), tags=["agent_output"])

        stored_outputs.append({"agent": agent_name, "task_id": task_id, "output": output_text})

    return {
        "raw_result": result,
        "task_outputs": stored_outputs,
    }

# -----------------------------
# Rendering helpers
# -----------------------------
def render_agent_output_raw(raw_text: str):
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

def manager_refine_phase(plan, phase_index, feedback):
    """
    Refines a specific phase in the plan based on user feedback.
    
    Args:
        plan (list): The original plan with all phases.
        phase_index (int): The index of the phase to refine.
        feedback (str): The feedback provided by the user to refine the phase.
    
    Returns:
        list: The refined plan with the updated phase.
    """
    refined_plan = plan.copy()

    # Get the phase to refine
    phase_to_refine = refined_plan[phase_index]

    # Basic logic to modify phase based on feedback
    if "adjust toolset" in feedback.lower():
        # Example: Update the tools used in the phase based on feedback
        new_tools = feedback.split("adjust toolset to")[-1].strip()
        phase_to_refine["tools"] = [tool.strip() for tool in new_tools.split(",")]

    if "change agent" in feedback.lower():
        # Example: Change agent role based on feedback
        new_agent = feedback.split("change agent to")[-1].strip()
        phase_to_refine["agent"] = new_agent

    if "modify task" in feedback.lower():
        # Example: Modify task description based on feedback
        new_task = feedback.split("modify task to")[-1].strip()
        phase_to_refine["task"] = new_task

    if "update plan" in feedback.lower():
        # Example: Update plan based on feedback
        new_plan = feedback.split("update plan to")[-1].strip()
        phase_to_refine["plan"] = new_plan

    # Save the refined phase back into the plan
    refined_plan[phase_index] = phase_to_refine

    return refined_plan


import streamlit as st

# Set up page configuration
st.set_page_config(page_title="🤖 DevHero – Multi-Agent Builder", page_icon="🛠️", layout="wide")

# Header
st.markdown("<h1 style='text-align: center; color: #005fae;'>🤖 DevHero – Multi-Agent Builder</h1>", unsafe_allow_html=True)

# Initialize session state keys if missing
if "plan" not in st.session_state:
    st.session_state.plan = None
if "plan_id" not in st.session_state:
    st.session_state.plan_id = None
if "show_run_button" not in st.session_state:
    st.session_state.show_run_button = False

# Layout Columns
col1, col2 = st.columns([1, 2])  # GIF on left, input on right

with col1:
    st.image("devhero.gif", caption="DevHero Hero", use_container_width=300)

with col2:
    user_prompt = st.text_area(
        "Enter your request:",
        placeholder="e.g., Create a login page with React frontend and Spring Boot backend",
        height=180,
        label_visibility="collapsed"
    )

# Step 1: Analyze Request
if st.button("🔍 Analyze Request", use_container_width=True):
    if user_prompt.strip():
        with st.spinner("Manager analyzing your request..."):
            try:
                st.session_state.plan = manager_suggests_plan(user_prompt)
                st.session_state.plan_refined = False
            except Exception as e:
                st.error(f"Manager failed: {e}")
                st.session_state.plan = None

        if st.session_state.plan:
            st.success("✅ Plan generated! Scroll down to view & refine.")
        else:
            st.warning("⚠️ Manager could not generate a valid plan.")
    else:
        st.warning("⚠️ Please enter a request first.")

# --- Step 2: Display Plan (if exists) ---
if st.session_state.get("plan"):
    st.subheader("✅ Manager Suggestion")
    for idx, item in enumerate(st.session_state.plan, start=1):
        agent_role = item.get("agent", "—")
        task_desc = item.get("task", "—")
        tools = item.get("tools", [])
        if isinstance(tools, str):
            tools = [tools]
        plan_text = item.get("plan", "—")

        # Each phase as a card
        with st.expander(f"📌 Phase {idx}: {agent_role} — {task_desc}", expanded=True):
            st.markdown(f"**🛠️ Tools:** {', '.join(tools) if tools else '—'}")
            st.markdown(f"**📋 Plan:** {plan_text}")

    # Feedback & Refine Plan Section
    st.markdown("### 🔁 Refine the Plan")
    feedback = st.text_input(
        "Suggest improvements (optional):",
        placeholder="e.g., Add QA role, or focus only on frontend",
        key="feedback_input",
    )

    if st.button("✨ Refine Plan", use_container_width=True):
        if not feedback.strip():
            st.warning("Please provide feedback text first.")
        else:
            with st.spinner("Manager refining plan..."):
                try:
                    refined_plan = manager_refine_plan(st.session_state.plan, feedback, user_prompt)
                    st.session_state.plan = refined_plan
                    st.session_state.plan_refined = True
                    st.toast("✅ Plan refined successfully!", icon="✨")
                except Exception as e:
                    st.error(f"Refinement failed: {e}")

    # Show refined plan if available
    if st.session_state.get("plan_refined"):
        st.markdown("### 🧩 Refined Plan")
        for idx, item in enumerate(st.session_state.plan, start=1):
            agent_role = item.get("agent", "—")
            task_desc = item.get("task", "—")
            tools = item.get("tools", [])
            if isinstance(tools, str):
                tools = [tools]
            plan_text = item.get("plan", "—")

            with st.expander(f"📌 Phase {idx}: {agent_role} — {task_desc}", expanded=True):
                st.markdown(f"**🛠️ Tools:** {', '.join(tools) if tools else '—'}")
                st.markdown(f"**📋 Plan:** {plan_text}")

    st.success("✅ Plan ready! When satisfied, click below to run the agents.")
    st.session_state.show_run_button = True

# --- Step 3: Run Agents ---
if st.session_state.get("show_run_button"):
    st.markdown("### 🚀 Run Agents Sequentially")
    if "current_phase_index" not in st.session_state:
        st.session_state.current_phase_index = 0
        st.session_state.phase_results = {}
        st.session_state.approved = False

    phases = st.session_state.plan
    current_index = st.session_state.current_phase_index

    if current_index >= len(phases):
        st.success("🎉 All agents have completed successfully!")
    else:
        phase = phases[current_index]
        agent_role = phase.get("agent", "Unknown")
        task_desc = phase.get("task", "—")
        tools = ", ".join(phase.get("tools", []))
        plan_text = phase.get("plan", "—")

        st.markdown(f"#### 📍 Phase {current_index + 1}: {agent_role}")
        st.markdown(f"**🛠️ Tools:** {tools}")
        st.markdown(f"**📋 Task:** {task_desc}")
        st.markdown(f"**🧩 Plan:** {plan_text}")

        # Run current agent
        if st.button(f"▶️ Run {agent_role}", key=f"run_{current_index}", use_container_width=True):
            with st.spinner(f"{agent_role} executing task..."):
                try:
                    result = run_dynamic_flow(plan=[phase])  # run only this phase
                    output = result["task_outputs"][0]["output"] if result.get("task_outputs") else "No output"
                    st.session_state.phase_results[current_index] = output
                    st.session_state.approved = False
                    st.toast(f"{agent_role} completed successfully!", icon="🤖")
                except Exception as e:
                    st.error(f"{agent_role} failed: {e}")

    # Show result & approval checkbox if result exists
    if current_index in st.session_state.phase_results:
        output = st.session_state.phase_results[current_index]
        st.markdown("### 🧾 Agent Output:")
        render_agent_output_raw(output)

        # Action Buttons (styled)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 Download Entire Code", key=f"download_{current_index}", use_container_width=True):
                outputs_to_zip = [st.session_state.phase_results[i] for i in range(current_index + 1)]
                # Prepare list of dicts for the helper
                outputs_list = []
                for i, output in enumerate(outputs_to_zip):
                    outputs_list.append({
                        "agent": st.session_state.plan[i]["agent"],
                        "output": output
                    })

                zip_bytes = save_agent_outputs_and_zip(outputs_list, zip_name="generated_code.zip")
                st.download_button(
                    label="📥 Download Generated Code ZIP",
                    data=zip_bytes,
                    file_name="generated_code.zip",
                    mime="application/zip"
                )

        with col2:
            if st.button("💾 Push to GitHub", key=f"github_push_{current_index}", use_container_width=True):
                outputs_to_push = [st.session_state.phase_results[i] for i in range(current_index + 1)]
                # Prepare structured output dicts
                structured_outputs = []
                for i, output in enumerate(outputs_to_push):
                    structured_outputs.append({
                        "agent": st.session_state.plan[i]["agent"],
                        "output": output  # This can be text, code, or binary
                    })
                with st.spinner("📦 Pushing outputs to GitHub..."):
                    success = push_outputs_to_github(structured_outputs, phase_index=current_index)
                    if success:
                        st.success("✅ Outputs pushed to GitHub successfully!")
                    else:
                        st.error("❌ Failed to push outputs to GitHub.")

        # Approve Phase or Refine Phase
        col1, col2 = st.columns(2)
        with col1:
            # Approve Phase
            approved = st.checkbox("✅ Approve this phase to continue", key=f"approve_{current_index}", help="Approve this phase to move to the next.")
            if approved and not st.session_state.approved:
                st.session_state.approved = True
                st.session_state.current_phase_index += 1
                st.toast(f"✅ Phase {current_index + 1} approved! Moving to next...", icon="➡️")
                st.rerun()

        with col2:
            # Refine Phase
            refine_feedback = st.text_area(
                "📝 Provide feedback to refine this phase:",
                placeholder="e.g., Adjust the toolset or change the agent's task description.",
                key=f"refine_feedback_{current_index}",
            )
            refine_button = st.button("🔄 Refine Phase", key=f"refine_{current_index}")
            
            if refine_button and refine_feedback.strip():
                with st.spinner("🔄 Refining phase..."):
                    try:
                        # Handle refinement logic here
                        refined_plan = manager_refine_phase(st.session_state.plan, current_index, refine_feedback)
                        st.session_state.plan = refined_plan
                        st.session_state.phase_results[current_index] = None  # Reset the result as it needs to be re-run
                        st.session_state.approved = False
                        
                        # Get the refined phase to re-run
                        refined_phase = refined_plan[current_index]
                        agent_role = refined_phase.get("agent", "Unknown")
                        task_desc = refined_phase.get("task", "—")
                        tools = ", ".join(refined_phase.get("tools", []))
                        plan_text = refined_phase.get("plan", "—")

                        # Print debug info to verify that the plan has been updated
                        st.write("### Refined Phase Info")
                        st.write(f"Agent Role: {agent_role}")
                        st.write(f"Task Description: {task_desc}")
                        st.write(f"Tools: {tools}")
                        st.write(f"Plan: {plan_text}")

                        # Run the refined phase
                        with st.spinner(f"{agent_role} executing task..."):
                            try:
                                result = run_dynamic_flow(plan=[refined_phase])  # Run the newly refined phase
                                output = result["task_outputs"][0]["output"] if result.get("task_outputs") else "No output"
                                st.session_state.phase_results[current_index] = output
                                st.session_state.approved = False
                                st.toast(f"{agent_role} completed successfully!", icon="🤖")
                            except Exception as e:
                                st.error(f"{agent_role} failed: {e}")
                        
                        st.toast("✅ Phase refined and re-executed successfully! You can now review again.", icon="✨")
                        st.rerun()  # Re-run the phase after refinement
                    except Exception as e:
                        st.error(f"❌ Refinement failed: {e}")








