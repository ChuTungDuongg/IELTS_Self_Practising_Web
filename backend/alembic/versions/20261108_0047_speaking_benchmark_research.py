"""Private ASR references and reproducible research experiments. Frozen schema."""
from alembic import op

revision = '20261108_0047'
down_revision = '20261108_0046'
branch_labels = None
depends_on = None

def _create_tables():
    op.execute("\nCREATE TABLE speaking_benchmark_asr_references (\n\tsample_id UUID NOT NULL, \n\towner_id UUID NOT NULL, \n\treview_revision INTEGER NOT NULL, \n\tsource_sha256 VARCHAR(64) NOT NULL, \n\tmanifest_fingerprint VARCHAR(64) NOT NULL, \n\tsegment_id VARCHAR(100) NOT NULL, \n\tstart_ms INTEGER NOT NULL, \n\tend_ms INTEGER NOT NULL, \n\trevision INTEGER NOT NULL, \n\tnormalization VARCHAR(80) NOT NULL, \n\ttext TEXT NOT NULL, \n\tannotations JSONB NOT NULL, \n\tuncertainty JSONB NOT NULL, \n\tmetadata_labels JSONB NOT NULL, \n\tstatus VARCHAR(16) NOT NULL, \n\tprovenance VARCHAR(80) NOT NULL, \n\tsource_reference VARCHAR(1000) NOT NULL, \n\tauthor_id UUID NOT NULL, \n\treviewer_id UUID, \n\tverified_at TIMESTAMP WITH TIME ZONE, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tCONSTRAINT pk_speaking_benchmark_asr_references PRIMARY KEY (id), \n\tCONSTRAINT fk_speaking_benchmark_asr_references_sample_id_speaking_84f5 FOREIGN KEY(sample_id, owner_id) REFERENCES speaking_benchmark_samples (id, owner_id) ON DELETE CASCADE, \n\tCONSTRAINT fk_speaking_benchmark_asr_references_sample_id_speaking_8757 FOREIGN KEY(sample_id, review_revision) REFERENCES speaking_benchmark_reviews (sample_id, revision) ON DELETE CASCADE, \n\tCONSTRAINT uq_speaking_benchmark_asr_references_sample_id_review_revision UNIQUE (sample_id, review_revision, segment_id, revision), \n\tCONSTRAINT ck_speaking_benchmark_asr_references_bounds CHECK (revision > 0 AND review_revision > 0 AND start_ms >= 0 AND end_ms > start_ms), \n\tCONSTRAINT ck_speaking_benchmark_asr_references_status CHECK (status IN ('DRAFT','VERIFIED')), \n\tCONSTRAINT ck_speaking_benchmark_asr_references_verification CHECK (status != 'VERIFIED' OR (provenance = 'independent_human_transcriber' AND reviewer_id IS NOT NULL AND verified_at IS NOT NULL AND length(trim(source_reference)) > 0)), \n\tCONSTRAINT fk_speaking_benchmark_asr_references_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE RESTRICT, \n\tCONSTRAINT fk_speaking_benchmark_asr_references_author_id_users FOREIGN KEY(author_id) REFERENCES users (id) ON DELETE RESTRICT, \n\tCONSTRAINT fk_speaking_benchmark_asr_references_reviewer_id_users FOREIGN KEY(reviewer_id) REFERENCES users (id) ON DELETE RESTRICT\n)\n\n")
    op.execute('CREATE INDEX ix_speaking_research_reference_window ON speaking_benchmark_asr_references (sample_id, review_revision, segment_id, revision)')
    op.execute("\nCREATE TABLE speaking_benchmark_experiments (\n\towner_id UUID NOT NULL, \n\tsubmission_key UUID NOT NULL, \n\tname VARCHAR(160) NOT NULL, \n\tdescription TEXT NOT NULL, \n\tmode VARCHAR(24) NOT NULL, \n\tconfiguration JSONB NOT NULL, \n\tfingerprint VARCHAR(64) NOT NULL, \n\tevaluation_selection JSONB NOT NULL, \n\tconsent JSONB, \n\tstatus VARCHAR(20) NOT NULL, \n\tstarted_at TIMESTAMP WITH TIME ZONE, \n\tfinished_at TIMESTAMP WITH TIME ZONE, \n\tholdout_executed_at TIMESTAMP WITH TIME ZONE, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tCONSTRAINT pk_speaking_benchmark_experiments PRIMARY KEY (id), \n\tCONSTRAINT uq_speaking_benchmark_experiments_id_owner_id UNIQUE (id, owner_id), \n\tCONSTRAINT uq_speaking_benchmark_experiments_owner_id_submission_key UNIQUE (owner_id, submission_key), \n\tCONSTRAINT ck_speaking_benchmark_experiments_mode CHECK (mode IN ('ASR_ONLY','PAIRED_GRADING')), \n\tCONSTRAINT ck_speaking_benchmark_experiments_status CHECK (status IN ('DRAFT','PENDING','RUNNING','INTERRUPTED','COMPLETED','PARTIAL','FAILED','CANCELLED')), \n\tCONSTRAINT fk_speaking_benchmark_experiments_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE RESTRICT\n)\n\n")
    op.execute('CREATE INDEX ix_speaking_research_owner_created ON speaking_benchmark_experiments (owner_id, created_at, id)')
    op.execute("\nCREATE TABLE speaking_benchmark_experiment_variants (\n\texperiment_id UUID NOT NULL, \n\towner_id UUID NOT NULL, \n\tsample_id UUID NOT NULL, \n\treview_revision INTEGER NOT NULL, \n\tsource_sha256 VARCHAR(64) NOT NULL, \n\tmanifest_fingerprint VARCHAR(64) NOT NULL, \n\tprovider_key VARCHAR(80) NOT NULL, \n\tconfiguration JSONB NOT NULL, \n\tfingerprint VARCHAR(64) NOT NULL, \n\twindows JSONB NOT NULL, \n\tstatus VARCHAR(20) NOT NULL, \n\terror_code VARCHAR(100), \n\tgrading_run_id UUID, \n\tlease_token UUID, \n\tlease_expires_at TIMESTAMP WITH TIME ZONE, \n\tstarted_at TIMESTAMP WITH TIME ZONE, \n\tfinished_at TIMESTAMP WITH TIME ZONE, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tCONSTRAINT pk_speaking_benchmark_experiment_variants PRIMARY KEY (id), \n\tCONSTRAINT fk_speaking_benchmark_experiment_variants_experiment_id_3b87 FOREIGN KEY(experiment_id, owner_id) REFERENCES speaking_benchmark_experiments (id, owner_id) ON DELETE CASCADE, \n\tCONSTRAINT fk_speaking_benchmark_experiment_variants_sample_id_spe_ed28 FOREIGN KEY(sample_id, owner_id) REFERENCES speaking_benchmark_samples (id, owner_id) ON DELETE CASCADE, \n\tCONSTRAINT fk_speaking_benchmark_experiment_variants_sample_id_spe_63bb FOREIGN KEY(sample_id, review_revision) REFERENCES speaking_benchmark_reviews (sample_id, revision) ON DELETE CASCADE, \n\tCONSTRAINT uq_speaking_benchmark_experiment_variants_experiment_id_bf89 UNIQUE (experiment_id, sample_id, provider_key), \n\tCONSTRAINT ck_speaking_benchmark_experiment_variants_status CHECK (status IN ('PENDING','RUNNING','WAITING','INTERRUPTED','COMPLETED','PARTIAL','FAILED','CANCELLED')), \n\tCONSTRAINT ck_speaking_benchmark_experiment_variants_lease CHECK (status != 'RUNNING' OR (lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)), \n\tCONSTRAINT fk_speaking_benchmark_experiment_variants_grading_run_i_a7d3 FOREIGN KEY(grading_run_id) REFERENCES speaking_benchmark_grading_runs (id) ON DELETE SET NULL\n)\n\n")
    op.execute('CREATE INDEX ix_speaking_research_variant_queue ON speaking_benchmark_experiment_variants (status, created_at)')
    op.execute("\nCREATE TABLE speaking_benchmark_asr_observations (\n\tvariant_id UUID NOT NULL, \n\tsegment_id VARCHAR(100) NOT NULL, \n\tidentity VARCHAR(64) NOT NULL, \n\tattempt INTEGER NOT NULL, \n\tstatus VARCHAR(40) NOT NULL, \n\tbilling_state VARCHAR(24) NOT NULL, \n\tresult JSONB, \n\tusage JSONB, \n\terror_code VARCHAR(100), \n\treused_from UUID, \n\treconciliation JSONB, \n\tfinished_at TIMESTAMP WITH TIME ZONE, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tCONSTRAINT pk_speaking_benchmark_asr_observations PRIMARY KEY (id), \n\tCONSTRAINT uq_speaking_benchmark_asr_observations_variant_id_segment_id UNIQUE (variant_id, segment_id, attempt), \n\tCONSTRAINT ck_speaking_benchmark_asr_observations_attempt CHECK (attempt > 0), \n\tCONSTRAINT ck_speaking_benchmark_asr_observations_status CHECK (status IN ('ATTEMPTED','COMPLETED','FAILED','INTERRUPTED_BILLING_UNKNOWN')), \n\tCONSTRAINT ck_speaking_benchmark_asr_observations_result CHECK (status != 'COMPLETED' OR result IS NOT NULL), \n\tCONSTRAINT fk_speaking_benchmark_asr_observations_variant_id_speak_6851 FOREIGN KEY(variant_id) REFERENCES speaking_benchmark_experiment_variants (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_speaking_benchmark_asr_observations_reused_from_spea_7f00 FOREIGN KEY(reused_from) REFERENCES speaking_benchmark_asr_observations (id) ON DELETE SET NULL\n)\n\n")
    op.execute('CREATE INDEX ix_speaking_research_observation_cache ON speaking_benchmark_asr_observations (identity, status)')

def _install_guards():
    op.execute("""CREATE FUNCTION speaking_research_frozen() RETURNS trigger AS $$
    BEGIN
      IF TG_TABLE_NAME = 'speaking_benchmark_asr_references' THEN
        IF TG_OP = 'UPDATE' THEN RAISE EXCEPTION 'Reference revisions are append only'; END IF;
        IF NOT EXISTS (SELECT 1 FROM speaking_benchmark_samples s
          JOIN speaking_benchmark_reviews r ON r.sample_id=s.id,
          LATERAL jsonb_array_elements(r.manifest->'segments') w
          WHERE s.id=NEW.sample_id AND s.owner_id=NEW.owner_id
          AND s.source_sha256=NEW.source_sha256 AND r.revision=NEW.review_revision
          AND r.approved_at IS NOT NULL AND r.fingerprint=NEW.manifest_fingerprint
          AND w->>'id'=NEW.segment_id AND (w->>'start_ms')::int=NEW.start_ms
          AND (w->>'end_ms')::int=NEW.end_ms) THEN
          RAISE EXCEPTION 'Approved reference window binding required'; END IF;
      ELSIF TG_TABLE_NAME = 'speaking_benchmark_experiments' THEN
        IF TG_OP = 'UPDATE' AND ROW(NEW.owner_id,NEW.submission_key,NEW.name,NEW.description,NEW.mode,NEW.configuration,NEW.fingerprint,NEW.evaluation_selection)
          IS DISTINCT FROM ROW(OLD.owner_id,OLD.submission_key,OLD.name,OLD.description,OLD.mode,OLD.configuration,OLD.fingerprint,OLD.evaluation_selection)
          THEN RAISE EXCEPTION 'Research configuration is frozen'; END IF;
      ELSIF TG_TABLE_NAME = 'speaking_benchmark_experiment_variants' THEN
        IF NEW.grading_run_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM speaking_benchmark_grading_runs g WHERE g.id=NEW.grading_run_id
          AND g.owner_id=NEW.owner_id AND g.sample_id=NEW.sample_id
          AND g.review_revision=NEW.review_revision AND g.source_sha256=NEW.source_sha256
          AND g.manifest_fingerprint=NEW.manifest_fingerprint
          AND g.configuration=NEW.configuration->'grading')
          THEN RAISE EXCEPTION 'Research P2 run binding required'; END IF;
        IF TG_OP = 'UPDATE' AND OLD.status IN ('COMPLETED','PARTIAL','FAILED','CANCELLED') AND
          (to_jsonb(NEW)-'updated_at'-'grading_run_id') IS DISTINCT FROM (to_jsonb(OLD)-'updated_at'-'grading_run_id')
          THEN RAISE EXCEPTION 'Final research variant is immutable'; END IF;
        IF TG_OP = 'UPDATE' AND OLD.status IN ('COMPLETED','PARTIAL','FAILED','CANCELLED') AND
          NEW.grading_run_id IS NOT NULL AND NEW.grading_run_id IS DISTINCT FROM OLD.grading_run_id
          THEN RAISE EXCEPTION 'Final linked prediction is immutable'; END IF;
        IF TG_OP = 'INSERT' AND NOT EXISTS (SELECT 1 FROM speaking_benchmark_reviews r
          JOIN speaking_benchmark_samples s ON s.id=r.sample_id
          WHERE s.id=NEW.sample_id AND s.owner_id=NEW.owner_id AND s.source_sha256=NEW.source_sha256
          AND r.revision=NEW.review_revision AND r.approved_at IS NOT NULL AND r.fingerprint=NEW.manifest_fingerprint)
          THEN RAISE EXCEPTION 'Approved variant binding required'; END IF;
        IF TG_OP = 'UPDATE' AND ROW(NEW.experiment_id,NEW.owner_id,NEW.sample_id,NEW.review_revision,NEW.source_sha256,NEW.manifest_fingerprint,NEW.provider_key,NEW.configuration,NEW.fingerprint,NEW.windows)
          IS DISTINCT FROM ROW(OLD.experiment_id,OLD.owner_id,OLD.sample_id,OLD.review_revision,OLD.source_sha256,OLD.manifest_fingerprint,OLD.provider_key,OLD.configuration,OLD.fingerprint,OLD.windows)
          THEN RAISE EXCEPTION 'Research variant inputs are frozen'; END IF;
      ELSIF TG_TABLE_NAME = 'speaking_benchmark_asr_observations' THEN
        IF TG_OP = 'UPDATE' AND ROW(NEW.variant_id,NEW.segment_id,NEW.identity,NEW.attempt)
          IS DISTINCT FROM ROW(OLD.variant_id,OLD.segment_id,OLD.identity,OLD.attempt)
          THEN RAISE EXCEPTION 'Physical attempt identity is frozen'; END IF;
        IF TG_OP = 'UPDATE' AND OLD.status IN ('COMPLETED','FAILED') AND
          (to_jsonb(NEW)-'updated_at'-'reused_from') IS DISTINCT FROM (to_jsonb(OLD)-'updated_at'-'reused_from')
          THEN RAISE EXCEPTION 'Final research observations are immutable'; END IF;
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql""")
    for table in ('speaking_benchmark_asr_references', 'speaking_benchmark_experiments', 'speaking_benchmark_experiment_variants', 'speaking_benchmark_asr_observations'):
        op.execute(f'CREATE TRIGGER research_frozen BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION speaking_research_frozen()')


def upgrade():
    _create_tables()
    _install_guards()


def downgrade():
    op.drop_table('speaking_benchmark_asr_observations')
    op.drop_table('speaking_benchmark_experiment_variants')
    op.drop_table('speaking_benchmark_experiments')
    op.drop_table('speaking_benchmark_asr_references')
    op.execute('DROP FUNCTION speaking_research_frozen()')
