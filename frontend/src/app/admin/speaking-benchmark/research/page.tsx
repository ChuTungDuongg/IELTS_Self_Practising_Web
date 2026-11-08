import { AdminGuard } from "@/features/auth/admin-guard";
import { ResearchList } from "@/features/speaking-benchmark/research/research-list";

export default function Page() { return <AdminGuard><ResearchList /></AdminGuard>; }
