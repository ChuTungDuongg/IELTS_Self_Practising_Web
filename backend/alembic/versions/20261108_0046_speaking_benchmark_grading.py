"""Source-bound admin grading runs and append-only request ledger."""

import sqlalchemy as sa

from alembic import op

revision = "20261108_0046"
down_revision = "20261107_0045"
branch_labels = depends_on = None


def upgrade():
    op.add_column("speaking_benchmark_samples", sa.Column("deletion_pending_at", sa.DateTime(timezone=True)))
    op.create_unique_constraint("uq_speaking_benchmark_sample_owner_binding", "speaking_benchmark_samples", ["id", "owner_id"])
    # Frozen additive DDL; independent of future ORM model changes.
    op.execute("\nCREATE TABLE speaking_benchmark_grading_runs (\n\tsample_id UUID NOT NULL, \n\towner_id UUID NOT NULL, \n\treview_revision INTEGER NOT NULL, \n\tsource_sha256 VARCHAR(64) NOT NULL, \n\tmanifest_fingerprint VARCHAR(64) NOT NULL, \n\tconfig_fingerprint VARCHAR(64) NOT NULL, \n\tsubmission_key UUID NOT NULL, \n\tconfiguration JSONB NOT NULL, \n\tconsent JSONB NOT NULL, \n\tcandidate_ms INTEGER NOT NULL, \n\twindow_count INTEGER NOT NULL, \n\tstatus VARCHAR(20) NOT NULL, \n\tstage VARCHAR(100) NOT NULL, \n\tprogress INTEGER NOT NULL, \n\tlease_token UUID, \n\tlease_expires_at TIMESTAMP WITH TIME ZONE, \n\theartbeat_at TIMESTAMP WITH TIME ZONE, \n\tstarted_at TIMESTAMP WITH TIME ZONE, \n\tfinished_at TIMESTAMP WITH TIME ZONE, \n\terror_code VARCHAR(100), \n\tprediction JSONB, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tCONSTRAINT pk_speaking_benchmark_grading_runs PRIMARY KEY (id), \n\tCONSTRAINT fk_speaking_benchmark_grading_runs_sample_id_speaking_b_214f FOREIGN KEY(sample_id, owner_id) REFERENCES speaking_benchmark_samples (id, owner_id) ON DELETE CASCADE, \n\tCONSTRAINT fk_speaking_benchmark_grading_runs_sample_id_speaking_b_360a FOREIGN KEY(sample_id, review_revision) REFERENCES speaking_benchmark_reviews (sample_id, revision) ON DELETE CASCADE, \n\tCONSTRAINT uq_speaking_benchmark_grading_runs_owner_id_submission_key UNIQUE (owner_id, submission_key), \n\tCONSTRAINT ck_speaking_benchmark_grading_runs_status CHECK (status IN ('PENDING','RUNNING','INTERRUPTED','COMPLETED','PARTIAL','FAILED','CANCELLED')), \n\tCONSTRAINT ck_speaking_benchmark_grading_runs_bounds CHECK (review_revision > 0 AND candidate_ms > 0 AND window_count > 0 AND progress BETWEEN 0 AND 100), \n\tCONSTRAINT ck_speaking_benchmark_grading_runs_lease CHECK (status != 'RUNNING' OR (lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)), \n\tCONSTRAINT fk_speaking_benchmark_grading_runs_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE RESTRICT\n)\n\n")
    op.execute('CREATE INDEX ix_speaking_benchmark_grading_queue ON speaking_benchmark_grading_runs (status, created_at)')
    op.execute("CREATE UNIQUE INDEX uq_speaking_benchmark_grading_active ON speaking_benchmark_grading_runs (sample_id) WHERE status IN ('PENDING','RUNNING','INTERRUPTED')")
    op.execute("\nCREATE TABLE speaking_benchmark_grading_checkpoints (\n\trun_id UUID NOT NULL, \n\tstage VARCHAR(100) NOT NULL, \n\tprovider VARCHAR(80) NOT NULL, \n\tidentity VARCHAR(64) NOT NULL, \n\tattempt INTEGER NOT NULL, \n\tstatus VARCHAR(40) NOT NULL, \n\tbilling_state VARCHAR(20) NOT NULL, \n\tresult JSONB, \n\tusage JSONB, \n\terror_code VARCHAR(100), \n\treused_from UUID, \n\tfinished_at TIMESTAMP WITH TIME ZONE, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tCONSTRAINT pk_speaking_benchmark_grading_checkpoints PRIMARY KEY (id), \n\tCONSTRAINT uq_speaking_benchmark_grading_checkpoints_run_id_stage UNIQUE (run_id, stage, identity, attempt), \n\tCONSTRAINT ck_speaking_benchmark_grading_checkpoints_attempt CHECK (attempt > 0), \n\tCONSTRAINT ck_speaking_benchmark_grading_checkpoints_status CHECK (status IN ('ATTEMPTED','COMPLETED','FAILED','INTERRUPTED_BILLING_UNKNOWN')), \n\tCONSTRAINT ck_speaking_benchmark_grading_checkpoints_billing CHECK (billing_state IN ('UNKNOWN','OBSERVED','NOT_BILLABLE')), \n\tCONSTRAINT ck_speaking_benchmark_grading_checkpoints_result CHECK (status != 'COMPLETED' OR result IS NOT NULL), \n\tCONSTRAINT fk_speaking_benchmark_grading_checkpoints_run_id_speaki_ad9e FOREIGN KEY(run_id) REFERENCES speaking_benchmark_grading_runs (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_speaking_benchmark_grading_checkpoints_reused_from_s_cad2 FOREIGN KEY(reused_from) REFERENCES speaking_benchmark_grading_checkpoints (id) ON DELETE SET NULL\n)\n\n")
    op.execute('CREATE INDEX ix_speaking_benchmark_checkpoint_reuse ON speaking_benchmark_grading_checkpoints (identity, status)')
    op.execute("""CREATE FUNCTION speaking_benchmark_frozen() RETURNS trigger AS $$
    BEGIN
      IF TG_TABLE_NAME = 'speaking_benchmark_grading_runs' THEN
        IF TG_OP = 'INSERT' AND NOT EXISTS (
          SELECT 1 FROM speaking_benchmark_samples s JOIN speaking_benchmark_reviews r ON r.sample_id=s.id
          WHERE s.id=NEW.sample_id AND s.owner_id=NEW.owner_id AND s.source_sha256=NEW.source_sha256
          AND r.revision=NEW.review_revision AND r.approved_at IS NOT NULL
          AND r.fingerprint=NEW.manifest_fingerprint) THEN
          RAISE EXCEPTION 'Approved source/review binding required';
        END IF;
        IF TG_OP = 'UPDATE' AND ROW(NEW.sample_id,NEW.owner_id,NEW.review_revision,NEW.source_sha256,
          NEW.manifest_fingerprint,NEW.config_fingerprint,NEW.configuration,NEW.submission_key,NEW.candidate_ms,NEW.window_count)
          IS DISTINCT FROM ROW(OLD.sample_id,OLD.owner_id,OLD.review_revision,OLD.source_sha256,
          OLD.manifest_fingerprint,OLD.config_fingerprint,OLD.configuration,OLD.submission_key,OLD.candidate_ms,OLD.window_count) THEN
          RAISE EXCEPTION 'Admitted inference inputs are immutable';
        END IF;
        IF TG_OP = 'UPDATE' AND OLD.status IN ('COMPLETED','PARTIAL','FAILED','CANCELLED') AND
           (to_jsonb(NEW) - 'updated_at') IS DISTINCT FROM (to_jsonb(OLD) - 'updated_at') THEN
          RAISE EXCEPTION 'Finalized benchmark predictions are immutable';
        END IF;
        IF NEW.prediction IS NOT NULL THEN
          IF EXISTS (SELECT 1 FROM jsonb_each(NEW.prediction->'bands') b
            WHERE b.value <> 'null'::jsonb AND ((b.value::text)::numeric NOT BETWEEN 0 AND 9 OR
            (b.value::text)::numeric * 2 <> floor((b.value::text)::numeric * 2))) THEN
            RAISE EXCEPTION 'Invalid benchmark half band';
          END IF;
        END IF;
      ELSE
        IF TG_OP = 'UPDATE' AND OLD.status IN ('COMPLETED','FAILED') AND
          (to_jsonb(NEW) - 'updated_at' - 'reused_from') IS DISTINCT FROM
          (to_jsonb(OLD) - 'updated_at' - 'reused_from') THEN
          RAISE EXCEPTION 'Completed benchmark attempts are immutable';
        END IF;
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql""")
    for table in ("speaking_benchmark_grading_runs", "speaking_benchmark_grading_checkpoints"):
        op.execute(f"CREATE TRIGGER frozen_result BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION speaking_benchmark_frozen()")


def downgrade():
    op.drop_table("speaking_benchmark_grading_checkpoints")
    op.drop_table("speaking_benchmark_grading_runs")
    op.execute("DROP FUNCTION speaking_benchmark_frozen()")
    op.drop_constraint("uq_speaking_benchmark_sample_owner_binding", "speaking_benchmark_samples", type_="unique")
    op.drop_column("speaking_benchmark_samples", "deletion_pending_at")
