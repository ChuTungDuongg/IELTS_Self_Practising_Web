import { AdminGuard } from "@/features/auth/admin-guard";
import { SuiteManager } from "@/features/speaking-benchmark/quality/suite-manager";

export default function SuitesPage() {
  return (
    <AdminGuard>
      <SuiteManager />
    </AdminGuard>
  );
}
