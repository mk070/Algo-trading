"""Migration 011: AI Research Agent tables.

Adds:
  ai_agent_executions
  ai_research_assessments
  ai_provider_usage

Revision ID: 011_ai_research_agents
Revises: 010_lab_paper_connect
"""
from alembic import op
import sqlalchemy as sa

revision = "011_ai_research_agents"
down_revision = "010_lab_paper_connect"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. ai_agent_executions ──────────────────────────────────────────────
    op.create_table(
        "ai_agent_executions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("agent_name", sa.String(50), nullable=False),
        sa.Column("symbol", sa.String(50), nullable=False),
        sa.Column("market", sa.String(10), nullable=False, server_default="IN"),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model_id", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(20), nullable=False, server_default="1.0"),
        sa.Column("input_record_ids", sa.Text, nullable=True),
        sa.Column("output_json", sa.Text, nullable=True),
        sa.Column("validation_status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("latency_sec", sa.Float, nullable=True),
        sa.Column("input_tokens", sa.Integer, nullable=True),
        sa.Column("output_tokens", sa.Integer, nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("is_valid", sa.Boolean, nullable=False, server_default="false"),
    )
    op.create_index("idx_ai_exec_agent_sym", "ai_agent_executions", ["agent_name", "symbol"])
    op.create_index("idx_ai_exec_hash", "ai_agent_executions", ["input_hash"])
    op.create_index("idx_ai_exec_generated", "ai_agent_executions", ["generated_at"])

    # ── 2. ai_research_assessments ──────────────────────────────────────────
    op.create_table(
        "ai_research_assessments",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(50), nullable=False),
        sa.Column("market", sa.String(10), nullable=False, server_default="IN"),
        sa.Column("final_status", sa.String(30), nullable=False),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("evidence_json", sa.Text, nullable=True),
        sa.Column("risks_json", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("requires_human_review", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("agent_execution_id", sa.Integer, sa.ForeignKey("ai_agent_executions.id"), nullable=True),
        sa.Column(
            "superseded_by",
            sa.Integer,
            sa.ForeignKey("ai_research_assessments.id", name="fk_ai_assess_superseded", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("idx_ai_assess_sym_mkt", "ai_research_assessments", ["symbol", "market"])
    op.create_index("idx_ai_assess_status", "ai_research_assessments", ["final_status"])
    op.create_index("idx_ai_assess_generated", "ai_research_assessments", ["generated_at"])

    # ── 3. ai_provider_usage ───────────────────────────────────────────────
    op.create_table(
        "ai_provider_usage",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model_id", sa.String(100), nullable=False),
        sa.Column("reserved_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("request_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_input_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_output_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("quota_exhausted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_ai_usage_date_provider", "ai_provider_usage", ["date", "provider"])
    op.create_index(
        "uq_ai_usage_date_prov_model",
        "ai_provider_usage",
        ["date", "provider", "model_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_ai_usage_date_prov_model", table_name="ai_provider_usage")
    op.drop_index("idx_ai_usage_date_provider", table_name="ai_provider_usage")
    op.drop_table("ai_provider_usage")

    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_constraint("fk_ai_assess_superseded", "ai_research_assessments", type_="foreignkey")
    op.drop_index("idx_ai_assess_generated", table_name="ai_research_assessments")
    op.drop_index("idx_ai_assess_status", table_name="ai_research_assessments")
    op.drop_index("idx_ai_assess_sym_mkt", table_name="ai_research_assessments")
    op.drop_table("ai_research_assessments")

    op.drop_index("idx_ai_exec_generated", table_name="ai_agent_executions")
    op.drop_index("idx_ai_exec_hash", table_name="ai_agent_executions")
    op.drop_index("idx_ai_exec_agent_sym", table_name="ai_agent_executions")
    op.drop_table("ai_agent_executions")
