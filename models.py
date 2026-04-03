"""
models.py — Shared data contracts for all agents and the orchestrator.

Every inter-agent message is typed here. If you change one, update all callers.
"""
from __future__ import annotations
from enum import Enum
from typing import Any, Optional
from datetime import datetime
from pydantic import AliasChoices, BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class TaskStatus(str, Enum):
    QUEUED     = "queued"
    REASONING  = "reasoning"
    PLANNING   = "planning"
    EXECUTING  = "executing"
    EVALUATING = "evaluating"
    DONE       = "done"
    FAILED     = "failed"

class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED  = "failed"
    SKIPPED = "skipped"

class ToolName(str, Enum):
    FILESYSTEM = "filesystem"
    TERMINAL   = "terminal"
    COMMUNICATE = "communicate"
    BROWSER    = "browser"
    HTTP       = "http"
    EMAIL      = "email"      # Phase 3 ✓
    GOOGLE_SHEETS = "google_sheets"
    MARKET_DATA = "market_data"
    WEBSITE_BUILDER = "website_builder"
    CONTENT_CREATOR = "content_creator"
    FINANCE = "finance"
    CODE_BUILDER = "code_builder"
    PHONE = "phone"
    DATABASE = "database"
    PDF_GENERATOR = "pdf_generator"
    IMAGE_ANALYZER = "image_analyzer"
    RESEARCHER = "researcher"
    SECURITY_SCANNER = "security_scanner"
    COMPLIANCE = "compliance"
    DEPLOYER = "deployer"
    VIDEO_GENERATOR = "video_generator"
    NOTION = "notion"
    ZOHO_CRM = "zoho_crm"
    GOOGLE_CALENDAR = "google_calendar"
    TALLY = "tally"
    AMAZON_SELLER = "amazon_seller"
    MEESHO = "meesho"
    WHATSAPP_COMMERCE = "whatsapp_commerce"
    ZAPIER = "zapier"
    HUBSPOT = "hubspot"
    WORDPRESS = "wordpress"
    SHOPIFY = "shopify"
    LINKEDIN = "linkedin"
    INSTAGRAM = "instagram"
    TWITTER = "twitter"
    GEM_PORTAL = "gem_portal"
    CUSTOM     = "custom"     # Phase 3 — dynamically built tools


# ─────────────────────────────────────────────────────────────────────────────
# Agent I/O — each agent has a typed Input and Output
# ─────────────────────────────────────────────────────────────────────────────

class ReasoningInput(BaseModel):
    """What the Reasoning Agent receives."""
    raw_goal: str
    context: dict[str, Any] = {}
    prior_attempts: list[str] = []        # summaries of previous failed loops
    memory_snippets: list[str] = []        # relevant past task learnings

class ReasoningOutput(BaseModel):
    """What the Reasoning Agent returns after deep thinking."""
    understood_goal: str                   # rephrased, unambiguous
    goal_type: str                         # "build" | "automate" | "analyze" | "research" | "devops"
    complexity: str                        # "low" | "medium" | "high"
    risks: list[str] = []
    constraints: list[str] = []
    success_criteria: list[str] = []       # evaluator will check these
    clarifications_needed: list[str] = []  # empty = proceed


class ExecutionStep(BaseModel):
    """A single atomic step in the execution plan."""
    step_id: int
    tool: ToolName
    action: str
    params: dict[str, Any] = {}
    depends_on: list[int] = []
    description: str = ""
    retry_count: int = 0
    status: StepStatus = StepStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None

class PlanningInput(BaseModel):
    reasoning: ReasoningOutput
    memory_snippets: list[str] = []
    language: str = "en"

class PlanningOutput(BaseModel):
    """Structured, executable plan."""
    goal_summary: str
    steps: list[ExecutionStep]
    estimated_seconds: int = 0
    notes: str = ""


class ExecutionInput(BaseModel):
    task_id: str
    plan: PlanningOutput
    user_id: Optional[str] = None

class StepResult(BaseModel):
    step_id: int
    status: StepStatus
    result: Optional[Any] = None
    error: Optional[str] = None
    retries_used: int = 0

class ExecutionOutput(BaseModel):
    steps_run: int
    succeeded: int
    failed: int
    results: list[StepResult]
    raw_outputs: dict[int, Any] = {}      # step_id → result value


class EvaluatorInput(BaseModel):
    goal: str
    success_criteria: list[str]
    plan: PlanningOutput
    execution: ExecutionOutput
    task_id: Optional[str] = None          # for grounded verification logs
    goal_type: str = ""
    user_id: Optional[str] = None
    workspace_path: Optional[str] = None

class EvaluatorOutput(BaseModel):
    score: float                           # 0.0 – 1.0
    goal_met: bool
    what_worked: list[str] = []
    what_failed: list[str] = []
    improvement_hints: list[str] = []     # fed back into next loop iteration
    summary: str = ""
    auto_checks: list[dict[str, Any]] = Field(default_factory=list)  # {check_type, step_id, passed, detail}
    auto_check_override: bool = False      # True if score was capped by grounded checks


class MemoryInput(BaseModel):
    task_id: str
    goal: str
    goal_type: str
    plan: PlanningOutput
    execution: ExecutionOutput
    evaluation: EvaluatorOutput

class MemoryOutput(BaseModel):
    stored: bool
    learning: str = ""                    # distilled lesson for future tasks


# ─────────────────────────────────────────────────────────────────────────────
# API-facing models
# ─────────────────────────────────────────────────────────────────────────────

class CommandRequest(BaseModel):
    command: str = Field(..., min_length=3)
    context: dict[str, Any] = {}
    dry_run: bool = False
    source: str = "api"
    team_id: Optional[str] = None

class SuggestionOutput(BaseModel):
    suggestions: list[str] = []


class TradingAnalysisOutput(BaseModel):
    symbol: str = ""
    trend: str = "neutral"
    summary: str = ""
    key_levels: dict[str, Any] = {}
    risk_factors: list[str] = []
    disclaimer: str = ""


class CodeReviewOutput(BaseModel):
    issues: list[str] = []
    suggestions: list[str] = []
    score: int = 0


class BrandStrategyOutput(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    content_pillars: list[Any] = []
    posting_schedule: Any = None
    hashtag_strategy: list[Any] = []
    ninety_day_plan: list[Any] = Field(
        default_factory=list,
        validation_alias=AliasChoices("ninety_day_plan", "90_day_plan"),
        serialization_alias="90_day_plan",
    )


class ViralIdeaOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    hook: str = ""
    body_outline: str = ""
    cta: str = ""
    hashtags: list[str] = []


class ViralIdeasListOutput(BaseModel):
    ideas: list[ViralIdeaOutput] = []


class ContentPackOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    linkedin: list[Any] = []
    twitter: list[Any] = []
    instagram: list[Any] = []


class CommandResponse(BaseModel):
    task_id: str
    status: TaskStatus
    goal: str = ""
    loop_iterations: int = 0
    evaluation_score: Optional[float] = None
    summary: str = ""
    plan: Optional[PlanningOutput] = None
    results: list[StepResult] = []
    error: Optional[str] = None
    suggestions: list[str] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    queue_position: Optional[int] = None

class TaskRecord(BaseModel):
    task_id: str
    command: str
    status: TaskStatus = TaskStatus.QUEUED
    loop_iterations: int = 0
    eval_score: Optional[float] = None
    goal: str = ""
    goal_type: str = ""
    plan_json: str = "{}"
    results_json: str = "[]"
    summary: str = ""
    error: Optional[str] = None
    source: str = "api"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

# ─────────────────────────────────────────────────────────────────────────────
# Phase 3 — Tool Builder models
# ─────────────────────────────────────────────────────────────────────────────

class ToolBuildResult(BaseModel):
    tool_id: str = ""
    tool_name: str = ""
    description: str = ""
    actions: list[str] = []
    module_path: str = ""
    triggered_by_pattern: str = ""
    success: bool = False
    error: Optional[str] = None

class ScheduleRequest(BaseModel):
    name: str
    command: str
    cron: str = "0 * * * *"
    enabled: bool = True

# ─────────────────────────────────────────────────────────────────────────────
# Phase 5 — Project, Briefing, Parallel Execution
# ─────────────────────────────────────────────────────────────────────────────

class ProjectStatus(str, Enum):
    ACTIVE    = "active"
    COMPLETED = "completed"
    PAUSED    = "paused"
    FAILED    = "failed"


class SubTask(BaseModel):
    """A single sub-task within a project."""
    sub_task_id: int
    command: str
    depends_on: list[int] = []       # other sub_task_ids that must complete first
    priority: int = 1                # 1=low, 2=medium, 3=high
    description: str = ""


class ProjectRequest(BaseModel):
    """Create a long-running project from a high-level goal."""
    name: str
    goal: str
    context: dict[str, Any] = {}
    auto_start: bool = True          # immediately start executing sub-tasks


class ProjectResponse(BaseModel):
    project_id: str
    name: str
    goal: str
    status: ProjectStatus = ProjectStatus.ACTIVE
    sub_tasks: list[SubTask] = []
    task_ids: list[str] = []
    progress: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


class BriefingRequest(BaseModel):
    """Request a COO daily briefing report."""
    recipients: list[str] = []       # email addresses to send report to
    whatsapp_numbers: list[str] = [] # WhatsApp numbers to send summary to
    hours: int = 24                  # coverage window


class BriefingSection(BaseModel):
    title: str
    content: str
    status: str = "info"             # info | warning | critical


class BriefingReport(BaseModel):
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    period_hours: int = 24
    headline: str = ""
    health: str = "good"
    sections: list[BriefingSection] = []
    metrics_snapshot: dict[str, Any] = {}
    recommendations: list[str] = []
    full_text: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Auth — multi-user
# ─────────────────────────────────────────────────────────────────────────────

class AuthRegisterBody(BaseModel):
    email: str = Field(..., min_length=3)
    name: str = Field(..., min_length=1)
    password: str = Field(..., min_length=8)
    industry: str = ""  # medical | retail | agency | tech | other
    ref_code: Optional[str] = None
    country_code: Optional[str] = None
    timezone: Optional[str] = None


class TemplateRunBody(BaseModel):
    variables: dict[str, str] = {}


class AuthLoginBody(BaseModel):
    email: str
    password: str
