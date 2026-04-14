import { PageHeader } from '@/components/layout';

export default function DashboardPage() {
  return (
    <div>
      <PageHeader title="Dashboard" />
      <div className="p-8">
        <p className="text-muted font-bold uppercase tracking-widest text-sm">
          Loading dashboard...
        </p>
      </div>
    </div>
  );
}
