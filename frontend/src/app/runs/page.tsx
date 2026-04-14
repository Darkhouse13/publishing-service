'use client';

import { useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { PageHeader } from '@/components/layout';
import Button from '@/components/ui/Button';
import Select from '@/components/ui/Select';
import TabBar from '@/components/ui/TabBar';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHeaderCell,
} from '@/components/ui/Table';
import RunRow from '@/components/runs/RunRow';
import { useRuns } from '@/hooks/useRuns';
import { useBlogs } from '@/hooks/useBlogs';
import type { RunStatus } from '@/lib/types';
import { getMockBlogName } from '@/lib/mock-data';

/* ----------------------------------------------------------------
   /runs page — Generation Runs list with filters and polling
   - Filter bar: blog dropdown + status tabs (All/Pending/Running/Completed/Failed)
   - Table: Run code, Blog, Status badge, Progress bar, Duration, Last Updated
   - Polling: refresh every 5s when any run is active
   - Header has 'New Generation Run' button → /runs/new
   ---------------------------------------------------------------- */

const STATUS_TABS = [
  { key: 'all', label: 'All' },
  { key: 'pending', label: 'Pending' },
  { key: 'running', label: 'Running' },
  { key: 'completed', label: 'Completed' },
  { key: 'failed', label: 'Failed' },
];

// Active statuses that should trigger polling
const ACTIVE_STATUSES = new Set<string>(['pending', 'running', 'generating']);

export default function RunsPage() {
  const router = useRouter();
  const { runs, isLoading, hasActiveRuns } = useRuns();
  const { blogs } = useBlogs();

  // Filter state
  const [activeStatusTab, setActiveStatusTab] = useState('all');
  const [selectedBlogId, setSelectedBlogId] = useState('');

  // Build blog options for dropdown
  const blogOptions = useMemo(
    () => [
      { value: '', label: 'All Blogs' },
      ...blogs.map((blog) => ({ value: blog.id, label: blog.name })),
    ],
    [blogs],
  );

  // Build blog name lookup map
  const blogNameMap = useMemo(() => {
    const map: Record<string, string> = {};
    for (const blog of blogs) {
      map[blog.id] = blog.name;
    }
    return map;
  }, [blogs]);

  // Apply filters
  const filteredRuns = useMemo(() => {
    let result = runs;

    // Filter by status tab
    if (activeStatusTab !== 'all') {
      // 'running' tab should include 'generating' too
      if (activeStatusTab === 'running') {
        result = result.filter(
          (run) => run.status === 'running' || run.status === 'generating',
        );
      } else {
        result = result.filter((run) => run.status === activeStatusTab);
      }
    }

    // Filter by blog
    if (selectedBlogId) {
      result = result.filter((run) => run.blog_id === selectedBlogId);
    }

    return result;
  }, [runs, activeStatusTab, selectedBlogId]);

  return (
    <div>
      <PageHeader title="Runs">
        <Button variant="primary" onClick={() => router.push('/runs/new')}>
          + New Generation Run
        </Button>
      </PageHeader>

      <div className="p-8">
        {/* Filter Bar */}
        <div className="flex items-end gap-4 mb-6">
          {/* Blog Dropdown */}
          <div className="w-64">
            <Select
              label="Filter by Blog"
              options={blogOptions}
              value={selectedBlogId}
              onChange={(e) => setSelectedBlogId(e.target.value)}
            />
          </div>

          {/* Status Tabs */}
          <div className="flex-1 pb-[26px]">
            <TabBar
              tabs={STATUS_TABS}
              activeTab={activeStatusTab}
              onChange={setActiveStatusTab}
            />
          </div>
        </div>

        {/* Active Polling Indicator */}
        {hasActiveRuns && (
          <div className="mb-4 flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-muted">
            <span className="inline-block w-2 h-2 bg-accent animate-sharp-blink rounded-none" />
            Live — Refreshing every 5s
          </div>
        )}

        {/* Runs Table */}
        <div className="bg-white border-[3px] border-base shadow-solid-md overflow-hidden rounded-none">
          {isLoading ? (
            <div className="p-12 text-center">
              <div className="inline-block w-8 h-8 border-[3px] border-base border-t-transparent animate-spin rounded-none" />
              <p className="mt-4 text-muted font-bold uppercase tracking-widest text-sm">
                Loading runs...
              </p>
            </div>
          ) : filteredRuns.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHeaderCell>Run Code</TableHeaderCell>
                  <TableHeaderCell>Blog</TableHeaderCell>
                  <TableHeaderCell>Status</TableHeaderCell>
                  <TableHeaderCell>Progress</TableHeaderCell>
                  <TableHeaderCell>Duration</TableHeaderCell>
                  <TableHeaderCell>Last Updated</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredRuns.map((run) => (
                  <RunRow
                    key={run.id}
                    run={run}
                    blogName={blogNameMap[run.blog_id]}
                  />
                ))}
              </TableBody>
            </Table>
          ) : (
            <div className="p-12 text-center">
              <p className="text-muted font-black uppercase tracking-widest text-lg">
                No Runs Found
              </p>
              <p className="text-muted font-bold text-sm mt-2">
                {activeStatusTab !== 'all' || selectedBlogId
                  ? 'Try adjusting your filters to see more results.'
                  : 'Start your first generation run to see results here.'}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
