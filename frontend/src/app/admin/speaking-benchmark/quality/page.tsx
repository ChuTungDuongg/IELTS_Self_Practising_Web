import { AdminGuard } from "@/features/auth/admin-guard";
import { QualityDashboard } from "@/features/speaking-benchmark/quality/quality-dashboard";

export default function QualityPage() {
  return (
    <AdminGuard>
      <QualityDashboard />
    </AdminGuard>
  );
}
