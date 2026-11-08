"""Assisted questions, independent human ratings and frozen quality gates."""
from alembic import op

revision = "20261108_0048"
down_revision = "20261108_0047"
branch_labels = None
depends_on = None

def upgrade():
    op.execute('\nCREATE TABLE speaking_benchmark_evaluation_suites (\n\towner_id UUID NOT NULL, \n\tfamily_id UUID NOT NULL, \n\trevision INTEGER NOT NULL, \n\tname VARCHAR(160) NOT NULL, \n\tdescription TEXT NOT NULL, \n\tconfiguration JSONB NOT NULL, \n\tfingerprint VARCHAR(64) NOT NULL, \n\tfrozen_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tCONSTRAINT pk_speaking_benchmark_evaluation_suites PRIMARY KEY (id), \n\tCONSTRAINT uq_speaking_benchmark_evaluation_suites_id_owner_id UNIQUE (id, owner_id), \n\tCONSTRAINT uq_speaking_benchmark_evaluation_suites_owner_id_family_id UNIQUE (owner_id, family_id, revision), \n\tCONSTRAINT ck_speaking_benchmark_evaluation_suites_revision CHECK (revision > 0), \n\tCONSTRAINT fk_speaking_benchmark_evaluation_suites_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE RESTRICT\n)\n\n')
    op.execute('CREATE INDEX ix_speaking_suite_owner_created ON speaking_benchmark_evaluation_suites (owner_id, created_at, id)')
    op.execute('\nCREATE TABLE speaking_benchmark_quality_snapshots (\n\towner_id UUID NOT NULL, \n\tprotocol VARCHAR(80) NOT NULL, \n\tconfiguration JSONB NOT NULL, \n\tfingerprint VARCHAR(64) NOT NULL, \n\tstatus VARCHAR(24) NOT NULL, \n\treport JSONB NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tCONSTRAINT pk_speaking_benchmark_quality_snapshots PRIMARY KEY (id), \n\tCONSTRAINT fk_speaking_benchmark_quality_snapshots_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE RESTRICT\n)\n\n')
    op.execute('CREATE INDEX ix_speaking_quality_owner_created ON speaking_benchmark_quality_snapshots (owner_id, created_at, id)')
    op.execute("\nCREATE TABLE speaking_benchmark_raters (\n\towner_id UUID NOT NULL, \n\tkind VARCHAR(16) NOT NULL, \n\tuser_id UUID, \n\texternal_key VARCHAR(160), \n\tdisplay_name VARCHAR(200) NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tCONSTRAINT pk_speaking_benchmark_raters PRIMARY KEY (id), \n\tCONSTRAINT uq_speaking_benchmark_raters_id_owner_id UNIQUE (id, owner_id), \n\tCONSTRAINT uq_speaking_benchmark_raters_owner_id_user_id UNIQUE (owner_id, user_id), \n\tCONSTRAINT uq_speaking_benchmark_raters_owner_id_external_key UNIQUE (owner_id, external_key), \n\tCONSTRAINT ck_speaking_benchmark_raters_kind CHECK (kind IN ('INTERNAL','EXTERNAL')), \n\tCONSTRAINT ck_speaking_benchmark_raters_identity CHECK ((kind = 'INTERNAL' AND user_id IS NOT NULL AND external_key IS NULL) OR (kind = 'EXTERNAL' AND user_id IS NULL AND length(trim(external_key)) > 0)), \n\tCONSTRAINT ck_speaking_benchmark_raters_display_name CHECK (length(trim(display_name)) > 0), \n\tCONSTRAINT fk_speaking_benchmark_raters_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE RESTRICT, \n\tCONSTRAINT fk_speaking_benchmark_raters_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT\n)\n\n")
    op.execute('CREATE INDEX ix_speaking_benchmark_rater_owner ON speaking_benchmark_raters (owner_id, created_at, id)')
    op.execute('\nCREATE TABLE speaking_benchmark_holdout_audits (\n\towner_id UUID NOT NULL, \n\tsuite_id UUID NOT NULL, \n\tactor_id UUID NOT NULL, \n\taction VARCHAR(40) NOT NULL, \n\tdetails JSONB NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tCONSTRAINT pk_speaking_benchmark_holdout_audits PRIMARY KEY (id), \n\tCONSTRAINT fk_speaking_benchmark_holdout_audits_suite_id_speaking__3921 FOREIGN KEY(suite_id, owner_id) REFERENCES speaking_benchmark_evaluation_suites (id, owner_id) ON DELETE RESTRICT, \n\tCONSTRAINT fk_speaking_benchmark_holdout_audits_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE RESTRICT, \n\tCONSTRAINT fk_speaking_benchmark_holdout_audits_actor_id_users FOREIGN KEY(actor_id) REFERENCES users (id) ON DELETE RESTRICT\n)\n\n')
    op.execute('\nCREATE TABLE speaking_benchmark_regression_gates (\n\towner_id UUID NOT NULL, \n\tsuite_id UUID NOT NULL, \n\tname VARCHAR(160) NOT NULL, \n\tbaseline JSONB NOT NULL, \n\tcandidate JSONB NOT NULL, \n\tpolicy JSONB NOT NULL, \n\tfingerprint VARCHAR(64) NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tCONSTRAINT pk_speaking_benchmark_regression_gates PRIMARY KEY (id), \n\tCONSTRAINT uq_speaking_benchmark_regression_gates_id_owner_id UNIQUE (id, owner_id), \n\tCONSTRAINT fk_speaking_benchmark_regression_gates_suite_id_speakin_fdc3 FOREIGN KEY(suite_id, owner_id) REFERENCES speaking_benchmark_evaluation_suites (id, owner_id) ON DELETE RESTRICT, \n\tCONSTRAINT fk_speaking_benchmark_regression_gates_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE RESTRICT\n)\n\n')
    op.execute('CREATE INDEX ix_speaking_gate_owner_created ON speaking_benchmark_regression_gates (owner_id, created_at, id)')
    op.execute("\nCREATE TABLE speaking_benchmark_regression_reports (\n\towner_id UUID NOT NULL, \n\tgate_id UUID NOT NULL, \n\tstatus VARCHAR(20) NOT NULL, \n\tprotocol VARCHAR(80) NOT NULL, \n\tfingerprint VARCHAR(64) NOT NULL, \n\treport JSONB NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tCONSTRAINT pk_speaking_benchmark_regression_reports PRIMARY KEY (id), \n\tCONSTRAINT fk_speaking_benchmark_regression_reports_gate_id_speaki_c44b FOREIGN KEY(gate_id, owner_id) REFERENCES speaking_benchmark_regression_gates (id, owner_id) ON DELETE RESTRICT, \n\tCONSTRAINT ck_speaking_benchmark_regression_reports_status CHECK (status IN ('PASS','FAIL','INCONCLUSIVE','INVALID')), \n\tCONSTRAINT fk_speaking_benchmark_regression_reports_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE RESTRICT\n)\n\n")
    op.execute('CREATE INDEX ix_speaking_gate_report_owner ON speaking_benchmark_regression_reports (owner_id, gate_id, created_at, id)')
    op.execute("\nCREATE TABLE speaking_benchmark_adjudications (\n\towner_id UUID NOT NULL, \n\tsample_id UUID NOT NULL, \n\treview_revision INTEGER NOT NULL, \n\tsource_sha256 VARCHAR(64) NOT NULL, \n\tmanifest_fingerprint VARCHAR(64) NOT NULL, \n\trevision INTEGER NOT NULL, \n\tassessment_refs JSONB NOT NULL, \n\tfc NUMERIC, \n\tlr NUMERIC, \n\tgra NUMERIC, \n\tpr NUMERIC, \n\toverall NUMERIC, \n\trationale TEXT NOT NULL, \n\tpolicy_version VARCHAR(100) NOT NULL, \n\tprovenance VARCHAR(40) NOT NULL, \n\tadjudicator_id UUID NOT NULL, \n\tadjudicated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tCONSTRAINT pk_speaking_benchmark_adjudications PRIMARY KEY (id), \n\tCONSTRAINT fk_speaking_benchmark_adjudications_sample_id_speaking__7d7b FOREIGN KEY(sample_id, owner_id) REFERENCES speaking_benchmark_samples (id, owner_id) ON DELETE CASCADE, \n\tCONSTRAINT fk_speaking_benchmark_adjudications_sample_id_speaking__b706 FOREIGN KEY(sample_id, review_revision) REFERENCES speaking_benchmark_reviews (sample_id, revision) ON DELETE CASCADE, \n\tCONSTRAINT ck_speaking_benchmark_adjudications_review_revision CHECK (review_revision > 0), \n\tCONSTRAINT ck_speaking_benchmark_adjudications_fingerprints CHECK (source_sha256 ~ '^[a-f0-9]{64}$' AND manifest_fingerprint ~ '^[a-f0-9]{64}$'), \n\tCONSTRAINT ck_speaking_benchmark_adjudications_fc_half_band CHECK (fc IS NULL OR (fc BETWEEN 0 AND 9 AND fc * 2 = floor(fc * 2))), \n\tCONSTRAINT ck_speaking_benchmark_adjudications_lr_half_band CHECK (lr IS NULL OR (lr BETWEEN 0 AND 9 AND lr * 2 = floor(lr * 2))), \n\tCONSTRAINT ck_speaking_benchmark_adjudications_gra_half_band CHECK (gra IS NULL OR (gra BETWEEN 0 AND 9 AND gra * 2 = floor(gra * 2))), \n\tCONSTRAINT ck_speaking_benchmark_adjudications_pr_half_band CHECK (pr IS NULL OR (pr BETWEEN 0 AND 9 AND pr * 2 = floor(pr * 2))), \n\tCONSTRAINT ck_speaking_benchmark_adjudications_overall_half_band CHECK (overall IS NULL OR (overall BETWEEN 0 AND 9 AND overall * 2 = floor(overall * 2))), \n\tCONSTRAINT uq_speaking_benchmark_adjudications_sample_id_review_revision UNIQUE (sample_id, review_revision, revision), \n\tCONSTRAINT ck_speaking_benchmark_adjudications_decision CHECK (revision > 0 AND length(trim(rationale)) > 0 AND length(trim(policy_version)) > 0), \n\tCONSTRAINT ck_speaking_benchmark_adjudications_assessments CHECK (jsonb_typeof(assessment_refs) = 'array' AND jsonb_array_length(assessment_refs) > 0), \n\tCONSTRAINT fk_speaking_benchmark_adjudications_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE RESTRICT, \n\tCONSTRAINT fk_speaking_benchmark_adjudications_adjudicator_id_users FOREIGN KEY(adjudicator_id) REFERENCES users (id) ON DELETE RESTRICT\n)\n\n")
    op.execute('CREATE INDEX ix_speaking_benchmark_adjudication_sample ON speaking_benchmark_adjudications (sample_id, review_revision, revision)')
    op.execute("\nCREATE TABLE speaking_benchmark_question_jobs (\n\tsample_id UUID NOT NULL, \n\towner_id UUID NOT NULL, \n\tsubmission_key UUID NOT NULL, \n\treview_revision INTEGER NOT NULL, \n\tsource_sha256 VARCHAR(64) NOT NULL, \n\tdraft_fingerprint VARCHAR(64) NOT NULL, \n\tmodel_fingerprint VARCHAR(64) NOT NULL, \n\texaminer_speaker_id VARCHAR(100) NOT NULL, \n\tconfiguration JSONB NOT NULL, \n\tfingerprint VARCHAR(64) NOT NULL, \n\twindows JSONB NOT NULL, \n\texclusions JSONB NOT NULL, \n\tconsent JSONB, \n\tproposals JSONB NOT NULL, \n\tdecisions JSONB NOT NULL, \n\tstatus VARCHAR(20) NOT NULL, \n\terror_code VARCHAR(100), \n\tlease_token UUID, \n\tlease_expires_at TIMESTAMP WITH TIME ZONE, \n\tstarted_at TIMESTAMP WITH TIME ZONE, \n\tfinished_at TIMESTAMP WITH TIME ZONE, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tCONSTRAINT pk_speaking_benchmark_question_jobs PRIMARY KEY (id), \n\tCONSTRAINT fk_speaking_benchmark_question_jobs_sample_id_speaking__0aa4 FOREIGN KEY(sample_id, owner_id) REFERENCES speaking_benchmark_samples (id, owner_id) ON DELETE CASCADE, \n\tCONSTRAINT fk_speaking_benchmark_question_jobs_sample_id_speaking__1f85 FOREIGN KEY(sample_id, review_revision) REFERENCES speaking_benchmark_reviews (sample_id, revision) ON DELETE CASCADE, \n\tCONSTRAINT uq_speaking_benchmark_question_jobs_owner_id_submission_key UNIQUE (owner_id, submission_key), \n\tCONSTRAINT ck_speaking_benchmark_question_jobs_revision CHECK (review_revision > 0), \n\tCONSTRAINT ck_speaking_benchmark_question_jobs_status CHECK (status IN ('DRAFT','PENDING','RUNNING','INTERRUPTED','COMPLETED','PARTIAL','FAILED','CANCELLED')), \n\tCONSTRAINT ck_speaking_benchmark_question_jobs_lease CHECK (status != 'RUNNING' OR (lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)), \n\tCONSTRAINT fk_speaking_benchmark_question_jobs_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE RESTRICT\n)\n\n")
    op.execute('CREATE INDEX ix_speaking_questions_queue ON speaking_benchmark_question_jobs (status, created_at)')
    op.execute('CREATE INDEX ix_speaking_questions_sample ON speaking_benchmark_question_jobs (sample_id, created_at, id)')
    op.execute("\nCREATE TABLE speaking_benchmark_rater_assignments (\n\towner_id UUID NOT NULL, \n\tsample_id UUID NOT NULL, \n\treview_revision INTEGER NOT NULL, \n\tsource_sha256 VARCHAR(64) NOT NULL, \n\tmanifest_fingerprint VARCHAR(64) NOT NULL, \n\trater_id UUID NOT NULL, \n\tassigned_by UUID NOT NULL, \n\tpermitted_original_audio BOOLEAN NOT NULL, \n\trevision INTEGER NOT NULL, \n\trevoked_at TIMESTAMP WITH TIME ZONE, \n\trevoked_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tCONSTRAINT pk_speaking_benchmark_rater_assignments PRIMARY KEY (id), \n\tCONSTRAINT fk_speaking_benchmark_rater_assignments_sample_id_speak_3f59 FOREIGN KEY(sample_id, owner_id) REFERENCES speaking_benchmark_samples (id, owner_id) ON DELETE CASCADE, \n\tCONSTRAINT fk_speaking_benchmark_rater_assignments_sample_id_speak_bbd9 FOREIGN KEY(sample_id, review_revision) REFERENCES speaking_benchmark_reviews (sample_id, revision) ON DELETE CASCADE, \n\tCONSTRAINT ck_speaking_benchmark_rater_assignments_review_revision CHECK (review_revision > 0), \n\tCONSTRAINT ck_speaking_benchmark_rater_assignments_fingerprints CHECK (source_sha256 ~ '^[a-f0-9]{64}$' AND manifest_fingerprint ~ '^[a-f0-9]{64}$'), \n\tCONSTRAINT fk_speaking_benchmark_rater_assignments_rater_id_speaki_ea6d FOREIGN KEY(rater_id, owner_id) REFERENCES speaking_benchmark_raters (id, owner_id) ON DELETE CASCADE, \n\tCONSTRAINT uq_speaking_benchmark_rater_assignments_id_owner_id UNIQUE (id, owner_id), \n\tCONSTRAINT ck_speaking_benchmark_rater_assignments_revision CHECK (revision >= 1), \n\tCONSTRAINT fk_speaking_benchmark_rater_assignments_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE RESTRICT, \n\tCONSTRAINT fk_speaking_benchmark_rater_assignments_assigned_by_users FOREIGN KEY(assigned_by) REFERENCES users (id) ON DELETE RESTRICT, \n\tCONSTRAINT fk_speaking_benchmark_rater_assignments_revoked_by_users FOREIGN KEY(revoked_by) REFERENCES users (id) ON DELETE RESTRICT\n)\n\n")
    op.execute('CREATE INDEX ix_speaking_benchmark_assignment_rater ON speaking_benchmark_rater_assignments (rater_id, created_at, id)')
    op.execute('CREATE UNIQUE INDEX uq_speaking_benchmark_active_assignment ON speaking_benchmark_rater_assignments (sample_id, review_revision, rater_id) WHERE revoked_at IS NULL')
    op.execute("\nCREATE TABLE speaking_benchmark_human_assessments (\n\towner_id UUID NOT NULL, \n\tsample_id UUID NOT NULL, \n\treview_revision INTEGER NOT NULL, \n\tsource_sha256 VARCHAR(64) NOT NULL, \n\tmanifest_fingerprint VARCHAR(64) NOT NULL, \n\tassignment_id UUID NOT NULL, \n\trater_id UUID NOT NULL, \n\trevision INTEGER NOT NULL, \n\tstatus VARCHAR(16) NOT NULL, \n\tfc NUMERIC, \n\tlr NUMERIC, \n\tgra NUMERIC, \n\tpr NUMERIC, \n\toverall NUMERIC, \n\tcomments JSONB NOT NULL, \n\tprovenance VARCHAR(40) NOT NULL, \n\tsource_reference TEXT NOT NULL, \n\tindependently_performed BOOLEAN NOT NULL, \n\tauthored_by UUID NOT NULL, \n\tsubmitted_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tCONSTRAINT pk_speaking_benchmark_human_assessments PRIMARY KEY (id), \n\tCONSTRAINT fk_speaking_benchmark_human_assessments_sample_id_speak_8adb FOREIGN KEY(sample_id, owner_id) REFERENCES speaking_benchmark_samples (id, owner_id) ON DELETE CASCADE, \n\tCONSTRAINT fk_speaking_benchmark_human_assessments_sample_id_speak_e283 FOREIGN KEY(sample_id, review_revision) REFERENCES speaking_benchmark_reviews (sample_id, revision) ON DELETE CASCADE, \n\tCONSTRAINT ck_speaking_benchmark_human_assessments_review_revision CHECK (review_revision > 0), \n\tCONSTRAINT ck_speaking_benchmark_human_assessments_fingerprints CHECK (source_sha256 ~ '^[a-f0-9]{64}$' AND manifest_fingerprint ~ '^[a-f0-9]{64}$'), \n\tCONSTRAINT ck_speaking_benchmark_human_assessments_fc_half_band CHECK (fc IS NULL OR (fc BETWEEN 0 AND 9 AND fc * 2 = floor(fc * 2))), \n\tCONSTRAINT ck_speaking_benchmark_human_assessments_lr_half_band CHECK (lr IS NULL OR (lr BETWEEN 0 AND 9 AND lr * 2 = floor(lr * 2))), \n\tCONSTRAINT ck_speaking_benchmark_human_assessments_gra_half_band CHECK (gra IS NULL OR (gra BETWEEN 0 AND 9 AND gra * 2 = floor(gra * 2))), \n\tCONSTRAINT ck_speaking_benchmark_human_assessments_pr_half_band CHECK (pr IS NULL OR (pr BETWEEN 0 AND 9 AND pr * 2 = floor(pr * 2))), \n\tCONSTRAINT ck_speaking_benchmark_human_assessments_overall_half_band CHECK (overall IS NULL OR (overall BETWEEN 0 AND 9 AND overall * 2 = floor(overall * 2))), \n\tCONSTRAINT fk_speaking_benchmark_human_assessments_assignment_id_s_938e FOREIGN KEY(assignment_id, owner_id) REFERENCES speaking_benchmark_rater_assignments (id, owner_id) ON DELETE CASCADE, \n\tCONSTRAINT fk_speaking_benchmark_human_assessments_rater_id_speaki_091f FOREIGN KEY(rater_id, owner_id) REFERENCES speaking_benchmark_raters (id, owner_id) ON DELETE CASCADE, \n\tCONSTRAINT uq_speaking_benchmark_human_assessments_assignment_id_revision UNIQUE (assignment_id, revision), \n\tCONSTRAINT ck_speaking_benchmark_human_assessments_submission CHECK (revision > 0 AND status = 'SUBMITTED'), \n\tCONSTRAINT ck_speaking_benchmark_human_assessments_provenance CHECK (provenance IN ('internal_blind','external_verified_report','external_unverified')), \n\tCONSTRAINT ck_speaking_benchmark_human_assessments_verified_reference CHECK (provenance != 'external_verified_report' OR length(trim(source_reference)) > 0), \n\tCONSTRAINT fk_speaking_benchmark_human_assessments_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE RESTRICT, \n\tCONSTRAINT fk_speaking_benchmark_human_assessments_authored_by_users FOREIGN KEY(authored_by) REFERENCES users (id) ON DELETE RESTRICT\n)\n\n")
    op.execute('CREATE INDEX ix_speaking_benchmark_assessment_sample ON speaking_benchmark_human_assessments (sample_id, review_revision, rater_id, revision)')
    op.execute("\nCREATE TABLE speaking_benchmark_question_requests (\n\tjob_id UUID NOT NULL, \n\twindow_id VARCHAR(100) NOT NULL, \n\tidentity VARCHAR(64) NOT NULL, \n\tattempt INTEGER NOT NULL, \n\tstatus VARCHAR(40) NOT NULL, \n\tbilling_state VARCHAR(24) NOT NULL, \n\tresult JSONB, \n\tusage JSONB, \n\terror_code VARCHAR(100), \n\treused_from UUID, \n\treconciliation JSONB, \n\tfinished_at TIMESTAMP WITH TIME ZONE, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tCONSTRAINT pk_speaking_benchmark_question_requests PRIMARY KEY (id), \n\tCONSTRAINT uq_speaking_benchmark_question_requests_job_id_window_id UNIQUE (job_id, window_id, attempt), \n\tCONSTRAINT ck_speaking_benchmark_question_requests_attempt CHECK (attempt > 0), \n\tCONSTRAINT ck_speaking_benchmark_question_requests_status CHECK (status IN ('ATTEMPTED','COMPLETED','FAILED','INTERRUPTED_BILLING_UNKNOWN')), \n\tCONSTRAINT ck_speaking_benchmark_question_requests_result CHECK (status != 'COMPLETED' OR result IS NOT NULL), \n\tCONSTRAINT fk_speaking_benchmark_question_requests_job_id_speaking_48b9 FOREIGN KEY(job_id) REFERENCES speaking_benchmark_question_jobs (id) ON DELETE CASCADE, \n\tCONSTRAINT fk_speaking_benchmark_question_requests_reused_from_spe_ddba FOREIGN KEY(reused_from) REFERENCES speaking_benchmark_question_requests (id) ON DELETE SET NULL\n)\n\n")
    op.execute('CREATE INDEX ix_speaking_questions_cache ON speaking_benchmark_question_requests (identity, status)')
    _guards()

def downgrade():
    op.execute('DROP TABLE speaking_benchmark_question_requests CASCADE')
    op.execute('DROP TABLE speaking_benchmark_human_assessments CASCADE')
    op.execute('DROP TABLE speaking_benchmark_rater_assignments CASCADE')
    op.execute('DROP TABLE speaking_benchmark_question_jobs CASCADE')
    op.execute('DROP TABLE speaking_benchmark_adjudications CASCADE')
    op.execute('DROP TABLE speaking_benchmark_regression_reports CASCADE')
    op.execute('DROP TABLE speaking_benchmark_regression_gates CASCADE')
    op.execute('DROP TABLE speaking_benchmark_holdout_audits CASCADE')
    op.execute('DROP TABLE speaking_benchmark_raters CASCADE')
    op.execute('DROP TABLE speaking_benchmark_quality_snapshots CASCADE')
    op.execute('DROP TABLE speaking_benchmark_evaluation_suites CASCADE')
    op.execute("DROP FUNCTION speaking_quality_guard()")

def _guards():
    op.execute("""CREATE FUNCTION speaking_quality_guard() RETURNS trigger AS $$
    DECLARE ref jsonb;
    BEGIN
      IF TG_TABLE_NAME IN ('speaking_benchmark_quality_snapshots',
        'speaking_benchmark_evaluation_suites','speaking_benchmark_regression_gates',
        'speaking_benchmark_regression_reports','speaking_benchmark_holdout_audits',
        'speaking_benchmark_raters') THEN
        IF TG_OP = 'UPDATE' THEN RAISE EXCEPTION 'Frozen P4 artifact is append only'; END IF;
      ELSIF TG_TABLE_NAME IN ('speaking_benchmark_rater_assignments',
        'speaking_benchmark_human_assessments','speaking_benchmark_adjudications') THEN
        IF TG_OP = 'INSERT' AND NOT EXISTS (SELECT 1 FROM speaking_benchmark_samples s
          JOIN speaking_benchmark_reviews r ON r.sample_id=s.id
          WHERE s.id=NEW.sample_id AND s.owner_id=NEW.owner_id
          AND s.deletion_pending_at IS NULL AND s.source_sha256=NEW.source_sha256
          AND r.revision=NEW.review_revision AND r.approved_at IS NOT NULL
          AND r.fingerprint=NEW.manifest_fingerprint) THEN
          RAISE EXCEPTION 'Approved source and review binding required'; END IF;
        IF TG_TABLE_NAME = 'speaking_benchmark_rater_assignments' THEN
          IF TG_OP = 'UPDATE' AND (
            (to_jsonb(NEW)-'updated_at'-'revoked_at'-'revoked_by'-'revision') IS DISTINCT FROM
            (to_jsonb(OLD)-'updated_at'-'revoked_at'-'revoked_by'-'revision') OR
            OLD.revoked_at IS NOT NULL OR NEW.revoked_at IS NULL OR NEW.revoked_by IS NULL
            OR NEW.revision != OLD.revision + 1) THEN
            RAISE EXCEPTION 'Assignment binding frozen; revocation is terminal'; END IF;
        ELSE
          IF TG_OP = 'UPDATE' THEN RAISE EXCEPTION 'Human revisions are append only'; END IF;
          IF TG_TABLE_NAME = 'speaking_benchmark_human_assessments' THEN
            IF NOT EXISTS (SELECT 1 FROM speaking_benchmark_rater_assignments a
              JOIN speaking_benchmark_raters t ON t.id=a.rater_id
              WHERE a.id=NEW.assignment_id AND a.owner_id=NEW.owner_id
              AND a.sample_id=NEW.sample_id AND a.rater_id=NEW.rater_id
              AND a.review_revision=NEW.review_revision AND a.source_sha256=NEW.source_sha256
              AND a.manifest_fingerprint=NEW.manifest_fingerprint AND a.revoked_at IS NULL
              AND ((t.kind='INTERNAL' AND NEW.provenance='internal_blind'
                AND NEW.authored_by=t.user_id AND t.user_id != NEW.owner_id)
                OR (t.kind='EXTERNAL' AND NEW.provenance IN
                  ('external_verified_report','external_unverified') AND NEW.authored_by=NEW.owner_id)))
              THEN RAISE EXCEPTION 'Active rater and authenticated author required'; END IF;
          ELSE
            IF NEW.adjudicator_id != NEW.owner_id OR NEW.provenance != 'owner_human_adjudication'
              THEN RAISE EXCEPTION 'Owner human adjudication required'; END IF;
            FOR ref IN SELECT * FROM jsonb_array_elements(NEW.assessment_refs) LOOP
              IF NOT EXISTS (SELECT 1 FROM speaking_benchmark_human_assessments a
                WHERE a.id=(ref->>'id')::uuid AND a.revision=(ref->>'revision')::int
                AND a.rater_id=(ref->>'rater_id')::uuid AND a.owner_id=NEW.owner_id
                AND a.sample_id=NEW.sample_id AND a.review_revision=NEW.review_revision
                AND a.source_sha256=NEW.source_sha256 AND a.manifest_fingerprint=NEW.manifest_fingerprint
                AND a.independently_performed AND a.provenance IN ('internal_blind','external_verified_report'))
                THEN RAISE EXCEPTION 'Source-bound independent assessment required'; END IF;
            END LOOP;
          END IF;
        END IF;
      ELSIF TG_TABLE_NAME = 'speaking_benchmark_question_jobs' THEN
        IF TG_OP = 'INSERT' AND NOT EXISTS (SELECT 1 FROM speaking_benchmark_samples s
          JOIN speaking_benchmark_reviews r ON r.sample_id=s.id
          JOIN speaking_benchmark_jobs j ON j.id=r.job_id
          WHERE s.id=NEW.sample_id AND s.owner_id=NEW.owner_id AND s.deletion_pending_at IS NULL
          AND s.source_sha256=NEW.source_sha256 AND r.revision=NEW.review_revision
          AND j.source_sha256=NEW.source_sha256 AND r.draft->>'model_fingerprint'=NEW.model_fingerprint
          AND r.draft->>'source_sha256'=NEW.source_sha256)
          THEN RAISE EXCEPTION 'Question source and diarization binding required'; END IF;
        IF TG_OP = 'UPDATE' THEN
          IF ROW(NEW.sample_id,NEW.owner_id,NEW.submission_key,NEW.review_revision,
            NEW.source_sha256,NEW.draft_fingerprint,NEW.model_fingerprint,NEW.examiner_speaker_id,
            NEW.configuration,NEW.fingerprint,NEW.windows,NEW.exclusions) IS DISTINCT FROM
            ROW(OLD.sample_id,OLD.owner_id,OLD.submission_key,OLD.review_revision,
            OLD.source_sha256,OLD.draft_fingerprint,OLD.model_fingerprint,OLD.examiner_speaker_id,
            OLD.configuration,OLD.fingerprint,OLD.windows,OLD.exclusions)
            THEN RAISE EXCEPTION 'Question job inputs are frozen'; END IF;
          IF jsonb_array_length(NEW.decisions) < jsonb_array_length(OLD.decisions) OR
            EXISTS (SELECT 1 FROM jsonb_array_elements(OLD.decisions) WITH ORDINALITY d(v,n)
              WHERE NEW.decisions->(d.n::int-1) IS DISTINCT FROM d.v)
            THEN RAISE EXCEPTION 'Question decisions are append only'; END IF;
          IF OLD.status IN ('COMPLETED','PARTIAL','FAILED','CANCELLED') AND
            (to_jsonb(NEW)-'updated_at'-'decisions') IS DISTINCT FROM
            (to_jsonb(OLD)-'updated_at'-'decisions')
            THEN RAISE EXCEPTION 'Final question proposals are frozen'; END IF;
        END IF;
      ELSIF TG_TABLE_NAME = 'speaking_benchmark_question_requests' THEN
        IF TG_OP = 'UPDATE' THEN
          IF ROW(NEW.job_id,NEW.window_id,NEW.identity,NEW.attempt,NEW.reused_from)
            IS DISTINCT FROM ROW(OLD.job_id,OLD.window_id,OLD.identity,OLD.attempt,OLD.reused_from)
            THEN RAISE EXCEPTION 'Physical question identity frozen'; END IF;
          IF OLD.status IN ('COMPLETED','FAILED') AND
            (to_jsonb(NEW)-'updated_at') IS DISTINCT FROM (to_jsonb(OLD)-'updated_at')
            THEN RAISE EXCEPTION 'Final question result frozen'; END IF;
          IF OLD.reconciliation IS NOT NULL AND NEW.reconciliation IS DISTINCT FROM OLD.reconciliation
            AND NOT (NOT (OLD.reconciliation ? 'replacement_id') AND
              (NEW.reconciliation-'replacement_id')=OLD.reconciliation AND EXISTS (
                SELECT 1 FROM speaking_benchmark_question_requests r
                WHERE r.id=(NEW.reconciliation->>'replacement_id')::uuid
                AND r.job_id=OLD.job_id AND r.window_id=OLD.window_id AND r.identity=OLD.identity))
            THEN RAISE EXCEPTION 'Question reconciliation is write once'; END IF;
        END IF;
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql""")
    for table in (
        'quality_snapshots','evaluation_suites','regression_gates','regression_reports',
        'holdout_audits','raters','rater_assignments','human_assessments','adjudications',
        'question_jobs','question_requests',
    ):
        op.execute(f'CREATE TRIGGER speaking_quality_frozen BEFORE INSERT OR UPDATE ON speaking_benchmark_{table} FOR EACH ROW EXECUTE FUNCTION speaking_quality_guard()')
