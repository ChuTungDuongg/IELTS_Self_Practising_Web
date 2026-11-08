import { AdminGuard } from "@/features/auth/admin-guard";
import { GateManager } from "@/features/speaking-benchmark/quality/gate-manager";

export default function GatesPage() {
  return (
    <AdminGuard>
      <GateManager />
    </AdminGuard>
  );
}
