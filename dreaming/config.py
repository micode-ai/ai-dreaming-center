"""Global config — Pydantic-settings + config.yaml + DC_* env vars."""
from __future__ import annotations
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml


CONFIG_PATH = Path("config.yaml")


def _load_yaml() -> dict:
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DC_", extra="ignore")

    # === Database ===
    db_path: str = "data/dreaming.db"

    # === Projects ===
    projects_root: str = ""
    default_locale: str = "ru"

    # === Server ===
    host: str = "0.0.0.0"
    port: int = 8086

    # === Claude CLI / runners ===
    claude_path: str = "claude"
    orchestration_local_runner: str = "claude"  # claude | codex | continue
    codex_path: str = "codex"
    codex_api_key: str = ""
    continue_path: str = ".continue\\continue.cmd"
    model_backend_profile: str = "native"  # native | openrouter | openai_proxy
    anthropic_base_url: str = ""
    anthropic_auth_token: str = ""
    anthropic_api_key: str = ""
    openai_proxy_base_url: str = ""
    openai_proxy_api_key: str = ""
    codex_command_template: str = 'codex -p "{prompt}" --model {model}'
    continue_command_template: str = 'continue -p "{prompt}"'

    # === Self-study core ===
    model: str = "sonnet"
    max_turns: int = 25
    timeout_minutes: int = 20
    self_study_command: str = "/self-study"
    question_reminder_minutes: int = 15
    question_expire_minutes: int = 60

    # === Scheduling — nightly ===
    cron_expression: str = "0 2 * * *"
    cron_enabled: bool = True
    agents_per_night: int = 5
    max_concurrent: int = 2
    wait_between_sec: int = 5

    # === Scheduling — weekly (per-project, default disabled to opt-in) ===
    weekly_tech_debt_scan_cron: str = "0 3 * * 6"
    weekly_tech_debt_scan_enabled: bool = False
    weekly_timur_duty_cron: str = "0 2 * * 0"
    weekly_timur_duty_enabled: bool = False
    weekly_product_ideas_scan_cron: str = "0 20 * * 0"
    weekly_product_ideas_scan_enabled: bool = False
    weekly_wiki_lint_cron: str = "0 1 * * 6"
    weekly_wiki_lint_enabled: bool = False
    weekly_evolve_apply_cron: str = "0 4 * * 0"
    weekly_evolve_apply_enabled: bool = False
    daily_bootstrap_cron: str = "0 4 * * *"
    daily_bootstrap_enabled: bool = False
    daily_plans_cleanup_cron: str = "30 23 * * *"
    daily_plans_cleanup_enabled: bool = False
    monthly_deep_audit_cron: str = "0 5 1 * *"
    monthly_deep_audit_enabled: bool = False

    # === Watchdogs ===
    loop_watchdog_enabled: bool = True
    loop_watchdog_interval_minutes: int = 60
    sidecar_findings_enabled: bool = False
    evolutions_stale_days: int = 7
    loop_stagnation_hours: int = 6
    plans_archive_days: int = 14

    # === Paths (most overridable per-project) ===
    obsidian_vault: str = ""
    agents_dir: str = ""
    tech_debt_dir: str = ""
    product_ideas_dir: str = ""
    contracts_dir: str = ""
    learning_notes_dir: str = ""
    evolutions_dir: str = ""
    context_overrides_dir: str = ""
    lessons_cursor_path: str = ""
    loops_dir: str = ""
    plans_dir: str = ""
    sidecar_findings_dir: str = ""
    loops_templates_dir: str = ""
    wiki_dir: str = ""

    # === Jira ===
    jira_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    jira_project_key: str = ""
    jira_user_account_id: str = ""

    # === Harness (orchestration; Wave 3+) ===
    harness_base_url: str = ""
    harness_api_key: str = ""
    harness_timeout_sec: int = 30
    harness_stream_enabled: bool = True
    harness_start_path: str = "/api/orchestration/start"
    harness_events_stream_path: str = "/api/orchestration/{run_id}/stream"
    harness_events_path: str = "/api/orchestration/{run_id}/events"
    harness_send_input_path: str = "/api/orchestration/{run_id}/nodes/{node_id}/message"
    harness_verify_tls: bool = True

    # === AI Usage ingest ===
    claude_projects_dir: str = ""  # override; default ~/.claude/projects
    ai_usage_scan_enabled: bool = True
    ai_usage_scan_interval_minutes: int = 5
    ai_usage_scan_on_startup: bool = True

    # === Routing ===
    work_routing_mode: str = "ask"  # ask | claude | codex | continue

    @classmethod
    def load(cls) -> "AppSettings":
        return cls(**_load_yaml())


def settings() -> AppSettings:
    return AppSettings.load()


SETTINGS_GROUPS: list[tuple[str, list[str]]] = [
    ("Database", ["db_path"]),
    ("Projects", ["projects_root", "default_locale"]),
    ("Server", ["host", "port"]),
    ("Claude CLI / runners", [
        "claude_path", "orchestration_local_runner", "codex_path", "codex_api_key",
        "continue_path", "model_backend_profile",
        "anthropic_base_url", "anthropic_auth_token", "anthropic_api_key",
        "openai_proxy_base_url", "openai_proxy_api_key",
        "codex_command_template", "continue_command_template",
    ]),
    ("Self-study", [
        "model", "max_turns", "timeout_minutes", "self_study_command",
        "question_reminder_minutes", "question_expire_minutes",
    ]),
    ("Scheduling — nightly", [
        "cron_expression", "cron_enabled", "agents_per_night",
        "max_concurrent", "wait_between_sec",
    ]),
    ("Scheduling — weekly (opt-in)", [
        "weekly_tech_debt_scan_cron", "weekly_tech_debt_scan_enabled",
        "weekly_timur_duty_cron", "weekly_timur_duty_enabled",
        "weekly_product_ideas_scan_cron", "weekly_product_ideas_scan_enabled",
        "weekly_wiki_lint_cron", "weekly_wiki_lint_enabled",
        "weekly_evolve_apply_cron", "weekly_evolve_apply_enabled",
        "daily_bootstrap_cron", "daily_bootstrap_enabled",
        "daily_plans_cleanup_cron", "daily_plans_cleanup_enabled",
        "monthly_deep_audit_cron", "monthly_deep_audit_enabled",
    ]),
    ("Watchdogs", [
        "loop_watchdog_enabled", "loop_watchdog_interval_minutes",
        "sidecar_findings_enabled", "evolutions_stale_days",
        "loop_stagnation_hours", "plans_archive_days",
    ]),
    ("Paths (Obsidian / artifacts)", [
        "obsidian_vault", "agents_dir", "tech_debt_dir", "product_ideas_dir",
        "contracts_dir", "learning_notes_dir", "evolutions_dir",
        "context_overrides_dir", "lessons_cursor_path", "loops_dir",
        "plans_dir", "sidecar_findings_dir", "loops_templates_dir", "wiki_dir",
    ]),
    ("Jira", [
        "jira_url", "jira_email", "jira_api_token",
        "jira_project_key", "jira_user_account_id",
    ]),
    ("Harness (orchestration)", [
        "harness_base_url", "harness_api_key", "harness_timeout_sec",
        "harness_stream_enabled", "harness_start_path",
        "harness_events_stream_path", "harness_events_path",
        "harness_send_input_path", "harness_verify_tls",
    ]),
    ("AI Usage ingest", [
        "claude_projects_dir", "ai_usage_scan_enabled",
        "ai_usage_scan_interval_minutes", "ai_usage_scan_on_startup",
    ]),
    ("Routing", ["work_routing_mode"]),
]
