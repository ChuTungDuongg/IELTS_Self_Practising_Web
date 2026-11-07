"""Private admin Speaking dataset and fenced CPU jobs. No learner table changes."""

from alembic import op

revision = "20261107_0045"
down_revision = "20261102_0044"
branch_labels = depends_on = None


def upgrade():
    op.execute(
        """CREATE TABLE speaking_benchmark_samples (
	owner_id UUID NOT NULL,
	code VARCHAR(80) NOT NULL,
	audio_key VARCHAR(512) NOT NULL,
	source_sha256 VARCHAR(64) NOT NULL,
	mime_type VARCHAR(32) NOT NULL,
	byte_size INTEGER NOT NULL,
	duration_ms INTEGER NOT NULL,
	candidate_id VARCHAR(120) NOT NULL,
	split VARCHAR(12) NOT NULL,
	source_note TEXT NOT NULL,
	rights_confirmed BOOLEAN NOT NULL,
	status VARCHAR(16) NOT NULL,
	revision INTEGER NOT NULL,
	review_revision INTEGER NOT NULL,
	label_revision INTEGER NOT NULL,
	approved_fingerprint VARCHAR(64),
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_speaking_benchmark_samples PRIMARY KEY (id),
	CONSTRAINT uq_speaking_benchmark_samples_owner_id_code UNIQUE (owner_id, code),
	CONSTRAINT uq_speaking_benchmark_samples_owner_id_source_sha256 UNIQUE (owner_id, source_sha256),
	CONSTRAINT ck_speaking_benchmark_samples_split CHECK (split IN ('DEV','HOLDOUT')),
	CONSTRAINT ck_speaking_benchmark_samples_status CHECK (status IN ('DRAFT','PROCESSING','REVIEW','APPROVED')),
	CONSTRAINT ck_speaking_benchmark_samples_audio_bounds CHECK (byte_size BETWEEN 1 AND 134217728 AND duration_ms BETWEEN 1 AND 1800000),
	CONSTRAINT ck_speaking_benchmark_samples_mime CHECK (mime_type IN ('audio/wav','audio/mpeg')),
	CONSTRAINT ck_speaking_benchmark_samples_metadata CHECK (length(trim(code)) > 0 AND length(trim(source_note)) BETWEEN 1 AND 2000),
	CONSTRAINT ck_speaking_benchmark_samples_sha256 CHECK (source_sha256 ~ '^[a-f0-9]{64}$'),
	CONSTRAINT ck_speaking_benchmark_samples_rights CHECK (rights_confirmed),
	CONSTRAINT ck_speaking_benchmark_samples_revisions CHECK (revision >= 1 AND review_revision >= 0 AND label_revision >= 0),
	CONSTRAINT fk_speaking_benchmark_samples_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE RESTRICT,
	CONSTRAINT uq_speaking_benchmark_samples_audio_key_ UNIQUE (audio_key)
)"""
    )
    op.execute(
        "CREATE INDEX ix_speaking_benchmark_owner_created ON speaking_benchmark_samples (owner_id, created_at, id)"
    )
    op.execute(
        """CREATE TABLE speaking_benchmark_jobs (
	sample_id UUID NOT NULL,
	kind VARCHAR(20) NOT NULL,
	status VARCHAR(16) NOT NULL,
	stage VARCHAR(40) NOT NULL,
	progress INTEGER NOT NULL,
	attempts INTEGER NOT NULL,
	lease_token UUID,
	heartbeat_at TIMESTAMP WITH TIME ZONE,
	lease_expires_at TIMESTAMP WITH TIME ZONE,
	fingerprint VARCHAR(64) NOT NULL,
	source_sha256 VARCHAR(64) NOT NULL,
	configuration JSONB NOT NULL,
	result JSONB,
	error_code VARCHAR(100),
	started_at TIMESTAMP WITH TIME ZONE,
	finished_at TIMESTAMP WITH TIME ZONE,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_speaking_benchmark_jobs PRIMARY KEY (id),
	CONSTRAINT ck_speaking_benchmark_jobs_kind CHECK (kind = 'DIARIZATION'),
	CONSTRAINT ck_speaking_benchmark_jobs_status CHECK (status IN ('PENDING','RUNNING','COMPLETED','FAILED','CANCELLED')),
	CONSTRAINT ck_speaking_benchmark_jobs_bounds CHECK (progress BETWEEN 0 AND 100 AND attempts BETWEEN 0 AND 3),
	CONSTRAINT ck_speaking_benchmark_jobs_running_lease CHECK (status != 'RUNNING' OR (lease_token IS NOT NULL AND lease_expires_at IS NOT NULL AND heartbeat_at IS NOT NULL)),
	CONSTRAINT ck_speaking_benchmark_jobs_completed_result CHECK (status != 'COMPLETED' OR result IS NOT NULL),
	CONSTRAINT fk_speaking_benchmark_jobs_sample_id_speaking_benchmark_samples FOREIGN KEY(sample_id) REFERENCES speaking_benchmark_samples (id) ON DELETE CASCADE
)"""
    )
    op.execute(
        "CREATE INDEX ix_speaking_benchmark_job_queue ON speaking_benchmark_jobs (status, created_at)"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_speaking_benchmark_job_active ON speaking_benchmark_jobs (sample_id) WHERE status IN ('PENDING','RUNNING')"
    )
    op.execute(
        """CREATE TABLE speaking_benchmark_reviews (
	sample_id UUID NOT NULL,
	revision INTEGER NOT NULL,
	job_id UUID NOT NULL,
	draft JSONB NOT NULL,
	manifest JSONB,
	approved_by UUID,
	approved_at TIMESTAMP WITH TIME ZONE,
	fingerprint VARCHAR(64),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_speaking_benchmark_reviews PRIMARY KEY (sample_id, revision),
	CONSTRAINT ck_speaking_benchmark_reviews_revision CHECK (revision >= 1),
	CONSTRAINT ck_speaking_benchmark_reviews_approval CHECK ((manifest IS NULL) = (approved_at IS NULL)),
	CONSTRAINT fk_speaking_benchmark_reviews_sample_id_speaking_benchm_1312 FOREIGN KEY(sample_id) REFERENCES speaking_benchmark_samples (id) ON DELETE CASCADE,
	CONSTRAINT fk_speaking_benchmark_reviews_job_id_speaking_benchmark_jobs FOREIGN KEY(job_id) REFERENCES speaking_benchmark_jobs (id) ON DELETE CASCADE,
	CONSTRAINT fk_speaking_benchmark_reviews_approved_by_users FOREIGN KEY(approved_by) REFERENCES users (id) ON DELETE SET NULL
)"""
    )
    op.execute(
        """CREATE TABLE speaking_benchmark_human_labels (
	sample_id UUID NOT NULL,
	revision INTEGER NOT NULL,
	fc NUMERIC,
	lr NUMERIC,
	gra NUMERIC,
	pr NUMERIC,
	overall NUMERIC,
	provenance VARCHAR(40) NOT NULL,
	reference TEXT NOT NULL,
	verified BOOLEAN NOT NULL,
	examiner VARCHAR(500) NOT NULL,
	notes TEXT NOT NULL,
	authored_by UUID,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_speaking_benchmark_human_labels PRIMARY KEY (sample_id, revision),
	CONSTRAINT ck_speaking_benchmark_human_labels_revision CHECK (revision >= 1),
	CONSTRAINT ck_speaking_benchmark_human_labels_provenance CHECK (provenance IN ('human_examiner','published_human_assessment','unverified')),
	CONSTRAINT ck_speaking_benchmark_human_labels_verified CHECK (NOT verified OR (provenance IN ('human_examiner','published_human_assessment') AND length(trim(reference)) > 0)),
	CONSTRAINT ck_speaking_benchmark_human_labels_fc_half_band CHECK (fc IS NULL OR (fc BETWEEN 0 AND 9 AND fc * 2 = floor(fc * 2))),
	CONSTRAINT ck_speaking_benchmark_human_labels_lr_half_band CHECK (lr IS NULL OR (lr BETWEEN 0 AND 9 AND lr * 2 = floor(lr * 2))),
	CONSTRAINT ck_speaking_benchmark_human_labels_gra_half_band CHECK (gra IS NULL OR (gra BETWEEN 0 AND 9 AND gra * 2 = floor(gra * 2))),
	CONSTRAINT ck_speaking_benchmark_human_labels_pr_half_band CHECK (pr IS NULL OR (pr BETWEEN 0 AND 9 AND pr * 2 = floor(pr * 2))),
	CONSTRAINT ck_speaking_benchmark_human_labels_overall_half_band CHECK (overall IS NULL OR (overall BETWEEN 0 AND 9 AND overall * 2 = floor(overall * 2))),
	CONSTRAINT fk_speaking_benchmark_human_labels_sample_id_speaking_b_5190 FOREIGN KEY(sample_id) REFERENCES speaking_benchmark_samples (id) ON DELETE CASCADE,
	CONSTRAINT fk_speaking_benchmark_human_labels_authored_by_users FOREIGN KEY(authored_by) REFERENCES users (id) ON DELETE SET NULL
)"""
    )


def downgrade():
    op.drop_table("speaking_benchmark_human_labels")
    op.drop_table("speaking_benchmark_reviews")
    op.drop_table("speaking_benchmark_jobs")
    op.drop_table("speaking_benchmark_samples")
