'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import useSWR from 'swr';
import { PageHeader } from '@/components/layout';
import TabBar from '@/components/ui/TabBar';
import Button from '@/components/ui/Button';
import { blogsApi, pipelineConfigApi, ApiClientError } from '@/lib/api';
import { mockBlogs, mockPipelineConfigs } from '@/lib/mock-data';
import type { Blog, PipelineConfig } from '@/lib/types';
import ConnectionTab from '@/components/connections/tabs/ConnectionTab';
import AIPersonalityTab from '@/components/connections/tabs/AIPersonalityTab';
import CategoriesTab from '@/components/connections/tabs/CategoriesTab';
import PinterestTab from '@/components/connections/tabs/PinterestTab';
import PipelineTab from '@/components/connections/tabs/PipelineTab';

const tabs = [
  { key: 'connection', label: 'Connection' },
  { key: 'ai-personality', label: 'AI Personality' },
  { key: 'categories', label: 'Categories' },
  { key: 'pinterest', label: 'Pinterest' },
  { key: 'pipeline', label: 'Pipeline' },
];

export default function BlogSettingsPage({ params }: { params: { id: string } }) {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState('connection');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  // Look up mock blog for fallback
  const mockBlog = mockBlogs.find((b) => b.id === params.id);

  // Fetch blog data
  const {
    data: blog,
    error: blogError,
    isLoading: blogLoading,
    mutate: mutateBlog,
  } = useSWR<Blog>(
    `/blogs/${params.id}`,
    () => blogsApi.get(params.id),
    {
      revalidateOnFocus: false,
      fallbackData: mockBlog,
    }
  );

  // Look up mock pipeline config for fallback
  const mockPipeline = mockPipelineConfigs[params.id];

  // Fetch pipeline config (only when pipeline tab is active)
  const {
    data: pipelineConfig,
    isLoading: pipelineLoading,
    mutate: mutatePipeline,
  } = useSWR<PipelineConfig>(
    activeTab === 'pipeline' ? `/blogs/${params.id}/pipeline-config` : null,
    () => pipelineConfigApi.get(params.id),
    {
      revalidateOnFocus: false,
      fallbackData: mockPipeline,
    }
  );

  // Tab change handler — must be before any conditional returns
  const handleTabChange = useCallback((tabKey: string) => {
    setActiveTab(tabKey);
  }, []);

  // Determine if we have a 404 — only if we have no data and got a 404 error
  const is404 =
    !blog &&
    blogError &&
    blogError instanceof ApiClientError &&
    blogError.status === 404;

  // Loading state — only show when loading and no data yet
  if (blogLoading && !blog) {
    return (
      <div>
        <PageHeader title="Blog Settings" />
        <div className="p-8">
          <div className="bg-white border-[3px] border-base shadow-solid-md p-8">
            <div className="space-y-4">
              <div className="h-8 bg-panel animate-pulse" />
              <div className="h-8 bg-panel animate-pulse w-3/4" />
              <div className="h-8 bg-panel animate-pulse w-1/2" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  // 404 state
  if (is404) {
    return (
      <div>
        <PageHeader title="Blog Settings" />
        <div className="p-8">
          <div className="bg-white border-[3px] border-base shadow-solid-md p-12 text-center">
            <p className="text-lg font-black uppercase tracking-widest text-error mb-4">
              Blog Not Found
            </p>
            <p className="text-sm font-bold text-muted mb-6">
              The blog you are looking for does not exist or has been deleted.
            </p>
            <Button variant="primary" onClick={() => router.push('/connections')}>
              Back to Connections
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // Other error state — only show when there's no data and a non-404 error
  if (blogError && !blog) {
    return (
      <div>
        <PageHeader title="Blog Settings" />
        <div className="p-8">
          <div className="bg-white border-[3px] border-error p-8">
            <p className="text-sm font-bold text-error uppercase tracking-widest">
              Failed to load blog. Please try again.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (!blog) return null;

  // Blog update handler
  const handleBlogUpdate = async (data: Partial<Blog>) => {
    const updated = await blogsApi.update(blog.id, data);
    await mutateBlog(updated, false);
  };

  // Pipeline config update handler
  const handlePipelineUpdate = async (data: Partial<PipelineConfig>) => {
    const updated = await pipelineConfigApi.update(blog.id, data);
    await mutatePipeline(updated, false);
  };

  // Delete handler
  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await blogsApi.delete(blog.id);
      router.push('/connections');
    } catch {
      setIsDeleting(false);
      setShowDeleteConfirm(false);
    }
  };

  return (
    <div>
      <PageHeader title={blog.name}>
        <Button
          variant="danger"
          onClick={() => setShowDeleteConfirm(true)}
        >
          Delete Blog
        </Button>
      </PageHeader>

      <div className="p-8">
        {/* TabBar */}
        <div className="mb-6">
          <TabBar
            tabs={tabs}
            activeTab={activeTab}
            onChange={handleTabChange}
          />
        </div>

        {/* Tab Content */}
        <div className="bg-white border-[3px] border-base shadow-solid-md">
          <div className="p-8">
            {activeTab === 'connection' && (
              <ConnectionTab blog={blog} onSave={handleBlogUpdate} />
            )}
            {activeTab === 'ai-personality' && (
              <AIPersonalityTab blog={blog} onSave={handleBlogUpdate} />
            )}
            {activeTab === 'categories' && (
              <CategoriesTab blog={blog} onSave={handleBlogUpdate} />
            )}
            {activeTab === 'pinterest' && (
              <PinterestTab blog={blog} onSave={handleBlogUpdate} />
            )}
            {activeTab === 'pipeline' && (
              <PipelineTab
                pipelineConfig={pipelineConfig ?? null}
                isLoading={pipelineLoading}
                onSave={handlePipelineUpdate}
              />
            )}
          </div>
        </div>
      </div>

      {/* Delete Confirmation Dialog */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white border-[3px] border-base shadow-solid-lg max-w-md w-full mx-4">
            <div className="p-8">
              <h3 className="text-lg font-black uppercase tracking-widest mb-4">
                Delete Blog
              </h3>
              <p className="font-bold text-sm mb-6">
                Are you sure you want to delete <strong>{blog.name}</strong>?
                This action cannot be undone. All associated data will be
                permanently removed.
              </p>
              <div className="flex items-center gap-4">
                <Button
                  variant="danger"
                  onClick={handleDelete}
                  disabled={isDeleting}
                >
                  {isDeleting ? 'Deleting...' : 'Yes, Delete'}
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => setShowDeleteConfirm(false)}
                  disabled={isDeleting}
                >
                  Cancel
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
